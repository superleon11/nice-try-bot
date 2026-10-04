"""Throwback of the Day.

Once a day the bot reads a random 30-day slice of ONE channel's history straight from Discord,
picks one of the best (most-reacted) messages, posts it in that channel, and forgets everything
it read.
"""

import asyncio
import logging
import os
from datetime import time as dtime, timezone

import discord
from discord.ext import commands, tasks

from archive import find_throwback
from helpers import truncate

log = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        log.warning("%s=%r is not a number, using %s", name, raw, default)
        return default


class Throwback(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # The one channel the bot posts in. Unless THROWBACK_SOURCE_CHANNEL_ID says otherwise,
        # it is also the one channel the bot reads history from.
        self.channel_id = _env_int("THROWBACK_CHANNEL_ID", 0)
        self.source_id = _env_int("THROWBACK_SOURCE_CHANNEL_ID", 0) or self.channel_id
        self.window_days = max(1, _env_int("THROWBACK_WINDOW_DAYS", 30))
        hour = _env_int("THROWBACK_HOUR_UTC", 12) % 24
        self.daily.change_interval(time=dtime(hour=hour, tzinfo=timezone.utc))
        self._lock = asyncio.Lock()  # one scan at a time

    async def cog_load(self) -> None:
        if self.channel_id:
            self.daily.start()
        else:
            log.warning("THROWBACK_CHANNEL_ID not set: the throwback is disabled")

    async def cog_unload(self) -> None:
        self.daily.cancel()

    # ---- daily job ------------------------------------------------------

    @tasks.loop(time=dtime(hour=12, tzinfo=timezone.utc))
    async def daily(self) -> None:
        try:
            problem = await self.post_throwback()
        except Exception:
            # Never let one failure kill the loop.
            log.exception("Daily throwback failed")
            return
        if problem:
            log.error("Daily throwback not posted: %s", problem)

    @daily.before_loop
    async def _before_daily(self) -> None:
        await self.bot.wait_until_ready()

    async def post_throwback(self) -> str | None:
        """Post a throwback. Returns None on success, or a short reason it could not."""
        target = self.bot.get_channel(self.channel_id)
        source = self.bot.get_channel(self.source_id)
        if not isinstance(target, discord.TextChannel):
            return f"I can't find the throwback channel ({self.channel_id}). Is the ID right, and is the bot in that server?"
        if not isinstance(source, discord.TextChannel):
            return f"I can't find the channel to read history from ({self.source_id})."
        if source.is_nsfw() and not target.is_nsfw():
            return ("The channel I read from is NSFW but the one I post in is not, "
                    "so I won't repost its messages there.")
        perms = source.permissions_for(source.guild.me)
        if not (perms.view_channel and perms.read_message_history):
            return f"I don't have View Channel + Read Message History permission in #{source.name}."

        async with self._lock:
            found = await find_throwback(source.guild, [source], self.bot.command_prefix, self.window_days)
        if found is None:
            return "I couldn't find anything good to post this time."

        m = found.message
        embed = discord.Embed(
            title="📼 Throwback of the Day",
            description=truncate(found.text, 1500),
            colour=discord.Colour.gold(),
        )
        embed.add_field(name="From", value=discord.utils.escape_markdown(m.author.display_name))
        if m.channel.id != target.id:
            embed.add_field(name="In", value=f"<#{m.channel.id}>")
        embed.add_field(name="When", value=discord.utils.format_dt(m.created_at, "D"))
        if found.reactions:
            embed.add_field(name="Reactions", value=f"⭐ {found.reactions}")
        embed.add_field(name="​", value=f"[Jump to message]({m.jump_url})", inline=False)
        await target.send(embed=embed)
        return None

    # ---- command --------------------------------------------------------

    @commands.command(name="throwback")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def throwback(self, ctx: commands.Context) -> None:
        """Dig up a throwback right now (can take a minute or two). It posts in the throwback channel."""
        if not self.channel_id:
            await ctx.send("THROWBACK_CHANNEL_ID isn't set, so I don't know which channel to use.")
            return
        if self._lock.locked():
            await ctx.send("I'm already digging through the archives, give me a moment.")
            return
        await ctx.send("📼 Digging through the archives… this can take a minute or two.")
        problem = await self.post_throwback()
        if problem:
            await ctx.send(problem)
        elif ctx.channel.id != self.channel_id:
            await ctx.send(f"Posted in <#{self.channel_id}>.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Throwback(bot))
