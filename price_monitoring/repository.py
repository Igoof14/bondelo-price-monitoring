"""Доступ к базе данных: настройки, портфели, история цен, отправленные алерты."""

import logging
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import delete, select, text

from .db import session_scope
from .models import MoexBondPrice, PriceAlertSent, PriceAlertSettings
from .schemas import AlertType, BondQuote, PortfolioBond

logger = logging.getLogger(__name__)

# Часовой пояс Москвы: "сегодня" для эскалации и дневного лимита считается
# по московскому времени — оно совпадает с торговым днём MOEX.
MOSCOW_TZ = timezone(timedelta(hours=3))


def _moscow_day_start() -> datetime:
    """Начало текущих суток по Москве, в UTC."""
    now_moscow = datetime.now(MOSCOW_TZ)
    return now_moscow.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


class AlertSettingsRepository:
    """Чтение настроек уведомлений (таблицей владеет бот)."""

    @classmethod
    async def list_enabled(cls) -> list[PriceAlertSettings]:
        """Возвращает настройки всех пользователей с включёнными алертами."""
        async with session_scope() as session:
            result = await session.execute(
                select(PriceAlertSettings).where(PriceAlertSettings.alerts_enabled.is_(True))
            )
            rows = list(result.scalars().all())
            for row in rows:
                session.expunge(row)
            return rows


class PortfolioRepository:
    """Портфели пользователей: user_bonds ⋈ bot_users ⋈ moex_bonds."""

    @classmethod
    async def load_portfolios(cls) -> dict[int, list[PortfolioBond]]:
        """Возвращает облигации портфеля по telegram_id.

        Бумаги матчатся с MOEX по ISIN; позиции без ISIN или без пары
        в moex_bonds пропускаются. Одна бумага на нескольких счетах
        схлопывается в одну (цена у неё одна).
        """
        query = text("""
            SELECT DISTINCT
                bu.telegram_id,
                mb.secid,
                mb.isin,
                COALESCE(mb.name, mb.shortname, mb.secid) AS name
            FROM user_bonds ub
            JOIN bot_users bu ON bu.id = ub.bot_user_id
            JOIN moex_bonds mb ON mb.isin = ub.isin
            WHERE ub.isin IS NOT NULL
              AND mb.is_traded IS TRUE
        """)
        async with session_scope() as session:
            result = await session.execute(query)
            portfolios: dict[int, list[PortfolioBond]] = {}
            for telegram_id, secid, isin, name in result:
                portfolios.setdefault(telegram_id, []).append(
                    PortfolioBond(secid=secid, isin=isin, name=name)
                )
            return portfolios

    @classmethod
    async def load_primary_boards(cls, secids: Iterable[str]) -> dict[str, str]:
        """Возвращает primary_boardid для указанных secid из moex_bonds."""
        secid_list = list(secids)
        if not secid_list:
            return {}

        query = text("""
            SELECT secid, primary_boardid
            FROM moex_bonds
            WHERE secid = ANY(:secids) AND primary_boardid IS NOT NULL
        """)
        async with session_scope() as session:
            result = await session.execute(query, {"secids": secid_list})
            return {secid: boardid for secid, boardid in result}


class PriceHistoryRepository:
    """История цен moex_bond_prices (таблицей владеет этот сервис)."""

    @classmethod
    async def save_snapshot(cls, quotes: Iterable[BondQuote]) -> int:
        """Сохраняет снимок котировок, возвращает количество записей."""
        quotes_list = list(quotes)
        async with session_scope() as session:
            for quote in quotes_list:
                session.add(
                    MoexBondPrice(
                        secid=quote.secid,
                        boardid=quote.boardid,
                        price=quote.price,
                        prev_close=quote.prev_close,
                        change_pct=quote.change_percent,
                    )
                )
            await session.commit()
        logger.debug(f"Сохранён снимок цен: {len(quotes_list)} бумаг")
        return len(quotes_list)

    @classmethod
    async def cleanup_older_than(cls, days_to_keep: int) -> int:
        """Удаляет записи цен старше указанного количества дней."""
        async with session_scope() as session:
            cutoff = datetime.now(UTC) - timedelta(days=days_to_keep)
            result = await session.execute(
                delete(MoexBondPrice).where(MoexBondPrice.recorded_at < cutoff)
            )
            await session.commit()
            deleted = getattr(result, "rowcount", 0)
            if deleted:
                logger.info(f"Удалено {deleted} старых записей цен")
            return deleted


class SentAlertRepository:
    """Учёт поставленных в очередь алертов (для эскалации и дневного лимита)."""

    @classmethod
    async def get_today(cls, telegram_id: int) -> dict[str, list[AlertType]]:
        """Возвращает отправленные сегодня алерты пользователя: secid -> типы."""
        async with session_scope() as session:
            result = await session.execute(
                select(PriceAlertSent.secid, PriceAlertSent.alert_type).where(
                    PriceAlertSent.telegram_id == telegram_id,
                    PriceAlertSent.sent_at >= _moscow_day_start(),
                )
            )
            sent: dict[str, list[AlertType]] = {}
            for secid, alert_type_raw in result:
                try:
                    sent.setdefault(secid, []).append(AlertType(alert_type_raw))
                except ValueError:
                    logger.warning(f"Невалидный alert_type в БД: {alert_type_raw}")
            return sent

    @classmethod
    async def count_today(cls, telegram_id: int) -> int:
        """Количество алертов пользователя за сегодня (по Москве)."""
        async with session_scope() as session:
            result = await session.execute(
                select(PriceAlertSent.id).where(
                    PriceAlertSent.telegram_id == telegram_id,
                    PriceAlertSent.sent_at >= _moscow_day_start(),
                )
            )
            return len(result.all())

    @classmethod
    async def record_batch(cls, telegram_id: int, alerts: Iterable[tuple[str, AlertType]]) -> None:
        """Записывает факт постановки алертов в очередь."""
        async with session_scope() as session:
            for secid, alert_type in alerts:
                session.add(
                    PriceAlertSent(
                        telegram_id=telegram_id,
                        secid=secid,
                        alert_type=alert_type.value,
                    )
                )
            await session.commit()

    @classmethod
    async def cleanup_older_than(cls, days_to_keep: int) -> int:
        """Удаляет записи алертов старше указанного количества дней."""
        async with session_scope() as session:
            cutoff = datetime.now(UTC) - timedelta(days=days_to_keep)
            result = await session.execute(
                delete(PriceAlertSent).where(PriceAlertSent.sent_at < cutoff)
            )
            await session.commit()
            deleted = getattr(result, "rowcount", 0)
            if deleted:
                logger.info(f"Удалено {deleted} старых записей алертов")
            return deleted
