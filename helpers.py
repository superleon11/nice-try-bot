"""Pure helper functions (no discord / database imports) so they are easy to test."""

import random
import re

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
