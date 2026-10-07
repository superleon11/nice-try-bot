"""Pure helper functions (no discord / database imports) so they are easy to test."""

import heapq
import itertools
import json
import random
import re
from datetime import datetime, time, timedelta, timezone

# (trigger words, replies). First matching group wins; a random reply is picked from it.
REPLY_GROUPS = [
    (
        {"thanks", "thx", "thank", "ty"},
        [
            "No problem!",
            "You're welcome.",
            "Anytime.",
        ],
    ),
    (
        {"lol", "lmao", "haha", "rofl"},
        [
            "Ha, that's a good one.",
            "That got me.",
            "Fair enough, that's funny.",
        ],
    ),
    (
        {"gm", "morning"},
        [
            "Morning!",
            "Good morning, hope you slept well.",
        ],
    ),
    (
        {"gn", "goodnight", "night"},
        [
            "Night!",
            "Goodnight, sleep well.",
        ],
    ),
    (
        {"win", "won", "nice", "congrats", "awesome", "great"},
        [
            "Nice one!",
            "Well done.",
            "That's brilliant, congrats.",
        ],
    ),
    (
        {"bored", "boring"},
        [
            "Bored? Maybe get a game going.",
            "Same, honestly. What's everyone up for?",
        ],
    ),
    (
        {"fail", "broken", "bug", "crashed", "crash"},
        [
            "Have you tried turning it off and on again?",
            "Ah, that's annoying. Hope it's an easy fix.",
            "Rough. Good luck with it.",
        ],
    ),
]

MENTION_REPLIES = [
    "Hey, what's up?",
    "I'm here, what do you need?",
    "Yep?",
    "What can I do for you?",
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
                  rng: random.Random = random, min_fraction: float = 1.0) -> tuple[datetime, datetime]:
    """A random span between earliest and latest. Its length is `days`, or, if min_fraction < 1,
    a random length between min_fraction * days and days. Its position is uniform over the range."""
    length = days * (min_fraction + (1.0 - min_fraction) * rng.random())
    span = timedelta(days=length)
    if latest - earliest <= span:
        return earliest, latest
    start = earliest + (latest - span - earliest) * rng.random()
    return start, start + span


