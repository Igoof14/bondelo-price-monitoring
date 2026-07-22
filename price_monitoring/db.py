"""Подключение к базе данных (замена core.database из монорепы)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _normalize_url(url: str) -> str:
    """Приводит URL к asyncpg-схеме (postgresql+asyncpg://)."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def init_engine(database_url: str) -> None:
    """Инициализирует engine и фабрику сессий. Вызывается один раз при старте."""
    global _engine, _session_factory
    _engine = create_async_engine(_normalize_url(database_url), pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def dispose_engine() -> None:
    """Закрывает пул соединений при завершении джоба."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Контекст сессии с автоматическим rollback при ошибке."""
    if _session_factory is None:
        raise RuntimeError("Engine не инициализирован — вызовите init_engine()")

    async with _session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
