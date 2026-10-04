"""Tests cogs/reactions.py with stand-ins for discord.py and the AI.

Run with:  python tests/test_reactions.py
"""

import asyncio
import os
import random
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---- minimal fake discord ------------------------------------------------------------------
discord = types.ModuleType("discord")
ext = types.ModuleType("discord.ext")
commands = types.ModuleType("discord.ext.commands")


class HTTPException(Exception):
    pass


class Forbidden(HTTPException):
    pass


class NotFound(HTTPException):
    pass


class Cog:
    @staticmethod
    def listener(*a, **k):
        return lambda f: f


discord.Message, discord.HTTPException, discord.Forbidden, discord.NotFound = object, HTTPException, Forbidden, NotFound
commands.Cog, commands.Bot = Cog, object
discord.ext, ext.commands = ext, commands
sys.modules.update({"discord": discord, "discord.ext": ext, "discord.ext.commands": commands})

os.environ["REACT_CHANCE"] = "1"
os.environ["REACT_COOLDOWN_SECONDS"] = "0"
from cogs import reactions  # noqa: E402
from helpers import DEFAULT_REACTIONS, choose_random_emojis, parse_emoji_reply  # noqa: E402
from llm import BudgetExceeded, LLMError  # noqa: E402

BOT = types.SimpleNamespace(id=99)


class FakeLLM:
    def __init__(self, reply="😂 🔥", error=None):
        self.reply, self.error, self.calls = reply, error, []

    async def complete(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return self.reply


class FakeMessage:
    def __init__(self, text="that was a hilarious thing to say", bot=False, channel=1, mentions=(), guild=True,
                 custom=(), errors=None):
        self.author = types.SimpleNamespace(bot=bot)
        self.content = self.clean_content = text
        self.channel = types.SimpleNamespace(id=channel, name="general")
        self.guild = types.SimpleNamespace(emojis=list(custom)) if guild else None
        self.mentions = list(mentions)
        self.added, self.errors = [], errors or {}

    async def add_reaction(self, emoji):
        err = self.errors.get(emoji)
        if err:
            raise err
        self.added.append(emoji)


def make(llm=None, **attrs):
    brain = types.SimpleNamespace(llm=llm) if llm is not None else None
    bot = types.SimpleNamespace(command_prefix="!", user=BOT, get_cog=lambda n: brain if n == "Brain" else None)
    cog = reactions.Reactions(bot)
    for k, v in attrs.items():
        setattr(cog, k, v)
    return cog


def run(cog, msg):
    asyncio.run(cog.on_message(msg))
    return msg.added


def test_parse_emoji_reply():
    assert parse_emoji_reply("😂 🔥 💀 👀") == ["😂", "🔥", "💀"]
    assert parse_emoji_reply("Sure! 😂 haha 🔥") == ["😂", "🔥"]
    assert parse_emoji_reply("😂 😂 😂") == ["😂"]
    assert parse_emoji_reply("no emoji here") == []
    assert parse_emoji_reply("") == []
    assert parse_emoji_reply("1️⃣") == []


def test_random_choice_uses_pools_sensibly():
    rng = random.Random(1)
    assert choose_random_emojis([], [], rng) == []
    assert all(e in ["a", "b"] for _ in range(50) for e in choose_random_emojis(["a", "b"], [], rng))
    assert all(e == "X" for _ in range(50) for e in choose_random_emojis([], ["X"], rng))
    seen = set()
    for s in range(300):
        seen.update(choose_random_emojis(["a"], ["X"], random.Random(s)))
    assert seen == {"a", "X"}                       # mixes in custom emoji
    counts = {len(choose_random_emojis(["a", "b", "c"], [], random.Random(s))) for s in range(200)}
    assert counts == {1, 2}                          # usually one, sometimes two


def test_ai_picks_the_emoji():
    llm = FakeLLM("😂 🔥")
    msg = FakeMessage()
    assert run(make(llm), msg) == ["😂", "🔥"]
    assert llm.calls[0]["purpose"] == "reaction" and llm.calls[0]["max_tokens"] == 20
    assert llm.calls[0]["prompt"] == "that was a hilarious thing to say"


def test_unusable_ai_reply_or_budget_or_error_falls_back_to_random():
    for llm in (FakeLLM("haha nice one"), FakeLLM(error=BudgetExceeded("cap")), FakeLLM(error=LLMError("500"))):
        added = run(make(llm), FakeMessage())
        assert added and all(e in DEFAULT_REACTIONS for e in added)


def test_without_ai_it_reacts_randomly_and_can_use_server_emoji():
    assert all(e in DEFAULT_REACTIONS for e in run(make(), FakeMessage()))
    custom = ["<server emoji>"]
    seen = set()
    for _ in range(200):
        seen.update(run(make(), FakeMessage(custom=custom)))
    assert "<server emoji>" in seen
    cog = make(use_server_emojis=False)
    assert all(e in DEFAULT_REACTIONS for _ in range(50) for e in run(cog, FakeMessage(custom=custom)))


def test_ai_can_be_switched_off_and_short_messages_skip_it():
    llm = FakeLLM()
    run(make(llm, use_ai=False), FakeMessage())
    run(make(llm), FakeMessage("ok"))
    assert llm.calls == []


def test_skips_bots_commands_dms_and_messages_to_the_bot():
    cog = make()
    assert run(cog, FakeMessage(bot=True)) == []
    assert run(cog, FakeMessage("!stats please")) == []
    assert run(cog, FakeMessage(guild=False)) == []
    assert run(cog, FakeMessage(mentions=[BOT])) == []
    assert run(cog, FakeMessage(mentions=[types.SimpleNamespace(id=5)])) != []   # mentioning someone else is fine


def test_chance_zero_disables_and_channel_whitelist_applies():
    assert run(make(chance=0.0), FakeMessage()) == []
    cog = make(channels={7})
    assert run(cog, FakeMessage(channel=8)) == []
    assert run(cog, FakeMessage(channel=7)) != []


def test_cooldown_is_per_channel():
    cog = make(cooldown=60.0)
    assert run(cog, FakeMessage(channel=1)) != []
    assert run(cog, FakeMessage(channel=1)) == []      # too soon in the same channel
    assert run(cog, FakeMessage(channel=2)) != []      # other channel is unaffected


def test_missing_permission_stops_quietly_and_only_warns_once():
    cog = make(pool=["A", "B"], use_server_emojis=False)
    msg = FakeMessage(errors={"A": Forbidden(), "B": Forbidden()})
    assert run(cog, msg) == [] and cog._warned_permissions
    assert run(cog, FakeMessage(errors={"A": Forbidden(), "B": Forbidden()})) == []   # no crash


def test_unknown_emoji_or_deleted_message_does_not_crash():
    cog = make(pool=["A"], use_server_emojis=False)
    assert run(cog, FakeMessage(errors={"A": NotFound()})) == []
    assert run(cog, FakeMessage(errors={"A": HTTPException()})) == []


def test_custom_emoji_list_from_env():
    os.environ["REACT_EMOJIS"] = "🐐, <:pog:123456789>  🧀"
    try:
        assert make().pool == ["🐐", "<:pog:123456789>", "🧀"]
    finally:
        del os.environ["REACT_EMOJIS"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
