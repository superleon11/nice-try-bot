"""Tests the image request parser, cost maths and spending cap (no network, no database).

Run with:  python tests/test_images.py
"""

import asyncio
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import parse_image_request  # noqa: E402
from images import ImageClient, image_cost_usd  # noqa: E402
from llm import BudgetExceeded, LLMError  # noqa: E402


def test_parser_finds_the_description():
    p = parse_image_request
    assert p("generate me an image of a cat in a wizard hat") == "a cat in a wizard hat"
    assert p("Generate me an image: Dave falling off a bike") == "Dave falling off a bike"
    assert p("can you make a picture of the boys at the pub?") == "the boys at the pub"
    assert p("hey please draw me a picture of a dragon") == "a dragon"
    assert p("create an image showing a haunted toaster") == "a haunted toaster"
    assert p("generate image of sunset") == "sunset"


def test_parser_empty_description_is_empty_string():
    assert parse_image_request("generate me an image") == ""
    assert parse_image_request("Generate me an image of") == ""


def test_parser_ignores_normal_chat():
    p = parse_image_request
    assert p("did you see the image he generated yesterday") is None
    assert p("I made a picture of my dog earlier") is None
    assert p("hello there") is None
    assert p("") is None
    assert p("what image generator should I use") is None


def test_cost_from_usage():
    usage = {"input_tokens": 100, "input_tokens_details": {"text_tokens": 100, "image_tokens": 0},
             "output_tokens": 1710}
    assert abs(image_cost_usd(usage, 0.25) - (100 * 5 + 1710 * 30) / 1e6) < 1e-9
    assert image_cost_usd(None, 0.25) == 0.25
    assert image_cost_usd({}, 0.25) == 0.25


class FakeDB:
    def __init__(self, image_today=0.0, total_today=0.0, total_month=0.0):
        self.image_today, self.total_today, self.total_month = image_today, total_today, total_month
        self.usage = []
        self._plain_calls = 0

    async def llm_spend_since(self, since, purpose=None):
        if purpose == "image":
            return self.image_today
        self._plain_calls += 1   # the client asks for "today" first, then "this month"
        return self.total_today if self._plain_calls % 2 == 1 else self.total_month

    async def record_llm_usage(self, model, purpose, i, o, cost):
        self.usage.append((model, purpose, i, o, cost))


def make(db, post, **kw):
    args = dict(model="gpt-image-2.5-flare", quality="medium", size="1024x1024", reserve_usd=0.25,
                daily_cap=1.0, total_daily_cap=5.0, total_monthly_cap=50.0, post=post)
    args.update(kw)
    return ImageClient(db, "key", **args)


def ok_post(tokens=1710):
    async def post(payload):
        post.payloads.append(payload)
        return {"data": [{"b64_json": base64.b64encode(b"PNGDATA").decode()}], "output_format": "png",
                "usage": {"input_tokens": 50, "input_tokens_details": {"text_tokens": 50, "image_tokens": 0},
                          "output_tokens": tokens}}
    post.payloads = []
    return post


async def _generates_and_records_real_cost():
    db, post = FakeDB(), ok_post()
    data, ext = await make(db, post).generate("a cat")
    assert data == b"PNGDATA" and ext == "png"
    sent = post.payloads[0]
    assert sent["model"] == "gpt-image-2.5-flare" and sent["prompt"] == "a cat"
    assert sent["quality"] == "medium" and sent["size"] == "1024x1024" and sent["n"] == 1
    assert len(db.usage) == 1 and db.usage[0][1] == "image"
    assert abs(db.usage[0][4] - (50 * 5 + 1710 * 30) / 1e6) < 1e-9


async def _image_cap_blocks_before_calling():
    db, post = FakeDB(image_today=0.90), ok_post()   # 0.90 + 0.25 reserve > 1.00
    try:
        await make(db, post).generate("a cat")
        assert False
    except BudgetExceeded as exc:
        assert "image" in str(exc)
    assert post.payloads == [] and db.usage == []


async def _overall_daily_cap_blocks():
    db, post = FakeDB(total_today=4.9), ok_post()
    try:
        await make(db, post).generate("a cat")
        assert False
    except BudgetExceeded as exc:
        assert "daily cap" in str(exc)
    assert post.payloads == []


async def _api_error_costs_nothing():
    async def post(payload):
        raise LLMError("HTTP 400: blocked by moderation", retryable=False)
    db = FakeDB()
    try:
        await make(db, post).generate("a cat")
        assert False
    except LLMError:
        pass
    assert db.usage == []


async def _empty_response_is_an_error_but_still_charged():
    async def post(payload):
        return {"data": [], "usage": {"input_tokens": 10, "output_tokens": 0}}
    db = FakeDB()
    try:
        await make(db, post).generate("a cat")
        assert False
    except LLMError:
        pass
    assert len(db.usage) == 1


def test_generates_and_records_real_cost():
    asyncio.run(_generates_and_records_real_cost())


def test_image_cap_blocks_before_calling():
    asyncio.run(_image_cap_blocks_before_calling())


def test_overall_daily_cap_blocks():
    asyncio.run(_overall_daily_cap_blocks())


def test_monthly_cap_blocks():
    async def go():
        db, post = FakeDB(total_month=49.9), ok_post()
        try:
            await make(db, post).generate("a cat")
            assert False
        except BudgetExceeded as exc:
            assert "monthly" in str(exc)
        assert post.payloads == []
    asyncio.run(go())


def test_api_error_costs_nothing():
    asyncio.run(_api_error_costs_nothing())


def test_empty_response_is_an_error_but_still_charged():
    asyncio.run(_empty_response_is_an_error_but_still_charged())


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
