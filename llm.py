"""Tiny Anthropic Messages API client with a hard spending cap.

Talks to the API over aiohttp (already installed as a dependency of discord.py), so there is no
extra package to install. Every call's token usage and cost is recorded in the database, and a call
is refused up front if its worst-case cost would push today's or this month's spend over the cap.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

# USD per million tokens: (input, output).
# Source: Anthropic's pricing page, checked 2026-10-04. Update these if prices change.
PRICES = {
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-fable-5-1": (10.0, 50.0),
}
# A model we don't know the price of is treated as the most expensive one, so the cap stays safe.
FALLBACK_PRICE = (10.0, 50.0)


class LLMError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class BudgetExceeded(Exception):
    """The daily or monthly spending cap would be exceeded by this call."""


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = PRICES.get(model, FALLBACK_PRICE)
    return (input_tokens * in_price + output_tokens * out_price) / 1_000_000


class LLMClient:
    def __init__(self, db, api_key: str, *, daily_cap: float, monthly_cap: float,
                 post=None, max_concurrent: int = 2):
        self.db = db
        self.api_key = api_key
        self.daily_cap = daily_cap
        self.monthly_cap = monthly_cap
        self._post = post or self._http_post  # injectable for tests
        self._session = None
        self._sem = asyncio.Semaphore(max_concurrent)

    # ---- spend ----------------------------------------------------------

    async def spent_today(self) -> float:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return await self.db.llm_spend_since(start)

    async def spent_this_month(self) -> float:
        start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return await self.db.llm_spend_since(start)

    async def _check_budget(self, model: str, system: str, prompt: str, max_tokens: int) -> None:
        # Worst case for this call: roughly 1 token per 3 characters in, and every output token used.
        worst = cost_usd(model, (len(system) + len(prompt)) // 3 + 50, max_tokens)
        today = await self.spent_today()
        if today + worst > self.daily_cap:
            raise BudgetExceeded(f"daily cap ${self.daily_cap:.2f} reached (spent ${today:.4f} today)")
        month = await self.spent_this_month()
        if month + worst > self.monthly_cap:
            raise BudgetExceeded(f"monthly cap ${self.monthly_cap:.2f} reached (spent ${month:.4f} this month)")

    # ---- the call -------------------------------------------------------

    async def complete(self, *, model: str, system: str, prompt: str, max_tokens: int, purpose: str) -> str:
        """Returns the model's text. Raises BudgetExceeded if over the cap, LLMError on API failure."""
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        async with self._sem:
            await self._check_budget(model, system, prompt, max_tokens)
            data = None
            for attempt in range(3):
                try:
                    data = await self._post(payload)
                    break
                except LLMError as exc:
                    if not exc.retryable or attempt == 2:
                        raise
                    log.warning("LLM call failed (%s), retrying", exc)
                    await asyncio.sleep(2 * (attempt + 1))

        usage = data.get("usage") or {}
        in_tokens = int(usage.get("input_tokens", (len(system) + len(prompt)) // 3))
        out_tokens = int(usage.get("output_tokens", max_tokens))
        cost = cost_usd(model, in_tokens, out_tokens)
        await self.db.record_llm_usage(model, purpose, in_tokens, out_tokens, cost)
        log.info("LLM %s: %s, %d in / %d out tokens, $%.5f", purpose, model, in_tokens, out_tokens, cost)

        blocks = data.get("content") or []
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()

    async def _http_post(self, payload: dict) -> dict:
        import aiohttp  # imported here so the pure logic can be tested without it

        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45))
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }
        try:
            async with self._session.post(API_URL, json=payload, headers=headers) as resp:
                raw = await resp.text()
                status = resp.status
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise LLMError(f"network error: {exc!r}", retryable=True) from exc
        try:
            body = json.loads(raw)
        except ValueError:
            body = {}
        if status != 200:
            message = (body.get("error") or {}).get("message") if isinstance(body, dict) else None
            raise LLMError(f"HTTP {status}: {message or raw[:200]}",
                           retryable=status in (429, 500, 502, 503, 529))
        return body

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
