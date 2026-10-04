"""
Activity Tracking Cog

Tracks user messages and voice channel activity.
Listens for on_message and on_voice_state_update events.
"""

import logging
from datetime import datetime
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class ActivityTracking(commands.Cog):
    """Tracks user activity (messages and voice)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        # Track active voice sessions in memory {(user_id, guild_id): joined_at}
        self.voice_sessions = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Track messages for activity statistics.
        Called every time a message is sent.
        """
        # Ignore bot messages
        if message.author.bot:
            return

        # Ignore messages in DM
        if not message.guild:
            return

        try:
            # Ensure user exists in database
            await self.db.upsert_user(message.author.id, message.author.name)

            # Record the message
            await self.db.add_message(
                message_id=message.id,
                user_id=message.author.id,
                channel_id=message.channel.id,
                guild_id=message.guild.id,
                content=message.content,
                created_at=message.created_at
            )

            # Update activity summary
            await self.db.update_activity_summary(
                message.author.id,
                message.guild.id
            )

            logger.debug(
                f"Tracked message: {message.author.name} in {message.guild.name}"
            )

        except Exception as e:
            logger.error(f"Error tracking message: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState,
                                    after: discord.VoiceState):
        """
        Track voice channel activity.
        Called when a user's voice state changes (join, leave, mute, etc.)
        """
        try:
            # User joined a voice channel
            if before.channel is None and after.channel is not None:
                await self._handle_voice_join(member, after)

            # User left a voice channel
            elif before.channel is not None and after.channel is None:
                await self._handle_voice_leave(member, before)

            # User moved channels (changed channel)
            elif before.channel != after.channel and after.channel is not None:
                # This is handled as leave + join
                await self._handle_voice_leave(member, before)
                await self._handle_voice_join(member, after)

        except Exception as e:
            logger.error(f"Error tracking voice state: {e}")

    async def _handle_voice_join(self, member: discord.Member,
                                 voice_state: discord.VoiceState):
        """Handle user joining a voice channel."""
        try:
            # Ensure user exists
            await self.db.upsert_user(member.id, member.name)

            # Create voice session
            joined_at = datetime.utcnow()
            session = await self.db.start_voice_session(
                user_id=member.id,
                guild_id=member.guild.id,
                channel_id=voice_state.channel.id,
                joined_at=joined_at
            )

            # Track in memory
            self.voice_sessions[(member.id, member.guild.id)] = joined_at

            logger.debug(
                f"{member.name} joined voice channel in {member.guild.name}"
            )
        except Exception as e:
            logger.error(f"Error handling voice join: {e}")

    async def _handle_voice_leave(self, member: discord.Member,
                                  voice_state: discord.VoiceState):
        """Handle user leaving a voice channel."""
        try:
            left_at = datetime.utcnow()

            # End voice session and get duration
            duration = await self.db.end_voice_session(
                user_id=member.id,
                guild_id=member.guild.id,
                left_at=left_at
            )

            # Remove from memory
            self.voice_sessions.pop((member.id, member.guild.id), None)

            if duration:
                hours = duration // 3600
                minutes = (duration % 3600) // 60
                logger.debug(
                    f"{member.name} left voice channel after {hours}h {minutes}m"
                )

            # Update activity summary
            await self.db.update_activity_summary(
                member.id,
                member.guild.id
            )

        except Exception as e:
            logger.error(f"Error handling voice leave: {e}")

    async def get_active_sessions(self) -> dict:
        """Get all currently active voice sessions."""
        return self.voice_sessions.copy()


async def setup(bot: commands.Bot):
    """Load the cog."""
    await bot.add_cog(ActivityTracking(bot))
