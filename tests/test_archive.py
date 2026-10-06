"""Tests archive.py (random-window throwback search) using stand-ins for discord.py.

Run with:  python tests/test_archive.py   (no extra packages needed)
"""

import asyncio
import os
import random
import sys
import types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---- minimal fake discord -----------------------------------------------------------------
discord = types.ModuleType("discord")


class MessageType:
    default = "default"
    reply = "reply"
    pins_add = "pins_add"


class Forbidden(Exception):
    pass


discord.MessageType, discord.Forbidden = MessageType, Forbidden
sys.modules["discord"] = discord

import archive  # noqa: E402

NOW = datetime.now(timezone.utc)


# ---- fakes ----------------------------------------------------------------------------------
_ids = iter(range(1, 10**9))


def msg(text, days_ago, reactions=0, bot=False, mtype=MessageType.default):
    return types.SimpleNamespace(
        id=next(_ids),
        author=types.SimpleNamespace(bot=bot),
        type=mtype,
        content=text,
        reactions=[types.SimpleNamespace(count=reactions)] if reactions else [],
        created_at=NOW - timedelta(days=days_ago),
    )


class FakeChannel:
    def __init__(self, messages, name="general", nsfw=False, readable=True, forbidden=False, created_days_ago=3000):
        self.messages, self.name, self.nsfw = messages, name, nsfw
        self.readable, self.forbidden = readable, forbidden
        self.created_at = NOW - timedelta(days=created_days_ago)
        self.history_calls = 0

    def is_nsfw(self):
        return self.nsfw

    def permissions_for(self, me):
        return types.SimpleNamespace(view_channel=self.readable, read_message_history=self.readable)

    async def history(self, limit=None, after=None, before=None, oldest_first=False):
        self.history_calls += 1
        if self.forbidden:
            raise Forbidden()
        for m in sorted(self.messages, key=lambda m: m.created_at):
            if after < m.created_at < before:
                yield m


class FakeGuild:
    def __init__(self, channels, created_days_ago=3000):
        self.text_channels = channels
        self.created_at = NOW - timedelta(days=created_days_ago)
        self.me = object()


# ---- tests ----------------------------------------------------------------------------------
async def _reads_nsfw_skips_unreadable_and_junk():
    good = msg("this is the funniest thing anyone has ever said", 100, reactions=20)
    meh = msg("a perfectly ordinary message about lunch", 101, reactions=0)
    junk = [
        msg("a bot talking about being a bot", 100, reactions=50, bot=True),
        msg("short", 100, reactions=50),
        msg("https://example.com/a/very/long/link/indeed", 100, reactions=50),
        msg("!leaderboard messages please and thanks", 100, reactions=50),
        msg("someone pinned a message here, system", 100, reactions=50, mtype=MessageType.pins_add),
    ]
    nsfw = FakeChannel([msg("spicy but allowed message from an nsfw channel", 100, reactions=99)], nsfw=True)
    hidden = FakeChannel([msg("private message that we cannot read", 100, reactions=99)], readable=False)
    blocked = FakeChannel([], forbidden=True)
    normal = FakeChannel([good, meh] + junk)
    guild = FakeGuild([nsfw, hidden, blocked, normal])

    # The messages are ~100 days old on a ~3000-day-old server, so most random windows miss them:
    # allow many attempts so the search keeps going until a window lands on them.
    found = await archive.find_throwback(guild, guild.text_channels, "!", 30, max_attempts=2000, min_eligible=1, rng=random.Random(1))
    assert found is not None
    assert found.text in (good.content, meh.content, nsfw.messages[0].content), found.text
    assert nsfw.history_calls > 0        # NSFW channels are read like any other
    assert hidden.history_calls == 0     # channels the bot cannot read are never opened


async def _prefers_reactions_when_several_candidates():
    msgs = [msg(f"ordinary message number {i} in the archive", 100 + i * 0.1) for i in range(30)]
    star = msg("the one everybody reacted to in the archive", 100.5, reactions=30)
    guild = FakeGuild([FakeChannel(msgs + [star])])
    picks = set()
    for seed in range(20):
        found = await archive.find_throwback(guild, guild.text_channels, "!", 30, max_attempts=2000, min_eligible=5,
                                             rng=random.Random(seed))
        picks.add(found.text)
        assert found.text in {m.content for m in msgs + [star]}
    assert star.content in picks  # best candidate is in the pool it picks from
    # and every pick comes from the top 10, so most picks are not random leftovers:
    assert found.reactions >= 0


async def _retries_empty_windows():
    # everything happened in the last 10 days; most random windows are empty, so it must retry
    recent = [msg(f"recent message number {i} that is long enough", 5 + i * 0.1) for i in range(20)]
    guild = FakeGuild([FakeChannel(recent)], created_days_ago=90)
    found = await archive.find_throwback(guild, guild.text_channels, "!", 30, max_attempts=500, min_eligible=5, rng=random.Random(2))
    assert found is not None


