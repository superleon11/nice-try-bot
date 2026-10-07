"""Searches the server's message history for what particular people have said.

Nothing is stored: messages are read straight from Discord, only the best few candidates are kept in
memory while the scan runs, and everything is dropped afterwards. The scan is limited by time and
by number of messages, newest first, so on a very big server it may not reach the oldest messages.
"""

import logging
import random
import time
from dataclasses import dataclass, field

from helpers import Reservoir, TopN, clean_candidate, score_message

log = logging.getLogger(__name__)

TOPIC_N = 60      # messages matching the requested topic words
TOP_N = 40        # most-reacted
RANDOM_N = 60     # random sample of the rest


@dataclass
class Hit:
    message: object
    text: str
    reactions: int


@dataclass
class RecallResult:
    pool: list = field(default_factory=list)
    scanned: int = 0
    matched: int = 0           # messages by the wanted people that were usable
    channels_total: int = 0
    channels_done: int = 0     # channels read all the way back to their first message
    oldest: object = None      # date of the oldest message looked at

    @property
    def complete(self) -> bool:
        return self.channels_total > 0 and self.channels_done == self.channels_total


async def search_history(guild, asker, user_ids, topic, *, prefix="!", seconds=40.0, max_scanned=30000,
                         rng: random.Random = random, now=time.monotonic) -> RecallResult:
    """Read what `user_ids` (empty = anyone) wrote in channels both the bot and `asker` can read."""
    import discord   # imported here so tests can stub it

    channels = []
    for ch in guild.text_channels:
        mine, theirs = ch.permissions_for(guild.me), ch.permissions_for(asker)
        if mine.view_channel and mine.read_message_history and theirs.view_channel and theirs.read_message_history:
            channels.append(ch)
    rng.shuffle(channels)   # so a time-limited scan doesn't always favour the same channels

    wanted = set(user_ids)
    topic_hits = TopN(TOPIC_N)
    top = TopN(TOP_N)
    sample = Reservoir(RANDOM_N, rng)
    result = RecallResult(channels_total=len(channels))
    deadline = now() + seconds

    for i, ch in enumerate(channels):
        left = deadline - now()
        if left <= 0 or result.scanned >= max_scanned:
            break
        slice_end = now() + left / (len(channels) - i)   # share what's left of the time between channels
        finished = True
        try:
            async for m in ch.history(limit=None):   # newest first
                result.scanned += 1
                result.oldest = m.created_at if result.oldest is None else min(result.oldest, m.created_at)
                if wanted and m.author.id not in wanted:
                    pass
                elif not m.author.bot and m.type in (discord.MessageType.default, discord.MessageType.reply):
                    text = clean_candidate(m.content, prefix, min_len=8)
                    if text is not None:
                        result.matched += 1
                        reactions = sum(r.count for r in m.reactions)
                        hit = Hit(m, text, reactions)
                        low = text.lower()
                        if topic and any(w in low for w in topic):
                            topic_hits.push(score_message(reactions, len(text), rng), hit)
                        top.push(score_message(reactions, len(text), rng), hit)
                        sample.add(hit)
                if result.scanned >= max_scanned or now() > slice_end:
                    finished = False
                    break
        except discord.Forbidden:
            log.warning("No access to history of #%s", ch.name)
        if finished:
            result.channels_done += 1

    pool, taken = [], set()
    for hit in topic_hits.best() + top.best() + sample.items:
        if id(hit) not in taken:
            taken.add(id(hit))
            pool.append(hit)
    # With a topic, only keep the topic matches when there are enough of them to choose from.
    if topic and len(topic_hits) >= 3:
        pool = [h for h in pool if any(w in h.text.lower() for w in topic)]
    result.pool = pool
    return result
