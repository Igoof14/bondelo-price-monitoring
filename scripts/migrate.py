"""Применяет SQL-миграции из каталога migrations/.

Запуск: uv run python scripts/migrate.py

Применяются файлы 0xx_*.sql в лексикографическом порядке.
Файлы 9xx_*.sql (ручные, разрушающие) пропускаются.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def _normalize_url(url: str) -> str:
    """asyncpg не понимает SQLAlchemy-схему postgresql+asyncpg://."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def main() -> None:
    """Применяет все автоматические миграции по порядку."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL не задан")
        sys.exit(1)

    sql_files = sorted(
        f for f in MIGRATIONS_DIR.glob("*.sql") if not f.name.startswith("9")
    )
    if not sql_files:
        logger.warning("Миграции не найдены в %s", MIGRATIONS_DIR)
        return

    conn = await asyncpg.connect(_normalize_url(database_url))
    try:
        for sql_file in sql_files:
            logger.info("Применяю %s", sql_file.name)
            await conn.execute(sql_file.read_text())
        logger.info("Миграции применены: %d", len(sql_files))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
