"""Оркестратор мониторинга цен: один прогон джоба."""

import logging
from datetime import UTC, datetime

from .alert_state import filter_alerts
from .config import DEFAULT_POLICY, AlertPolicyConfig, AlertThresholds, Settings
from .detector import detect_anomalies
from .models import PriceAlertSettings
from .moex import RawQuote, fetch_market_data
from .repository import (
    AlertSettingsRepository,
    PortfolioRepository,
    PriceHistoryRepository,
    SentAlertRepository,
)
from .schemas import BondQuote, PortfolioBond
from .tasks import AlertTaskQueue

logger = logging.getLogger(__name__)


class PriceMonitoringService:
    """Один прогон: загрузка портфелей, котировки MOEX, детект, постановка задач."""

    def __init__(self, settings: Settings, policy: AlertPolicyConfig = DEFAULT_POLICY):
        """Собирает сервис с настройками окружения и политикой алертов."""
        self._settings = settings
        self._policy = policy
        self._task_queue = AlertTaskQueue(settings, run_started_at=datetime.now(UTC))

    async def run_once(self) -> None:
        """Полный цикл проверки цен."""
        logger.info("Запуск проверки цен облигаций")

        users_settings = await AlertSettingsRepository.list_enabled()
        if not users_settings:
            logger.info("Нет пользователей с включенными уведомлениями")
            return

        portfolios = await PortfolioRepository.load_portfolios()
        monitored_secids = {b.secid for bonds in portfolios.values() for b in bonds}
        if not monitored_secids:
            logger.info("Нет облигаций для мониторинга (user_bonds пуст или не сматчился)")
            return

        logger.info(
            f"Пользователей с алертами: {len(users_settings)}, "
            f"бумаг под мониторингом: {len(monitored_secids)}"
        )

        quotes = await self._load_quotes(monitored_secids)
        if not quotes:
            logger.info("Нет валидных котировок (торги не идут?) — прогон завершён")
            return

        await PriceHistoryRepository.save_snapshot(quotes.values())

        for settings_row in users_settings:
            portfolio = portfolios.get(settings_row.telegram_id)
            if not portfolio:
                continue
            try:
                await self._check_user(settings_row, portfolio, quotes)
            except Exception as e:
                logger.error(f"Ошибка проверки пользователя {settings_row.telegram_id}: {e}")

        await self._cleanup()
        logger.info("Проверка цен завершена")

    async def _load_quotes(self, secids: set[str]) -> dict[str, BondQuote]:
        """Загружает котировки MOEX и отбирает валидные по нужным бумагам.

        Бумаги без сделок ни на одном борде (нет цены) или без закрытия
        предыдущей сессии (новый выпуск) отбрасываются.
        """
        raw_quotes = await fetch_market_data()
        primary_boards = await PortfolioRepository.load_primary_boards(secids)

        by_secid: dict[str, list[RawQuote]] = {}
        for raw in raw_quotes.values():
            by_secid.setdefault(raw.secid, []).append(raw)

        quotes: dict[str, BondQuote] = {}
        skipped: list[str] = []
        for secid in secids:
            quote = self._pick_quote(secid, by_secid.get(secid, []), primary_boards.get(secid))
            if quote is None:
                skipped.append(secid)
                continue
            quotes[secid] = quote

        logger.info(f"Валидных котировок: {len(quotes)}, пропущено бумаг: {len(skipped)}")
        if skipped:
            logger.info(f"Пропущены (нет валидной котировки ни на одном борде): {skipped}")
        return quotes

    def _pick_quote(
        self,
        secid: str,
        board_quotes: list[RawQuote],
        primary_boardid: str | None,
    ) -> BondQuote | None:
        """Выбирает лучшую валидную котировку бумаги.

        Приоритет бордов: primary из moex_bonds, затем основные T+
        (TQ*), затем остальные. Фолбэк нужен, потому что primary_boardid
        бывает нерабочим: у ОФЗ синк ставит SPOB, где торгов нет, —
        реальные котировки на TQOB.
        """
        ordered = sorted(
            board_quotes,
            key=lambda q: (
                q.boardid != primary_boardid,
                not q.boardid.startswith("TQ"),
                q.boardid,
            ),
        )
        for raw in ordered:
            price = raw.price(self._settings.price_field)
            if price is None or raw.prev_price is None or raw.prev_price <= 0:
                continue
            return BondQuote(
                secid=secid, boardid=raw.boardid, price=price, prev_close=raw.prev_price
            )
        return None

    async def _check_user(
        self,
        settings_row: PriceAlertSettings,
        portfolio: list[PortfolioBond],
        quotes: dict[str, BondQuote],
    ) -> None:
        """Проверяет портфель одного пользователя и ставит задачу на алерты."""
        telegram_id = settings_row.telegram_id
        thresholds = AlertThresholds(
            drop_warning=settings_row.drop_warning_threshold,
            drop_critical=settings_row.drop_critical_threshold,
            rise_warning=settings_row.rise_warning_threshold,
            rise_critical=settings_row.rise_critical_threshold,
        )

        anomalies = detect_anomalies(portfolio, quotes, thresholds)
        if not anomalies:
            return

        sent_today = await SentAlertRepository.get_today(telegram_id)
        sent_count = await SentAlertRepository.count_today(telegram_id)

        to_send = filter_alerts(
            anomalies,
            sent_today,
            sent_today_count=sent_count,
            max_daily_alerts=self._policy.max_daily_alerts,
        )
        if not to_send:
            logger.debug(f"Пользователь {telegram_id}: все аномалии отфильтрованы эскалацией")
            return

        enqueued = await self._task_queue.enqueue(telegram_id, to_send)
        # В dry-run состояние эскалации не трогаем — повторные прогоны
        # должны показывать те же алерты.
        if enqueued and not self._settings.dry_run:
            await SentAlertRepository.record_batch(
                telegram_id, [(a.secid, a.alert_type) for a in to_send]
            )

    async def _cleanup(self) -> None:
        """Удаляет устаревшие записи истории цен и алертов."""
        await PriceHistoryRepository.cleanup_older_than(self._policy.retention_days)
        await SentAlertRepository.cleanup_older_than(self._policy.retention_days)
