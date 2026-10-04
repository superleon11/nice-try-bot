"""Pure helper functions (no discord / database imports) so they are easy to test."""

import heapq
import itertools
import json
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


# ---- memory (notes about people) ---------------------------------------------------------------

MEMORY_SYSTEM = (
    "You keep short notes about members of a small friend-group Discord server, to help a "
    "funny bot make good inside jokes about them. You are given each person's existing notes "
    "(with ids and a source) and some of their recent messages. For each person decide what "
    "to add or remove.\n"
    "- Add short notes (max about 15 words each): lasting facts, habits, opinions, nicknames, "
    "running jokes, memorable things they said. Only add what the messages clearly support, and "
    "never repeat an existing note.\n"
    "- Remove a note only if its source is 'auto' and it is a duplicate or clearly outdated. "
    "Never remove a 'manual' note.\n"
    "- Adding nothing is fine.\n"
    'Reply with ONLY JSON: {"users": [{"user_id": "<id>", "add": ["note", ...], "remove": [<note id>, ...]}]}'
)


def format_memory_prompt(people: list[dict]) -> str:
    """people: [{"user_id", "name", "notes": [(id, source, text)], "messages": [str]}]"""
    parts = []
    for p in people:
        lines = [f"### user_id={p['user_id']} name={p['name']}"]
        lines.append("Existing notes:" + ("" if p["notes"] else " (none)"))
        for note_id, source, text in p["notes"]:
            lines.append(f"  [{note_id} {source}] {text}")
        lines.append("Recent messages:")
        lines.extend(f"  - {m}" for m in p["messages"])
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def parse_memory_update(text: str, valid: dict[int, set[int]]) -> dict[int, tuple[list[str], list[int]]]:
    """Parse the model's JSON reply into {user_id: (notes_to_add, note_ids_to_remove)}.

    `valid` maps each user we asked about to the ids of their AI-written notes. Anything about other
    users, and removals of ids that are not AI-written notes of that user, is ignored. Garbage in
    gives an empty result rather than an error.
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return {}
    entries = data.get("users") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return {}
    result: dict[int, tuple[list[str], list[int]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            user_id = int(entry.get("user_id"))
        except (TypeError, ValueError):
            continue
        if user_id not in valid:
            continue
        adds: list[str] = []
        raw_adds = entry.get("add")
        for note in raw_adds if isinstance(raw_adds, list) else []:
            if not isinstance(note, str):
                continue
            note = " ".join(note.split())
            if 3 <= len(note) <= 200 and note.lower() not in {a.lower() for a in adds}:
                adds.append(note)
        removes: list[int] = []
        raw_removes = entry.get("remove")
        for rid in raw_removes if isinstance(raw_removes, list) else []:
            try:
                rid = int(rid)
            except (TypeError, ValueError):
                continue
            if rid in valid[user_id] and rid not in removes:
                removes.append(rid)
        result[user_id] = (adds, removes)
    return result


# ---- image requests ---------------------------------------------------------

_IMAGE_REQUEST = re.compile(
    r"^\s*(?:(?:hey|yo|ok|okay|please|pls|can you|could you|can u|would you)[,\s]+)*"
    r"(?:generate|make|create|draw|imagine|render|paint)\s+(?:me\s+|us\s+)?(?:an?\s+|the\s+|some\s+)?"
    r"(?:image|picture|pic|photo|drawing|illustration)s?\b"
    r"[\s,:\-]*(?:of|showing|with|where|that|depicting)?\b\s*(?P<what>.*)$",
    re.IGNORECASE | re.DOTALL,
)


def parse_image_request(text: str):
    """None if this isn't a request for an image, otherwise the description ('' if they gave none).

    Only matches at the START of the message, e.g. "generate me an image of a cat in a hat".
    """
    m = _IMAGE_REQUEST.match(text or "")
    if not m:
        return None
    return " ".join(m.group("what").split()).strip(" ?!.,:;-")
