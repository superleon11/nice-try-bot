"""Tests the scheduling logic of cogs/soundboard.py with stand-ins for discord.py.

Run with:  python tests/test_soundboard_logic.py   (no extra packages needed)
This checks OUR logic (timers, cancelling, join/play/leave order). It cannot check discord.py itself.
"""

import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---- minimal fake discord / discord.ext.commands -----------------------------------------
discord = types.ModuleType("discord")
ext = types.ModuleType("discord.ext")
commands = types.ModuleType("discord.ext.commands")


class VoiceChannel:  # the real cog does isinstance(channel, discord.VoiceChannel)
    pass


class HTTPException(Exception):
    pass


class Cog:
    @staticmethod
    def listener(*a, **k):
        return lambda f: f


def _passthrough(*a, **k):
    return lambda f: f


discord.VoiceChannel, discord.HTTPException = VoiceChannel, HTTPException
discord.Guild = discord.Member = discord.VoiceState = object
commands.Cog, commands.Bot, commands.Context = Cog, object, object
commands.command = commands.guild_only = commands.has_permissions = _passthrough
discord.ext, ext.commands = ext, commands
sys.modules.update({"discord": discord, "discord.ext": ext, "discord.ext.commands": commands})

from cogs.soundboard import SoundVisits  # noqa: E402


# ---- fakes ---------------------------------------------------------------------------------
class FakeVC:
    def __init__(self, log):
        self.log = log

    async def disconnect(self, force=False):
        self.log.append("disconnect")


class FakeSound:
    name = "airhorn"
    available = True


class FakeGuild:
    id = 1
    voice_client = None
    me = object()
    soundboard_sounds = [FakeSound()]


class FakeChannel(VoiceChannel):
    def __init__(self, humans):
        self.id = 10
        self.name = "General"
        self.guild = FakeGuild()
        self.members = [types.SimpleNamespace(bot=False) for _ in range(humans)]
        self.events = []

    def permissions_for(self, me):
        return types.SimpleNamespace(connect=True, speak=True)

    async def connect(self, timeout=60.0, reconnect=True):
        self.events.append("connect")
        return FakeVC(self.events)

    async def send_sound(self, sound):
        self.events.append("send")


def make_cog(**overrides):
    bot = types.SimpleNamespace(voice_clients=[], guilds=[])
    cog = SoundVisits(bot)
    cog.min_call = 0.05
    cog.min_delay = cog.max_delay = 0.05
    cog.settle_seconds = 0.01
    cog.listen_seconds = 0.01
    for k, v in overrides.items():
        setattr(cog, k, v)
    return cog


# ---- tests ---------------------------------------------------------------------------------
async def _visit_happens_in_order():
    cog, ch = make_cog(), FakeChannel(humans=2)
    cog._refresh(ch)
    await asyncio.sleep(0.5)
    assert ch.events[:3] == ["connect", "send", "disconnect"], ch.events
    # call still going -> it keeps coming back
    assert ch.events.count("send") >= 2, ch.events
    cog._refresh(FakeChannel(humans=0))  # different object, same id=10, now empty
    ch.members.clear()
    cog._refresh(ch)
    assert ch.id not in cog.tasks
    await asyncio.sleep(0.01)


async def _too_few_people_never_visits():
    cog, ch = make_cog(), FakeChannel(humans=1)  # default min_humans is 2
    cog._refresh(ch)
    await asyncio.sleep(0.3)
    assert ch.events == [] and ch.id not in cog.tasks


async def _call_must_last_min_call_first():
    cog, ch = make_cog(min_call=0.3), FakeChannel(humans=2)
    cog._refresh(ch)
    await asyncio.sleep(0.15)
    assert ch.events == []  # not yet: call hasn't lasted long enough
    ch.members.clear()
    cog._refresh(ch)  # everyone left: reset
    await asyncio.sleep(0.4)
    assert ch.events == []


async def _cancel_mid_visit_still_leaves():
    cog, ch = make_cog(listen_seconds=5), FakeChannel(humans=2)
    cog._refresh(ch)
    await asyncio.sleep(0.4)  # now inside the 5s "listen" wait
    assert ch.events == ["connect", "send"], ch.events
    ch.members.clear()
    cog._refresh(ch)  # everyone leaves mid-visit
    await asyncio.sleep(0.05)
    assert ch.events[-1] == "disconnect", ch.events


async def _skips_if_already_in_voice():
    cog, ch = make_cog(), FakeChannel(humans=2)
    ch.guild.voice_client = object()
    assert await cog.visit(ch) is False
    assert ch.events == []


async def _falls_back_to_default_sounds():
    cog, ch = make_cog(), FakeChannel(humans=2)
    ch.guild.soundboard_sounds = []  # no custom sounds

    async def defaults():
        return [FakeSound()]

    cog.bot.fetch_soundboard_default_sounds = defaults
    assert await cog.visit(ch) is True
    assert ch.events == ["connect", "send", "disconnect"]


def test_visit_happens_in_order():
    asyncio.run(_visit_happens_in_order())


def test_too_few_people_never_visits():
    asyncio.run(_too_few_people_never_visits())


def test_call_must_last_min_call_first():
    asyncio.run(_call_must_last_min_call_first())


def test_cancel_mid_visit_still_leaves():
    asyncio.run(_cancel_mid_visit_still_leaves())


def test_skips_if_already_in_voice():
    asyncio.run(_skips_if_already_in_voice())


def test_falls_back_to_default_sounds():
    asyncio.run(_falls_back_to_default_sounds())


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
