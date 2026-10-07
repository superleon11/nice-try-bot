"""Tests context.py (replied-to / linked / forwarded messages).  Run: python tests/test_context.py"""

import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import context  # noqa: E402

NS = types.SimpleNamespace
G, BOT = 1, 999
PERMS_OK = NS(view_channel=True, read_message_history=True)
PERMS_NO = NS(view_channel=False, read_message_history=False)


def msg(mid, text, name="Sam", uid=7, **kw):
    d = dict(id=mid, content=text, clean_content=text, author=NS(id=uid, display_name=name),
             embeds=[], attachments=[], message_snapshots=[])
    d.update(kw)
    return NS(**d)


class Chan:
    def __init__(self, cid, store, me, denied_for=()):
        self.id, self.store, self.denied_for = cid, store, denied_for
        self.guild = NS(id=G, me=me)

    def permissions_for(self, who):
        return PERMS_NO if who in self.denied_for else PERMS_OK

    async def fetch_message(self, mid):
        if mid not in self.store:
            raise RuntimeError("404")
        return self.store[mid]


def setup(denied_for=()):
    me, asker = NS(id=BOT), NS(id=5, display_name="Dave")
    store = {100: msg(100, "pineapple belongs on pizza"), 101: msg(101, "see ya", name="Lee", uid=8)}
    chan = Chan(50, store, me, denied_for=[asker] if denied_for else [])
    bot = NS(get_channel=lambda cid: chan if cid == 50 else None)
    return bot, chan, asker, store


def mk(content, chan, asker, reference=None):
    return NS(id=200, content=content, clean_content=content, author=asker, channel=chan,
              guild=chan.guild, reference=reference)


def run(coro):
    return asyncio.run(coro)


def test_reply_that_discord_already_resolved():
    bot, chan, asker, store = setup()
    ref = NS(resolved=store[100], message_id=100, channel_id=50)
    text, msgs = run(context.context_block(mk("@bot is this true?", chan, asker, ref), bot, BOT))
    assert "Sam: pineapple belongs on pizza" in text and "replying to" in text
    assert msgs == [store[100]]


def test_reply_that_has_to_be_fetched():
    bot, chan, asker, store = setup()
    ref = NS(resolved=None, message_id=100, channel_id=50)
    text, _ = run(context.context_block(mk("thoughts?", chan, asker, ref), bot, BOT))
    assert "pineapple" in text


def test_deleted_reply_target_is_skipped():
    bot, chan, asker, store = setup()
    ref = NS(resolved=NS(id=100), message_id=555, channel_id=50)   # deleted: no author, can't be fetched
    assert run(context.context_block(mk("hm", chan, asker, ref), bot, BOT)) == ("", [])


def test_linked_messages_same_server_only_and_capped():
    bot, chan, asker, store = setup()
    store[102] = msg(102, "third")
    links = " ".join(f"https://discord.com/channels/{G}/50/{i}" for i in (100, 101, 102))
    other = f"https://discord.com/channels/777/50/100"
    text, msgs = run(context.context_block(mk(f"what about {links} {other}", chan, asker), bot, BOT))
    assert len(msgs) == context.MAX_LINKS and "A message they linked to" in text
    text, msgs = run(context.context_block(mk(f"look {other}", chan, asker), bot, BOT))
    assert (text, msgs) == ("", [])    # another server's message is never read


def test_private_channel_messages_are_not_leaked_to_someone_who_cannot_see_them():
    bot, chan, asker, store = setup(denied_for=True)
    link = f"https://discord.com/channels/{G}/50/100"
    assert run(context.context_block(mk(link, chan, asker), bot, BOT)) == ("", [])


def test_replying_to_the_bot_labels_it_you_and_same_message_not_repeated():
    bot, chan, asker, store = setup()
    store[100] = msg(100, "earlier answer", name="FunBot", uid=BOT)
    ref = NS(resolved=store[100], message_id=100, channel_id=50)
    text, msgs = run(context.context_block(
        mk(f"https://discord.com/channels/{G}/50/100 why", chan, asker, ref), bot, BOT))
    assert "You: earlier answer" in text and len(msgs) == 1


def test_embeds_forwards_and_attachments_are_described():
    emb = NS(title="Big news", description="Cats can fly", fields=[NS(name="Source", value="trust me")])
    snap = NS(content="forwarded words", embeds=[], attachments=[NS(filename="cat.png")])
    d = context.describe_message(msg(1, "", embeds=[emb], message_snapshots=[snap],
                                     attachments=[NS(filename="a.jpg")]))
    assert "Cats can fly" in d and "Source: trust me" in d and "forwarded words" in d
    assert "cat.png" in d and "a.jpg" in d
    assert context.describe_message(msg(2, "")) == ""


def test_long_messages_are_truncated():
    assert len(context.describe_message(msg(1, "x " * 2000))) < 760


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} passed")
