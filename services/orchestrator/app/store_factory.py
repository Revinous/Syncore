from services.memory import MemoryStoreProtocol, create_memory_store

from app.config import Settings


def build_memory_store(settings: Settings) -> MemoryStoreProtocol:
    return create_memory_store(
        db_backend=settings.syncore_db_backend,
        postgres_dsn=settings.postgres_dsn,
        sqlite_db_path=settings.sqlite_db_path,
    )
