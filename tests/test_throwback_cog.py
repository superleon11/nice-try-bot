"""Tests cogs/throwback.py end to end with stand-ins for discord.py, the AI and the image API.

Run with:  python tests/test_throwback_cog.py
"""

import asyncio
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---- minimal fake discord ------------------------------------------------------------------
discord = types.ModuleType("discord")
ext = types.ModuleType("discord.ext")
commands = types.ModuleType("discord.ext.commands")
tasks = types.ModuleType("discord.ext.tasks")


class _Loop:
    def __init__(self, f):
        self.f = f

    def change_interval(self, **kw):
        pass

    def start(self):
        pass

    def cancel(self):
        pass

    def before_loop(self, f):
        return f


tasks.loop = lambda **kw: (lambda f: _Loop(f))


class Cog:
    pass


def _passthrough(*a, **k):
    return lambda f: f


class Embed:
    def __init__(self, title=None, description=None, colour=None):
        self.title, self.description, self.fields, self.image = title, description, [], None

    def add_field(self, name, value, inline=True):
        self.fields.append((name, value))

    def set_image(self, url):
        self.image = url


class File:
    def __init__(self, fp, filename=None):
        self.fp, self.filename = fp, filename


class TextChannel:
    def __init__(self, cid=1):
        self.id, self.sent, self.guild = cid, [], types.SimpleNamespace(me=object())
        self.name = "general"

    def is_nsfw(self):
        return True

    def permissions_for(self, me):
        return types.SimpleNamespace(view_channel=True, read_message_history=True)

    async def send(self, **kw):
        self.sent.append(kw)


discord.Embed, discord.File, discord.TextChannel = Embed, File, TextChannel
discord.Colour = types.SimpleNamespace(gold=lambda: 0)
discord.utils = types.SimpleNamespace(escape_markdown=lambda s: s, format_dt=lambda d, f: "DATE")
commands.Cog, commands.Bot, commands.Context = Cog, object, object
commands.command = commands.guild_only = commands.has_permissions = _passthrough
discord.ext, ext.commands, ext.tasks = ext, commands, tasks
sys.modules.update({"discord": discord, "discord.ext": ext,
                    "discord.ext.commands": commands, "discord.ext.tasks": tasks})

os.environ["THROWBACK_CHANNEL_ID"] = "1"
from cogs import throwback  # noqa: E402
from llm import BudgetExceeded, LLMError  # noqa: E402


# ---- fakes ----------------------------------------------------------------------------------
def cand(i, reactions=0):
    msg = types.SimpleNamespace(
        author=types.SimpleNamespace(display_name=f"User{i}"), channel=types.SimpleNamespace(id=1),
        created_at=None, jump_url=f"https://discord.com/x/{i}")
    return types.SimpleNamespace(message=msg, text=f"message number {i} in the pool", reactions=reactions)


class FakeLLM:
    def __init__(self, reply=None, error=None):
        self.reply, self.error = reply, error

    async def complete(self, **kw):
        if self.error:
            raise self.error
        return self.reply(kw)


def pick_message(n):
    def reply(kw):
        for line in kw["prompt"].splitlines():
            if f"message number {n} in the pool" in line:
                num = int(line[1:line.index("]")])
                return json.dumps({"pick": num, "comment": "A fine moment.", "image_prompt": "a cartoon"})
    return reply


