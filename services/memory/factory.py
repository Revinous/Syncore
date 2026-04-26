from typing import Literal

from services.memory.base import MemoryStoreProtocol
from services.memory.sqlite_store import SQLiteMemoryStore
from services.memory.store import MemoryStore


def create_memory_store(
    *,
    db_backend: Literal["postgres", "sqlite"],
    postgres_dsn: str,
    sqlite_db_path: str,
) -> MemoryStoreProtocol:
    if db_backend == "sqlite":
        return SQLiteMemoryStore(sqlite_db_path)
    if db_backend == "postgres":
        return MemoryStore(postgres_dsn)
    raise ValueError(f"Unsupported SYNCORE_DB_BACKEND '{db_backend}'")
