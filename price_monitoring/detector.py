"""Детектор аномальных изменений цен облигаций.

Изменение считается от закрытия предыдущей сессии (PREVPRICE) —
фиксированный дневной baseline. Кейс «цена выросла и вернулась» не даёт
ложного алерта о падении: изменение от baseline снова около нуля.
"""

from collections.abc import Iterable, Mapping

from .config import AlertThresholds
from .schemas import (
    AlertDirection,
    AlertSeverity,
    AlertType,
    BondQuote,
    PortfolioBond,
    PriceAnomaly,
)


def classify(change_percent: float, thresholds: AlertThresholds) -> AlertType | None:
    """Возвращает тип алерта для изменения цены или None, если порог не пробит."""
    if change_percent < 0:
        abs_change = -change_percent
        if abs_change >= thresholds.drop_critical:
            return AlertType.from_parts(AlertDirection.DROP, AlertSeverity.CRITICAL)
        if abs_change >= thresholds.drop_warning:
            return AlertType.from_parts(AlertDirection.DROP, AlertSeverity.WARNING)
        return None

    if change_percent > 0:
        if change_percent >= thresholds.rise_critical:
            return AlertType.from_parts(AlertDirection.RISE, AlertSeverity.CRITICAL)
        if change_percent >= thresholds.rise_warning:
            return AlertType.from_parts(AlertDirection.RISE, AlertSeverity.WARNING)
        return None

    return None


def detect_anomalies(
    portfolio: Iterable[PortfolioBond],
    quotes: Mapping[str, BondQuote],
    thresholds: AlertThresholds,
) -> list[PriceAnomaly]:
    """Находит аномалии в портфеле пользователя по котировкам MOEX.

    Args:
        portfolio: Облигации портфеля пользователя.
        quotes: Котировки по secid (только валидные: есть и цена, и baseline).
        thresholds: Пороги срабатывания пользователя.

    Returns:
        Список аномалий. Бумаги без котировки (нет сделок сегодня,
        делистинг, новый выпуск без PREVPRICE) пропускаются.

    """
    anomalies: list[PriceAnomaly] = []
    for bond in portfolio:
        quote = quotes.get(bond.secid)
        if quote is None:
            continue

        change_percent = quote.change_percent
        alert_type = classify(change_percent, thresholds)
        if alert_type is None:
            continue

        anomalies.append(
            PriceAnomaly(
                secid=bond.secid,
                ticker=bond.ticker,
                name=bond.name,
                price=quote.price,
                prev_close=quote.prev_close,
                change_percent=change_percent,
                alert_type=alert_type,
            )
        )

    return anomalies