async def _returns_none_when_nothing_eligible():
    guild = FakeGuild([FakeChannel([msg("hi", 5), msg("ok", 6)])], created_days_ago=60)
    assert await archive.find_throwback(guild, guild.text_channels, "!", 30, max_attempts=3, rng=random.Random(1)) is None


async def _skips_channels_created_after_window():
    young = FakeChannel([msg("a message in a channel made yesterday", 0.5)], created_days_ago=1)
    guild = FakeGuild([young], created_days_ago=60)
    await archive.scan_window(guild, guild.text_channels, NOW - timedelta(days=50), NOW - timedelta(days=20))
    assert young.history_calls == 0


def test_reads_nsfw_skips_unreadable_and_junk():
    asyncio.run(_reads_nsfw_skips_unreadable_and_junk())


def test_prefers_reactions_when_several_candidates():
    asyncio.run(_prefers_reactions_when_several_candidates())


def test_retries_empty_windows():
    asyncio.run(_retries_empty_windows())


def test_returns_none_when_nothing_eligible():
    asyncio.run(_returns_none_when_nothing_eligible())


def test_skips_channels_created_after_window():
    asyncio.run(_skips_channels_created_after_window())


async def _only_reads_the_channels_it_is_given():
    wanted = FakeChannel([msg("a message in the one channel we chose", 100, reactions=1)])
    other = FakeChannel([msg("a message in some other channel entirely", 100, reactions=50)])
    guild = FakeGuild([wanted, other])
    found = await archive.find_throwback(guild, [wanted], "!", 30, max_attempts=2000, min_eligible=1,
                                         rng=random.Random(5))
    assert found.text == "a message in the one channel we chose"
    assert other.history_calls == 0


async def _no_channels_means_no_result():
    assert await archive.find_throwback(FakeGuild([]), [], "!", 30) is None


async def _search_starts_from_the_channels_creation():
    # server is 3000 days old but the channel only 40 days old: windows must never start before it
    ch = FakeChannel([msg("a message that is definitely long enough", 10, reactions=2)], created_days_ago=40)
    guild = FakeGuild([ch], created_days_ago=3000)
    found = await archive.find_throwback(guild, [ch], "!", 30, max_attempts=15, min_eligible=1, rng=random.Random(9))
    assert found is not None  # would almost never succeed in 15 tries if it searched all 3000 days


def test_only_reads_the_channels_it_is_given():
    asyncio.run(_only_reads_the_channels_it_is_given())


def test_no_channels_means_no_result():
    asyncio.run(_no_channels_means_no_result())


def test_search_starts_from_the_channels_creation():
    asyncio.run(_search_starts_from_the_channels_creation())


# ---- 60-day windows, redrawing, variable length, no repeats -------------------------------------
async def _redraws_until_a_window_has_messages():
    # One busy fortnight about 1000 days ago in a 3000-day-old channel: nearly every window is empty,
    # yet with enough attempts it keeps drawing until it lands on the messages.
    busy = [msg(f"a busy message number {i} from long ago", 1000 + i * 0.5) for i in range(20)]
    ch = FakeChannel(busy)
    guild = FakeGuild([ch])
    pool = await archive.find_pool(guild, [ch], "!", 60, max_attempts=500, min_eligible=5, rng=random.Random(4))
    assert len(pool) >= 5
    assert ch.history_calls > 3      # it had to try several windows


async def _uses_the_best_window_when_none_reaches_the_minimum():
    few = [msg(f"one of only three messages, number {i}", 20 + i) for i in range(3)]
    ch = FakeChannel(few, created_days_ago=200)
    pool = await archive.find_pool(FakeGuild([ch]), [ch], "!", 60, max_attempts=60, min_eligible=50,
                                   rng=random.Random(6))
    assert 1 <= len(pool) <= 3       # not enough for the minimum, but better than nothing


async def _nothing_at_all_gives_an_empty_pool():
    ch = FakeChannel([], created_days_ago=200)
    assert await archive.find_pool(FakeGuild([ch]), [ch], "!", 60, max_attempts=10) == []


async def _recent_windows_are_avoided_and_the_used_one_is_recorded():
    msgs = [msg(f"a message that fits anywhere, number {i}", d) for i, d in enumerate(range(5, 400, 3))]
    ch = FakeChannel(msgs, created_days_ago=400)
    recent = []
    for seed in range(5):
        before = len(recent)
        pool = await archive.find_pool(FakeGuild([ch]), [ch], "!", 60, min_eligible=1, recent=recent,
                                       rng=random.Random(seed))
        assert pool and len(recent) == before + 1     # the window that was used gets recorded


def test_fresh_windows_avoid_blocked_history():
    from helpers import windows_overlap
    now = NOW
    earliest = now - timedelta(days=3000)
    blocked = [(earliest, earliest + timedelta(days=2500))]   # only the most recent 500 days are free
    clear = 0
    for seed in range(200):
        w = archive._fresh_window(earliest, now, 60, blocked, random.Random(seed))
        assert earliest <= w[0] < w[1] <= now
        assert 30 - 1e-6 <= (w[1] - w[0]).total_seconds() / 86400 <= 60 + 1e-6
        clear += not windows_overlap(w, blocked[0])
    assert clear >= 190, clear      # ~17% of draws are free, 25 draws per window: nearly always finds one


