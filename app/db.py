from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _normalize_url(url: str) -> str:
    """Chuẩn hoá URL Postgres về driver psycopg 3."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


database_url = _normalize_url(settings.database_url)

if not database_url.startswith(("postgresql", "postgres")):
    raise RuntimeError(
        "FraudLens chỉ hỗ trợ PostgreSQL. Đặt DATABASE_URL dạng "
        "postgresql+psycopg://user:pass@host:5432/fraudlens "
        f"(giá trị hiện tại: {database_url.split('://')[0]}://...)"
    )

engine = create_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=10)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401  (register mappers)
    from app.schema_migrations import apply_schema_migrations

    Base.metadata.create_all(bind=engine)
    apply_schema_migrations(engine)
