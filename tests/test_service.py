"""Тесты выбора котировок в оркестраторе."""

from price_monitoring.config import Settings
from price_monitoring.moex import RawQuote
from price_monitoring.service import PriceMonitoringService


def _settings(price_field: str = "LAST") -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://test/test",
        gcp_project_id="",
        cloud_tasks_location="",
        cloud_tasks_queue="",
        alert_target_url="",
        alert_task_sa_email="",
        dry_run=True,
        price_field=price_field,
    )


def _raw(
    secid: str = "RU000A100001",
    boardid: str = "TQCB",
    last: float | None = 98.5,
    prev_price: float | None = 100.0,
    waprice: float | None = 98.7,
) -> RawQuote:
    return RawQuote(
        secid=secid,
        boardid=boardid,
        prev_price=prev_price,
        last=last,
        lcurrentprice=None,
        waprice=waprice,
        marketprice=None,
    )


BOARDS = {"RU000A100001": "TQCB"}


class TestPickQuote:
    def test_valid_quote(self):
        service = PriceMonitoringService(_settings())
        quote = service._pick_quote("RU000A100001", {("RU000A100001", "TQCB"): _raw()}, BOARDS)
        assert quote is not None
        assert quote.price == 98.5
        assert quote.prev_close == 100.0

    def test_no_trades_today_skipped(self):
        """LAST is None (нет сделок) — бумага пропускается, ложных алертов нет."""
        service = PriceMonitoringService(_settings())
        quote = service._pick_quote(
            "RU000A100001", {("RU000A100001", "TQCB"): _raw(last=None)}, BOARDS
        )
        assert quote is None

    def test_no_prev_close_skipped(self):
        """Новый выпуск без закрытия предыдущей сессии — скип."""
        service = PriceMonitoringService(_settings())
        quote = service._pick_quote(
            "RU000A100001", {("RU000A100001", "TQCB"): _raw(prev_price=None)}, BOARDS
        )
        assert quote is None

    def test_wrong_board_skipped(self):
        """Котировка есть только на непрофильном борде — скип."""
        service = PriceMonitoringService(_settings())
        quote = service._pick_quote(
            "RU000A100001", {("RU000A100001", "SPOB"): _raw(boardid="SPOB")}, BOARDS
        )
        assert quote is None

    def test_unknown_board_skipped(self):
        """Бумаги нет в moex_bonds / нет primary_boardid — скип."""
        service = PriceMonitoringService(_settings())
        quote = service._pick_quote("RU000A999999", {}, BOARDS)
        assert quote is None

    def test_price_field_switch(self):
        """PRICE_FIELD=WAPRICE переключает источник текущей цены."""
        service = PriceMonitoringService(_settings(price_field="WAPRICE"))
        quote = service._pick_quote("RU000A100001", {("RU000A100001", "TQCB"): _raw()}, BOARDS)
        assert quote is not None
        assert quote.price == 98.7
