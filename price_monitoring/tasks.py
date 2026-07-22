"""Постановка задач на отправку алертов в Google Cloud Tasks.

Контракт задачи: POST {ALERT_TARGET_URL} с JSON:

    {
        "telegram_id": 123456,
        "alerts": [
            {
                "secid": "RU000A108EF8",
                "ticker": "СамолетP12",
                "name": "...",
                "price_pct": 94.3,
                "prev_close_pct": 99.5,
                "change_pct": -5.2,
                "alert_type": "drop_critical"
            }
        ]
    }

Одна задача на пользователя за прогон. Имя задачи детерминировано
(price-alert-{telegram_id}-{yyyymmddHHMM}) — при ретрае джоба Cloud Tasks
отбросит дубликат как AlreadyExists.
"""

import asyncio
import json
import logging
from collections.abc import Sequence
from datetime import datetime

from google.api_core.exceptions import AlreadyExists
from google.cloud import tasks_v2

from .config import Settings
from .schemas import PriceAnomaly

logger = logging.getLogger(__name__)


class AlertTaskQueue:
    """Ставит задачи на отправку алертов в Cloud Tasks."""

    def __init__(self, settings: Settings, *, run_started_at: datetime):
        """Инициализирует очередь.

        Args:
            settings: Настройки сервиса (проект, очередь, target URL).
            run_started_at: Время старта прогона — входит в имя задачи
                для идемпотентности при ретрае.

        """
        self._settings = settings
        self._run_suffix = run_started_at.strftime("%Y%m%d%H%M")
        self._client: tasks_v2.CloudTasksClient | None = None

    def _get_client(self) -> tasks_v2.CloudTasksClient:
        """Ленивая инициализация клиента (в dry-run не нужен вовсе)."""
        if self._client is None:
            self._client = tasks_v2.CloudTasksClient()
        return self._client

    async def enqueue(self, telegram_id: int, anomalies: Sequence[PriceAnomaly]) -> bool:
        """Ставит задачу на отправку алертов пользователю.

        Returns:
            True, если задача поставлена (или уже существовала), иначе False.

        """
        payload: dict[str, object] = {
            "telegram_id": telegram_id,
            "alerts": [a.to_payload() for a in anomalies],
        }

        if self._settings.dry_run:
            logger.info(
                f"[DRY_RUN] Задача для пользователя {telegram_id}:\n"
                f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
            )
            return True

        try:
            # Клиент синхронный — уводим вызов в поток.
            await asyncio.to_thread(self._create_task, telegram_id, payload)
        except AlreadyExists:
            logger.info(f"Задача для пользователя {telegram_id} уже в очереди (ретрай джоба)")
            return True
        except Exception as e:
            logger.error(f"Ошибка постановки задачи для пользователя {telegram_id}: {e}")
            return False

        logger.info(f"Поставлена задача для пользователя {telegram_id}: {len(anomalies)} алертов")
        return True

    def _create_task(self, telegram_id: int, payload: dict[str, object]) -> None:
        """Синхронный вызов Cloud Tasks API."""
        client = self._get_client()
        s = self._settings

        queue_path = client.queue_path(s.gcp_project_id, s.cloud_tasks_location, s.cloud_tasks_queue)
        task_name = client.task_path(
            s.gcp_project_id,
            s.cloud_tasks_location,
            s.cloud_tasks_queue,
            f"price-alert-{telegram_id}-{self._run_suffix}",
        )

        http_request = tasks_v2.HttpRequest(
            url=s.alert_target_url,
            http_method=tasks_v2.HttpMethod.POST,
            headers={"Content-Type": "application/json"},
            body=json.dumps(payload, ensure_ascii=False).encode(),
        )
        if s.alert_task_sa_email:
            http_request.oidc_token = tasks_v2.OidcToken(
                service_account_email=s.alert_task_sa_email
            )

        client.create_task(
            tasks_v2.CreateTaskRequest(
                parent=queue_path,
                task=tasks_v2.Task(name=task_name, http_request=http_request),
            )
        )
