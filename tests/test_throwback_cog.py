"""Tests the moderated throwback (cogs/throwback.py) with stand-ins for discord.py, the AI and the image API.

Run with:  python tests/test_throwback_cog.py
"""

import asyncio
import json
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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
    @staticmethod
    def listener(*a, **k):
        return lambda f: f


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


class HTTPException(Exception):
    pass


class SentMessage:
    _next = 5000

    def __init__(self):
        SentMessage._next += 1
        self.id, self.reactions = SentMessage._next, []

    async def add_reaction(self, emoji):
        self.reactions.append(emoji)


class TextChannel:
    def __init__(self, cid=1):
        self.id, self.sent, self.guild = cid, [], types.SimpleNamespace(me=object())
        self.name = "general"
        self.store = {}

    def is_nsfw(self):
        return True

    def permissions_for(self, me):
        return types.SimpleNamespace(view_channel=True, read_message_history=True)

    async def send(self, *args, **kw):
        kw["text"] = args[0] if args else None
        self.sent.append(kw)
        msg = SentMessage()
        kw["message"] = msg
        return msg

    async def fetch_message(self, mid):
        if mid not in self.store:
            raise HTTPException("gone")
        return self.store[mid]


discord.Embed, discord.File, discord.TextChannel, discord.HTTPException = Embed, File, TextChannel, HTTPException
discord.AllowedMentions = types.SimpleNamespace(none=lambda: None)
discord.Colour = types.SimpleNamespace(gold=lambda: 0)
discord.utils = types.SimpleNamespace(escape_markdown=lambda s: s, format_dt=lambda d, f: "DATE")
commands.Cog, commands.Bot, commands.Context = Cog, object, object
commands.command = commands.guild_only = commands.has_permissions = _passthrough
discord.ext, ext.commands, ext.tasks = ext, commands, tasks
sys.modules.update({"discord": discord, "discord.ext": ext,
                    "discord.ext.commands": commands, "discord.ext.tasks": tasks})

os.environ["THROWBACK_CHANNEL_ID"] = "1"
os.environ["THROWBACK_MOD_CHANNEL_ID"] = "2"
from cogs import throwback  # noqa: E402
from llm import BudgetExceeded, LLMError  # noqa: E402
from helpers import parse_top_reply, throwback_action  # noqa: E402
throwback.PoolResult = __import__("archive").PoolResult


# ---- fakes ----------------------------------------------------------------------------------
LONDON = ZoneInfo("Europe/London")
WIN_START, WIN_END = datetime(2019, 3, 1, tzinfo=timezone.utc), datetime(2019, 4, 15, tzinfo=timezone.utc)
CLOCK = {"now": None}


class FakeDT(datetime):
    @classmethod
    def now(cls, tz=None):
        return CLOCK["now"].astimezone(tz) if tz else CLOCK["now"]


throwback.datetime = FakeDT


def at(hour, minute=0, day=8):
    CLOCK["now"] = datetime(2026, 10, day, hour, minute, tzinfo=LONDON).astimezone(timezone.utc)


def cand(i, reactions=0):
    msg = types.SimpleNamespace(
        id=1000 + i, author=types.SimpleNamespace(display_name=f"User{i}"), channel=types.SimpleNamespace(id=1),
        created_at=None, jump_url=f"https://discord.com/x/{i}")
    return types.SimpleNamespace(message=msg, text=f"message number {i} in the pool", reactions=reactions)


class FakeDB:
    def __init__(self, used=(), windows=()):
        self.used, self.windows, self.added, self.rounds = set(used), list(windows), [], []

    async def recent_throwback_windows(self, limit=30):
        return list(self.windows)

    async def posted_throwback_ids(self):
        return set(self.used)

    async def proposed_throwback_ids(self):
        return {c["id"] for r in self.rounds for c in json.loads(r["candidates"])}

    async def add_throwback(self, message_id, start, end, **details):
        self.added.append((message_id, start, end))
        self.details = details

    async def add_round(self, day, round_no, candidates, **details):
        self.rounds.append(dict(id=len(self.rounds) + 1, day=day, round_no=round_no, candidates=candidates,
                                status="open", mod_message_id=None, chosen_id=None, chosen_channel_id=None,
                                post_at=None, **details))
        return len(self.rounds)

    async def set_round_mod_message(self, rid, mid):
        self.rounds[rid - 1]["mod_message_id"] = mid

    async def rounds_for_day(self, day):
        return [dict(r) for r in self.rounds if r["day"] == day]

    async def round_by_mod_message(self, mid):
        return next((dict(r) for r in self.rounds if r["mod_message_id"] == mid), None)

    async def change_round_status(self, rid, expected, new, *, chosen_id=None, chosen_channel_id=None, post_at=None):
        r = self.rounds[rid - 1]
        if r["status"] != expected:
            return False
        r["status"] = new
        r["chosen_id"] = chosen_id or r["chosen_id"]
        r["chosen_channel_id"] = chosen_channel_id or r["chosen_channel_id"]
        r["post_at"] = post_at or r["post_at"]
        return True


