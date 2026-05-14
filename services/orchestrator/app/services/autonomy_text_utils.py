from __future__ import annotations

import re
from uuid import UUID


def string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def extract_first_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return str(match.group(1)).strip()
    return ""


def parse_plan_lines(text: str) -> list[str]:
    lines = [line.strip(" -\t") for line in text.splitlines() if line.strip()]
    return [line[:240] for line in lines[:60]]


def extract_paths(text: str) -> list[str]:
    candidates = re.findall(
        r"\b(?:[\w.-]+/)*[\w.-]+\.(?:py|ts|tsx|js|jsx|json|md|toml|yaml|yml|ini|cfg|txt|rs|go|java|kt|sh)\b",
        text,
    )
    seen: set[str] = set()
    paths: list[str] = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            paths.append(item)
    return paths[:12]


def extract_list_items(text: str, *, headers: tuple[str, ...]) -> list[str]:
    lines = [line.strip() for line in text.splitlines()]
    items: list[str] = []
    capture = False
    for line in lines:
        normalized = line.lower().rstrip(":")
        if normalized in headers:
            capture = True
            continue
        if capture:
            if not line:
                break
            if line.startswith(("-", "*")):
                items.append(line.lstrip("-* ").strip())
                continue
            if re.match(r"^\d+\.\s+", line):
                items.append(re.sub(r"^\d+\.\s+", "", line).strip())
                continue
            break
    return [item for item in items if item][:8]


def extract_command_candidates(text: str) -> list[str]:
    commands: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if any(
            marker in lowered
            for marker in (
                "verify",
                "test command",
                "verification command",
                "run ",
                "pytest",
                "uv run",
                "npm run",
                "cargo test",
                "go test",
            )
        ):
            candidate = stripped.split(":", 1)[-1].strip() if ":" in stripped else stripped
            candidate = candidate.lstrip("-* ").strip("`")
            if candidate and len(candidate) < 180:
                commands.append(candidate)
    seen: set[str] = set()
    ordered: list[str] = []
    for command in commands:
        if command not in seen:
            seen.add(command)
            ordered.append(command)
    return ordered[:6]


def extract_acceptance_checks(text: str) -> list[str]:
    checks = extract_list_items(
        text,
        headers=("acceptance", "acceptance checks", "success criteria", "criteria"),
    )
    if checks:
        return checks
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if any(token in lowered for token in ("must", "should", "verify", "pass", "confirm")):
            lines.append(stripped.lstrip("-* ").strip())
    return lines[:6]


def split_delimited(value: str, *, delimiter: str = ",") -> list[str]:
    if not value.strip():
        return []
    return [item.strip() for item in value.split(delimiter) if item.strip()]


def parse_uuid(raw: str | None) -> UUID | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None
