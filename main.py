"""Entrypoint Cloud Run Job: один прогон мониторинга цен."""

import asyncio
import logging
import sys

from price_monitoring.config import Settings
from price_monitoring.db import dispose_engine, init_engine
from price_monitoring.service import PriceMonitoringService
from scripts.migrate import apply_migrations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


async def run() -> None:
    """Инициализирует окружение и выполняет один прогон проверки цен."""
    settings = Settings.from_env()
    await apply_migrations(settings.database_url)
    init_engine(settings.database_url)
    try:
        await PriceMonitoringService(settings).run_once()
    finally:
        await dispose_engine()


def main() -> None:
    """Синхронная обёртка для запуска из контейнера."""
    try:
        asyncio.run(run())
    except Exception:
        logging.getLogger(__name__).exception("Прогон завершился с ошибкой")
        sys.exit(1)


if __name__ == "__main__":
    main()
