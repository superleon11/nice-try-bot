"""Tests the spending cap and cost maths in llm.py (no network, no database needed).

Run with:  python tests/test_llm.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm import BudgetExceeded, LLMClient, LLMError, cost_usd  # noqa: E402


class FakeDB:
    """Remembers what was recorded and reports it back as 'spend so far'."""

    def __init__(self, spent_today=0.0, spent_month=None):
        self.spent_today = spent_today
        self.spent_month = spent_today if spent_month is None else spent_month
        self.usage = []
        self._calls = 0

    async def llm_spend_since(self, since):
        # the client asks for "today" first, then "this month"
        self._calls += 1
        return self.spent_today if self._calls % 2 == 1 else self.spent_month

    async def record_llm_usage(self, model, purpose, input_tokens, output_tokens, cost):
        self.usage.append((model, purpose, input_tokens, output_tokens, cost))


def reply(text="hello", in_tokens=100, out_tokens=20):
    async def post(payload):
        post.payloads.append(payload)
        return {"content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": in_tokens, "output_tokens": out_tokens}}
    post.payloads = []
    return post


def client(db, post, daily=0.50, monthly=10.0):
    return LLMClient(db, "key", daily_cap=daily, monthly_cap=monthly, post=post)


HAIKU, SONNET = "claude-haiku-4-5-20251001", "claude-sonnet-5-5"


def test_cost_maths_matches_published_prices():
    assert abs(cost_usd(HAIKU, 1_000_000, 0) - 1.0) < 1e-9
    assert abs(cost_usd(HAIKU, 0, 1_000_000) - 5.0) < 1e-9
    assert abs(cost_usd(SONNET, 1000, 1000) - 0.012) < 1e-9   # 0.002 + 0.010
    assert abs(cost_usd(HAIKU, 1000, 1000) - 0.006) < 1e-9


def test_unknown_model_is_priced_as_most_expensive():
    assert cost_usd("some-future-model", 1_000_000, 0) == 10.0
    assert cost_usd("some-future-model", 0, 1_000_000) == 50.0


async def _normal_call_is_recorded():
    db, post = FakeDB(), reply("a joke", in_tokens=1000, out_tokens=200)
    text = await client(db, post).complete(model=HAIKU, system="s", prompt="p", max_tokens=300, purpose="chat")
    assert text == "a joke"
    assert len(db.usage) == 1
    model, purpose, in_t, out_t, cost = db.usage[0]
    assert (model, purpose, in_t, out_t) == (HAIKU, "chat", 1000, 200)
    assert abs(cost - (0.001 + 0.001)) < 1e-9
    sent = post.payloads[0]
    assert sent["model"] == HAIKU and sent["max_tokens"] == 300 and sent["system"] == "s"
    assert sent["messages"] == [{"role": "user", "content": "p"}]


async def _daily_cap_blocks_the_call_before_it_is_made():
    db, post = FakeDB(spent_today=0.50), reply()
    try:
        await client(db, post, daily=0.50).complete(model=HAIKU, system="s", prompt="p", max_tokens=300, purpose="chat")
        assert False, "should have been refused"
    except BudgetExceeded as exc:
        assert "daily" in str(exc)
    assert post.payloads == [] and db.usage == []   # no API call, no cost


async def _monthly_cap_blocks_even_when_today_is_fine():
    db, post = FakeDB(spent_today=0.01, spent_month=10.0), reply()
    try:
        await client(db, post, daily=0.50, monthly=10.0).complete(
            model=HAIKU, system="s", prompt="p", max_tokens=300, purpose="chat")
        assert False, "should have been refused"
    except BudgetExceeded as exc:
        assert "monthly" in str(exc)
    assert post.payloads == []


async def _worst_case_must_fit_under_the_cap():
    # $0.0001 left today: a 1500-token Haiku answer could cost up to $0.0075, so refuse
    db, post = FakeDB(spent_today=0.4999), reply()
    try:
        await client(db, post, daily=0.50).complete(model=HAIKU, system="s", prompt="p", max_tokens=1500, purpose="memory")
        assert False, "should have been refused"
    except BudgetExceeded:
        pass
    assert post.payloads == []


async def _pricier_model_hits_the_cap_sooner():
    db1, db2 = FakeDB(spent_today=0.495), FakeDB(spent_today=0.495)
    await client(db1, reply()).complete(model=HAIKU, system="s", prompt="p", max_tokens=300, purpose="chat")  # worst ~$0.0015
    try:
        await client(db2, reply()).complete(model="claude-fable-5-1", system="s", prompt="p", max_tokens=300, purpose="chat")
        assert False, "worst case ~$0.015 should not fit in the remaining $0.005"
    except BudgetExceeded:
        pass


async def _api_error_costs_nothing_and_is_raised():
    async def post(payload):
        raise LLMError("HTTP 400: bad request", retryable=False)
    db = FakeDB()
    try:
        await client(db, post).complete(model=HAIKU, system="s", prompt="p", max_tokens=300, purpose="chat")
        assert False
    except LLMError:
        pass
    assert db.usage == []


async def _empty_text_still_records_the_cost():
    db = FakeDB()
    async def post(payload):
        return {"content": [], "usage": {"input_tokens": 50, "output_tokens": 10}}
    text = await client(db, post).complete(model=HAIKU, system="s", prompt="p", max_tokens=300, purpose="chat")
    assert text == "" and len(db.usage) == 1


async def _retries_a_temporary_failure_once_then_succeeds():
    import llm
    calls = {"n": 0}
    async def post(payload):
        calls["n"] += 1
        if calls["n"] == 1:
            raise LLMError("HTTP 529: overloaded", retryable=True)
        return {"content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 1, "output_tokens": 1}}
    real_sleep, llm.asyncio.sleep = llm.asyncio.sleep, (lambda s: real_sleep(0))
    try:
        db = FakeDB()
        assert await client(db, post).complete(model=HAIKU, system="s", prompt="p", max_tokens=10, purpose="chat") == "ok"
    finally:
        llm.asyncio.sleep = real_sleep
    assert calls["n"] == 2 and len(db.usage) == 1   # charged once, for the call that worked


def test_normal_call_is_recorded():
    asyncio.run(_normal_call_is_recorded())


def test_daily_cap_blocks_the_call_before_it_is_made():
    asyncio.run(_daily_cap_blocks_the_call_before_it_is_made())


def test_monthly_cap_blocks_even_when_today_is_fine():
    asyncio.run(_monthly_cap_blocks_even_when_today_is_fine())


def test_worst_case_must_fit_under_the_cap():
    asyncio.run(_worst_case_must_fit_under_the_cap())


def test_pricier_model_hits_the_cap_sooner():
    asyncio.run(_pricier_model_hits_the_cap_sooner())


def test_api_error_costs_nothing_and_is_raised():
    asyncio.run(_api_error_costs_nothing_and_is_raised())


def test_empty_text_still_records_the_cost():
    asyncio.run(_empty_text_still_records_the_cost())


def test_retries_a_temporary_failure_once_then_succeeds():
    asyncio.run(_retries_a_temporary_failure_once_then_succeeds())


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
