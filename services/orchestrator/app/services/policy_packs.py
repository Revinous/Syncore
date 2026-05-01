from __future__ import annotations

from typing import Any

POLICY_PACKS: dict[str, dict[str, Any]] = {
    "python-fastapi": {
        "profile": "balanced",
        "runner": "python-fastapi",
        "required_binaries": ("python",),
        "allow_commands": (
            "uv sync",
            "uv run pytest",
            "pytest",
            "python -m pytest",
            "python -m ruff",
            "python -m pip install",
        ),
        "allowed_command_patterns": (r"^uv run pytest( .*)?$", r"^pytest( .*)?$"),
        "verification_required_commands": ("pytest",),
        "allowed_actions": (
            "read_file",
            "search_code",
            "write_file",
            "patch_file",
            "run_command",
            "run_test",
            "run_lint",
            "complete_work",
            "next_action",
            "finish",
        ),
        "approval_required_paths": ("alembic/", "migrations/", "infra/"),
        "network_policy": "package_registries_only",
    },
    "python-django": {
        "profile": "balanced",
        "runner": "python-django",
        "required_binaries": ("python",),
        "allow_commands": (
            "python -m pip install",
            "python manage.py test",
            "pytest",
            "python -m pytest",
            "python manage.py check",
        ),
        "allowed_command_patterns": (
            r"^python manage\.py (test|check)( .*)?$",
            r"^pytest( .*)?$",
        ),
        "verification_required_commands": ("python manage.py test",),
        "allowed_actions": (
            "read_file",
            "search_code",
            "write_file",
            "patch_file",
            "run_command",
            "run_test",
            "run_lint",
            "complete_work",
            "next_action",
            "finish",
        ),
        "approval_required_paths": ("migrations/", "settings/", "infra/"),
        "network_policy": "package_registries_only",
    },
    "python-flask": {
        "profile": "balanced",
        "runner": "python-flask",
        "required_binaries": ("python",),
        "allow_commands": (
            "python -m pip install",
            "pytest",
            "python -m pytest",
            "python -m ruff",
        ),
        "allowed_command_patterns": (r"^pytest( .*)?$", r"^python -m pytest( .*)?$"),
        "verification_required_commands": ("pytest",),
        "allowed_actions": (
            "read_file",
            "search_code",
            "write_file",
            "patch_file",
            "run_command",
            "run_test",
            "run_lint",
            "complete_work",
            "next_action",
            "finish",
        ),
        "approval_required_paths": ("migrations/", "infra/"),
        "network_policy": "package_registries_only",
    },
    "node-next": {
        "profile": "balanced",
        "runner": "node-next",
        "required_binaries": ("node", "npm"),
        "allow_commands": (
            "npm install",
            "npm test",
            "npm run test",
            "npm run lint",
            "npm run build",
        ),
        "allowed_command_patterns": (
            r"^npm (run )?(test|lint|build)( .*)?$",
            r'^node -e "console\.log\(.*\)"$',
        ),
        "verification_required_commands": ("npm test", "npm run build"),
        "allowed_actions": (
            "read_file",
            "search_code",
            "write_file",
            "patch_file",
            "run_command",
            "run_test",
            "run_build",
            "run_lint",
            "complete_work",
            "next_action",
            "finish",
        ),
        "approval_required_paths": ("pages/api/", "src/app/api/", "infra/"),
        "network_policy": "package_registries_only",
    },
    "node-express": {
        "profile": "balanced",
        "runner": "node-express",
        "required_binaries": ("node", "npm"),
        "allow_commands": ("npm test", "npm run test", "npm run lint"),
        "allowed_command_patterns": (
            r"^npm (run )?(test|lint)( .*)?$",
            r'^node -e "console\.log\(.*\)"$',
        ),
        "verification_required_commands": ("npm test",),
        "allowed_actions": (
            "read_file",
            "search_code",
            "write_file",
            "patch_file",
            "run_command",
            "run_test",
            "run_lint",
            "complete_work",
            "next_action",
            "finish",
        ),
        "approval_required_paths": ("infra/", "migrations/"),
        "network_policy": "package_registries_only",
    },
    "node-nest": {
        "profile": "balanced",
        "runner": "node-nest",
        "required_binaries": ("node", "npm"),
        "allow_commands": ("npm test", "npm run test", "npm run build", "npm run lint"),
        "allowed_command_patterns": (
            r"^npm (run )?(test|build|lint)( .*)?$",
            r'^node -e "console\.log\(.*\)"$',
        ),
        "verification_required_commands": ("npm test", "npm run build"),
        "allowed_actions": (
            "read_file",
            "search_code",
            "write_file",
            "patch_file",
            "run_command",
            "run_test",
            "run_build",
            "run_lint",
            "complete_work",
            "next_action",
            "finish",
        ),
        "approval_required_paths": ("infra/", "migrations/"),
        "network_policy": "package_registries_only",
    },
    "vite-react": {
        "profile": "balanced",
        "runner": "vite-react",
        "required_binaries": ("node", "npm"),
        "allow_commands": ("npm test", "npm run test", "npm run build", "npm run lint"),
        "allowed_command_patterns": (
            r"^npm (run )?(test|build|lint)( .*)?$",
            r'^node -e "console\.log\(.*\)"$',
        ),
        "verification_required_commands": ("npm run build",),
        "allowed_actions": (
            "read_file",
            "search_code",
            "write_file",
            "patch_file",
            "run_command",
            "run_test",
            "run_build",
            "run_lint",
            "complete_work",
            "next_action",
            "finish",
        ),
        "approval_required_paths": ("infra/",),
        "network_policy": "package_registries_only",
    },
    "monorepo-pnpm": {
        "profile": "full-dev",
        "runner": "monorepo-pnpm",
        "required_binaries": ("node", "pnpm"),
        "allow_commands": ("pnpm install", "pnpm test", "pnpm lint", "pnpm build"),
        "allowed_command_patterns": (
            r"^pnpm (install|test|lint|build)( .*)?$",
            r'^node -e "console\.log\(.*\)"$',
        ),
        "verification_required_commands": ("pnpm test",),
        "allowed_actions": (
            "read_file",
            "search_code",
            "write_file",
            "patch_file",
            "move_file",
            "run_command",
            "run_test",
            "run_build",
            "run_lint",
            "complete_work",
            "next_action",
            "finish",
        ),
        "approval_required_paths": ("infra/", "apps/", "packages/"),
        "network_policy": "package_registries_only",
    },
    "go-service": {
        "profile": "full-dev",
        "runner": "go-service",
        "required_binaries": ("go",),
        "allow_commands": ("go mod tidy", "go test", "go test ./...", "go build", "go vet"),
        "allowed_command_patterns": (r"^go (test|build|vet)( .*)?$",),
        "verification_required_commands": ("go test",),
        "allowed_actions": (
            "read_file",
            "search_code",
            "write_file",
            "patch_file",
            "run_command",
            "run_test",
            "run_build",
            "complete_work",
            "next_action",
            "finish",
        ),
        "approval_required_paths": ("migrations/", "infra/"),
        "network_policy": "offline",
    },
    "rust-cli": {
        "profile": "full-dev",
        "runner": "rust-cli",
        "required_binaries": ("cargo",),
        "allow_commands": ("cargo fetch", "cargo build", "cargo test", "cargo fmt", "cargo clippy"),
        "allowed_command_patterns": (r"^cargo (build|test|fmt|clippy)( .*)?$",),
        "verification_required_commands": ("cargo test",),
        "allowed_actions": (
            "read_file",
            "search_code",
            "write_file",
            "patch_file",
            "run_command",
            "run_test",
            "run_build",
            "run_format",
            "complete_work",
            "next_action",
            "finish",
        ),
        "approval_required_paths": (".github/", "infra/"),
        "network_policy": "offline",
    },
    "java-gradle": {
        "profile": "full-dev",
        "runner": "java-gradle",
        "required_binaries": ("java", "gradle"),
        "allow_commands": (
            "gradle dependencies",
            "./gradlew test",
            "gradle test",
            "./gradlew build",
            "gradle build",
            "java -version",
        ),
        "allowed_command_patterns": (r"^(\./gradlew|gradle) (test|build)( .*)?$",),
        "verification_required_commands": ("test",),
        "allowed_actions": (
            "read_file",
            "search_code",
            "write_file",
            "patch_file",
            "run_command",
            "run_test",
            "run_build",
            "complete_work",
            "next_action",
            "finish",
        ),
        "approval_required_paths": ("infra/", "src/main/resources/"),
        "network_policy": "package_registries_only",
    },
}


def infer_policy_pack(scan: dict[str, Any]) -> str | None:
    frameworks = set(scan.get("frameworks") or [])
    package_managers = set(scan.get("package_managers") or [])
    languages = set(scan.get("languages") or [])

    if "nextjs" in frameworks:
        return "node-next"
    if "nestjs" in frameworks:
        return "node-nest"
    if "express" in frameworks:
        return "node-express"
    if "vite" in frameworks and "react" in frameworks:
        return "vite-react"
    if "pnpm-workspace" in frameworks or ("pnpm" in package_managers and "nx" in frameworks):
        return "monorepo-pnpm"
    if "django" in frameworks:
        return "python-django"
    if "flask" in frameworks:
        return "python-flask"
    if "fastapi" in frameworks:
        return "python-fastapi"
    if "python" in languages and ("pip" in package_managers or "uv" in package_managers):
        return "python-fastapi"
    if "jvm" in frameworks or "java" in languages or "kotlin" in languages:
        return "java-gradle"
    if "go" in languages:
        return "go-service"
    if "rust" in languages:
        return "rust-cli"
    return None


def get_policy_pack(name: str | None) -> dict[str, Any]:
    if not name:
        return {}
    return dict(POLICY_PACKS.get(name, {}))
