"""Офіційні курси гривні з відкритого API Національного банку України."""

import logging
import math
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from .models import HistoryPoint, Rate, Stats

KYIV = ZoneInfo("Europe/Kyiv")
RATES_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"
HISTORY_URL = "https://bank.gov.ua/NBU_Exchange/exchange_site"
USER_AGENT = "tk42-nbu-rates/1.0 (student lab project)"
CACHE_SECONDS = 30 * 60        # курс НБУ змінюється раз на день, тож кеш на 30 хв

log = logging.getLogger("nbu-rates")
_cache: dict[tuple, tuple[float, object]] = {}


class NbuError(Exception):
    pass


class CurrencyNotFound(Exception):
    pass


async def _get_json(url: str, params: dict):
    key = (url, tuple(sorted(params.items())))
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as error:
        log.warning("НБУ недоступний: %s", error)
        raise NbuError("Сервіс курсів НБУ тимчасово недоступний. Спробуйте ще раз за хвилину.") from error
    _cache[key] = (time.time(), data)
    return data


async def get_rates() -> list[Rate]:
    """Усі офіційні курси на сьогодні."""
    data = await _get_json(RATES_URL, {"json": ""})
    rates = [Rate(code=item["cc"], name=item["txt"], rate=float(item["rate"]),
                  date=item["exchangedate"]) for item in data]
    return sorted(rates, key=lambda r: r.code)


async def get_rate(code: str) -> Rate:
    for rate in await get_rates():
        if rate.code == code.upper():
            return rate
    raise CurrencyNotFound(code)


async def get_history(code: str, days: int) -> tuple[str, list[HistoryPoint]]:
    """Курс однієї валюти за останні days днів (у порядку дат)."""
    # Дата за київським часом (сервер працює в UTC). НБУ публікує курс на завтра
    # вже вдень, тому беремо і завтрашній день, щоб історія закінчувалась тим самим
    # курсом, що й таблиця «Курси на сьогодні».
    end = datetime.now(KYIV).date() + timedelta(days=1)
    start = end - timedelta(days=days)
    params = {"start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"),
              "valcode": code.lower(), "sort": "exchangedate", "order": "asc", "json": ""}
    data = await _get_json(HISTORY_URL, params)
    if not data:
        raise CurrencyNotFound(code)
    points = [HistoryPoint(date=item["exchangedate"], rate=float(item["rate_per_unit"]))
              for item in data]
    return data[-1].get("txt") or code.upper(), points


def compute_stats(points: list[HistoryPoint]) -> Stats:
    """Статистика ряду курсів: зміна, мінімум, максимум, середнє, волатильність."""
    if not points:
        raise ValueError("Немає даних для статистики.")
    rates = [p.rate for p in points]
    low = min(range(len(rates)), key=rates.__getitem__)
    high = max(range(len(rates)), key=rates.__getitem__)
    changes = [(b - a) / a * 100 for a, b in zip(rates, rates[1:]) if a]
    if len(changes) > 1:
        mean = sum(changes) / len(changes)
        volatility = math.sqrt(sum((c - mean) ** 2 for c in changes) / (len(changes) - 1))
    else:
        volatility = 0.0
    return Stats(
        first=rates[0], last=rates[-1],
        change=round(rates[-1] - rates[0], 4),
        change_percent=round((rates[-1] - rates[0]) / rates[0] * 100, 2) if rates[0] else 0.0,
        minimum=rates[low], minimum_date=points[low].date,
        maximum=rates[high], maximum_date=points[high].date,
        average=round(sum(rates) / len(rates), 4),
        volatility_percent=round(volatility, 3),
    )


def cross_rate(source: Rate | None, target: Rate | None) -> float:
    """Скільки target за 1 source; None означає гривню (UAH)."""
    source_uah = source.rate if source else 1.0
    target_uah = target.rate if target else 1.0
    return source_uah / target_uah
