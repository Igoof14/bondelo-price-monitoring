"""Клиент MOEX ISS: котировки всех облигаций одним запросом.

Цены облигаций MOEX отдаёт в процентах от номинала, поэтому изменение
не искажается амортизацией: и текущая цена, и закрытие предыдущей
сессии считаются от одного номинала.
"""

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ISS_URL = "https://iss.moex.com/iss/engines/stock/markets/bonds/securities.json"

# PREVPRICE живёт в блоке securities, текущие цены — в marketdata.
ISS_PARAMS = {
    "iss.meta": "off",
    "iss.only": "securities,marketdata",
    "securities.columns": "SECID,BOARDID,PREVPRICE",
    "marketdata.columns": "SECID,BOARDID,LAST,LCURRENTPRICE,WAPRICE,MARKETPRICE",
}

REQUEST_TIMEOUT = 30.0


@dataclass(frozen=True, slots=True)
class RawQuote:
    """Сырая котировка одной облигации на одном борде."""

    secid: str
    boardid: str
    prev_price: float | None
    last: float | None
    lcurrentprice: float | None
    waprice: float | None
    marketprice: float | None

    def price(self, field: str) -> float | None:
        """Возвращает цену по имени поля MOEX (LAST, LCURRENTPRICE, ...)."""
        return getattr(self, field.lower())


async def fetch_market_data() -> dict[tuple[str, str], RawQuote]:
    """Загружает котировки всех облигаций, ключ — (secid, boardid).

    Одна бумага торгуется на нескольких бордах; выбор нужного борда
    (primary_boardid из moex_bonds) — ответственность вызывающего.
    """
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.get(ISS_URL, params=ISS_PARAMS)
        response.raise_for_status()
        data = response.json()

    securities = _rows_as_dicts(data["securities"])
    marketdata = _rows_as_dicts(data["marketdata"])

    prev_by_key = {(row["SECID"], row["BOARDID"]): row.get("PREVPRICE") for row in securities}

    quotes: dict[tuple[str, str], RawQuote] = {}
    for row in marketdata:
        key = (row["SECID"], row["BOARDID"])
        quotes[key] = RawQuote(
            secid=row["SECID"],
            boardid=row["BOARDID"],
            prev_price=prev_by_key.get(key),
            last=row.get("LAST"),
            lcurrentprice=row.get("LCURRENTPRICE"),
            waprice=row.get("WAPRICE"),
            marketprice=row.get("MARKETPRICE"),
        )

    logger.info(f"Загружено {len(quotes)} котировок с MOEX ISS")
    return quotes


def _rows_as_dicts(block: dict[str, Any]) -> list[dict[str, Any]]:
    """Преобразует ISS-блок {columns: [...], data: [[...]]} в список словарей."""
    columns = block["columns"]
    return [dict(zip(columns, row, strict=True)) for row in block["data"]]
