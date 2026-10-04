"""Finds a throwback by reading a random slice of the server's history straight from Discord.

Nothing is stored: messages stream past, only the best few candidates are kept in memory, and
everything is thrown away once one has been chosen.
"""

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone

import discord

from helpers import Reservoir, TopN, clean_candidate, random_window, score_message

log = logging.getLogger(__name__)

TOP_N = 40          # most-reacted candidates kept in memory per scanned window
RANDOM_N = 100      # plus a random sample of the rest, so funny-but-unreacted messages get a chance
PICK_FROM = 10      # without the AI, the final pick is random among the best this many


@dataclass
class Candidate:
    message: "discord.Message"
    text: str
    reactions: int


async def scan_window(guild, channels, start: datetime, end: datetime, prefix: str = "!",
                      rng: random.Random = random) -> tuple[list[Candidate], int, int]:
    """Read the given channels between start and end.

    Returns (candidate pool, how many messages were eligible, how many were scanned). The pool is the
    best-scoring messages first (best first), followed by a random sample of the others.
    """
    top = TopN(TOP_N)
    sample = Reservoir(RANDOM_N, rng)
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
                cand = Candidate(m, text, reactions)
                top.push(score_message(reactions, len(text), rng), cand)
                sample.add(cand)
        except discord.Forbidden:
            log.warning("No access to history of #%s", channel.name)
    pool = top.best()
    taken = {id(c) for c in pool}
    pool += [c for c in sample.items if id(c) not in taken]
    return pool, eligible, scanned


async def find_pool(guild, channels, prefix: str = "!", window_days: int = 30, *,
                    max_attempts: int = 6, min_eligible: int = 15,
                    rng: random.Random = random) -> list[Candidate]:
    """Pick random windows until one has enough material; return that window's candidate pool."""
    if not channels:
        return []
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
    return chosen[1] if chosen else []


async def find_throwback(guild, channels, prefix: str = "!", window_days: int = 30, *,
                         max_attempts: int = 6, min_eligible: int = 15,
                         rng: random.Random = random) -> Candidate | None:
    """Without the AI: pick one of the best (most-reacted) messages of a random window."""
    pool = await find_pool(guild, channels, prefix, window_days, max_attempts=max_attempts,
                           min_eligible=min_eligible, rng=rng)
    return rng.choice(pool[:PICK_FROM]) if pool else None
