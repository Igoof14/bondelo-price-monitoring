"""Эскалация алертов в течение торгового дня.

Baseline (закрытие предыдущей сессии) фиксирован весь день, поэтому
вместо time-cooldown работает эскалация состояний: по каждой паре
(secid, направление) алерт уходит, только если новая severity выше
максимальной уже отправленной сегодня.

    нет алерта -> warning -> critical

Следствия:
- Цена держится выше порога весь день — один алерт, повторы глушатся.
- warning -> critical — эскалация, алерт уходит.
- Рост утром и реальное падение днём — направления независимы,
  алерт о падении уходит.
- Новый день — новый baseline, состояния обнуляются сами (учитываются
  только сегодняшние записи price_alert_sent).

Дополнительно действует дневной лимит алертов на пользователя.
"""

import logging
from collections.abc import Iterable, Mapping

from .schemas import AlertDirection, AlertType, PriceAnomaly

logger = logging.getLogger(__name__)


def _max_sent_rank(sent_types: Iterable[AlertType], direction: AlertDirection) -> int:
    """Максимальный ранг severity среди отправленных алертов данного направления."""
    ranks = [t.severity.rank for t in sent_types if t.direction is direction]
    return max(ranks, default=0)


def filter_alerts(
    anomalies: Iterable[PriceAnomaly],
    sent_today: Mapping[str, list[AlertType]],
    *,
    sent_today_count: int,
    max_daily_alerts: int,
) -> list[PriceAnomaly]:
    """Возвращает аномалии, по которым нужно отправить алерт сейчас.

    Args:
        anomalies: Обнаруженные аномалии пользователя.
        sent_today: Отправленные сегодня алерты: secid -> список типов.
        sent_today_count: Сколько алертов пользователь уже получил сегодня.
        max_daily_alerts: Дневной лимит алертов на пользователя.

    """
    budget = max_daily_alerts - sent_today_count
    if budget <= 0:
        logger.debug(f"Дневной лимит алертов исчерпан ({sent_today_count}/{max_daily_alerts})")
        return []

    # Критичные — в первую очередь, если упираемся в дневной лимит.
    ordered = sorted(anomalies, key=lambda a: a.severity.rank, reverse=True)

    result: list[PriceAnomaly] = []
    for anomaly in ordered:
        already_sent = sent_today.get(anomaly.secid, [])
        if anomaly.severity.rank <= _max_sent_rank(already_sent, anomaly.direction):
            continue

        result.append(anomaly)
        if len(result) >= budget:
            logger.debug("Достигнут дневной лимит алертов, остальные аномалии отброшены")
            break

    return result
