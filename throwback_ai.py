"""Lets the AI choose the throwback from a pool of candidate messages and dress it up.

One call returns the pick, a one-line comment in the bot's voice, and a prompt for an illustration.
"""

import logging
import random
from dataclasses import dataclass

from helpers import JUDGE_RULES, format_judge_prompt, parse_judge_reply, truncate

log = logging.getLogger(__name__)


@dataclass
class Verdict:
    candidate: object
    comment: str
    image_prompt: str


async def judge_pool(llm, model: str, persona: str, pool: list, rng: random.Random = random) -> Verdict | None:
    """Ask the model for the best message in `pool`. None if the reply was unusable.

    Raises llm.BudgetExceeded / llm.LLMError like any other call, for the caller to handle.
    """
    if len(pool) < 2:
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
