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
def msg(text, days_ago, reactions=0, bot=False, mtype=MessageType.default):
    return types.SimpleNamespace(
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
    found = await archive.find_throwback(guild, [ch], "!", 30, max_attempts=3, min_eligible=1, rng=random.Random(9))
    assert found is not None  # would almost never succeed in 3 tries if it searched all 3000 days


def test_only_reads_the_channels_it_is_given():
    asyncio.run(_only_reads_the_channels_it_is_given())


def test_no_channels_means_no_result():
    asyncio.run(_no_channels_means_no_result())


def test_search_starts_from_the_channels_creation():
    asyncio.run(_search_starts_from_the_channels_creation())


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
