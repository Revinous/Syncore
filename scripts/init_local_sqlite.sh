#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

cp -n .env.example .env || true
set -a
source .env
set +a

DB_PATH="${SQLITE_DB_PATH:-.syncore/syncore.db}"
mkdir -p "$(dirname "$DB_PATH")"

python3 - "$DB_PATH" <<'PY'
from pathlib import Path
import sqlite3
import sys

db_path = Path(sys.argv[1])
schema = Path("scripts/init_sqlite.sql").read_text(encoding="utf-8")

connection = sqlite3.connect(db_path)
try:
    table_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks' LIMIT 1"
    ).fetchone()
    if table_exists:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()}
        if "workspace_id" not in columns:
            connection.execute("ALTER TABLE tasks ADD COLUMN workspace_id TEXT")
    connection.executescript(schema)
    connection.commit()
finally:
    connection.close()

print(f"[db-local-init] initialized sqlite database at {db_path}")
PY
