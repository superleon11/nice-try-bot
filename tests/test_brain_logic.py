"""Tests the note-learning logic of cogs/brain.py with stand-ins for discord.py, the database and the AI.

Run with:  python tests/test_brain_logic.py   (no extra packages needed)
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
    def __init__(self, func):
        self.func = func

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


discord.Message = discord.Member = discord.HTTPException = Exception
discord.AllowedMentions = types.SimpleNamespace(none=lambda: None)
commands.Cog, commands.Bot, commands.Context = Cog, object, object
commands.command = commands.guild_only = commands.has_permissions = _passthrough
discord.ext, ext.commands, ext.tasks = ext, commands, tasks
sys.modules.update({"discord": discord, "discord.ext": ext,
                    "discord.ext.commands": commands, "discord.ext.tasks": tasks})

os.environ["ANTHROPIC_API_KEY"] = "test-key"
from cogs import brain  # noqa: E402
from llm import BudgetExceeded  # noqa: E402


# ---- fakes ----------------------------------------------------------------------------------
class FakeDB:
    def __init__(self):
        self.rows = []   # dicts: id, guild_id, user_id, note, source
        self.next_id = 1

    def seed(self, guild_id, user_id, note, source):
        self.rows.append({"id": self.next_id, "guild_id": guild_id, "user_id": user_id, "note": note, "source": source})
        self.next_id += 1
        return self.next_id - 1

    async def get_notes(self, guild_id, user_id, limit=20):
        rows = [r for r in self.rows if r["guild_id"] == guild_id and r["user_id"] == user_id]
        rows.sort(key=lambda r: (r["source"] != "manual", -r["id"]))
        return rows[:limit]

    async def add_note(self, guild_id, user_id, username, note, source="manual"):
        return self.seed(guild_id, user_id, note, source)

    async def delete_auto_notes(self, guild_id, user_id, ids):
        self.rows = [r for r in self.rows if not (r["guild_id"] == guild_id and r["user_id"] == user_id
                                                  and r["source"] == "auto" and r["id"] in ids)]

    async def trim_auto_notes(self, guild_id, user_id, keep):
        autos = sorted((r for r in self.rows if r["guild_id"] == guild_id and r["user_id"] == user_id
                        and r["source"] == "auto"), key=lambda r: -r["id"])
        drop = {r["id"] for r in autos[keep:]}
        self.rows = [r for r in self.rows if r["id"] not in drop]

    def notes_of(self, guild_id, user_id):
        return [(r["note"], r["source"]) for r in self.rows if r["guild_id"] == guild_id and r["user_id"] == user_id]


class FakeLLM:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []

    async def complete(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return self.answer(kw) if callable(self.answer) else self.answer


def make_brain(db, llm):
    bot = types.SimpleNamespace(db=db, user=types.SimpleNamespace(id=999))
    cog = brain.Brain(bot)
    cog.llm = llm
    return cog


def fill(cog, guild_id, user_id, n, name="Someone"):
    cog.buffer[(guild_id, user_id)] = [f"message number {i} from them" for i in range(n)]
    cog.names[(guild_id, user_id)] = name


G = 1

# ---- tests ----------------------------------------------------------------------------------
async def _adds_notes_and_never_touches_manual_ones():
    db = FakeDB()
    manual = db.seed(G, 10, "Is called Dave, hates mornings", "manual")
    stale = db.seed(G, 10, "Was playing chess last year", "auto")
    answer = json.dumps({"users": [{"user_id": "10",
                                    "add": ["Always late to calls", "Obsessed with his new bike"],
                                    "remove": [manual, stale]}]})   # model wrongly tries to remove the manual note
    llm = FakeLLM(answer)
    cog = make_brain(db, llm)
    fill(cog, G, 10, 5, "Dave")
    people, added = await cog.run_learning()
    assert (people, added) == (1, 2)
    notes = db.notes_of(G, 10)
    assert ("Is called Dave, hates mornings", "manual") in notes     # survived
    assert ("Was playing chess last year", "auto") not in notes       # auto note removed as asked
    assert ("Always late to calls", "auto") in notes
    assert llm.calls[0]["purpose"] == "memory"
    assert str(manual) in llm.calls[0]["prompt"] and "manual" in llm.calls[0]["prompt"]
    assert cog.buffer == {}                                            # raw messages thrown away


async def _ignores_duplicates_and_unknown_people():
    db = FakeDB()
    db.seed(G, 10, "Always late to calls", "auto")
    answer = json.dumps({"users": [
        {"user_id": "10", "add": ["always late to calls", "Loves pineapple pizza"], "remove": []},
        {"user_id": "777", "add": ["a person we never asked about"], "remove": []},
    ]})
    cog = make_brain(db, FakeLLM(answer))
    fill(cog, G, 10, 4)
    _, added = await cog.run_learning()
    assert added == 1
    assert db.notes_of(G, 777) == []
    assert len(db.notes_of(G, 10)) == 2


async def _garbage_reply_changes_nothing():
    db = FakeDB()
    cog = make_brain(db, FakeLLM("Sorry, I can't help with that."))
    fill(cog, G, 10, 5)
    assert await cog.run_learning() == (1, 0)
    assert db.rows == []


async def _people_with_too_few_messages_are_kept_for_later():
    db, llm = FakeDB(), FakeLLM('{"users": []}')
    cog = make_brain(db, llm)
    fill(cog, G, 10, 2)          # below MIN_MESSAGES
    assert await cog.run_learning() == (0, 0)
    assert llm.calls == []       # no API call, nothing spent
    assert len(cog.buffer[(G, 10)]) == 2   # still waiting


async def _budget_exceeded_keeps_the_messages_for_tomorrow():
    db = FakeDB()
    cog = make_brain(db, FakeLLM(error=BudgetExceeded("daily cap reached")))
    fill(cog, G, 10, 6)
    fill(cog, G, 11, 4)
    assert await cog.run_learning() == (0, 0)
    assert len(cog.buffer[(G, 10)]) == 6 and len(cog.buffer[(G, 11)]) == 4
    assert db.rows == []


async def _batches_people_and_caps_auto_notes():
    db = FakeDB()
    for uid in range(100, 100 + 20):           # 20 people -> two batches of 15 and 5
        fill_user = uid
        cog_msgs = None
    llm = FakeLLM('{"users": []}')
    cog = make_brain(db, llm)
    for uid in range(100, 120):
        fill(cog, G, uid, 4)
    assert await cog.run_learning() == (20, 0)
    assert len(llm.calls) == 2

    # trimming: 40 auto notes for one person are cut down to MAX_AUTO_NOTES, manual untouched
    db2 = FakeDB()
    db2.seed(G, 5, "manual note", "manual")
    for i in range(40):
        db2.seed(G, 5, f"auto note {i}", "auto")
    cog2 = make_brain(db2, FakeLLM(json.dumps({"users": [{"user_id": "5", "add": ["one more"], "remove": []}]})))
    fill(cog2, G, 5, 4)
    await cog2.run_learning()
    notes = db2.notes_of(G, 5)
    assert sum(1 for _, s in notes if s == "auto") == brain.MAX_AUTO_NOTES
    assert ("manual note", "manual") in notes
    assert ("one more", "auto") in notes     # the newest note is kept


def _msg(text, guild_id=G, user_id=5):
    return types.SimpleNamespace(
        clean_content=text, content=text,
        guild=types.SimpleNamespace(id=guild_id, me=types.SimpleNamespace(display_name="FunBot")),
        author=types.SimpleNamespace(id=user_id, display_name="Dave"),
    )


def test_remember_strips_the_bot_mention_and_caps_the_buffer():
    cog = make_brain(FakeDB(), FakeLLM(""))
    cog._remember(_msg("@FunBot   what do you   think of pineapple?"))
    assert cog.buffer[(G, 5)] == ["what do you think of pineapple?"]
    cog._remember(_msg("hi"))                       # too short to be worth keeping? ("hi" < 3 chars)
    assert len(cog.buffer[(G, 5)]) == 1
    for i in range(brain.MAX_BUFFER_PER_USER + 50):
        cog._remember(_msg(f"message {i} about something"))
    assert len(cog.buffer[(G, 5)]) == brain.MAX_BUFFER_PER_USER
    assert cog.buffer[(G, 5)][-1].startswith(f"message {brain.MAX_BUFFER_PER_USER + 49}")


def test_adds_notes_and_never_touches_manual_ones():
    asyncio.run(_adds_notes_and_never_touches_manual_ones())


def test_ignores_duplicates_and_unknown_people():
    asyncio.run(_ignores_duplicates_and_unknown_people())


def test_garbage_reply_changes_nothing():
    asyncio.run(_garbage_reply_changes_nothing())


def test_people_with_too_few_messages_are_kept_for_later():
    asyncio.run(_people_with_too_few_messages_are_kept_for_later())


def test_budget_exceeded_keeps_the_messages_for_tomorrow():
    asyncio.run(_budget_exceeded_keeps_the_messages_for_tomorrow())


def test_batches_people_and_caps_auto_notes():
    asyncio.run(_batches_people_and_caps_auto_notes())


# ---- unprompted replies -----------------------------------------------------------------------
class FakeChannel:
    def __init__(self, cid=50):
        self.id = cid

    async def history(self, limit=8, before=None):
        return
        yield  # makes this an (empty) async generator


def chat_msg(text, channel_id=50):
    sent = []

    async def reply(content, **kw):
        sent.append(content)

    return types.SimpleNamespace(
        content=text, clean_content=text, mentions=[], reference=None, reply=reply, sent=sent,
        channel=FakeChannel(channel_id),
        guild=types.SimpleNamespace(id=G, me=types.SimpleNamespace(display_name="FunBot")),
        author=types.SimpleNamespace(id=5, display_name="Dave", bot=False),
    )


def test_should_chime_in_respects_chance_cooldown_length_and_channels():
    cog = make_brain(FakeDB(), FakeLLM(""))
    cog.random_chance = 1.0
    assert cog._should_chime_in(chat_msg("this is a normal message"))
    cog._last_random[50] = __import__("time").monotonic()          # just replied in channel 50
    assert not cog._should_chime_in(chat_msg("this is a normal message"))
    assert cog._should_chime_in(chat_msg("this is a normal message", channel_id=51))   # other channel is fine
    cog._last_random.clear()
    assert not cog._should_chime_in(chat_msg("short"))               # too short to be worth it
    cog.random_chance = 0.0
    assert not cog._should_chime_in(chat_msg("this is a normal message"))
    cog.random_chance = 1.0
    cog.random_channels = {99}
    assert not cog._should_chime_in(chat_msg("this is a normal message", channel_id=50))
    assert cog._should_chime_in(chat_msg("this is a normal message", channel_id=99))


async def _chime_in_replies_when_the_ai_has_something_to_say():
    llm = FakeLLM("That's what she said about the bike.")
    cog = make_brain(FakeDB(), llm)
    m = chat_msg("I finally bought that motorbike")
    await cog._chime_in(m)
    assert m.sent == ["That's what she said about the bike."]
    assert llm.calls[0]["purpose"] == "chime-in" and "SKIP" in llm.calls[0]["prompt"]
    assert 50 in cog._last_random                      # cooldown started


async def _chime_in_stays_quiet_on_skip_but_still_starts_the_cooldown():
    for answer in ("SKIP", "  skip.", ""):
        cog = make_brain(FakeDB(), FakeLLM(answer))
        m = chat_msg("just had a really boring lunch")
        await cog._chime_in(m)
        assert m.sent == [] and 50 in cog._last_random


async def _chime_in_falls_back_to_canned_replies_over_budget():
    cog = make_brain(FakeDB(), FakeLLM(error=BudgetExceeded("daily cap reached")))
    thanks = chat_msg("thanks for sorting that out")
    await cog._chime_in(thanks)
    assert len(thanks.sent) == 1                       # a canned keyword reply
    plain = chat_msg("the weather is quite grey today")
    await cog._chime_in(plain)
    assert plain.sent == []                            # no keyword -> stays quiet


def test_chime_in_replies_when_the_ai_has_something_to_say():
    asyncio.run(_chime_in_replies_when_the_ai_has_something_to_say())


def test_chime_in_stays_quiet_on_skip_but_still_starts_the_cooldown():
    asyncio.run(_chime_in_stays_quiet_on_skip_but_still_starts_the_cooldown())


def test_chime_in_falls_back_to_canned_replies_over_budget():
    asyncio.run(_chime_in_falls_back_to_canned_replies_over_budget())


# ---- follow-up conversations ------------------------------------------------------------------
class FakeDiscordMessage(Exception):
    """Stands in for discord.Message (the stub makes discord.Message an Exception subclass)."""

    def __init__(self, author_id):
        super().__init__()
        self.author = types.SimpleNamespace(id=author_id)


def follow_up(text="and what about the second one?", channel_id=50, user_id=5, mentions=(), reply_to=None):
    m = chat_msg(text, channel_id)
    m.author.id = user_id
    m.mentions = list(mentions)
    m.reference = types.SimpleNamespace(resolved=reply_to) if reply_to is not None else None
    return m


def test_follow_up_works_for_the_same_person_in_the_same_channel_only():
    import time as _t
    cog = make_brain(FakeDB(), FakeLLM(""))
    assert not cog._in_conversation(follow_up())                     # bot has not spoken to them yet
    cog._convos[(50, 5)] = _t.monotonic()
    assert cog._in_conversation(follow_up())                          # same person, same channel
    assert not cog._in_conversation(follow_up(user_id=6))             # somebody else
    assert not cog._in_conversation(follow_up(channel_id=51))         # another channel
    assert cog.is_for_me(follow_up())


def test_follow_up_expires_and_can_be_switched_off():
    import time as _t
    cog = make_brain(FakeDB(), FakeLLM(""))
    cog._convos[(50, 5)] = _t.monotonic() - cog.convo_window - 1
    assert not cog._in_conversation(follow_up())                      # window has passed
    cog._convos[(50, 5)] = _t.monotonic()
    cog.convo_window = 0
    assert not cog._in_conversation(follow_up())                      # feature off


def test_follow_up_ignores_messages_aimed_at_other_people():
    import time as _t
    cog = make_brain(FakeDB(), FakeLLM(""))
    cog._convos[(50, 5)] = _t.monotonic()
    sam = types.SimpleNamespace(id=7, bot=False)
    assert not cog._in_conversation(follow_up("@Sam are you coming tonight?", mentions=[sam]))
    assert not cog._in_conversation(follow_up(reply_to=FakeDiscordMessage(author_id=7)))   # reply to Sam
    assert cog._in_conversation(follow_up(reply_to=FakeDiscordMessage(author_id=999)))     # reply to the bot (id 999)


class _Typing:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


async def _replying_starts_the_window_and_chiming_in_does_too():
    cog = make_brain(FakeDB(), FakeLLM("Because it is a good bike."))
    m = chat_msg("@FunBot why did I buy that motorbike")
    m.channel.typing = lambda: _Typing()
    assert not cog._in_conversation(follow_up())
    await cog._respond(m)
    assert m.sent == ["Because it is a good bike."]
    assert cog._in_conversation(follow_up())                          # now their next message counts

    cog2 = make_brain(FakeDB(), FakeLLM("A bold choice."))
    m2 = chat_msg("I finally bought that motorbike")
    await cog2._chime_in(m2)
    assert cog2._in_conversation(follow_up())                         # they can answer a chime-in without an @


def test_replying_starts_the_window_and_chiming_in_does_too():
    asyncio.run(_replying_starts_the_window_and_chiming_in_does_too())


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
