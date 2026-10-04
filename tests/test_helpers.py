"""Run with:  python tests/test_helpers.py   (no extra packages needed)"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import REPLY_GROUPS, format_duration, pick_mention_reply, pick_reply, truncate  # noqa: E402


def test_pick_reply_matches_trigger():
    rng = random.Random(1)
    reply = pick_reply("Thanks a lot!", rng)
    assert reply in dict((frozenset(t), r) for t, r in REPLY_GROUPS)[frozenset({"thanks", "thx", "thank", "ty"})]


def test_pick_reply_is_case_and_punctuation_insensitive():
    assert pick_reply("LOL!!!", random.Random(2)) is not None


def test_pick_reply_no_match():
    assert pick_reply("the quick brown fox", random.Random(3)) is None
    assert pick_reply("", random.Random(3)) is None
    assert pick_reply("!!! ???", random.Random(3)) is None


def test_no_substring_false_positives():
    # "nice" is a trigger but "nicest"/"venice" must not match; "ty" must not match "party"
    assert pick_reply("venice party", random.Random(4)) is None


def test_mention_reply():
    assert pick_mention_reply(random.Random(5))


def test_format_duration():
    assert format_duration(0) == "0m"
    assert format_duration(59) == "0m"
    assert format_duration(3600 + 5 * 60) == "1h 05m"
    assert format_duration(-10) == "0m"


def test_truncate():
    assert truncate("hello", 10) == "hello"
    assert len(truncate("x" * 100, 10)) == 10
    assert truncate("x" * 100, 10).endswith("…")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
