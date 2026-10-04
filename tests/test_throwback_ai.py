"""Tests the AI throwback judging (no network, no discord needed).

Run with:  python tests/test_throwback_ai.py
"""

import asyncio
import json
import os
import random
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import Reservoir, format_judge_prompt, parse_judge_reply  # noqa: E402
from llm import BudgetExceeded  # noqa: E402
from throwback_ai import judge_pool  # noqa: E402


def cand(name, text, reactions=0):
    return types.SimpleNamespace(
        message=types.SimpleNamespace(author=types.SimpleNamespace(display_name=name)),
        text=text, reactions=reactions)


class FakeLLM:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    async def complete(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return self.reply(kw) if callable(self.reply) else self.reply


def test_reservoir_is_a_bounded_uniform_sample():
    r = Reservoir(10, random.Random(1))
    for i in range(1000):
        r.add(i)
    assert len(r.items) == 10 and r.seen == 1000
    small = Reservoir(10, random.Random(1))
    for i in range(4):
        small.add(i)
    assert small.items == [0, 1, 2, 3]
    # every item should get picked sometimes
    hits = set()
    for seed in range(200):
        r = Reservoir(3, random.Random(seed))
        for i in range(10):
            r.add(i)
        hits.update(r.items)
    assert hits == set(range(10))


def test_prompt_is_numbered_and_includes_authors_and_reactions():
    p = format_judge_prompt([("Dave", 3, "I once ate a whole cake"), ("Sam", 0, "line one\nline two")])
    assert "[1] (Dave, 3 reactions) I once ate a whole cake" in p
    assert "[2] (Sam) line one line two" in p


def test_parse_valid_and_tolerant_of_extra_text():
    raw = 'Sure! ```json\n{"pick": 2, "comment": "\\"A classic.\\"", "image_prompt": "a cartoon cake"}\n```'
    assert parse_judge_reply(raw, 3) == (1, "A classic.", "a cartoon cake")
    assert parse_judge_reply('{"pick": "3"}', 3) == (2, "", "")


def test_parse_rejects_bad_replies():
    assert parse_judge_reply("", 3) is None
    assert parse_judge_reply("no json here", 3) is None
    assert parse_judge_reply('{"pick": 0}', 3) is None
    assert parse_judge_reply('{"pick": 4}', 3) is None
    assert parse_judge_reply('{"pick": "abc"}', 3) is None
    assert parse_judge_reply('{"comment": "x"}', 3) is None
    assert parse_judge_reply("{broken json}", 3) is None


async def _maps_the_pick_back_to_the_right_message_despite_shuffling():
    pool = [cand(f"User{i}", f"message number {i} in the pool") for i in range(8)]

    def reply(kw):
        # find which number the prompt gave to message 5 and pick that one
        for line in kw["prompt"].splitlines():
            if "message number 5 in the pool" in line:
                n = int(line[1:line.index("]")])
                return json.dumps({"pick": n, "comment": "Peak comedy.", "image_prompt": "a cartoon five"})
    llm = FakeLLM(reply)
    verdict = await judge_pool(llm, "claude-sonnet-5-5", "You are a bot.", pool, random.Random(3))
    assert verdict.candidate.text == "message number 5 in the pool"
    assert verdict.comment == "Peak comedy." and verdict.image_prompt == "a cartoon five"
    call = llm.calls[0]
    assert call["model"] == "claude-sonnet-5-5" and call["purpose"] == "throwback"
    assert call["system"].startswith("You are a bot.")
    assert "Reply with ONLY JSON" in call["system"]


async def _unusable_reply_gives_none():
    pool = [cand("A", "first message here"), cand("B", "second message here")]
    assert await judge_pool(FakeLLM("I like the first one!"), "m", "p", pool) is None


async def _too_small_a_pool_does_not_call_the_api():
    llm = FakeLLM('{"pick": 1}')
    assert await judge_pool(llm, "m", "p", [cand("A", "only message")]) is None
    assert llm.calls == []


async def _budget_errors_propagate_for_the_caller_to_handle():
    pool = [cand("A", "first message here"), cand("B", "second message here")]
    try:
        await judge_pool(FakeLLM(error=BudgetExceeded("cap")), "m", "p", pool)
        assert False
    except BudgetExceeded:
        pass


def test_maps_the_pick_back_to_the_right_message_despite_shuffling():
    asyncio.run(_maps_the_pick_back_to_the_right_message_despite_shuffling())


def test_unusable_reply_gives_none():
    asyncio.run(_unusable_reply_gives_none())


def test_too_small_a_pool_does_not_call_the_api():
    asyncio.run(_too_small_a_pool_does_not_call_the_api())


def test_budget_errors_propagate_for_the_caller_to_handle():
    asyncio.run(_budget_errors_propagate_for_the_caller_to_handle())


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
