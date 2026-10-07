"""Tests the "find something @user said" feature.  Run: python tests/test_recall.py"""

import asyncio
import os
import random
import sys
import types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

discord = types.ModuleType("discord")
ext = types.ModuleType("discord.ext")
commands = types.ModuleType("discord.ext.commands")


class HTTPException(Exception):
    pass


class Forbidden(HTTPException):
    pass


class Cog:
    @staticmethod
    def listener(*a, **k):
        return lambda f: f


class Embed:
    def __init__(self, **kw):
        self.kw, self.fields, self.footer = kw, [], None

    def add_field(self, **kw):
        self.fields.append(kw)

    def set_footer(self, text):
        self.footer = text


discord.Message, discord.HTTPException, discord.Forbidden, discord.Embed = object, HTTPException, Forbidden, Embed
discord.MessageType = types.SimpleNamespace(default=0, reply=19)
discord.Colour = types.SimpleNamespace(blurple=lambda: 0)
discord.AllowedMentions = types.SimpleNamespace(none=lambda: None)
discord.utils = types.SimpleNamespace(escape_markdown=lambda s: s, format_dt=lambda d, f: str(d.date()))
commands.Cog, commands.Bot = Cog, object
discord.ext, ext.commands = ext, commands
sys.modules.update({"discord": discord, "discord.ext": ext, "discord.ext.commands": commands})

from cogs import recall as recall_cog  # noqa: E402
from helpers import parse_recall_request  # noqa: E402
from llm import BudgetExceeded  # noqa: E402
import recall  # noqa: E402

NS = types.SimpleNamespace
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
OK = NS(view_channel=True, read_message_history=True)
NO = NS(view_channel=False, read_message_history=False)


# ---- parsing ---------------------------------------------------------------------------------
def test_parses_the_requests_people_actually_make():
    p = parse_recall_request
    assert p("@bot Find me a funny message @Dave has said in the past", True) == ("mentioned", [])
    assert p("what's the funniest thing I've ever said", False) == ("self", [])
    assert p("dig up something @Sam said about pineapple pizza", True) == ("mentioned", ["pineapple", "pizza"])
    assert p("find the best thing anyone ever said in here", False) == ("anyone", [])
    assert p("show me my most embarrassing message", False)[0] == "self"


def test_ordinary_chat_is_not_a_search():
    p = parse_recall_request
    assert p("what do you think about pizza", False) is None
    assert p("what did you say earlier?", False) is None
    assert p("hey bot how are you", True) is None
    assert p("find me a good pizza place", False) is None       # no 'said'/'message' word
    assert p("find the message", False) is None                   # no one specified


# ---- scanning ---------------------------------------------------------------------------------
def m(mid, uid, text, days=1, reactions=0, bot=False):
    return NS(id=mid, author=NS(id=uid, bot=bot, display_name=f"U{uid}"), content=text, type=0,
              created_at=NOW - timedelta(days=days), reactions=[NS(count=reactions)] if reactions else [],
              channel=NS(id=50), jump_url=f"https://x/{mid}")


class Chan:
    def __init__(self, cid, msgs, perms=OK):
        self.id, self.msgs, self.perms, self.name = cid, msgs, perms, f"c{cid}"

    def permissions_for(self, who):
        return self.perms if who.id != 5 or self.perms is OK else NO

    async def history(self, limit=None):
        for x in sorted(self.msgs, key=lambda x: x.created_at, reverse=True):
            yield x


def guild(*chans):
    return NS(id=1, me=NS(id=999), text_channels=list(chans))


ASKER = NS(id=5)


def search(g, ids, topic=(), **kw):
    return asyncio.run(recall.search_history(g, ASKER, ids, list(topic), rng=random.Random(1), **kw))


def test_only_the_wanted_users_messages_are_kept():
    c = Chan(1, [m(1, 10, "I said this myself"), m(2, 11, "somebody else said this"),
                 m(3, 10, "a bot-ish line here", bot=True), m(4, 10, "ok"), m(5, 10, "!command thing here")])
    r = search(guild(c), [10])
    assert [h.message.id for h in r.pool] == [1]
    assert r.complete and r.scanned == 5


def test_no_wanted_users_means_anyone():
    c = Chan(1, [m(1, 10, "message from ten"), m(2, 11, "message from eleven")])
    assert len(search(guild(c), []).pool) == 2


def test_unreadable_channels_are_skipped_including_ones_the_asker_cannot_see():
    c1 = Chan(1, [m(1, 10, "public message here")])
    c2 = Chan(2, [m(2, 10, "secret message here")], perms=NO)
    r = search(guild(c1, c2), [10])
    assert [h.message.id for h in r.pool] == [1] and r.channels_total == 1


def test_topic_matches_come_first_and_narrow_the_pool():
    msgs = [m(i, 10, f"random chatter number {i}") for i in range(20)]
    msgs += [m(100 + i, 10, f"pineapple opinion {i}") for i in range(4)]
    r = search(guild(Chan(1, msgs)), [10], ["pineapple"])
    assert len(r.pool) == 4 and all("pineapple" in h.text for h in r.pool)
    r = search(guild(Chan(1, msgs[:20] + msgs[20:21])), [10], ["pineapple"])   # only one match: keep everything
    assert len(r.pool) == 21


