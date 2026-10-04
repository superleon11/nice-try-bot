"""
Stats Commands Cog

Provides commands for users to view their activity statistics and server leaderboards.
Commands: !mystats, !leaderboard
"""

import logging
from datetime import datetime
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

# Medal emojis for rankings
MEDALS = ['🥇', '🥈', '🥉']


class StatsCommands(commands.Cog):
    """Provides activity statistics commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    @commands.hybrid_command(name='mystats')
    async def mystats(self, ctx: commands.Context):
        """
        Show your personal activity statistics.

        Displays:
        - Total messages sent
        - Total voice channel time
        - Your rank on the server
        """
        try:
            await ctx.defer()

            user_id = ctx.author.id
            guild_id = ctx.guild.id

            # Get user stats
            stats = await self.db.get_user_stats(user_id, guild_id)

            if not stats:
                embed = discord.Embed(
                    title="📊 Your Stats",
                    description="No activity recorded yet. Start chatting or join voice!",
                    color=discord.Color.blue()
                )
                await ctx.send(embed=embed)
                return

            # Get ranks
            message_rank = await self.db.get_user_rank(user_id, guild_id, 'messages')
            voice_rank = await self.db.get_user_rank(user_id, guild_id, 'voice')

            # Format voice time
            voice_seconds = stats.total_voice_seconds or 0
            hours = voice_seconds // 3600
            minutes = (voice_seconds % 3600) // 60
            voice_time_str = f"{hours}h {minutes}m"

            # Create embed
            embed = discord.Embed(
                title=f"📊 Stats for {ctx.author.name}",
                description=f"Activity in {ctx.guild.name}",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )

            embed.add_field(
                name="💬 Messages",
                value=f"{stats.total_messages:,}",
                inline=True
            )

            embed.add_field(
                name="🎤 Voice Time",
                value=voice_time_str,
                inline=True
            )

            if message_rank:
                embed.add_field(
                    name="📍 Message Rank",
                    value=f"#{message_rank}",
                    inline=True
                )

            if voice_rank:
                embed.add_field(
                    name="🎙️ Voice Rank",
                    value=f"#{voice_rank}",
                    inline=True
                )

            # Calculate combined score
            combined_score = (stats.total_messages or 0) + (voice_seconds // 60 or 0)
            embed.add_field(
                name="⭐ Engagement Score",
                value=f"{combined_score:,}",
                inline=True
            )

            embed.set_thumbnail(url=ctx.author.avatar.url)
            embed.set_footer(text="Last updated", icon_url=self.bot.user.avatar.url)

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in mystats command: {e}")
            await ctx.send(f"❌ Error retrieving stats: {e}")

    @commands.hybrid_command(name='leaderboard')
    async def leaderboard(self, ctx: commands.Context, metric: str = 'messages'):
        """
        Show server activity leaderboard.

        Metrics: messages, voice, combined
        Usage: !leaderboard [metric]
        """
        try:
            await ctx.defer()

            if metric not in ['messages', 'voice', 'combined']:
                await ctx.send("❌ Metric must be: messages, voice, or combined")
                return

            guild_id = ctx.guild.id
            limit = 10

            # Get leaderboard
            results = await self.db.get_leaderboard(guild_id, metric, limit)

            if not results:
                embed = discord.Embed(
                    title="🏆 Leaderboard",
                    description="No activity recorded yet!",
                    color=discord.Color.gold()
                )
                await ctx.send(embed=embed)
                return

            # Create embed
            metric_name = {
                'messages': '💬 Messages',
                'voice': '🎤 Voice Time',
                'combined': '⭐ Engagement'
            }

            embed = discord.Embed(
                title=f"🏆 {metric_name[metric]} Leaderboard",
                description=f"Top {len(results)} in {ctx.guild.name}",
                color=discord.Color.gold(),
                timestamp=datetime.utcnow()
            )

            leaderboard_text = ""

            for rank, (user, stats) in enumerate(results, 1):
                # Get medal or rank number
                if rank <= 3:
                    medal = MEDALS[rank - 1]
                else:
                    medal = f"#{rank}"

                # Format value based on metric
                if metric == 'messages':
                    value = f"{stats.total_messages:,} messages"
                elif metric == 'voice':
                    seconds = stats.total_voice_seconds or 0
                    hours = seconds // 3600
                    minutes = (seconds % 3600) // 60
                    value = f"{hours}h {minutes}m"
                else:  # combined
                    combined = (stats.total_messages or 0) + ((stats.total_voice_seconds or 0) // 60)
                    value = f"{combined:,} points"

                user_mention = f"<@{user.id}>"
                leaderboard_text += f"{medal} {user_mention} - {value}\n"

            embed.description = leaderboard_text
            embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)
            embed.set_footer(text="Check !mystats for your personal stats")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in leaderboard command: {e}")
            await ctx.send(f"❌ Error retrieving leaderboard: {e}")

    @commands.command(name='mystats_top3')
    async def mystats_top3(self, ctx: commands.Context):
        """Show your position in top 3 categories."""
        try:
            await ctx.defer()

            user_id = ctx.author.id
            guild_id = ctx.guild.id

            # Get ranks
            message_rank = await self.db.get_user_rank(user_id, guild_id, 'messages')
            voice_rank = await self.db.get_user_rank(user_id, guild_id, 'voice')

            if not message_rank and not voice_rank:
                await ctx.send("You haven't recorded any activity yet!")
                return

            embed = discord.Embed(
                title=f"🎯 {ctx.author.name}'s Rankings",
                color=discord.Color.purple()
            )

            if message_rank and message_rank <= 3:
                embed.add_field(
                    name="💬 Message Top 3",
                    value=f"{MEDALS[message_rank - 1]} Rank #{message_rank}",
                    inline=False
                )

            if voice_rank and voice_rank <= 3:
                embed.add_field(
                    name="🎤 Voice Top 3",
                    value=f"{MEDALS[voice_rank - 1]} Rank #{voice_rank}",
                    inline=False
                )

            if not (message_rank and message_rank <= 3) and not (voice_rank and voice_rank <= 3):
                embed.description = "You're not in the top 3 yet. Keep grinding! 💪"

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in mystats_top3 command: {e}")
            await ctx.send(f"❌ Error: {e}")


async def setup(bot: commands.Bot):
    """Load the cog."""
    await bot.add_cog(StatsCommands(bot))
