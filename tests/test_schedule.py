"""Tests the random daily scheduling (10am-3pm UK time by default).

Run with:  python tests/test_schedule.py
"""

import asyncio
import os
import random
import sys
import types
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import test_throwback_cog as tc  # noqa: E402  (installs the fake discord modules)
from helpers import pick_run_time  # noqa: E402

LON = ZoneInfo("Europe/London")
UTC = timezone.utc


def at(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=LON)


def local(dt):
    return dt.astimezone(LON)


def test_always_inside_the_window_and_in_the_future():
    now = at(2026, 10, 5, 6)   # BST, early morning
    times = [pick_run_time(now, LON, 10, 15, False, random.Random(s)) for s in range(300)]
    assert all(t > now.astimezone(UTC) for t in times)
    assert all(local(t).date() == now.date() for t in times)
    assert all(10 <= local(t).hour < 15 for t in times)
    assert all(t.tzinfo is not None and t.utcoffset() == timedelta(0) for t in times)
    # genuinely spread out across the window
    assert min(local(t).hour for t in times) == 10 and max(local(t).hour for t in times) == 14


def test_summer_and_winter_both_mean_uk_local_time():
    summer = pick_run_time(at(2026, 7, 1, 1), LON, 10, 15, False, random.Random(1))
    winter = pick_run_time(at(2026, 12, 1, 1), LON, 10, 15, False, random.Random(1))
    assert 9 <= summer.hour < 14      # 10:00-15:00 BST is 09:00-14:00 UTC
    assert 10 <= winter.hour < 15     # GMT: same as UTC


def test_clocks_going_back_day_is_still_10_to_3_local():
    now = at(2026, 10, 24, 20)        # the evening before clocks go back (25 Oct 2026)
    for s in range(100):
        t = local(pick_run_time(now, LON, 10, 15, False, random.Random(s)))
        assert t.date().isoformat() == "2026-10-25" and 10 <= t.hour < 15


def test_after_the_window_means_tomorrow():
    now = at(2026, 10, 5, 16)
    for s in range(50):
        t = local(pick_run_time(now, LON, 10, 15, False, random.Random(s)))
        assert t.date().isoformat() == "2026-10-06" and 10 <= t.hour < 15


def test_already_posted_today_means_tomorrow_even_before_the_window():
    now = at(2026, 10, 5, 8)
    for s in range(50):
        assert local(pick_run_time(now, LON, 10, 15, True, random.Random(s))).date().isoformat() == "2026-10-06"


def test_restart_mid_window_picks_a_time_between_now_and_the_end():
    now = at(2026, 10, 5, 12, 30)
    for s in range(100):
        t = local(pick_run_time(now, LON, 10, 15, False, random.Random(s)))
        assert at(2026, 10, 5, 12, 30) <= t < at(2026, 10, 5, 15) and t.date() == now.date()


def test_days_differ():
    picks = {local(pick_run_time(at(2026, 10, 5, 16), LON, 10, 15, False, random.Random(s))).strftime("%H:%M")
            for s in range(20)}
    assert len(picks) > 10


def test_bad_hours_are_rejected():
    try:
        pick_run_time(at(2026, 10, 5, 8), LON, 15, 10, False)
        assert False
    except ValueError:
        pass


# ---- the cog's defaults -------------------------------------------------------------------------
def test_defaults_are_scan_10_post_11_to_15_london():
    bot = types.SimpleNamespace(get_channel=lambda cid: None, get_cog=lambda n: None, command_prefix="!",
                                user=types.SimpleNamespace(id=99))
    cog = tc.throwback.Throwback(bot)
    assert (cog.scan_hour, cog.start_hour, cog.end_hour) == (10, 11, 15) and str(cog.tz) == "Europe/London"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and k != "test_throwback_cog"]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
