"""Тесты выбора котировок в оркестраторе."""

from price_monitoring.config import Settings
from price_monitoring.moex import RawQuote
from price_monitoring.service import PriceMonitoringService


def _settings(price_field: str = "LAST") -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://test/test",
        dry_run=True,
        price_field=price_field,
    )


def _raw(
    boardid: str = "TQCB",
    last: float | None = 98.5,
    prev_price: float | None = 100.0,
    waprice: float | None = 98.7,
) -> RawQuote:
    return RawQuote(
        secid="RU000A100001",
        boardid=boardid,
        prev_price=prev_price,
        last=last,
        lcurrentprice=None,
        waprice=waprice,
        marketprice=None,
    )


class TestPickQuote:
    def test_valid_primary_board(self):
        service = PriceMonitoringService(_settings())
        quote = service._pick_quote("RU000A100001", [_raw()], "TQCB")
        assert quote is not None
        assert quote.boardid == "TQCB"
        assert quote.price == 98.5
        assert quote.prev_close == 100.0

    def test_no_trades_on_any_board_skipped(self):
        """LAST is None на всех бордах (нет сделок) — бумага пропускается."""
        service = PriceMonitoringService(_settings())
        quote = service._pick_quote("RU000A100001", [_raw(last=None)], "TQCB")
        assert quote is None

    def test_no_prev_close_skipped(self):
        """Новый выпуск без закрытия предыдущей сессии — скип."""
        service = PriceMonitoringService(_settings())
        quote = service._pick_quote("RU000A100001", [_raw(prev_price=None)], "TQCB")
        assert quote is None

    def test_no_quotes_at_all_skipped(self):
        """Бумаги нет в marketdata (делистинг) — скип."""
        service = PriceMonitoringService(_settings())
        assert service._pick_quote("RU000A100001", [], "TQCB") is None

    def test_fallback_to_tq_board_when_primary_empty(self):
        """Кейс ОФЗ: primary=SPOB без торгов — фолбэк на TQOB."""
        service = PriceMonitoringService(_settings())
        quote = service._pick_quote(
            "RU000A100001",
            [
                _raw(boardid="SPOB", last=None, prev_price=None),
                _raw(boardid="TQOB", last=81.7, prev_price=81.3),
            ],
            "SPOB",
        )
        assert quote is not None
        assert quote.boardid == "TQOB"
        assert quote.price == 81.7

    def test_primary_preferred_over_other_valid_boards(self):
        """Если primary-борд валиден, фолбэк не используется."""
        service = PriceMonitoringService(_settings())
        quote = service._pick_quote(
            "RU000A100001",
            [
                _raw(boardid="SPOB", last=99.0, prev_price=99.5),
                _raw(boardid="TQCB", last=98.5, prev_price=100.0),
            ],
            "TQCB",
        )
        assert quote is not None
        assert quote.boardid == "TQCB"

    def test_tq_boards_preferred_without_primary(self):
        """Без primary_boardid основные борды TQ* приоритетнее прочих."""
        service = PriceMonitoringService(_settings())
        quote = service._pick_quote(
            "RU000A100001",
            [
                _raw(boardid="SPOB", last=99.0, prev_price=99.5),
                _raw(boardid="TQOB", last=81.7, prev_price=81.3),
            ],
            None,
        )
        assert quote is not None
        assert quote.boardid == "TQOB"

    def test_price_field_switch(self):
        """PRICE_FIELD=WAPRICE переключает источник текущей цены."""
        service = PriceMonitoringService(_settings(price_field="WAPRICE"))
        quote = service._pick_quote("RU000A100001", [_raw()], "TQCB")
        assert quote is not None
        assert quote.price == 98.7
