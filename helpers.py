"""Pure helper functions (no discord / database imports) so they are easy to test."""

import heapq
import itertools
import random
import re
from datetime import datetime, timedelta

# (trigger words, replies). First matching group wins; a random reply is picked from it.
REPLY_GROUPS = [
    (
        {"thanks", "thx", "thank", "ty"},
        [
            "Oh wow, gratitude. In *this* economy?",
            "You're welcome. I accept payment in memes.",
            "Aww, no problem!",
        ],
    ),
    (
        {"lol", "lmao", "haha", "rofl"},
        [
            "I laughed. Internally. In binary.",
            "This is the way.",
            "Sheesh.",
        ],
    ),
    (
        {"gm", "morning"},
        [
            "Good morning! Hydrate or diedrate.",
            "Rise and grind. Or rise and scroll, I won't judge.",
        ],
    ),
    (
        {"gn", "goodnight", "night"},
        [
            "Sleep well! The messages will still be here.",
            "Night night. Don't let the bugs bite.",
        ],
    ),
    (
        {"win", "won", "nice", "congrats", "awesome", "great"},
        [
            "That's really great, keep being awesome!",
            "Absolute legend behaviour.",
            "No cap, that's impressive.",
        ],
    ),
    (
        {"bored", "boring"},
        [
            "Bored? Have you tried touching grass?",
            "Boredom is just creativity in a trench coat.",
        ],
    ),
    (
        {"fail", "broken", "bug", "crashed", "crash"},
        [
            "Have you tried turning it off and on again?",
            "Works on my machine. 🤷",
            "F in the chat.",
        ],
    ),
]

MENTION_REPLIES = [
    "You rang?",
    "I'm here, I'm here. What did I miss?",
    "Yes? I was busy being a bot.",
    "Present!",
]

_WORD_RE = re.compile(r"[a-z0-9']+")


def pick_reply(text: str, rng: random.Random = random) -> str | None:
    """Return a reply if the text contains a trigger word, else None."""
    words = set(_WORD_RE.findall(text.lower()))
    if not words:
        return None
    for triggers, replies in REPLY_GROUPS:
        if words & triggers:
            return rng.choice(replies)
    return None


def pick_mention_reply(rng: random.Random = random) -> str:
    return rng.choice(MENTION_REPLIES)


def format_duration(total_seconds: int) -> str:
    """1h 05m style duration."""
    total_seconds = max(0, int(total_seconds))
    hours, rem = divmod(total_seconds, 3600)
    minutes = rem // 60
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


# ---- throwback helpers ----------------------------------------------------------------------

_URL_ONLY_RE = re.compile(r"^(https?://\S+\s*)+$")
_MASS_MENTIONS = ("@everyone", "@here")


def clean_candidate(content: str | None, prefix: str = "!",
                    min_len: int = 15, max_len: int = 600) -> str | None:
    """Return the message text if it is worth considering for a throwback, else None."""
    text = (content or "").strip()
    if not (min_len <= len(text) <= max_len):
        return None
    if text.startswith(prefix) or text.startswith("/"):
        return None  # bot commands
    if _URL_ONLY_RE.match(text):
        return None  # just a link
    if any(m in text for m in _MASS_MENTIONS):
        return None
    return text


def score_message(reactions: int, length: int, rng: random.Random = random) -> float:
    """Higher = more likely to be a good throwback. Reactions dominate; a little length and luck."""
    length_bonus = min(length, 300) / 150  # at most 2 points
    return reactions * 3 + length_bonus + rng.random()


def random_window(earliest: datetime, latest: datetime, days: int = 30,
                  rng: random.Random = random) -> tuple[datetime, datetime]:
    """A random span of `days` days that lies between earliest and latest."""
    span = timedelta(days=days)
    if latest - earliest <= span:
        return earliest, latest
    start = earliest + (latest - span - earliest) * rng.random()
    return start, start + span


class TopN:
    """Keeps only the N highest-scoring items, so we never hold a whole window in memory."""

    def __init__(self, n: int):
        self.n = n
        self._heap: list = []
        self._counter = itertools.count()  # tie-breaker so items themselves are never compared

    def push(self, score: float, item) -> None:
        entry = (score, next(self._counter), item)
        if len(self._heap) < self.n:
            heapq.heappush(self._heap, entry)
        elif score > self._heap[0][0]:
            heapq.heapreplace(self._heap, entry)

    def best(self) -> list:
        """Items, best first."""
        return [item for _, _, item in sorted(self._heap, reverse=True)]

    def __len__(self) -> int:
        return len(self._heap)
