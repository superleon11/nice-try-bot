"""Tiny OpenAI image client (gpt-image-2.5-flare by default) with the same kind of hard spending cap.

Talks to POST /v1/images/generations over aiohttp, so no extra package is needed. GPT image models
always return the picture as base64 and report token usage, which is turned into a dollar cost and
recorded in the same llm_usage table as the chat spend.

Worst-case cost of one image isn't published as a fixed number (it is billed per token and depends on
quality and size), so before each call the bot reserves IMAGE_MAX_COST_USD and refuses if that
wouldn't fit under the caps. The real cost recorded afterwards comes from the usage the API reports.
"""

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone

from llm import BudgetExceeded, LLMError

log = logging.getLogger(__name__)

API_URL = "https://api.openai.com/v1/images/generations"

# USD per million tokens for gpt-image-2.5-flare, from OpenAI's model page, checked 2026-10-04:
# text input $5, image input $8, image output $30. Update if prices change.
TEXT_IN, IMAGE_IN, IMAGE_OUT = 5.0, 8.0, 30.0
PURPOSE = "image"


def image_cost_usd(usage: dict | None, fallback: float) -> float:
    """Dollar cost from an images API 'usage' object; `fallback` if it's missing."""
    if not usage:
        return fallback
    details = usage.get("input_tokens_details") or {}
    image_in = int(details.get("image_tokens", 0))
    text_in = int(details.get("text_tokens", max(0, int(usage.get("input_tokens", 0)) - image_in)))
    out = int(usage.get("output_tokens", 0))
    if not (image_in or text_in or out):
        return fallback
    return (text_in * TEXT_IN + image_in * IMAGE_IN + out * IMAGE_OUT) / 1_000_000


class ImageClient:
    def __init__(self, db, api_key: str, *, model: str, quality: str, size: str,
                 reserve_usd: float, daily_cap: float, total_daily_cap: float, total_monthly_cap: float,
                 post=None, max_concurrent: int = 2):
        self.db = db
        self.api_key = api_key
        self.model = model
        self.quality = quality
        self.size = size
        self.reserve = reserve_usd              # assumed worst-case cost of one image
        self.daily_cap = daily_cap              # images only
        self.total_daily_cap = total_daily_cap  # chat + notes + images (the existing LLM caps)
        self.total_monthly_cap = total_monthly_cap
        self._post = post or self._http_post    # injectable for tests
        self._session = None
        self._sem = asyncio.Semaphore(max_concurrent)

    async def _check_budget(self) -> None:
        now = datetime.now(timezone.utc)
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month = day.replace(day=1)
        images_today = await self.db.llm_spend_since(day, PURPOSE)
        if images_today + self.reserve > self.daily_cap:
            raise BudgetExceeded(f"daily image cap ${self.daily_cap:.2f} reached (spent ${images_today:.4f} today)")
        total_today = await self.db.llm_spend_since(day)
        if total_today + self.reserve > self.total_daily_cap:
            raise BudgetExceeded(f"daily cap ${self.total_daily_cap:.2f} reached (spent ${total_today:.4f} today)")
        total_month = await self.db.llm_spend_since(month)
        if total_month + self.reserve > self.total_monthly_cap:
            raise BudgetExceeded(f"monthly cap ${self.total_monthly_cap:.2f} reached (spent ${total_month:.4f} this month)")

    async def generate(self, prompt: str) -> tuple[bytes, str]:
        """Returns (image bytes, file extension). Raises BudgetExceeded or LLMError."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": self.size,
            "quality": self.quality,
            "output_format": "png",
        }
        async with self._sem:
            await self._check_budget()
            data = None
            for attempt in range(2):
                try:
                    data = await self._post(payload)
                    break
                except LLMError as exc:
                    if not exc.retryable or attempt == 1:
                        raise
                    log.warning("Image call failed (%s), retrying", exc)
                    await asyncio.sleep(3)

        cost = image_cost_usd(data.get("usage"), self.reserve)
        usage = data.get("usage") or {}
        await self.db.record_llm_usage(
            self.model, PURPOSE, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)), cost)
        log.info("Image: %s %s %s, $%.4f", self.model, self.quality, self.size, cost)

        items = data.get("data") or []
        b64 = items[0].get("b64_json") if items else None
        if not b64:
            raise LLMError("the API returned no image")
        return base64.b64decode(b64), data.get("output_format") or "png"

    async def _http_post(self, payload: dict) -> dict:
        import aiohttp  # imported here so the pure logic can be tested without it

        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=240))
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
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
            raise LLMError(f"HTTP {status}: {message or raw[:200]}", retryable=status in (429, 500, 502, 503))
        return body

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
