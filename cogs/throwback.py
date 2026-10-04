"""Throwback of the Day, plus a backfill command to import old history."""

import logging
import os
from datetime import time as dtime, timezone

import discord
from discord.ext import commands, tasks

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
        self.channel_id = _env_int("THROWBACK_CHANNEL_ID", 0)
        hour = _env_int("THROWBACK_HOUR_UTC", 12) % 24
        self.daily.change_interval(time=dtime(hour=hour, tzinfo=timezone.utc))
        self._backfilling: set[int] = set()

    async def cog_load(self) -> None:
        if self.channel_id:
            self.daily.start()
        else:
            log.warning("THROWBACK_CHANNEL_ID not set: daily throwback disabled (!throwback still works)")

    async def cog_unload(self) -> None:
        self.daily.cancel()

    # ---- daily job ------------------------------------------------------

    @tasks.loop(time=dtime(hour=12, tzinfo=timezone.utc))
    async def daily(self) -> None:
        channel = self.bot.get_channel(self.channel_id)
        if channel is None:
            log.error("Throwback channel %s not found (is the bot in that server?)", self.channel_id)
            return
        try:
            await self.post_throwback(channel)
        except Exception:
            # Never let one failure kill the loop.
            log.exception("Daily throwback failed")

    @daily.before_loop
    async def _before_daily(self) -> None:
        await self.bot.wait_until_ready()

    async def post_throwback(self, channel: discord.abc.Messageable) -> bool:
        row = await self.bot.db.random_message(channel.guild.id)
        if row is None:
            return False
        url = f"https://discord.com/channels/{channel.guild.id}/{row['channel_id']}/{row['id']}"
        embed = discord.Embed(
            title="📼 Throwback of the Day",
            description=truncate(row["content"], 1500),
            colour=discord.Colour.gold(),
        )
        embed.add_field(name="From", value=discord.utils.escape_markdown(row["author_name"]))
        embed.add_field(name="In", value=f"<#{row['channel_id']}>")
        embed.add_field(name="When", value=discord.utils.format_dt(row["created_at"], "D"))
        embed.add_field(name="​", value=f"[Jump to message]({url})", inline=False)
        await channel.send(embed=embed)
        return True

    # ---- commands -------------------------------------------------------

    @commands.command(name="throwback")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def throwback(self, ctx: commands.Context) -> None:
        """Post a throwback right now (handy for testing)."""
        if not await self.post_throwback(ctx.channel):
            await ctx.send("I don't have any stored messages yet. Try `!backfill` first.")

    @commands.command(name="backfill")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def backfill(self, ctx: commands.Context) -> None:
        """Import this server's existing message history (can take a while)."""
        guild = ctx.guild
        if guild.id in self._backfilling:
            await ctx.send("A backfill is already running for this server.")
            return
        self._backfilling.add(guild.id)
        try:
            await ctx.send("Importing message history. This can take a while, I'll post when it's done.")
            seen = 0
            for channel in guild.text_channels:
                perms = channel.permissions_for(guild.me)
                if not (perms.view_channel and perms.read_message_history):
                    continue
                batch: list[tuple] = []
                try:
                    async for m in channel.history(limit=None, oldest_first=True):
                        if m.author.bot or not m.content or m.content.startswith(self.bot.command_prefix):
                            continue
                        batch.append((m.id, guild.id, channel.id, m.author.id,
                                      m.author.display_name, m.content, m.created_at))
                        if len(batch) >= 500:
                            await self.bot.db.insert_messages_bulk(batch)
                            seen += len(batch)
                            batch = []
                except discord.Forbidden:
                    log.warning("No access to history of #%s", channel.name)
                    continue
                if batch:
                    await self.bot.db.insert_messages_bulk(batch)
                    seen += len(batch)
            await self.bot.db.rebuild_message_counts(guild.id)
            await ctx.send(f"Done! Processed {seen:,} messages. Message counts have been rebuilt.")
        finally:
            self._backfilling.discard(guild.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Throwback(bot))
