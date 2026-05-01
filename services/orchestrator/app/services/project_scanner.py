from __future__ import annotations

import json
from pathlib import Path

IGNORED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "dist",
    "build",
    ".next",
    "__pycache__",
    "target",
    "vendor",
}

DOC_NAMES = {
    "README",
    "README.md",
    "README.rst",
    "CONTRIBUTING.md",
    "docs",
}

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".sh": "shell",
}


def scan_project(root_path: Path) -> dict[str, list[str]]:
    root = root_path.resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Workspace root not found: {root}")

    languages: set[str] = set()
    frameworks: set[str] = set()
    package_managers: set[str] = set()
    test_commands: set[str] = set()
    entrypoints: set[str] = set()
    docs: set[str] = set()
    important_files: set[str] = set()

    candidates: list[Path] = []
    for path in root.rglob("*"):
        if path.is_dir() and path.name in IGNORED_DIRS:
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in relative.parts):
            continue
        if not path.is_file():
            continue
        candidates.append(path)

    for file_path in candidates:
        rel = file_path.relative_to(root).as_posix()
        suffix = file_path.suffix.lower()
        if suffix in LANGUAGE_BY_SUFFIX:
            languages.add(LANGUAGE_BY_SUFFIX[suffix])

        name = file_path.name
        lowered = name.lower()

        if name in DOC_NAMES or lowered.startswith("readme") or rel.startswith("docs/"):
            docs.add(rel)

        if lowered in {
            "main.py",
            "manage.py",
            "app.py",
            "server.py",
            "index.js",
            "index.ts",
            "main.ts",
        }:
            entrypoints.add(rel)

        if lowered in {
            "requirements.txt",
            "pyproject.toml",
            "package.json",
            "cargo.toml",
            "go.mod",
            "pom.xml",
        }:
            important_files.add(rel)

        if lowered == "package.json":
            package_managers.add("npm")
            important_files.add(rel)
            _detect_node_ecosystem(file_path, frameworks, package_managers, test_commands)

        if lowered == "package-lock.json":
            package_managers.add("npm")
            important_files.add(rel)
        if lowered == "yarn.lock":
            package_managers.add("yarn")
            important_files.add(rel)
        if lowered == "pnpm-lock.yaml":
            package_managers.add("pnpm")
            important_files.add(rel)
            frameworks.add("pnpm-workspace")
        if lowered == "pnpm-workspace.yaml":
            package_managers.add("pnpm")
            frameworks.add("pnpm-workspace")
            important_files.add(rel)
        if lowered == "requirements.txt":
            languages.add("python")
            package_managers.add("pip")
            _detect_python_requirements(file_path, frameworks)
            test_commands.add("pytest")
        if lowered == "pyproject.toml":
            languages.add("python")
            package_managers.add("uv")
            _detect_pyproject(file_path, frameworks, test_commands)
        if lowered == "poetry.lock":
            package_managers.add("poetry")
        if lowered in {"manage.py"}:
            frameworks.add("django")
        if lowered == "cargo.toml":
            package_managers.add("cargo")
            frameworks.add("rust")
            test_commands.add("cargo test")
        if lowered == "go.mod":
            package_managers.add("go modules")
            test_commands.add("go test ./...")
        if lowered in {"pom.xml", "build.gradle", "build.gradle.kts"}:
            package_managers.add("gradle" if "gradle" in lowered else "maven")
            frameworks.add("jvm")
        if lowered == "turbo.json":
            frameworks.add("turborepo")
            important_files.add(rel)
        if lowered == "nx.json":
            frameworks.add("nx")
            important_files.add(rel)

        if rel in {"Dockerfile", "docker-compose.yml", "docker-compose.yaml"}:
            important_files.add(rel)

    if "python" in languages and not test_commands:
        test_commands.add("pytest")
    if "javascript" in languages or "typescript" in languages:
        test_commands.add("npm test")

    runbook_commands = _build_runbook_commands(
        languages=languages,
        package_managers=package_managers,
        test_commands=test_commands,
    )

    return {
        "languages": sorted(languages),
        "frameworks": sorted(frameworks),
        "package_managers": sorted(package_managers),
        "test_commands": sorted(test_commands),
        "entrypoints": sorted(entrypoints),
        "docs": sorted(docs)[:100],
        "important_files": sorted(important_files)[:200],
        "runbook_commands": runbook_commands,
    }


def _detect_node_ecosystem(
    package_json_path: Path,
    frameworks: set[str],
    package_managers: set[str],
    test_commands: set[str],
) -> None:
    try:
        payload = json.loads(package_json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return

    dependencies = {
        **(payload.get("dependencies") or {}),
        **(payload.get("devDependencies") or {}),
    }
    scripts = payload.get("scripts") or {}

    if "next" in dependencies:
        frameworks.add("nextjs")
    if "react" in dependencies:
        frameworks.add("react")
    if "vite" in dependencies:
        frameworks.add("vite")
    if "vue" in dependencies:
        frameworks.add("vue")
    if "@nestjs/core" in dependencies:
        frameworks.add("nestjs")
    if "express" in dependencies:
        frameworks.add("express")
    if "turbo" in dependencies:
        frameworks.add("turborepo")
    if "nx" in dependencies:
        frameworks.add("nx")

    if "test" in scripts:
        test_commands.add("npm test")


def _build_runbook_commands(
    *,
    languages: set[str],
    package_managers: set[str],
    test_commands: set[str],
) -> list[str]:
    commands: list[str] = []
    if "uv" in package_managers:
        commands.extend(["uv sync", "uv run pytest -q"])
    elif "pip" in package_managers:
        commands.extend(["python -m pip install -r requirements.txt", "pytest -q"])
    if "npm" in package_managers:
        commands.extend(["npm install", "npm test"])
    if "pnpm" in package_managers:
        commands.extend(["pnpm install", "pnpm test"])
    if "yarn" in package_managers:
        commands.extend(["yarn install", "yarn test"])
    if "cargo" in package_managers:
        commands.extend(["cargo build", "cargo test"])
    if "go modules" in package_managers:
        commands.extend(["go mod tidy", "go test ./..."])
    if not commands:
        commands.extend(sorted(test_commands))
    if not commands and "python" in languages:
        commands.append("pytest -q")
    return commands[:20]


def _detect_python_requirements(requirements_path: Path, frameworks: set[str]) -> None:
    try:
        content = requirements_path.read_text(encoding="utf-8").lower()
    except OSError:
        return

    if "fastapi" in content:
        frameworks.add("fastapi")
    if "django" in content:
        frameworks.add("django")
    if "flask" in content:
        frameworks.add("flask")
    if "uvicorn" in content:
        frameworks.add("asgi")


def _detect_pyproject(pyproject_path: Path, frameworks: set[str], test_commands: set[str]) -> None:
    try:
        content = pyproject_path.read_text(encoding="utf-8").lower()
    except OSError:
        return

    if "fastapi" in content:
        frameworks.add("fastapi")
    if "django" in content:
        frameworks.add("django")
    if "flask" in content:
        frameworks.add("flask")
    if "uvicorn" in content:
        frameworks.add("asgi")
    if "pytest" in content:
        test_commands.add("pytest")
