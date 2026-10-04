"""Finds a throwback by reading a random slice of the server's history straight from Discord.

Nothing is stored: messages stream past, only the best few candidates are kept in memory, and
everything is thrown away once one has been chosen.
"""

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone

import discord

from helpers import TopN, clean_candidate, random_window, score_message

log = logging.getLogger(__name__)

TOP_N = 25          # candidates kept in memory per scanned window
PICK_FROM = 10      # the final pick is random among the best this many


@dataclass
class Candidate:
    message: "discord.Message"
    text: str
    reactions: int


async def scan_window(guild, channels, start: datetime, end: datetime, prefix: str = "!",
                      rng: random.Random = random) -> tuple[list[Candidate], int, int]:
    """Read the given channels between start and end.

    Returns (best candidates, how many messages were eligible, how many were scanned).
    """
    top = TopN(TOP_N)
    eligible = scanned = 0
    for channel in channels:
        if channel.created_at > end:
            continue
        perms = channel.permissions_for(guild.me)
        if not (perms.view_channel and perms.read_message_history):
            continue
        try:
            async for m in channel.history(limit=None, after=start, before=end, oldest_first=True):
                scanned += 1
                if m.author.bot or m.type not in (discord.MessageType.default, discord.MessageType.reply):
                    continue
                text = clean_candidate(m.content, prefix)
                if text is None:
                    continue
                eligible += 1
                reactions = sum(r.count for r in m.reactions)
                top.push(score_message(reactions, len(text), rng), Candidate(m, text, reactions))
        except discord.Forbidden:
            log.warning("No access to history of #%s", channel.name)
    return top.best(), eligible, scanned


async def find_throwback(guild, channels, prefix: str = "!", window_days: int = 30, *,
                         max_attempts: int = 6, min_eligible: int = 15,
                         rng: random.Random = random) -> Candidate | None:
    """Pick random windows until one has enough material, then choose one of its best messages."""
    if not channels:
        return None
    earliest = min(c.created_at for c in channels)  # nothing can exist before the channel did
    now = datetime.now(timezone.utc)
    chosen: tuple[int, list[Candidate]] | None = None
    for attempt in range(1, max_attempts + 1):
        start, end = random_window(earliest, now, window_days, rng)
        candidates, eligible, scanned = await scan_window(guild, channels, start, end, prefix, rng)
        log.info("Throwback attempt %d: %s to %s, scanned %d messages, %d eligible",
                 attempt, start.date(), end.date(), scanned, eligible)
        if chosen is None or eligible > chosen[0]:
            chosen = (eligible, candidates)
        if eligible >= min_eligible:
            break
    if chosen is None or not chosen[1]:
        return None
    return rng.choice(chosen[1][:PICK_FROM])
