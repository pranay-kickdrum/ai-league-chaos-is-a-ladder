"""ExchangeRate API wrapper."""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.services.cache import cache_get, cache_set
from app.tools.resilience import resilient_api_call

logger = logging.getLogger(__name__)
settings = get_settings()


@resilient_api_call("exchangerate")
async def _fetch_rates(base: str) -> dict[str, float]:
    url = f"https://open.er-api.com/v6/latest/{base}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json().get("rates", {})


async def get_exchange_rate(from_currency: str, to_currency: str) -> float:
    """Get exchange rate between two currencies."""
    if from_currency == to_currency:
        return 1.0

    cached = cache_get("exchange", from_c=from_currency, to_c=to_currency)
    if cached is not None:
        return cached

    try:
        rates = await _fetch_rates(from_currency)
        rate = rates.get(to_currency, 1.0)
        cache_set("exchange", rate, from_c=from_currency, to_c=to_currency)
        return rate
    except Exception as e:
        logger.error("Exchange rate error: %s", e)
        return 1.0


async def convert_amount(amount: float, from_currency: str, to_currency: str) -> float:
    """Convert an amount between currencies."""
    rate = await get_exchange_rate(from_currency, to_currency)
    return round(amount * rate, 2)
