"""Tracks text messages and time spent in voice channels."""

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Activity(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # (guild_id, user_id) -> when they joined voice. In memory only: a restart loses open sessions.
        self.voice_joined: dict[tuple[int, int], datetime] = {}
        self._seeded = False

    # ---- text -----------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if not message.content and not message.attachments:
            return
        if message.content.startswith(self.bot.command_prefix):
            return  # bot commands are not "activity"
        try:
            # Only a counter is bumped: the message text is never stored.
            await self.bot.db.record_message(
                guild_id=message.guild.id,
                user_id=message.author.id,
                username=message.author.display_name,
            )
        except Exception:
            log.exception("Failed to record message %s", message.id)

    # ---- voice ----------------------------------------------------------

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Start timing anyone already in a voice channel when the bot comes online."""
        if self._seeded:
            return
        self._seeded = True
        now = _now()
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                for member in channel.members:
                    if not member.bot:
                        self.voice_joined.setdefault((guild.id, member.id), now)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState, after: discord.VoiceState) -> None:
        if member.bot:
            return
        key = (member.guild.id, member.id)
        if before.channel is None and after.channel is not None:
            self.voice_joined[key] = _now()
        elif before.channel is not None and after.channel is None:
            await self._finish_session(key, member.display_name)
        # Moving between channels, muting, etc.: the session simply continues.

    async def _finish_session(self, key: tuple[int, int], username: str) -> None:
        joined = self.voice_joined.pop(key, None)
        if joined is None:
            return
        seconds = int((_now() - joined).total_seconds())
        try:
            await self.bot.db.add_voice_seconds(key[0], key[1], username, seconds)
        except Exception:
            log.exception("Failed to save voice time for %s", key)

    async def cog_unload(self) -> None:
        """Save anyone still in voice when the bot shuts down."""
        for key in list(self.voice_joined):
            guild = self.bot.get_guild(key[0])
            member = guild.get_member(key[1]) if guild else None
            await self._finish_session(key, member.display_name if member else str(key[1]))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Activity(bot))
