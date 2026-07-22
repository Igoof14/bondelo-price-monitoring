"""Конфигурация сервиса: переменные окружения и политика алертов."""

from dataclasses import dataclass

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Поля котировки MOEX, допустимые как источник текущей цены.
ALLOWED_PRICE_FIELDS = ("LAST", "LCURRENTPRICE", "WAPRICE", "MARKETPRICE")


class Settings(BaseSettings):
    """Настройки сервиса из переменных окружения и .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    # Google Cloud Tasks (вне dry-run обязательны, кроме alert_task_sa_email)
    gcp_project_id: str = "bond-invest"
    cloud_tasks_location: str = "europe-west3"
    cloud_tasks_queue: str = "bot-alert-tasks"
    alert_target_url: str = "https://34.178.57.246:8080/notify"
    alert_task_sa_email: str = "cloud-tasks-invoker@bond-invest.iam.gserviceaccount.com"

    # Режим без побочных эффектов: алерты логируются, задачи не ставятся.
    dry_run: bool = False

    # Какое поле котировки MOEX использовать как текущую цену.
    price_field: str = "LAST"

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        """Проверяет поле цены и обязательные параметры Cloud Tasks."""
        object.__setattr__(self, "price_field", self.price_field.upper())
        if self.price_field not in ALLOWED_PRICE_FIELDS:
            raise ValueError(
                f"PRICE_FIELD={self.price_field} не поддерживается, "
                f"допустимо: {ALLOWED_PRICE_FIELDS}"
            )

        if not self.dry_run:
            missing = [
                name
                for name, value in (
                    ("GCP_PROJECT_ID", self.gcp_project_id),
                    ("CLOUD_TASKS_LOCATION", self.cloud_tasks_location),
                    ("CLOUD_TASKS_QUEUE", self.cloud_tasks_queue),
                    ("ALERT_TARGET_URL", self.alert_target_url),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"Не заданы переменные окружения: {', '.join(missing)}"
                )

        return self

    @classmethod
    def from_env(cls) -> "Settings":
        """Собирает настройки из окружения и .env."""
        return cls()  # type: ignore[call-arg] — поля приходят из env


@dataclass(frozen=True, slots=True)
class AlertPolicyConfig:
    """Политика ограничения количества алертов."""

    # Максимум алертов (записей price_alert_sent) на пользователя в сутки.
    max_daily_alerts: int = 20

    # Сколько дней хранить историю цен и отправленных алертов.
    retention_days: int = 30


DEFAULT_POLICY = AlertPolicyConfig()


@dataclass(frozen=True, slots=True)
class AlertThresholds:
    """Пороги пользователя для срабатывания алерта (в процентах изменения цены)."""

    drop_warning: float
    drop_critical: float
    rise_warning: float
    rise_critical: float
