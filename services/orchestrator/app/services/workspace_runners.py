from __future__ import annotations

from typing import Any

RUNNERS: dict[str, dict[str, Any]] = {
    "python-fastapi": {
        "required_binaries": ["python"],
        "expected_files": ["pyproject.toml", "requirements.txt"],
        "commands": {
            "setup": ["uv sync", "python -m pip install -r requirements.txt"],
            "test": ["uv run pytest -q", "pytest -q"],
            "lint": ["python -m ruff check ."],
            "build": [],
            "format": ["python -m ruff format ."],
            "probe": ['python -c "print(\'python-ready\')"'],
        },
    },
    "python-django": {
        "required_binaries": ["python"],
        "expected_files": ["manage.py", "pyproject.toml", "requirements.txt"],
        "commands": {
            "setup": ["python -m pip install -r requirements.txt"],
            "test": ["python manage.py test", "pytest -q"],
            "lint": ["python -m ruff check ."],
            "build": [],
            "format": ["python -m ruff format ."],
            "probe": ["python manage.py check"],
        },
    },
    "python-flask": {
        "required_binaries": ["python"],
        "expected_files": ["app.py", "pyproject.toml", "requirements.txt"],
        "commands": {
            "setup": ["python -m pip install -r requirements.txt"],
            "test": ["pytest -q"],
            "lint": ["python -m ruff check ."],
            "build": [],
            "format": ["python -m ruff format ."],
            "probe": ['python -c "print(\'flask-ready\')"'],
        },
    },
    "node-next": {
        "required_binaries": ["node", "npm"],
        "expected_files": ["package.json"],
        "commands": {
            "setup": ["npm install"],
            "test": ["npm test", "npm run test"],
            "lint": ["npm run lint"],
            "build": ["npm run build"],
            "format": [],
            "probe": ['node -e "console.log(\'node-ready\')"'],
        },
    },
    "node-express": {
        "required_binaries": ["node", "npm"],
        "expected_files": ["package.json"],
        "commands": {
            "setup": ["npm install"],
            "test": ["npm test", "npm run test"],
            "lint": ["npm run lint"],
            "build": [],
            "format": [],
            "probe": ['node -e "console.log(\'node-ready\')"'],
        },
    },
    "node-nest": {
        "required_binaries": ["node", "npm"],
        "expected_files": ["package.json"],
        "commands": {
            "setup": ["npm install"],
            "test": ["npm test", "npm run test"],
            "lint": ["npm run lint"],
            "build": ["npm run build"],
            "format": [],
            "probe": ['node -e "console.log(\'node-ready\')"'],
        },
    },
    "vite-react": {
        "required_binaries": ["node", "npm"],
        "expected_files": ["package.json", "vite.config.ts", "vite.config.js"],
        "commands": {
            "setup": ["npm install"],
            "test": ["npm test", "npm run test"],
            "lint": ["npm run lint"],
            "build": ["npm run build"],
            "format": [],
            "probe": ['node -e "console.log(\'node-ready\')"'],
        },
    },
    "monorepo-pnpm": {
        "required_binaries": ["node", "pnpm"],
        "expected_files": ["pnpm-workspace.yaml", "package.json"],
        "commands": {
            "setup": ["pnpm install"],
            "test": ["pnpm test"],
            "lint": ["pnpm lint"],
            "build": ["pnpm build"],
            "format": [],
            "probe": ['node -e "console.log(\'pnpm-ready\')"'],
        },
    },
    "go-service": {
        "required_binaries": ["go"],
        "expected_files": ["go.mod"],
        "commands": {
            "setup": ["go mod tidy"],
            "test": ["go test ./..."],
            "lint": ["go vet ./..."],
            "build": ["go build ./..."],
            "format": ["gofmt -w ."],
            "probe": ["go version"],
        },
    },
    "rust-cli": {
        "required_binaries": ["cargo"],
        "expected_files": ["Cargo.toml"],
        "commands": {
            "setup": ["cargo fetch"],
            "test": ["cargo test"],
            "lint": ["cargo clippy --all-targets --all-features"],
            "build": ["cargo build"],
            "format": ["cargo fmt --all"],
            "probe": ["cargo --version"],
        },
    },
    "java-gradle": {
        "required_binaries": ["java", "gradle"],
        "expected_files": ["build.gradle", "build.gradle.kts", "pom.xml"],
        "commands": {
            "setup": ["gradle dependencies"],
            "test": ["./gradlew test", "gradle test"],
            "lint": [],
            "build": ["./gradlew build", "gradle build"],
            "format": [],
            "probe": ["java -version"],
        },
    },
}


def select_workspace_runner(
    *,
    policy_pack: str | None,
    scan: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    requested = str(contract.get("runner") or "").strip()
    if requested and requested in RUNNERS:
        base = dict(RUNNERS[requested])
        base["name"] = requested
        return _apply_contract_overrides(base, contract)

    if policy_pack and policy_pack in RUNNERS:
        base = dict(RUNNERS[policy_pack])
        base["name"] = policy_pack
        return _apply_contract_overrides(base, contract)

    inferred = _infer_runner_name(scan)
    if inferred:
        base = dict(RUNNERS[inferred])
        base["name"] = inferred
        return _apply_contract_overrides(base, contract)

    return _apply_contract_overrides(
        {"name": "generic", "required_binaries": [], "expected_files": [], "commands": {}},
        contract,
    )


def _infer_runner_name(scan: dict[str, Any]) -> str | None:
    frameworks = set(scan.get("frameworks") or [])
    languages = set(scan.get("languages") or [])
    package_managers = set(scan.get("package_managers") or [])
    if "nextjs" in frameworks:
        return "node-next"
    if "nestjs" in frameworks:
        return "node-nest"
    if "express" in frameworks:
        return "node-express"
    if "vite" in frameworks and "react" in frameworks:
        return "vite-react"
    if "pnpm-workspace" in frameworks or "nx" in frameworks or "turborepo" in frameworks:
        return "monorepo-pnpm"
    if "django" in frameworks:
        return "python-django"
    if "flask" in frameworks:
        return "python-flask"
    if "fastapi" in frameworks or (
        "python" in languages and ("pip" in package_managers or "uv" in package_managers)
    ):
        return "python-fastapi"
    if "jvm" in frameworks or "java" in languages or "kotlin" in languages:
        return "java-gradle"
    if "go" in languages:
        return "go-service"
    if "rust" in languages:
        return "rust-cli"
    return None


def _apply_contract_overrides(base: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    environment = dict(contract.get("environment") or {})
    commands = dict(contract.get("commands") or {})
    merged_commands = dict(base.get("commands") or {})
    for key in ("setup", "build", "test", "lint", "format", "run", "migrations", "probe"):
        values = commands.get(key)
        if isinstance(values, list) and values:
            merged_commands[key] = [str(item).strip() for item in values if str(item).strip()]
    return {
        **base,
        "required_binaries": _merged_list(
            base.get("required_binaries"), environment.get("required_binaries")
        ),
        "expected_files": _merged_list(
            base.get("expected_files"),
            environment.get("required_files"),
        ),
        "package_manager": environment.get("package_manager") or base.get("package_manager"),
        "commands": merged_commands,
        "supported_os": environment.get("os") or [],
    }


def _merged_list(*values: Any) -> list[str]:
    seen: list[str] = []
    for value in values:
        if isinstance(value, list):
            for item in value:
                text = str(item).strip()
                if text and text not in seen:
                    seen.append(text)
        elif isinstance(value, tuple):
            for item in value:
                text = str(item).strip()
                if text and text not in seen:
                    seen.append(text)
    return seen
