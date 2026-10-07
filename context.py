"""Works out what a message is *about*, beyond its own text.

When someone replies to a message (or pastes a link to one, or quotes it) and tags the bot, the
thing they are pointing at is the interesting part. This module fetches those messages and turns
them, and embeds, forwards and attachments, into plain text the model can read.

It only duck-types discord.py objects (no isinstance checks), so it is easy to test.
"""

import logging
import re

from helpers import truncate

log = logging.getLogger(__name__)

LINK_RE = re.compile(r"https?://(?:\w+\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)")
MAX_LINKS = 2
PER_MESSAGE_LIMIT = 700


def _squash(text: str | None) -> str:
    return " ".join((text or "").split())


def describe_embeds(embeds) -> list[str]:
    """Readable text from a message's embeds (link previews, bot posts, etc.)."""
    out = []
    for e in embeds or []:
        bits = [getattr(e, "title", None), getattr(e, "description", None)]
        for f in getattr(e, "fields", None) or []:
            bits.append(f"{getattr(f, 'name', '')}: {getattr(f, 'value', '')}")
        text = _squash(" ".join(b for b in bits if b))
        if text:
            out.append(text)
    return out


def describe_message(m, bot_id: int | None = None, limit: int = PER_MESSAGE_LIMIT) -> str:
    """'Name: what they wrote [embed: ...] [forwarded: ...] [attached: file.png]' for one message."""
    author = getattr(m, "author", None)
    who = "You" if (bot_id is not None and getattr(author, "id", None) == bot_id) else \
        getattr(author, "display_name", None) or "Someone"
    parts = []
    text = _squash(getattr(m, "clean_content", None) or getattr(m, "content", None))
    if text:
        parts.append(text)
    for snap in getattr(m, "message_snapshots", None) or []:   # forwarded messages
        inner = _squash(getattr(snap, "content", None))
        emb = describe_embeds(getattr(snap, "embeds", None))
        files = [a.filename for a in getattr(snap, "attachments", None) or []]
        bits = [b for b in (inner, " / ".join(emb)) if b]
        if files:
            bits.append("attached: " + ", ".join(files))
        if bits:
            parts.append("[forwarded: " + " ".join(bits) + "]")
    emb = describe_embeds(getattr(m, "embeds", None))
    if emb:
        parts.append("[embed: " + " / ".join(emb) + "]")
    files = [a.filename for a in getattr(m, "attachments", None) or []]
    if files:
        parts.append("[attached: " + ", ".join(files) + "]")
    if not parts:
        return ""
    return f"{who}: {truncate(' '.join(parts), limit)}"


async def _fetch(bot, guild_id: int, channel_id: int, message_id: int, asker, fallback_channel):
    """Fetch a message from this guild, only if the bot AND the asker are allowed to read it there."""
    channel = bot.get_channel(channel_id) or (fallback_channel if fallback_channel.id == channel_id else None)
    if channel is None or getattr(getattr(channel, "guild", None), "id", None) != guild_id:
        return None
    try:
        for who in (channel.guild.me, asker):
            perms = channel.permissions_for(who)
            if not (perms.view_channel and perms.read_message_history):
                return None
        return await channel.fetch_message(message_id)
    except Exception:   # not found, forbidden, network...: just carry on without it
        log.debug("Could not fetch message %s", message_id, exc_info=True)
        return None


async def referenced_messages(message, bot, max_links: int = MAX_LINKS) -> tuple[list, list]:
    """(the message being replied to or None-list, linked messages): both as lists of messages.

    Returns (replied_to, linked). replied_to has zero or one message.
    """
    guild_id = message.guild.id
    seen = {getattr(message, "id", None)}
    replied, linked = [], []

    ref = getattr(message, "reference", None)
    if ref is not None:
        target = getattr(ref, "resolved", None)
        if target is None or not hasattr(target, "author"):   # not cached, or deleted
            mid = getattr(ref, "message_id", None)
            if mid:
                cid = getattr(ref, "channel_id", None) or message.channel.id
                target = await _fetch(bot, guild_id, cid, mid, message.author, message.channel)
            else:
                target = None
        if target is not None and hasattr(target, "author"):
            replied.append(target)
            seen.add(getattr(target, "id", None))

    for g, c, mid in LINK_RE.findall(message.content or ""):
        if len(linked) >= max_links:
            break
        if int(g) != guild_id or int(mid) in seen:
            continue
        seen.add(int(mid))
        found = await _fetch(bot, guild_id, int(c), int(mid), message.author, message.channel)
        if found is not None:
            linked.append(found)
    return replied, linked


async def context_block(message, bot, bot_id: int) -> tuple[str, list]:
    """Prompt text describing the replied-to and linked messages, plus those messages themselves
    (so callers can look up notes about their authors). ('', []) when there is nothing."""
    replied, linked = await referenced_messages(message, bot)
    lines = []
    for m in replied:
        d = describe_message(m, bot_id)
        if d:
            lines.append(f"The message they are replying to, so this is what they mean by 'this', "
                         f"'that' or 'it': {d}")
    for m in linked:
        d = describe_message(m, bot_id)
        if d:
            lines.append(f"A message they linked to: {d}")
    return "\n".join(lines), replied + linked
