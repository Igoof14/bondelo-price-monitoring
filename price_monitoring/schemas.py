"""Domain-объекты фичи мониторинга цен."""

from dataclasses import dataclass
from enum import Enum


class AlertSeverity(Enum):
    """Уровень критичности алерта."""

    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        """Числовой ранг для сравнения уровней (critical > warning)."""
        return 2 if self is AlertSeverity.CRITICAL else 1


class AlertDirection(Enum):
    """Направление изменения цены."""

    DROP = "drop"
    RISE = "rise"


class AlertType(Enum):
    """Тип алерта = направление + уровень критичности."""

    DROP_WARNING = "drop_warning"
    DROP_CRITICAL = "drop_critical"
    RISE_WARNING = "rise_warning"
    RISE_CRITICAL = "rise_critical"

    @property
    def severity(self) -> AlertSeverity:
        """Возвращает уровень критичности алерта."""
        if self in (AlertType.DROP_CRITICAL, AlertType.RISE_CRITICAL):
            return AlertSeverity.CRITICAL
        return AlertSeverity.WARNING

    @property
    def direction(self) -> AlertDirection:
        """Возвращает направление изменения цены."""
        if self in (AlertType.DROP_WARNING, AlertType.DROP_CRITICAL):
            return AlertDirection.DROP
        return AlertDirection.RISE

    @classmethod
    def from_parts(cls, direction: AlertDirection, severity: AlertSeverity) -> "AlertType":
        """Собирает AlertType из направления и уровня критичности."""
        return cls(f"{direction.value}_{severity.value}")


@dataclass(frozen=True, slots=True)
class BondQuote:
    """Котировка облигации с MOEX (цены в % от номинала).

    ``price`` — текущая цена (поле выбирается настройкой PRICE_FIELD),
    ``prev_close`` — цена закрытия предыдущей сессии (PREVPRICE), baseline
    для расчёта изменения.
    """

    secid: str
    boardid: str
    price: float
    prev_close: float

    @property
    def change_percent(self) -> float:
        """Изменение цены от закрытия предыдущей сессии, в процентах."""
        return (self.price - self.prev_close) / self.prev_close * 100


@dataclass(frozen=True, slots=True)
class PortfolioBond:
    """Облигация из портфеля пользователя (user_bonds ⋈ moex_bonds)."""

    secid: str
    ticker: str
    name: str


@dataclass(frozen=True, slots=True)
class PriceAnomaly:
    """Аномальное изменение цены облигации, требующее уведомления."""

    secid: str
    ticker: str
    name: str
    price: float
    prev_close: float
    change_percent: float
    alert_type: AlertType

    @property
    def direction(self) -> AlertDirection:
        """Направление изменения цены."""
        return self.alert_type.direction

    @property
    def severity(self) -> AlertSeverity:
        """Уровень критичности аномалии."""
        return self.alert_type.severity

    def to_payload(self) -> dict[str, object]:
        """Представление аномалии для payload задачи Cloud Tasks."""
        return {
            "secid": self.secid,
            "ticker": self.ticker,
            "name": self.name,
            "price_pct": round(self.price, 4),
            "prev_close_pct": round(self.prev_close, 4),
            "change_pct": round(self.change_percent, 2),
            "alert_type": self.alert_type.value,
        }
