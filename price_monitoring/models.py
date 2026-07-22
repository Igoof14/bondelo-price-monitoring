"""ORM-модели таблиц, которыми владеет или которые читает сервис."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, Numeric, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Базовый класс ORM-моделей сервиса."""


class MoexBondPrice(Base):
    """Снимок цены облигации с MOEX (в % от номинала). Владеет этот сервис."""

    __tablename__ = "moex_bond_prices"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    secid: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    boardid: Mapped[str] = mapped_column(Text, nullable=False)

    # Цены в % от номинала
    price: Mapped[float] = mapped_column(Numeric, nullable=False)
    prev_close: Mapped[float] = mapped_column(Numeric, nullable=False)
    change_pct: Mapped[float] = mapped_column(Numeric, nullable=False)

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        """Представление модели."""
        return f"<MoexBondPrice(secid={self.secid}, price={self.price})>"


class PriceAlertSent(Base):
    """Поставленные в очередь алерты (для эскалации и дневного лимита)."""

    __tablename__ = "price_alert_sent"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    secid: Mapped[str] = mapped_column(Text, nullable=False)

    # Тип алерта: 'drop_warning', 'drop_critical', 'rise_warning', 'rise_critical'
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)

    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        """Представление модели."""
        return f"<PriceAlertSent(secid={self.secid}, type={self.alert_type})>"


class PriceAlertSettings(Base):
    """Настройки ценовых уведомлений пользователя. Пишет бот, здесь read-only."""

    __tablename__ = "price_alert_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)

    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Пороги в процентах изменения цены
    drop_warning_threshold: Mapped[float] = mapped_column(Float, default=2.0)
    drop_critical_threshold: Mapped[float] = mapped_column(Float, default=5.0)
    rise_warning_threshold: Mapped[float] = mapped_column(Float, default=3.0)
    rise_critical_threshold: Mapped[float] = mapped_column(Float, default=7.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    def __repr__(self) -> str:
        """Представление модели."""
        return f"<PriceAlertSettings(telegram_id={self.telegram_id}, enabled={self.alerts_enabled})>"