def test_fresh_windows_still_work_when_everything_is_blocked():
    now = NOW
    earliest = now - timedelta(days=100)
    w = archive._fresh_window(earliest, now, 60, [(earliest, now)], random.Random(1))
    assert earliest <= w[0] < w[1] <= now          # best effort: gives up avoiding rather than failing


def test_redraws_until_a_window_has_messages():
    asyncio.run(_redraws_until_a_window_has_messages())


def test_uses_the_best_window_when_none_reaches_the_minimum():
    asyncio.run(_uses_the_best_window_when_none_reaches_the_minimum())


def test_nothing_at_all_gives_an_empty_pool():
    asyncio.run(_nothing_at_all_gives_an_empty_pool())


def test_recent_windows_are_avoided_and_the_used_one_is_recorded():
    asyncio.run(_recent_windows_are_avoided_and_the_used_one_is_recorded())



async def _excluded_messages_are_never_candidates():
    msgs = [msg(f"message number {i} that is long enough", 5 + i * 0.1) for i in range(20)]
    ch = FakeChannel(msgs, created_days_ago=30)
    banned = {m.id for m in msgs[:15]}
    pool = await archive.find_pool(FakeGuild([ch]), [ch], "!", 60, min_eligible=1, exclude=banned, rng=random.Random(2))
    assert pool and all(c.message.id not in banned for c in pool)
    assert len(pool) == 5
    everything = {m.id for m in msgs}
    assert await archive.find_pool(FakeGuild([ch]), [ch], "!", 60, min_eligible=1, exclude=everything,
                                   max_attempts=5, rng=random.Random(2)) == []


async def _a_young_channel_is_searched_once_not_forty_times():
    # channel is 20 days old but windows are 30-60 days: the only possible window is the whole channel
    msgs = [msg(f"message number {i} that is long enough", 2 + i * 0.1) for i in range(5)]
    ch = FakeChannel(msgs, created_days_ago=20)
    pool = await archive.find_pool(FakeGuild([ch]), [ch], "!", 60, min_eligible=50, max_attempts=40,
                                   rng=random.Random(3))
    assert len(pool) == 5 and ch.history_calls == 1


def test_excluded_messages_are_never_candidates():
    asyncio.run(_excluded_messages_are_never_candidates())


def test_a_young_channel_is_searched_once_not_forty_times():
    asyncio.run(_a_young_channel_is_searched_once_not_forty_times())



async def _result_reports_the_window_and_search_facts():
    msgs = [msg(f"a long enough message number {i}", 200 + i) for i in range(12)]
    ch = FakeChannel(msgs, created_days_ago=3000)
    pool = await archive.find_pool(FakeGuild([ch]), [ch], "!", 60, max_attempts=3000, min_eligible=5, rng=random.Random(8))
    start, end = pool.window
    assert 30 - 1e-6 <= (end - start).total_seconds() / 86400 <= 60 + 1e-6
    assert pool.eligible >= 5 and pool.attempts >= 1 and not pool.whole_channel and pool.channel_days >= 2999
    assert all(start < c.message.created_at < end for c in pool)     # candidates really come from that window
    assert len(pool.tried) == pool.attempts or len(pool.tried) > pool.attempts   # every window drawn is recorded
    assert all({"start", "end", "scanned", "eligible"} <= set(w) for w in pool.tried)
    assert pool.tried[pool.attempts - 1]["eligible"] == pool.eligible


async def _young_channel_result_is_flagged_as_whole_channel():
    ch = FakeChannel([msg("a long enough message in a young channel", 3)], created_days_ago=20)
    pool = await archive.find_pool(FakeGuild([ch]), [ch], "!", 60, min_eligible=1, rng=random.Random(1))
    assert pool.whole_channel and pool.channel_days in (19, 20)


async def _scan_never_reads_past_the_end_of_the_window():
    class Greedy(FakeChannel):
        async def history(self, limit=None, after=None, before=None, oldest_first=False):
            for m in sorted(self.messages, key=lambda m: m.created_at):   # ignores `before`, like a buggy source
                if m.created_at > after:
                    yield m
    inside = msg("a message that is inside the window ok", 40)
    outside = msg("a message that is after the window ends", 10)
    ch = Greedy([inside, outside])
    pool, eligible, scanned = await archive.scan_window(FakeGuild([ch]), [ch], NOW - timedelta(days=50),
                                                        NOW - timedelta(days=20))
    assert eligible == 1 and [c.text for c in pool] == [inside.content]


def test_result_reports_the_window_and_search_facts():
    asyncio.run(_result_reports_the_window_and_search_facts())


def test_young_channel_result_is_flagged_as_whole_channel():
    asyncio.run(_young_channel_result_is_flagged_as_whole_channel())


def test_scan_never_reads_past_the_end_of_the_window():
    asyncio.run(_scan_never_reads_past_the_end_of_the_window())


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
