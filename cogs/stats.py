"""!mystats and !leaderboard."""

import discord
from discord.ext import commands

from helpers import format_duration

MEDALS = ["🥇", "🥈", "🥉"]
KINDS = ("messages", "voice", "combined")


class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="mystats")
    @commands.guild_only()
    async def mystats(self, ctx: commands.Context) -> None:
        """Show your message count, voice time and rank in this server."""
        row = await self.bot.db.user_stats(ctx.guild.id, ctx.author.id)
        if row is None:
            await ctx.send("No activity recorded for you yet. Say something or hop in voice!")
            return

        voice_rank = f" (#{row['voice_rank']})" if row["voice_seconds"] > 0 else ""
        embed = discord.Embed(
            title=f"📊 Stats for {ctx.author.display_name}",
            colour=discord.Colour.blurple(),
        )
        embed.add_field(name="💬 Messages", value=f"{row['messages']:,} (#{row['message_rank']})")
        embed.add_field(name="🎤 Voice time", value=f"{format_duration(row['voice_seconds'])}{voice_rank}")
        await ctx.send(embed=embed)

    @commands.command(name="leaderboard", aliases=["lb"])
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context, kind: str = "combined") -> None:
        """Top 10 in this server. Usage: leaderboard [messages|voice|combined]"""
        kind = kind.lower()
        if kind not in KINDS:
            await ctx.send(f"Usage: `{ctx.prefix}leaderboard [{'|'.join(KINDS)}]`")
            return

        rows = await self.bot.db.leaderboard(ctx.guild.id, kind)
        if not rows:
            await ctx.send("Nothing to rank yet.")
            return

        lines = []
        for i, row in enumerate(rows):
            place = MEDALS[i] if i < len(MEDALS) else f"`{i + 1}.`"
            name = discord.utils.escape_markdown(row["username"])
            if kind == "messages":
                value = f"{row['messages']:,} messages"
            elif kind == "voice":
                value = format_duration(row["voice_seconds"])
            else:
                value = f"{row['messages']:,} messages · {format_duration(row['voice_seconds'])} voice"
            lines.append(f"{place} **{name}**: {value}")

        embed = discord.Embed(
            title=f"🏆 {kind.capitalize()} leaderboard",
            description="\n".join(lines),
            colour=discord.Colour.gold(),
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Stats(bot))