class FakeLLM:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    async def complete(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return self.reply(kw)


def smart(shortlist=(1, 2, 3)):
    """Answers the shortlist call with `shortlist` and the single-message call with a comment + image prompt."""
    def reply(kw):
        if kw["purpose"] == "throwback-shortlist":
            return json.dumps({"picks": list(shortlist)})
        return json.dumps({"pick": 1, "comment": "A fine moment.", "image_prompt": "a cartoon"})
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
    at(10, 5)
    main, mod = TextChannel(1), TextChannel(2)
    brain = types.SimpleNamespace(llm=llm, persona="You are a bot.") if llm is not None else None
    imagegen = types.SimpleNamespace(client=images) if images is not None else None
    cogs = {"Brain": brain, "ImageGen": imagegen}
    db = db or FakeDB()
    channels = {1: main, 2: mod}
    bot = types.SimpleNamespace(get_channel=lambda cid: channels.get(cid), get_cog=lambda name: cogs.get(name),
                                command_prefix="!", db=db, user=types.SimpleNamespace(id=99))
    cog = throwback.Throwback(bot)
    for k, v in flags.items():
        setattr(cog, k, v)
    pool = pool if pool is not None else [cand(i, reactions=20 - i) for i in range(30)]

    async def fake_find_pool(*a, recent=None, exclude=None, **k):
        fake_find_pool.calls.append({"recent": list(recent or []), "exclude": set(exclude or ())})
        result = throwback.PoolResult([c for c in pool if getattr(c.message, "id", None) not in (exclude or ())])
        if result:
            result.window, result.eligible = (WIN_START, WIN_END), 123
            result.attempts, result.channel_days, result.whole_channel = 3, 900, False
            result.tried = [{"start": "2019-03-01", "end": "2019-04-15", "scanned": 500, "eligible": 123}]
        return result
    fake_find_pool.calls = []
    throwback.find_pool = fake_find_pool
    cog.find_calls, cog.db, cog.main, cog.mod = fake_find_pool.calls, db, main, mod
    # the message that gets approved is fetched from the source channel (id 1)
    for i in range(30):
        main.store[1000 + i] = types.SimpleNamespace(
            id=1000 + i, content=f"message number {i} in the pool", reactions=[types.SimpleNamespace(count=3)],
            author=types.SimpleNamespace(display_name=f"User{i}"), channel=types.SimpleNamespace(id=1),
            created_at=None, jump_url=f"https://discord.com/x/{i}")
    return cog


def react(cog, emoji, message=None, channel=2, user=7):
    mid = message.id if message is not None else cog.mod.sent[-1]["message"].id
    payload = types.SimpleNamespace(channel_id=channel, message_id=mid, user_id=user, emoji=emoji)
    asyncio.run(cog.on_raw_reaction_add(payload))


def field(embed, name):
    return dict(embed.fields).get(name)


def run(coro):
    return asyncio.run(coro)


# ---- the daily decision (pure) --------------------------------------------------------------------
def _when(h, m=0):
    return datetime(2026, 10, 8, h, m, tzinfo=LONDON)


def test_action_waits_for_the_scan_hour_then_proposes():
    act = lambda now, rounds=(): throwback_action(now, LONDON, list(rounds), 10, 15, 5)  # noqa: E731
    assert act(_when(9, 59)) is None and act(_when(10, 0)) == "propose" and act(_when(14, 59)) == "propose"
    assert act(_when(15, 0)) is None                                        # too late to start


def test_action_states():
    act = lambda now, rounds: throwback_action(now, LONDON, rounds, 10, 15, 3)  # noqa: E731
    post_at = _when(12).astimezone(timezone.utc)
    assert act(_when(11), [{"status": "open"}]) is None                     # waiting for the moderator
    assert act(_when(15, 0), [{"status": "open"}]) == "expire_open"
    assert act(_when(11), [{"status": "approved", "post_at": post_at}]) is None
    assert act(_when(12), [{"status": "approved", "post_at": post_at}]) == "publish"
    assert act(_when(15, 5), [{"status": "approved", "post_at": post_at}]) == "publish"   # small grace
    assert act(_when(15, 30), [{"status": "approved", "post_at": post_at}]) == "expire_approved"
    assert act(_when(16), [{"status": "posted"}]) is None
    assert act(_when(12), [{"status": "rejected"}]) == "propose"
    assert act(_when(12), [{"status": "rejected"}, {"status": "failed"}, {"status": "rejected"}]) == "limit"


def test_parse_top_reply():
    assert parse_top_reply('{"picks": [3, 1, 2]}', 5) == [2, 0, 1]
    assert parse_top_reply('text {"picks": [2, 2, 9, 0, "x"]}', 5) == []  # "x" makes it unusable
    assert parse_top_reply('{"picks": [2, 2, 9, 0, 4]}', 5) == [1, 3]
    assert parse_top_reply("nope", 5) == [] and parse_top_reply('{"picks": [1,2,3,4]}', 9, 3) == [0, 1, 2]


# ---- candidates go to the moderation channel only ----------------------------------------------
def test_candidates_go_to_the_mod_channel_not_the_main_one():
    cog = make(FakeLLM(smart((4, 9, 2))))
    assert run(cog.tick()) == "propose"
    assert cog.main.sent == [] and len(cog.mod.sent) == 1
    sent = cog.mod.sent[0]
    assert len(sent["embeds"]) == 3 and "round 1" in sent["text"]
    assert sent["message"].reactions == ["1️⃣", "2️⃣", "3️⃣", "❌"]
    assert all("Throwback of the Day" not in (e.title or "") for e in sent["embeds"])
    assert cog.db.rounds[0]["status"] == "open" and cog.db.rounds[0]["mod_message_id"] == sent["message"].id
    assert cog.db.rounds[0]["ai_pick"] is True and cog.db.rounds[0]["eligible"] == 123


def test_no_candidates_are_sent_before_the_scan_hour_or_twice():
    cog = make()
    at(9, 30)
    assert run(cog.tick()) is None and cog.mod.sent == []
    at(10, 0)
    run(cog.tick())
    assert run(cog.tick()) is None and len(cog.mod.sent) == 1               # waiting for the moderator


def test_without_the_ai_candidates_come_from_the_most_reacted():
    cog = make()
    run(cog.tick())
    ids = {c["id"] for c in json.loads(cog.db.rounds[0]["candidates"])}
    assert len(ids) == 3 and ids <= {1000 + i for i in range(10)}


def test_ai_failure_or_budget_falls_back():
    for llm in (FakeLLM(error=BudgetExceeded("cap")), FakeLLM(error=LLMError("500")), FakeLLM(lambda kw: "huh")):
        cog = make(llm)
        run(cog.tick())
        assert len(cog.mod.sent[0]["embeds"]) == 3 and cog.db.rounds[0]["ai_pick"] is False


def test_tiny_pool_sends_what_there_is():
    cog = make(pool=[cand(0), cand(1)])
    run(cog.tick())
    assert len(cog.mod.sent[0]["embeds"]) == 2 and cog.mod.sent[0]["message"].reactions == ["1️⃣", "2️⃣", "❌"]


# ---- approving ----------------------------------------------------------------------------------
def test_approving_holds_the_message_and_schedules_it_between_11_and_3():
    cog = make(FakeLLM(smart()))
    run(cog.tick())
    ids = [c["id"] for c in json.loads(cog.db.rounds[0]["candidates"])]
    at(10, 20)
    react(cog, "2️⃣")
    r = cog.db.rounds[0]
    assert r["status"] == "approved" and r["chosen_id"] == ids[1]
    local = r["post_at"].astimezone(LONDON)
    assert local.date().day == 8 and 11 <= local.hour < 15
    assert "Number 2 is approved" in cog.mod.sent[-1]["text"]
    assert cog.main.sent == []                                               # nothing public yet


def test_only_the_first_choice_counts_and_other_reactions_are_ignored():
    cog = make()
    run(cog.tick())
    msg = cog.mod.sent[0]["message"]
    react(cog, "3️⃣")
    react(cog, "1️⃣")
    react(cog, "❌")
    assert cog.db.rounds[0]["status"] == "approved" and len(cog.db.rounds) == 1
    cog2 = make()
    run(cog2.tick())
    react(cog2, "1️⃣", user=99)             # the bot's own reaction
    react(cog2, "👍")                        # not a choice
    react(cog2, "1️⃣", channel=1)            # wrong channel
    react(cog2, "1️⃣", message=types.SimpleNamespace(id=1))   # not one of our messages
    assert cog2.db.rounds[0]["status"] == "open"
    assert msg


def test_approval_too_late_in_the_day_is_refused():
    cog = make()
    run(cog.tick())
    at(15, 30)
    react(cog, "1️⃣")
    assert cog.db.rounds[0]["status"] == "open" and "too late" in cog.mod.sent[-1]["text"]


def test_the_approved_message_is_posted_at_its_time_with_comment_and_image():
    images = FakeImages()
    cog = make(FakeLLM(smart()), images)
    run(cog.tick())
    react(cog, "1️⃣")
    r = cog.db.rounds[0]
    at(10, 59)
    assert run(cog.tick()) is None and cog.main.sent == []
    CLOCK["now"] = r["post_at"] + timedelta(seconds=1)
    assert run(cog.tick()) == "publish"
    sent = cog.main.sent[0]
    assert sent["embed"].description == f"message number {r['chosen_id'] - 1000} in the pool"
    assert field(sent["embed"], "The bot's verdict") == "A fine moment."
    assert sent["file"].filename == "throwback.png" and images.prompts == ["a cartoon"]
    assert sent["embed"].footer is None
    assert r["status"] == "posted" and cog.db.added == [(r["chosen_id"], WIN_START, WIN_END)]
    assert cog.db.details["eligible"] == 123 and cog.db.details["ai_pick"] is True
    CLOCK["now"] += timedelta(hours=1)
    assert run(cog.tick()) is None and len(cog.main.sent) == 1               # only once a day


def test_post_without_ai_or_with_image_trouble_still_goes_out():
    for kwargs in (dict(), dict(llm=FakeLLM(smart()), images=FakeImages(error=LLMError("HTTP 400"))),
                   dict(llm=FakeLLM(error=BudgetExceeded("cap")), images=FakeImages())):
        cog = make(**kwargs)
        run(cog.tick())
        react(cog, "1️⃣")
        CLOCK["now"] = cog.db.rounds[0]["post_at"] + timedelta(seconds=1)
        run(cog.tick())
        sent = cog.main.sent[0]
        assert "file" not in sent and sent["embed"].image is None and field(sent["embed"], "The bot's verdict") is None \
            or field(sent["embed"], "The bot's verdict") == "A fine moment."


def test_switches_turn_comment_and_image_off():
    images = FakeImages()
    cog = make(FakeLLM(smart()), images, with_image=False)
    run(cog.tick())
    react(cog, "1️⃣")
    CLOCK["now"] = cog.db.rounds[0]["post_at"] + timedelta(seconds=1)
    run(cog.tick())
    assert images.prompts == [] and "file" not in cog.main.sent[0]


def test_approved_message_that_was_deleted_leads_to_a_new_round():
    cog = make()
    run(cog.tick())
    react(cog, "1️⃣")
    del cog.main.store[cog.db.rounds[0]["chosen_id"]]
    CLOCK["now"] = cog.db.rounds[0]["post_at"] + timedelta(seconds=1)
    run(cog.tick())
    assert cog.db.rounds[0]["status"] == "failed" and cog.main.sent == []
    assert "deleted" in cog.mod.sent[-1]["text"]
    assert run(cog.tick()) == "propose" and len(cog.db.rounds) == 2


def test_restart_between_approval_and_posting_loses_nothing():
    cog = make()
    run(cog.tick())
    react(cog, "2️⃣")
    db = cog.db
    CLOCK["now"] = db.rounds[0]["post_at"] + timedelta(seconds=1)
    cog2 = make(db=db)                               # a new process, same database
    CLOCK["now"] = db.rounds[0]["post_at"] + timedelta(seconds=1)
    cog2.main.store = cog.main.store
    assert run(cog2.tick()) == "publish" and len(cog2.main.sent) == 1


# ---- rejecting / not choosing ---------------------------------------------------------------------
def test_rejecting_starts_another_round_with_new_messages():
    cog = make()
    run(cog.tick())
    first = {c["id"] for c in json.loads(cog.db.rounds[0]["candidates"])}
    react(cog, "❌")
    assert cog.db.rounds[0]["status"] == "rejected" and len(cog.db.rounds) == 2
    second = {c["id"] for c in json.loads(cog.db.rounds[1]["candidates"])}
    assert not first & second and cog.find_calls[1]["exclude"] >= first
    assert "round 2" in cog.mod.sent[-1]["text"] and cog.main.sent == []


def test_stops_after_the_maximum_number_of_rounds():
    cog = make(max_rounds=2)
    run(cog.tick())
    react(cog, "❌")
    react(cog, "❌")
    assert len(cog.db.rounds) == 2
    assert run(cog.tick()) == "limit" and run(cog.tick()) == "limit"
    assert sum("no throwback today" in (s["text"] or "") for s in cog.mod.sent) == 1   # said once
    assert cog.main.sent == []


def test_nothing_approved_by_the_end_of_the_window_means_no_throwback():
    cog = make()
    run(cog.tick())
    at(15, 1)
    assert run(cog.tick()) == "expire_open"
    assert cog.db.rounds[0]["status"] == "expired" and "no throwback today" in cog.mod.sent[-1]["text"]
    assert run(cog.tick()) is None and cog.main.sent == []
    at(10, 0, day=9)                                  # tomorrow starts fresh
    assert run(cog.tick()) == "propose"


def test_every_message_offered_before_can_come_back_only_when_nothing_else_is_left():
    db = FakeDB()
    cog = make(pool=[cand(i) for i in range(3)], db=db)
    run(cog.tick())
    react(cog, "❌")                                  # round 2: nothing new left -> offers the rejects again
    assert len(db.rounds) == 2 and len(cog.find_calls) == 3 and cog.find_calls[2]["exclude"] == set()


# ---- failures -----------------------------------------------------------------------------------
def test_empty_archive_tells_the_mods_and_waits_before_retrying():
    cog = make(pool=[])
    assert run(cog.tick()) == "propose"
    assert "couldn't put together" in cog.mod.sent[-1]["text"] and cog.db.rounds == []
    n = len(cog.find_calls)
    assert run(cog.tick()) is None and len(cog.find_calls) == n               # still waiting to retry
    assert cog.main.sent == []


def test_gives_up_for_the_day_after_repeated_failures():
    import time
    cog = make(pool=[])
    for _ in range(throwback.MAX_SEARCH_FAILURES + 2):
        cog._retry_at = 0
        run(cog.tick())
    assert cog._failures[cog._today()] == throwback.MAX_SEARCH_FAILURES
    assert "no throwback today" in cog.mod.sent[-1]["text"]
    assert time


def test_cannot_post_in_the_mod_channel_is_reported_not_silent():
    cog = make()

    async def boom(*a, **k):
        raise HTTPException("403")
    cog.mod.send = boom
    run(cog.tick())
    assert cog.db.rounds[0]["status"] == "failed"


def test_channel_ids_from_the_environment_are_exact():
    os.environ["THROWBACK_MOD_CHANNEL_ID"] = "1234567890123456789"
    try:
        assert make().mod_channel_id == 1234567890123456789
    finally:
        os.environ["THROWBACK_MOD_CHANNEL_ID"] = "2"


def test_a_crash_while_searching_is_reported_to_the_mods():
    cog = make()

    async def boom(*a, **k):
        raise RuntimeError("db exploded")
    cog.db.recent_throwback_windows = boom
    assert run(cog.tick()) == "propose"
    assert "db exploded" in cog.mod.sent[-1]["text"] and cog.main.sent == []


def test_disabled_without_a_mod_channel():
    cog = make()
    cog.mod_channel_id = 0
    run(cog.cog_load())
    assert cog._runner is None                       # nothing is ever posted unmoderated
    cog.mod_channel_id = 2
    cog.channel_id = 0
    run(cog.cog_load())
    assert cog._runner is None


def test_throwback_command_sends_a_new_set_and_replaces_the_open_one():
    cog = make()
    run(cog.tick())
    said = []

    async def send(text):
        said.append(text)
    ctx = types.SimpleNamespace(send=send)
    at(12, 0)
    run(cog.throwback(ctx))
    assert cog.db.rounds[0]["status"] == "expired" and cog.db.rounds[1]["status"] == "open"
    assert len(cog.mod.sent) == 2 and cog.main.sent == []


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