def test_time_limit_stops_the_scan_and_reports_incomplete():
    clock = [0.0]

    def now():
        clock[0] += 1.0
        return clock[0]

    c = Chan(1, [m(i, 10, f"some message {i} here", days=i) for i in range(1, 200)])
    r = search(guild(c), [10], seconds=30, now=now)
    assert not r.complete and 0 < r.scanned < 199 and r.oldest is not None


def test_max_scanned_limit():
    c = Chan(1, [m(i, 10, f"some message {i} here", days=i) for i in range(1, 100)])
    r = search(guild(c), [10], max_scanned=10)
    assert r.scanned == 10 and not r.complete


def test_big_history_keeps_memory_bounded():
    c = Chan(1, [m(i, 10, f"some message {i} here", days=i % 300 + 1, reactions=i % 7) for i in range(1, 3000)])
    r = search(guild(c), [10])
    assert len(r.pool) <= recall.TOP_N + recall.RANDOM_N and r.matched == 2999


# ---- the cog ----------------------------------------------------------------------------------
class FakeLLM:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []

    async def complete(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return self.answer


def make_cog(llm, enabled=True):
    brain = NS(enabled=enabled, llm=llm, persona="PERSONA", is_for_me=lambda msg: True)
    bot = NS(command_prefix="!", get_cog=lambda n: brain if n == "Brain" else None)
    return recall_cog.Recall(bot)


class Typing:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def request(text, mentions=(), g=None):
    sent = []

    async def reply(content=None, **kw):
        sent.append((content, kw))

    chan = NS(id=50, typing=lambda: Typing())
    me = NS(display_name="FunBot", id=999)
    g = g or guild(Chan(1, [m(1, 10, "the first thing he said"), m(2, 10, "the second thing he said")]))
    g.me = NS(id=999, display_name="FunBot")
    return NS(content=text, clean_content=text, author=NS(id=5, bot=False, display_name="Dave"), channel=chan,
              guild=g, mentions=list(mentions), reply=reply, sent=sent)


DAVE = NS(id=10, bot=False, display_name="Dave")


def go(cog, msg):
    cog.seconds = 5
    asyncio.run(cog.on_message(msg))
    return msg.sent


def test_end_to_end_picks_the_ai_choice_and_posts_an_embed():
    llm = FakeLLM('{"pick": 1, "comment": "classic"}')
    cog = make_cog(llm)
    sent = go(cog, request("@FunBot find me a funny message @Dave said in the past", [DAVE]))
    assert len(sent) == 1 and sent[0][0] == "classic" and sent[0][1]["embed"].kw["description"].endswith("he said")
    assert llm.calls[0]["purpose"] == "recall" and "funny message" in llm.calls[0]["prompt"]
    assert "PERSONA" in llm.calls[0]["system"]


def test_ai_says_nothing_fits():
    sent = go(make_cog(FakeLLM('{"pick": 0, "comment": ""}')),
              request("@FunBot find me a message @Dave said about cheese", [DAVE]))
    assert "nothing" in sent[0][0].lower() and "embed" not in sent[0][1]


def test_budget_or_garbage_falls_back_to_a_message_without_comment():
    for llm in (FakeLLM(error=BudgetExceeded("cap")), FakeLLM("lol no")):
        sent = go(make_cog(llm), request("@FunBot find me something @Dave said", [DAVE]))
        assert sent[0][0] is None and "embed" in sent[0][1]


def test_nothing_found_for_that_person():
    sent = go(make_cog(FakeLLM("")), request("@FunBot find me something @Dave said", [NS(id=77, bot=False)]))
    assert "couldn't find" in sent[0][0]


def test_incomplete_search_adds_a_footer():
    cog = make_cog(FakeLLM('{"pick": 1, "comment": "x"}'))
    cog.max_scanned = 100
    big = Chan(1, [m(i, 10, f"some message {i} here", days=i) for i in range(1, 400)])
    sent = go(cog, request("@FunBot find me something @Dave said", [DAVE], g=guild(big)))
    assert "search back to" in sent[0][1]["embed"].footer


def test_cooldown_and_one_search_at_a_time():
    cog = make_cog(FakeLLM('{"pick": 1, "comment": "x"}'))
    cog.cooldown = 1000
    go(cog, request("@FunBot find me something @Dave said", [DAVE]))
    sent = go(cog, request("@FunBot find me something @Dave said", [DAVE]))
    assert "seconds" in sent[0][0]
    cog2 = make_cog(FakeLLM(""))
    cog2._busy.add(1)
    assert "already" in go(cog2, request("@FunBot find me something @Dave said", [DAVE]))[0][0]


def test_claims_only_real_requests_and_respects_switches():
    cog = make_cog(FakeLLM(""))
    assert cog.claims(request("@FunBot find me something @Dave said", [DAVE]))
    assert not cog.claims(request("@FunBot how are you", [DAVE]))
    assert not cog.claims(request("!find something @Dave said", [DAVE]))
    cog.enabled = False
    assert not cog.claims(request("@FunBot find me something @Dave said", [DAVE]))
    assert not make_cog(FakeLLM(""), enabled=False).claims(request("find me something @Dave said", [DAVE]))


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
