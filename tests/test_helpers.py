"""Run with:  python tests/test_helpers.py   (no extra packages needed)"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone  # noqa: E402

from helpers import (  # noqa: E402
    REPLY_GROUPS, TopN, clean_candidate, format_duration, pick_mention_reply, pick_reply,
    random_window, score_message, truncate,
)


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


def test_clean_candidate():
    assert clean_candidate("this is a perfectly normal message") == "this is a perfectly normal message"
    assert clean_candidate("  padded message that is long enough  ") == "padded message that is long enough"
    assert clean_candidate("too short") is None
    assert clean_candidate("x" * 601) is None
    assert clean_candidate("!mystats and some more words here") is None
    assert clean_candidate("/something that looks like a slash command") is None
    assert clean_candidate("https://example.com/some/long/link/here") is None
    assert clean_candidate("https://a.example/x https://b.example/y") is None
    assert clean_candidate("hey @everyone look at this message") is None
    assert clean_candidate(None) is None


def test_score_prefers_reactions():
    import random
    rng = random.Random(7)
    popular = score_message(10, 50, rng)
    quiet = max(score_message(0, 300, rng) for _ in range(200))
    assert popular > quiet


def test_random_window_stays_in_range():
    import random
    rng = random.Random(3)
    earliest = datetime(2016, 10, 17, tzinfo=timezone.utc)
    latest = datetime(2026, 10, 4, tzinfo=timezone.utc)
    for _ in range(500):
        start, end = random_window(earliest, latest, 30, rng)
        assert earliest <= start and end <= latest
        assert end - start == timedelta(days=30)


def test_random_window_young_server():
    earliest = datetime(2026, 9, 25, tzinfo=timezone.utc)
    latest = datetime(2026, 10, 4, tzinfo=timezone.utc)
    assert random_window(earliest, latest, 30) == (earliest, latest)


def test_topn_keeps_best_and_never_compares_items():
    top = TopN(3)
    for i, score in enumerate([5, 1, 9, 9, 3, 7, 2]):
        top.push(score, {"id": i})  # dicts are not orderable: would raise if compared
    assert [item["id"] for item in top.best()] in ([2, 3, 5], [3, 2, 5])
    assert len(top) == 3


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