def windows_overlap(a: tuple[datetime, datetime], b: tuple[datetime, datetime]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


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


def pick_run_time(now: datetime, tz, start_hour: int, end_hour: int, posted_today: bool,
                  rng: random.Random = random) -> datetime:
    """When should the next daily post happen? A random moment between start_hour and end_hour
    (local time in `tz`), returned as an aware UTC datetime.

    If today's window hasn't ended and nothing was posted today, that's today (never in the past:
    a restart at 12:00 picks a time between 12:00 and the end of the window). Otherwise tomorrow.
    """
    now_local = now.astimezone(tz)
    day = now_local.date()
    for offset in range(0, 3):
        d = day + timedelta(days=offset)
        if offset == 0 and posted_today:
            continue
        start = datetime.combine(d, time(start_hour), tzinfo=tz).astimezone(timezone.utc)
        end = datetime.combine(d, time(end_hour), tzinfo=tz).astimezone(timezone.utc)
        start = max(start, now.astimezone(timezone.utc))
        if start < end:
            return start + (end - start) * rng.random()
    raise ValueError("start_hour must be earlier than end_hour")


class Reservoir:
    """A uniform random sample of up to N items from a stream, without holding the whole stream."""

    def __init__(self, n: int, rng: random.Random = random):
        self.n, self.rng, self.items, self.seen = n, rng, [], 0

    def add(self, item) -> None:
        self.seen += 1
        if len(self.items) < self.n:
            self.items.append(item)
        else:
            j = self.rng.randrange(self.seen)
            if j < self.n:
                self.items[j] = item


# ---- throwback judging ---------------------------------------------------------------------------

JUDGE_RULES = (
    "You are picking the Throwback of the Day for a friend-group Discord server. You will be shown a "
    "numbered list of old messages from one slice of the server's history, each with its author and "
    "how many reactions it got (reactions are only a hint: a funny message with no reactions can beat "
    "a popular boring one). Choose the single funniest or most interesting message: something that "
    "stands alone without needing context, is memorable, and will make the group laugh or reminisce. "
    "Then write:\n"
    '- "comment": ONE short line of commentary on your pick, in your own voice (under 200 characters).\n'
    '- "image_prompt": a prompt for a funny cartoon-style illustration of the scene or idea in the '
    "message (1-3 sentences). Describe it with generic cartoon characters, no real-person likeness, "
    "and no text or lettering in the image.\n"
    'Reply with ONLY JSON: {"pick": <number>, "comment": "...", "image_prompt": "..."}'
)


def format_judge_prompt(entries: list[tuple[str, int, str]]) -> str:
    """entries: (author name, reaction count, text). Numbered from 1."""
    lines = []
    for i, (author, reactions, text) in enumerate(entries, 1):
        tag = f"{author}, {reactions} reactions" if reactions else author
        lines.append(f"[{i}] ({tag}) {' '.join(text.split())}")
    return "Messages:\n" + "\n".join(lines)


def parse_judge_reply(raw: str, n: int):
    """-> (index 0..n-1, comment, image_prompt) or None if the reply is unusable."""
    if not raw:
        return None
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
        pick = int(data["pick"])
    except (ValueError, KeyError, TypeError):
        return None
    if not 1 <= pick <= n:
        return None
    comment = str(data.get("comment") or "").strip().strip('"')
    image_prompt = str(data.get("image_prompt") or "").strip()
    return pick - 1, truncate(comment, 250) if comment else "", truncate(image_prompt, 800)


# ---- emoji reactions ----------------------------------------------------------------------------

DEFAULT_REACTIONS = ["😂", "💀", "😭", "🔥", "👀", "🤔", "😬", "🙃", "🫡", "👏", "💯", "😎", "🥲", "🍿", "🫠", "🤨", "😳", "👍"]

REACTION_RULES = (
    "Pick 1 to 3 emoji that someone might react with to this chat message: matching its mood or "
    "content, and funny or ironic is welcome. Reply with ONLY the emoji, separated by spaces, "
    "no words."
)


def parse_emoji_reply(raw: str, max_n: int = 3) -> list[str]:
    """Pull plain emoji out of a model reply. Anything containing letters or digits is dropped."""
    out = []
    for token in (raw or "").split():
        if len(token) > 12 or any(ch.isascii() and ch.isalnum() for ch in token):
            continue
        if token not in out:
            out.append(token)
    return out[:max_n]


def choose_random_emojis(unicode_pool: list, custom_pool: list, rng: random.Random = random,
                         custom_chance: float = 0.4, two_chance: float = 0.2) -> list:
    """One emoji (sometimes two), from the server's custom emoji some of the time if it has any."""
    pools = [p for p in (unicode_pool, custom_pool) if p]
    if not pools:
        return []
    picks = []
    for _ in range(2 if rng.random() < two_chance else 1):
        pool = custom_pool if (custom_pool and (not unicode_pool or rng.random() < custom_chance)) else unicode_pool
        choice = rng.choice(pool)
        if choice not in picks:
            picks.append(choice)
    return picks


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


# ---- "find something @user said" requests ----------------------------------------------------------

_RECALL_VERB = re.compile(
    r"\b(find|search|look(?:\s+up|\s+for)?|dig(?:\s+up|\s+out)?|pull(?:\s+up)?|show|get|give|remind|"
    r"recall|remember|what(?:'s|s|\s+is|\s+was|\s+were|\s+did)|which|who)\b", re.IGNORECASE)
_RECALL_SAID = re.compile(r"\b(said|says|say|wrote|written|posted|sent|typed|messages?|quotes?|texted)\b",
                          re.IGNORECASE)
_YOU_SAID = re.compile(r"\byou(?:'ve|ve|\s+have)?\s+(?:ever\s+)?(?:said|say|wrote|sent|posted)\b", re.IGNORECASE)
_SELF_WORDS = re.compile(r"\b(i|i've|ive|my|mine)\b", re.IGNORECASE)
_ANYONE_WORDS = re.compile(r"\b(anyone|anybody|someone|somebody|everyone|everybody|ever|server|chat|"
                           r"past|old|history|archive)\b", re.IGNORECASE)
_TOPIC = re.compile(r"\b(?:about|regarding|mentioning|containing|involving|on the subject of)\s+(?P<t>[^?.!\n]+)",
                    re.IGNORECASE)
_TOPIC_STOP = {"the", "and", "that", "this", "with", "from", "have", "been", "they", "them", "their", "what",
               "when", "where", "which", "were", "was", "for", "his", "her", "its", "has", "had", "you",
               "your", "ever", "said", "said.", "like", "just", "some", "any"}


def parse_recall_request(text: str, has_user_mentions: bool):
    """Is this "find me a message @user said"? -> None, or (scope, topic_words).

    scope is 'mentioned' (the @-ed people), 'self' (the person asking) or 'anyone'.
    topic_words are lowercase words from an "about ..." phrase, to narrow the search.
    """
    text = text or ""
    if not (_RECALL_VERB.search(text) and _RECALL_SAID.search(text)):
        return None
    if not has_user_mentions and _YOU_SAID.search(text):
        return None   # asking about the bot itself, not searching history
    if has_user_mentions:
        scope = "mentioned"
    elif _SELF_WORDS.search(text):
        scope = "self"
    elif _ANYONE_WORDS.search(text):
        scope = "anyone"
    else:
        return None
    topic = []
    m = _TOPIC.search(text)
    if m:
        for w in re.findall(r"[a-z0-9']+", m.group("t").lower()):
            if len(w) >= 3 and w not in _TOPIC_STOP and w not in topic:
                topic.append(w)
    return scope, topic[:6]


RECALL_RULES = (
    "Someone in a friend-group Discord server asked you to dig up a message from its history. You will "
    "get their request and a numbered list of old messages (author, date, reactions). Choose the one "
    "that best matches what they asked for (funniest, most embarrassing, most wholesome, about a topic, "
    "and so on); when they just ask for a good one, pick the funniest or most memorable. Reactions are "
    "only a hint. If nothing in the list fits at all, use 0. Write a short comment (under 150 characters) "
    "in your own voice. Reply with ONLY JSON: "
    '{"pick": <number or 0>, "comment": "..."}'
)


def format_recall_prompt(request: str, entries: list[tuple[str, str, int, str]]) -> str:
    """entries: (author name, date text, reaction count, text). Numbered from 1."""
    lines = []
    for i, (author, when, reactions, text) in enumerate(entries, 1):
        tag = f"{author}, {when}" + (f", {reactions} reactions" if reactions else "")
        lines.append(f"[{i}] ({tag}) {' '.join(text.split())}")
    return f"Their request: {' '.join(request.split())}\n\nMessages:\n" + "\n".join(lines)