class FakeImages:
    def __init__(self, error=None):
        self.error, self.prompts = error, []

    async def generate(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return b"PNG", "png"


def make(llm=None, images=None, pool=None, **flags):
    target = TextChannel(1)
    brain = types.SimpleNamespace(llm=llm, persona="You are a bot.") if llm is not None else None
    imagegen = types.SimpleNamespace(client=images) if images is not None else None
    cogs = {"Brain": brain, "ImageGen": imagegen}
    bot = types.SimpleNamespace(get_channel=lambda cid: target, get_cog=lambda name: cogs.get(name),
                                command_prefix="!")
    cog = throwback.Throwback(bot)
    for k, v in flags.items():
        setattr(cog, k, v)
    pool = pool if pool is not None else [cand(i, reactions=10 - i) for i in range(12)]

    async def fake_find_pool(*a, **k):
        return pool
    throwback.find_pool = fake_find_pool
    return cog, target


def field(embed, name):
    return dict(embed.fields).get(name)


async def _ai_pick_comment_and_image():
    images = FakeImages()
    cog, target = make(FakeLLM(pick_message(7)), images)
    assert await cog.post_throwback() is None
    sent = target.sent[0]
    assert sent["embed"].description == "message number 7 in the pool"
    assert field(sent["embed"], "The bot's verdict") == "A fine moment."
    assert sent["file"].filename == "throwback.png" and sent["embed"].image == "attachment://throwback.png"
    assert images.prompts == ["a cartoon"]


async def _no_ai_falls_back_to_a_top_message_without_comment_or_image():
    cog, target = make()
    assert await cog.post_throwback() is None
    embed = target.sent[0]["embed"]
    assert "file" not in target.sent[0] and field(embed, "The bot's verdict") is None
    assert embed.description in {f"message number {i} in the pool" for i in range(10)}  # top 10 only


async def _budget_exhausted_falls_back():
    cog, target = make(FakeLLM(error=BudgetExceeded("cap")), FakeImages())
    assert await cog.post_throwback() is None
    assert field(target.sent[0]["embed"], "The bot's verdict") is None and "file" not in target.sent[0]


async def _api_error_falls_back():
    cog, target = make(FakeLLM(error=LLMError("HTTP 500")), FakeImages())
    assert await cog.post_throwback() is None
    assert len(target.sent) == 1


async def _garbled_ai_reply_falls_back():
    cog, target = make(FakeLLM(lambda kw: "no idea"), FakeImages())
    assert await cog.post_throwback() is None
    assert field(target.sent[0]["embed"], "The bot's verdict") is None


async def _image_failure_still_posts_text_and_comment():
    cog, target = make(FakeLLM(pick_message(3)), FakeImages(error=LLMError("HTTP 400: moderation")))
    assert await cog.post_throwback() is None
    sent = target.sent[0]
    assert "file" not in sent and sent["embed"].image is None
    assert field(sent["embed"], "The bot's verdict") == "A fine moment."


async def _image_budget_hit_still_posts():
    cog, target = make(FakeLLM(pick_message(3)), FakeImages(error=BudgetExceeded("cap")))
    assert await cog.post_throwback() is None
    assert "file" not in target.sent[0]


async def _switches_turn_features_off():
    images = FakeImages()
    cog, target = make(FakeLLM(pick_message(4)), images, with_image=False)
    await cog.post_throwback()
    assert images.prompts == [] and field(target.sent[0]["embed"], "The bot's verdict") == "A fine moment."
    cog2, target2 = make(FakeLLM(pick_message(4)), FakeImages(), ai_pick=False)
    await cog2.post_throwback()
    assert field(target2.sent[0]["embed"], "The bot's verdict") is None


async def _empty_pool_reports_a_problem():
    cog, target = make(pool=[])
    assert "couldn't find" in await cog.post_throwback()
    assert target.sent == []


def _t(coro):
    def run():
        asyncio.run(coro())
    run.__name__ = coro.__name__.lstrip("_")
    return run


test_ai_pick_comment_and_image = _t(_ai_pick_comment_and_image)
test_no_ai_falls_back = _t(_no_ai_falls_back_to_a_top_message_without_comment_or_image)
test_budget_exhausted_falls_back = _t(_budget_exhausted_falls_back)
test_api_error_falls_back = _t(_api_error_falls_back)
test_garbled_ai_reply_falls_back = _t(_garbled_ai_reply_falls_back)
test_image_failure_still_posts = _t(_image_failure_still_posts_text_and_comment)
test_image_budget_hit_still_posts = _t(_image_budget_hit_still_posts)
test_switches_turn_features_off = _t(_switches_turn_features_off)
test_empty_pool_reports_a_problem = _t(_empty_pool_reports_a_problem)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
