#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ROUTE_GLOBS = [ROOT / "services/orchestrator/app/api/routes"]
BANNED_ROUTE_PATTERNS = (
    "read_text(",
    "read_bytes(",
    "json.loads(",
    "json.load(",
)
ROUTE_PATTERN_ALLOWLIST = {
    "health.py": ("Path(",),
}

MAX_LINES_NEW_SERVICE = 400
MAX_LINES_ROUTE = 250
MAX_LINES_CLI_ENTRY = 250
MAX_LINES_WEB_PAGE = 250

RATCHET_BASELINES = {
    "services/orchestrator/app/services/autonomy_service.py": 2696,
    "services/orchestrator/app/services/run_execution_service.py": 2164,
    "apps/cli/syncore_cli/tui.py": 1282,
}

ROUTE_LINE_ALLOWLIST = {}

WEB_PAGE_ALLOWLIST = {
    "apps/web/pages/tasks/index.tsx": 279,
}


@dataclass
class Violation:
    path: str
    message: str


def line_count(path: Path) -> int:
    return sum(1 for _ in path.read_text(encoding="utf-8").splitlines())


def check_route_patterns() -> list[Violation]:
    violations: list[Violation] = []
    for route_dir in ROUTE_GLOBS:
        for path in sorted(route_dir.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            allowed = ROUTE_PATTERN_ALLOWLIST.get(path.name, ())
            for pattern in BANNED_ROUTE_PATTERNS:
                if pattern in text and pattern not in allowed:
                    violations.append(
                        Violation(
                            str(path.relative_to(ROOT)),
                            f"route contains disallowed adapter-local file/report loading pattern: {pattern}",
                        )
                    )
            if path.name != "__init__.py":
                rel = str(path.relative_to(ROOT))
                lines = line_count(path)
                allow = ROUTE_LINE_ALLOWLIST.get(rel)
                if allow is not None:
                    if lines > allow:
                        violations.append(
                            Violation(rel, f"route allowlist baseline exceeded: {lines} > {allow}")
                        )
                elif lines > MAX_LINES_ROUTE:
                    violations.append(
                        Violation(
                            rel,
                            f"route exceeds {MAX_LINES_ROUTE} lines ({lines})",
                        )
                    )
    return violations


def check_ratchet() -> list[Violation]:
    violations: list[Violation] = []
    for relative_path, baseline in RATCHET_BASELINES.items():
        path = ROOT / relative_path
        if not path.exists():
            continue
        lines = line_count(path)
        if lines > baseline:
            violations.append(
                Violation(relative_path, f"ratchet baseline exceeded: {lines} > {baseline}")
            )
    return violations


def check_new_service_sizes() -> list[Violation]:
    violations: list[Violation] = []
    services_dir = ROOT / "services/orchestrator/app/services"
    for path in sorted(services_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        rel = str(path.relative_to(ROOT))
        if rel in RATCHET_BASELINES:
            continue
        lines = line_count(path)
        if lines > MAX_LINES_NEW_SERVICE:
            violations.append(
                Violation(rel, f"service exceeds {MAX_LINES_NEW_SERVICE} lines ({lines})")
            )
    return violations


def check_cli_entry() -> list[Violation]:
    path = ROOT / "apps/cli/syncore_cli/main.py"
    lines = line_count(path)
    if lines > MAX_LINES_CLI_ENTRY:
        return [Violation(str(path.relative_to(ROOT)), f"CLI entry exceeds {MAX_LINES_CLI_ENTRY} lines ({lines})")]
    return []


def check_web_pages() -> list[Violation]:
    violations: list[Violation] = []
    pages_root = ROOT / "apps/web/pages"
    for path in sorted(pages_root.rglob("*.tsx")):
        rel = str(path.relative_to(ROOT))
        lines = line_count(path)
        allow = WEB_PAGE_ALLOWLIST.get(rel)
        if allow is not None:
            if lines > allow:
                violations.append(Violation(rel, f"web page allowlist baseline exceeded: {lines} > {allow}"))
            continue
        if lines > MAX_LINES_WEB_PAGE:
            violations.append(Violation(rel, f"web page exceeds {MAX_LINES_WEB_PAGE} lines ({lines})"))
    return violations


def main() -> int:
    violations = (
        check_route_patterns()
        + check_ratchet()
        + check_new_service_sizes()
        + check_cli_entry()
        + check_web_pages()
    )
    if violations:
        print("Structural guardrail violations detected:")
        for violation in violations:
            print(f"- {violation.path}: {violation.message}")
        return 1
    print("Structural guardrails passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
