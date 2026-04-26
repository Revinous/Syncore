#!/usr/bin/env bash
set -euo pipefail

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
    connection.executescript(schema)
    connection.commit()
finally:
    connection.close()

print(f"[db-local-init] initialized sqlite database at {db_path}")
PY
