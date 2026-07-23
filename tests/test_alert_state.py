"""Тесты дневной эскалации алертов."""

from price_monitoring.alert_state import filter_alerts
from price_monitoring.schemas import AlertType, PriceAnomaly


def _anomaly(alert_type: AlertType, secid: str = "RU000A100001") -> PriceAnomaly:
    sign = -1 if alert_type.value.startswith("drop") else 1
    return PriceAnomaly(
        secid=secid,
        isin=secid,
        name="Тестовая облигация",
        price=100.0 + sign * 5,
        prev_close=100.0,
        change_percent=sign * 5.0,
        alert_type=alert_type,
    )


def _filter(anomalies, sent_today, *, sent_count=0, limit=20):
    return filter_alerts(
        anomalies, sent_today, sent_today_count=sent_count, max_daily_alerts=limit
    )


class TestEscalation:
    def test_first_alert_passes(self):
        result = _filter([_anomaly(AlertType.DROP_WARNING)], {})
        assert len(result) == 1

    def test_same_severity_repeated_is_silenced(self):
        """Цена держится выше порога весь день — один алерт, повторы глушатся."""
        sent = {"RU000A100001": [AlertType.DROP_WARNING]}
        result = _filter([_anomaly(AlertType.DROP_WARNING)], sent)
        assert result == []

    def test_warning_to_critical_escalates(self):
        sent = {"RU000A100001": [AlertType.DROP_WARNING]}
        result = _filter([_anomaly(AlertType.DROP_CRITICAL)], sent)
        assert len(result) == 1

    def test_deescalation_is_silenced(self):
        """После critical откат к warning не алертится — уже сообщали о худшем."""
        sent = {"RU000A100001": [AlertType.DROP_CRITICAL]}
        result = _filter([_anomaly(AlertType.DROP_WARNING)], sent)
        assert result == []

    def test_directions_are_independent(self):
        """Рост утром, реальное падение днём — алерт о падении уходит."""
        sent = {"RU000A100001": [AlertType.RISE_CRITICAL]}
        result = _filter([_anomaly(AlertType.DROP_WARNING)], sent)
        assert len(result) == 1

    def test_other_secid_not_affected(self):
        sent = {"RU000A100001": [AlertType.DROP_WARNING]}
        result = _filter([_anomaly(AlertType.DROP_WARNING, secid="RU000A200002")], sent)
        assert len(result) == 1

    def test_new_day_state_is_empty(self):
        """Новый день — sent_today пуст, алерты снова проходят."""
        result = _filter([_anomaly(AlertType.DROP_WARNING)], {})
        assert len(result) == 1


class TestDailyLimit:
    def test_limit_exhausted(self):
        result = _filter([_anomaly(AlertType.DROP_CRITICAL)], {}, sent_count=20, limit=20)
        assert result == []

    def test_budget_respected(self):
        anomalies = [
            _anomaly(AlertType.DROP_WARNING, secid=f"RU000A10000{i}") for i in range(5)
        ]
        result = _filter(anomalies, {}, sent_count=18, limit=20)
        assert len(result) == 2

    def test_critical_prioritized_within_budget(self):
        """При нехватке бюджета критичные алерты уходят первыми."""
        anomalies = [
            _anomaly(AlertType.DROP_WARNING, secid="RU000A100001"),
            _anomaly(AlertType.DROP_CRITICAL, secid="RU000A200002"),
        ]
        result = _filter(anomalies, {}, sent_count=19, limit=20)
        assert len(result) == 1
        assert result[0].alert_type is AlertType.DROP_CRITICAL
