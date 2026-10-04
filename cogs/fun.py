"""Occasional, rate-limited fun replies."""

import logging
import random
import time

import discord
from discord.ext import commands

from addressing import is_addressed
from helpers import pick_mention_reply, pick_reply

log = logging.getLogger(__name__)

COOLDOWN_SECONDS = 300   # at most one keyword reply per channel every 5 minutes
REPLY_CHANCE = 0.5       # even when a keyword matches, only reply half the time


class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_reply: dict[int, float] = {}  # channel_id -> time.monotonic()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None or not message.content:
            return
        if message.content.startswith(self.bot.command_prefix):
            return

        # When the AI brain is on, it answers anything addressed to the bot.
        if getattr(self.bot, "brain_active", False):
            claims = getattr(self.bot, "brain_claims", None)
            if (claims(message) if claims else is_addressed(message, self.bot.user)):
                return

        # Otherwise always answer a direct mention with a canned line.
        if self.bot.user in message.mentions:
            await self._reply(message, pick_mention_reply())
            return

        if getattr(self.bot, "brain_random", False):
            return  # the AI brain chimes in on its own now (and falls back to these canned lines)

        now = time.monotonic()
        if now - self.last_reply.get(message.channel.id, float("-inf")) < COOLDOWN_SECONDS:
            return
        reply = pick_reply(message.content)
        if reply is None or random.random() > REPLY_CHANCE:
            return
        self.last_reply[message.channel.id] = now
        await self._reply(message, reply)

    async def _reply(self, message: discord.Message, text: str) -> None:
        try:
            await message.reply(text, mention_author=False)
        except discord.HTTPException:
            log.warning("Could not reply in channel %s", message.channel.id, exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fun(bot))
