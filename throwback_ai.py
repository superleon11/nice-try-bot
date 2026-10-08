"""Lets the AI choose the throwback from a pool of candidate messages and dress it up.

One call returns the pick, a one-line comment in the bot's voice, and a prompt for an illustration.
"""

import logging
import random
from dataclasses import dataclass

from helpers import (
    JUDGE_RULES, TOP_RULES, format_judge_prompt, parse_judge_reply, parse_top_reply, truncate,
)

log = logging.getLogger(__name__)


@dataclass
class Verdict:
    candidate: object
    comment: str
    image_prompt: str


async def judge_pool(llm, model: str, persona: str, pool: list, rng: random.Random = random,
                     min_pool: int = 2) -> Verdict | None:
    """Ask the model for the best message in `pool`. None if the reply was unusable.

    Raises llm.BudgetExceeded / llm.LLMError like any other call, for the caller to handle.
    """
    if len(pool) < min_pool:
        return None
    shuffled = list(pool)
    rng.shuffle(shuffled)   # so list position can't bias the choice
    entries = [(c.message.author.display_name, c.reactions, truncate(c.text, 400)) for c in shuffled]
    raw = await llm.complete(
        model=model, system=persona + "\n\n" + JUDGE_RULES, prompt=format_judge_prompt(entries),
        max_tokens=600, purpose="throwback",
    )
    parsed = parse_judge_reply(raw, len(shuffled))
    if parsed is None:
        log.warning("Could not understand the throwback judge's reply: %r", raw[:200])
        return None
    index, comment, image_prompt = parsed
    return Verdict(shuffled[index], comment, image_prompt)


async def judge_top(llm, model: str, persona: str, pool: list, k: int = 3,
                    rng: random.Random = random) -> list:
    """Ask the model for the k best candidates in `pool` (best-effort: may return fewer, or [] if the
    reply was unusable). Raises llm.BudgetExceeded / llm.LLMError for the caller to handle."""
    if len(pool) <= k:
        return list(pool)
    shuffled = list(pool)
    rng.shuffle(shuffled)   # so list position can't bias the choice
    entries = [(c.message.author.display_name, c.reactions, truncate(c.text, 400)) for c in shuffled]
    raw = await llm.complete(
        model=model, system=persona + "\n\n" + TOP_RULES.format(k=k), prompt=format_judge_prompt(entries),
        max_tokens=100, purpose="throwback-shortlist",
    )
    picks = parse_top_reply(raw, len(shuffled), k)
    if not picks:
        log.warning("Could not understand the throwback shortlist reply: %r", (raw or "")[:200])
    return [shuffled[i] for i in picks]
