from services.memory.factory import create_memory_store
from services.memory.sqlite_store import SQLiteMemoryStore
from services.memory.store import MemoryStore


def test_factory_returns_sqlite_store_for_sqlite_backend(tmp_path) -> None:
    store = create_memory_store(
        db_backend="sqlite",
        postgres_dsn="postgresql://unused",
        sqlite_db_path=str(tmp_path / "syncore.db"),
    )
    assert isinstance(store, SQLiteMemoryStore)


def test_factory_returns_postgres_store_for_postgres_backend() -> None:
    store = create_memory_store(
        db_backend="postgres",
        postgres_dsn="postgresql://unused",
        sqlite_db_path=".syncore/syncore.db",
    )
    assert isinstance(store, MemoryStore)
