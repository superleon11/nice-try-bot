"""
Throwback of the Day Cog

Posts a random old message from the server's history once per day.
Uses APScheduler to handle the daily scheduling.
"""

import logging
from datetime import datetime
import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from bot.utils.config import Config

logger = logging.getLogger(__name__)


class Throwback(commands.Cog):
    """Manages the daily throwback feature."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.scheduler = AsyncIOScheduler()
        self.throwback_channel_id = Config.THROWBACK_CHANNEL_ID
        self.throwback_hour = Config.THROWBACK_HOUR
        self.throwback_minute = Config.THROWBACK_MINUTE

    async def cog_load(self):
        """Called when the cog is loaded."""
        if Config.THROWBACK_ENABLED:
            await self.start_scheduler()

    async def start_scheduler(self):
        """Start the APScheduler for daily throwback."""
        try:
            # Schedule daily throwback at specified time (UTC)
            trigger = CronTrigger(
                hour=self.throwback_hour,
                minute=self.throwback_minute,
                timezone='UTC'
            )

            self.scheduler.add_job(
                self.post_throwback,
                trigger=trigger,
                id='daily_throwback',
                name='Daily Throwback of the Day',
                replace_existing=True
            )

            self.scheduler.start()
            logger.info(
                f"Throwback scheduler started - "
                f"will post daily at {self.throwback_hour:02d}:{self.throwback_minute:02d} UTC"
            )

        except Exception as e:
            logger.error(f"Error starting throwback scheduler: {e}")

    async def post_throwback(self):
        """Post the daily throwback message."""
        try:
            # Get the throwback channel
            channel = self.bot.get_channel(self.throwback_channel_id)

            if not channel:
                logger.error(f"Throwback channel {self.throwback_channel_id} not found")
                return

            # Get guild ID from channel
            guild_id = channel.guild.id

            # Get random message from guild
            message = await self.db.get_random_message(guild_id, exclude_bot=True)

            if not message:
                embed = discord.Embed(
                    title="📼 Throwback of the Day",
                    description="No messages found in server history!",
                    color=discord.Color.blue()
                )
                await channel.send(embed=embed)
                return

            # Get the original message author
            try:
                author = await self.bot.fetch_user(message.user_id)
                author_name = author.name if author else f"Unknown User ({message.user_id})"
            except discord.NotFound:
                author_name = f"Unknown User ({message.user_id})"

            # Get the channel where message was posted
            try:
                original_channel = self.bot.get_channel(message.channel_id)
                channel_name = original_channel.mention if original_channel else "#unknown"
            except:
                channel_name = "#unknown"

            # Format message content
            content = message.content or "*No text content*"
            if len(content) > 200:
                content = content[:197] + "..."

            # Calculate days ago
            now = datetime.utcnow()
            message_date = message.created_at
            days_ago = (now - message_date).days

            # Create embed for throwback
            embed = discord.Embed(
                title="📼 Throwback of the Day",
                description=content,
                color=discord.Color.blue(),
                timestamp=message_date
            )

            embed.set_author(name=author_name)

            embed.add_field(
                name="Channel",
                value=channel_name,
                inline=True
            )

            embed.add_field(
                name="Posted",
                value=f"{days_ago} days ago",
                inline=True
            )

            embed.set_footer(text="Memories ✨")

            # Send the throwback
            await channel.send(embed=embed)
            logger.info(f"Posted throwback message from {author_name} ({days_ago} days ago)")

        except Exception as e:
            logger.error(f"Error posting throwback: {e}")
            try:
                channel = self.bot.get_channel(self.throwback_channel_id)
                if channel:
                    await channel.send(
                        f"❌ Error generating throwback: {e}"
                    )
            except:
                pass

    @commands.command(name='throwback_now')
    @commands.has_permissions(administrator=True)
    async def throwback_now(self, ctx: commands.Context):
        """
        Manually trigger the throwback of the day (admin only).
        Useful for testing.
        """
        try:
            await ctx.defer()
            await self.post_throwback()
            await ctx.send("✅ Throwback posted!")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.command(name='throwback_set')
    @commands.has_permissions(administrator=True)
    async def throwback_set(self, ctx: commands.Context, hour: int, minute: int = 0):
        """
        Set the time for daily throwback (admin only).
        Usage: !throwback_set 2 30  (for 2:30 AM UTC)
        """
        try:
            if not (0 <= hour < 24 and 0 <= minute < 60):
                await ctx.send("❌ Hour must be 0-23, minute must be 0-59")
                return

            # Update config
            Config.THROWBACK_HOUR = hour
            Config.THROWBACK_MINUTE = minute

            # Reschedule
            self.scheduler.remove_job('daily_throwback')
            await self.start_scheduler()

            await ctx.send(f"✅ Throwback scheduled for {hour:02d}:{minute:02d} UTC daily")

        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.command(name='throwback_stats')
    async def throwback_stats(self, ctx: commands.Context):
        """Show throwback statistics."""
        try:
            guild_id = ctx.guild.id

            # Count total messages
            from sqlalchemy import select, func
            from database.models import Message

            # This would require access to session
            embed = discord.Embed(
                title="📼 Throwback Statistics",
                description=f"Server: {ctx.guild.name}",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="Daily Throwback Time",
                value=f"{self.throwback_hour:02d}:{self.throwback_minute:02d} UTC",
                inline=False
            )

            embed.add_field(
                name="Status",
                value="✅ Enabled" if Config.THROWBACK_ENABLED else "❌ Disabled",
                inline=False
            )

            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"❌ Error: {e}")


async def setup(bot: commands.Bot):
    """Load the cog."""
    cog = Throwback(bot)
    await bot.add_cog(cog)
