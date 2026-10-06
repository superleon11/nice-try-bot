"""Tests cogs/throwback.py end to end with stand-ins for discord.py, the AI and the image API.

Run with:  python tests/test_throwback_cog.py
"""

import asyncio
import json
import os
import sys
import types
from datetime import datetime, timezone

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
        self.title, self.description, self.fields, self.image, self.footer = title, description, [], None, None

    def add_field(self, name, value, inline=True):
        self.fields.append((name, value))

    def set_image(self, url):
        self.image = url

    def set_footer(self, text=None):
        self.footer = text


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
throwback.PoolResult = __import__("archive").PoolResult


# ---- fakes ----------------------------------------------------------------------------------
WIN_START, WIN_END = datetime(2019, 3, 1, tzinfo=timezone.utc), datetime(2019, 4, 15, tzinfo=timezone.utc)


def cand(i, reactions=0):
    msg = types.SimpleNamespace(
        id=1000 + i, author=types.SimpleNamespace(display_name=f"User{i}"), channel=types.SimpleNamespace(id=1),
        created_at=None, jump_url=f"https://discord.com/x/{i}")
    return types.SimpleNamespace(message=msg, text=f"message number {i} in the pool", reactions=reactions)


class FakeDB:
    def __init__(self, used=(), windows=()):
        self.used, self.windows, self.added = set(used), list(windows), []

    async def recent_throwback_windows(self, limit=30):
        return list(self.windows)

    async def posted_throwback_ids(self):
        return set(self.used)

    async def add_throwback(self, message_id, start, end, **details):
        self.added.append((message_id, start, end))
        self.details = details


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


def make(llm=None, images=None, pool=None, db=None, **flags):
    target = TextChannel(1)
    brain = types.SimpleNamespace(llm=llm, persona="You are a bot.") if llm is not None else None
    imagegen = types.SimpleNamespace(client=images) if images is not None else None
    cogs = {"Brain": brain, "ImageGen": imagegen}
    db = db or FakeDB()
    bot = types.SimpleNamespace(get_channel=lambda cid: target, get_cog=lambda name: cogs.get(name),
                                command_prefix="!", db=db)
    cog = throwback.Throwback(bot)
    for k, v in flags.items():
        setattr(cog, k, v)
    pool = pool if pool is not None else [cand(i, reactions=10 - i) for i in range(12)]

    async def fake_find_pool(*a, recent=None, exclude=None, **k):
        fake_find_pool.calls.append({"recent": list(recent or []), "exclude": set(exclude or ())})
        result = throwback.PoolResult([c for c in pool if getattr(c.message, "id", None) not in (exclude or ())])
        if result:
            result.window, result.eligible = (WIN_START, WIN_END), 123
            result.attempts, result.channel_days, result.whole_channel = 3, 900, False
            result.tried = [{"start": "2019-01-01", "end": "2019-02-15", "scanned": 40, "eligible": 2},
                            {"start": "2019-03-01", "end": "2019-04-15", "scanned": 500, "eligible": 123}]
            if recent is not None:
                recent.append(result.window)     # like the real find_pool: records the window it used
        return result
    fake_find_pool.calls = []
    throwback.find_pool = fake_find_pool
    cog.find_calls, cog.db = fake_find_pool.calls, db
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


async def _records_what_it_posted_and_the_window_used():
    cog, target = make(FakeLLM(pick_message(7)), FakeImages())
    assert await cog.post_throwback() is None
    assert cog.db.added == [(1007, WIN_START, WIN_END)]


async def _passes_earlier_windows_and_posted_ids_to_the_search():
    db = FakeDB(used={1001, 1002}, windows=[("S1", "E1"), ("S2", "E2")])
    cog, target = make(db=db)
    assert await cog.post_throwback() is None
    call = cog.find_calls[0]
    assert call["recent"] == [("S1", "E1"), ("S2", "E2")] and call["exclude"] == {1001, 1002}
    assert target.sent[0]["embed"].description not in ("message number 1 in the pool", "message number 2 in the pool")


async def _repeats_are_allowed_only_when_everything_was_already_posted():
    pool = [cand(0), cand(1)]
    db = FakeDB(used={1000, 1001})
    cog, target = make(pool=pool, db=db)
    assert await cog.post_throwback() is None            # everything excluded -> second search without exclusion
    assert len(cog.find_calls) == 2 and cog.find_calls[1]["exclude"] == set()
    assert len(target.sent) == 1 and len(db.added) == 1


async def _nothing_posted_is_not_recorded():
    cog, target = make(pool=[])
    await cog.post_throwback()
    assert cog.db.added == []


test_records_what_it_posted_and_the_window_used = _t(_records_what_it_posted_and_the_window_used)
test_passes_earlier_windows_and_posted_ids = _t(_passes_earlier_windows_and_posted_ids_to_the_search)
test_repeats_only_when_everything_was_posted = _t(_repeats_are_allowed_only_when_everything_was_already_posted)
test_nothing_posted_is_not_recorded = _t(_nothing_posted_is_not_recorded)


async def _search_details_go_to_the_database_not_the_post():
    cog, target = make(FakeLLM(pick_message(7)), FakeImages())
    await cog.post_throwback()
    embed = target.sent[0]["embed"]
    assert embed.footer is None                                   # nothing about the search is shown to users
    assert "Searched" not in str([embed.description, embed.fields, embed.footer])
    d = cog.db.details
    assert (d["eligible"], d["attempts"], d["channel_days"], d["whole_channel"], d["ai_pick"]) == (123, 3, 900, False, True)
    import json
    tried = json.loads(d["windows_tried"])
    assert [w["eligible"] for w in tried] == [2, 123] and tried[0]["scanned"] == 40


async def _non_ai_post_is_logged_as_such():
    cog, target = make()
    await cog.post_throwback()
    assert cog.db.details["ai_pick"] is False


async def _a_database_failure_does_not_break_the_post():
    class BrokenDB(FakeDB):
        async def add_throwback(self, *a, **k):
            raise RuntimeError("db down")
    cog, target = make(db=BrokenDB())
    assert await cog.post_throwback() is None and len(target.sent) == 1


test_search_details_go_to_the_database_not_the_post = _t(_search_details_go_to_the_database_not_the_post)
test_non_ai_post_is_logged_as_such = _t(_non_ai_post_is_logged_as_such)
test_a_database_failure_does_not_break_the_post = _t(_a_database_failure_does_not_break_the_post)



if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
