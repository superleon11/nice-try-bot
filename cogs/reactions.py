"""Randomly reacts to messages with emoji.

By default about 8% of messages get 1-2 reactions, with a short cooldown per channel. If the AI is on
(ANTHROPIC_API_KEY) the model picks emoji that fit the message, using a cheap model; otherwise, or if
the AI fails or the cost cap is hit, it picks randomly from a built-in list (plus the server's own
custom emoji). Needs the Add Reactions permission.
"""

import logging
import os
import random
import re
import time

import discord
from discord.ext import commands

from envutil import env_bool, env_float
from helpers import DEFAULT_REACTIONS, REACTION_RULES, choose_random_emojis, parse_emoji_reply
from llm import BudgetExceeded, LLMError

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class Reactions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.chance = min(1.0, max(0.0, env_float("REACT_CHANCE", 0.08)))
        self.cooldown = max(0.0, env_float("REACT_COOLDOWN_SECONDS", 20))
        self.channels = {int(x) for x in os.getenv("REACT_CHANNEL_IDS", "").replace(" ", "").split(",") if x.isdigit()}
        self.use_server_emojis = env_bool("REACT_USE_SERVER_EMOJIS", True)
        self.use_ai = env_bool("REACT_AI", True)
        self.model = os.getenv("LLM_REACTION_MODEL", "").strip() or DEFAULT_MODEL
        custom = [t for t in re.split(r"[,\s]+", os.getenv("REACT_EMOJIS", "").strip()) if t]
        self.pool = custom or list(DEFAULT_REACTIONS)
        self._last: dict[int, float] = {}    # channel id -> time.monotonic() of the last reaction
        self._warned_permissions = False

    async def cog_load(self) -> None:
        if self.chance > 0:
            log.info("Reactions on: %.0f%% of messages, %ds cooldown, %s, %s", self.chance * 100, self.cooldown,
                     f"{len(self.channels)} channel(s)" if self.channels else "all channels",
                     "AI picks when available" if self.use_ai else "random picks only")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if self.chance <= 0 or message.author.bot or message.guild is None:
            return
        if self.channels and message.channel.id not in self.channels:
            return
        if message.content.startswith(self.bot.command_prefix) or self.bot.user in message.mentions:
            return   # commands, and messages talking to the bot (it replies to those instead)
        now = time.monotonic()
        if now - self._last.get(message.channel.id, float("-inf")) < self.cooldown:
            return
        if random.random() >= self.chance:
            return
        self._last[message.channel.id] = now
        for emoji in await self._choose(message):
            try:
                await message.add_reaction(emoji)
            except discord.Forbidden:
                if not self._warned_permissions:
                    log.warning("Can't add reactions in #%s: the bot needs the Add Reactions permission",
                                getattr(message.channel, "name", message.channel.id))
                    self._warned_permissions = True
                return
            except discord.NotFound:
                return   # the message was deleted, or this emoji doesn't exist
            except discord.HTTPException:
                log.warning("Could not add reaction %r", emoji, exc_info=True)

    async def _choose(self, message: discord.Message) -> list:
        llm = getattr(self.bot.get_cog("Brain"), "llm", None)
        text = " ".join(message.clean_content.split())
        if self.use_ai and llm is not None and len(text) >= 8:
            try:
                raw = await llm.complete(model=self.model, system=REACTION_RULES, prompt=text[:500],
                                         max_tokens=20, purpose="reaction")
                emojis = parse_emoji_reply(raw)
                if emojis:
                    return emojis
            except (BudgetExceeded, LLMError) as exc:
                log.info("No AI reaction (%s), picking randomly", exc)
            except Exception:
                log.exception("Unexpected error choosing a reaction")
        custom = []
        if self.use_server_emojis:
            custom = [e for e in message.guild.emojis if getattr(e, "available", True)]
        return choose_random_emojis(self.pool, custom)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Reactions(bot))
