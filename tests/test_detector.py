"""Тесты детектора аномалий."""

from price_monitoring.config import AlertThresholds
from price_monitoring.detector import classify, detect_anomalies
from price_monitoring.schemas import AlertType, BondQuote, PortfolioBond

THRESHOLDS = AlertThresholds(
    drop_warning=2.0,
    drop_critical=5.0,
    rise_warning=3.0,
    rise_critical=7.0,
)


def _bond(secid: str = "RU000A100001") -> PortfolioBond:
    return PortfolioBond(secid=secid, isin=secid, name="Тестовая облигация")


def _quote(price: float, prev_close: float = 100.0, secid: str = "RU000A100001") -> BondQuote:
    return BondQuote(secid=secid, boardid="TQCB", price=price, prev_close=prev_close)


class TestClassify:
    def test_no_change(self):
        assert classify(0.0, THRESHOLDS) is None

    def test_small_move_below_thresholds(self):
        assert classify(-1.9, THRESHOLDS) is None
        assert classify(2.9, THRESHOLDS) is None

    def test_drop_warning(self):
        assert classify(-2.0, THRESHOLDS) is AlertType.DROP_WARNING
        assert classify(-4.9, THRESHOLDS) is AlertType.DROP_WARNING

    def test_drop_critical(self):
        assert classify(-5.0, THRESHOLDS) is AlertType.DROP_CRITICAL

    def test_rise_warning(self):
        assert classify(3.0, THRESHOLDS) is AlertType.RISE_WARNING

    def test_rise_critical(self):
        assert classify(7.5, THRESHOLDS) is AlertType.RISE_CRITICAL


class TestDetectAnomalies:
    def test_detects_drop_from_prev_close(self):
        anomalies = detect_anomalies(
            [_bond()], {"RU000A100001": _quote(price=94.0, prev_close=100.0)}, THRESHOLDS
        )
        assert len(anomalies) == 1
        assert anomalies[0].alert_type is AlertType.DROP_CRITICAL
        assert anomalies[0].change_percent == -6.0

    def test_bond_without_quote_skipped(self):
        """Нет сделок сегодня / делистинг — котировки нет, аномалии нет."""
        anomalies = detect_anomalies([_bond()], {}, THRESHOLDS)
        assert anomalies == []

    def test_returned_to_baseline_is_quiet(self):
        """Кейс «выросла и вернулась»: изменение от baseline ~0 — тихо."""
        anomalies = detect_anomalies(
            [_bond()], {"RU000A100001": _quote(price=100.1, prev_close=100.0)}, THRESHOLDS
        )
        assert anomalies == []

    def test_change_computed_on_relative_prices(self):
        """Цены в % от номинала: амортизация не искажает изменение."""
        # После амортизации обе цены в % от нового номинала — изменение честное.
        anomalies = detect_anomalies(
            [_bond()], {"RU000A100001": _quote(price=97.0, prev_close=99.0)}, THRESHOLDS
        )
        assert len(anomalies) == 1
        assert anomalies[0].alert_type is AlertType.DROP_WARNING
