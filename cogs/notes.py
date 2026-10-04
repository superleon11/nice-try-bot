"""!note commands: set up and edit the notes the bot knows about people.

You can also edit the `user_notes` table in the database directly (see the README).
"""

import discord
from discord.ext import commands

from helpers import truncate

MAX_NOTE_LENGTH = 300


class Notes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="note", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def note(self, ctx: commands.Context) -> None:
        """Manage the notes the bot knows about people."""
        p = ctx.prefix
        await ctx.send(
            f"`{p}note add @user text`: add a note\n"
            f"`{p}note list @user`: show their notes\n"
            f"`{p}note edit <id> text`: change a note\n"
            f"`{p}note remove <id>`: delete a note"
        )

    @note.command(name="add")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def note_add(self, ctx: commands.Context, member: discord.Member, *, text: str) -> None:
        text = " ".join(text.split())
        if len(text) > MAX_NOTE_LENGTH:
            await ctx.send(f"Too long: keep notes under {MAX_NOTE_LENGTH} characters.")
            return
        note_id = await self.bot.db.add_note(ctx.guild.id, member.id, member.display_name, text, "manual")
        await ctx.send(f"Saved note #{note_id} for {member.display_name}.")

    @note.command(name="list")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def note_list(self, ctx: commands.Context, member: discord.Member) -> None:
        rows = await self.bot.db.get_notes(ctx.guild.id, member.id, 100)
        if not rows:
            await ctx.send(f"No notes for {member.display_name} yet.")
            return
        lines = [f"`#{r['id']}` [{r['source']}] {r['note']}" for r in rows]
        header = f"Notes for **{discord.utils.escape_markdown(member.display_name)}**:\n"
        await ctx.send(truncate(header + "\n".join(lines), 1900))

    @note.command(name="edit")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def note_edit(self, ctx: commands.Context, note_id: int, *, text: str) -> None:
        text = " ".join(text.split())
        if len(text) > MAX_NOTE_LENGTH:
            await ctx.send(f"Too long: keep notes under {MAX_NOTE_LENGTH} characters.")
            return
        if await self.bot.db.update_note(ctx.guild.id, note_id, text):
            await ctx.send(f"Updated note #{note_id}. (It is now a manual note, so the AI won't remove it.)")
        else:
            await ctx.send(f"I couldn't find note #{note_id} in this server.")

    @note.command(name="remove", aliases=["delete"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def note_remove(self, ctx: commands.Context, note_id: int) -> None:
        if await self.bot.db.delete_note(ctx.guild.id, note_id):
            await ctx.send(f"Deleted note #{note_id}.")
        else:
            await ctx.send(f"I couldn't find note #{note_id} in this server.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Notes(bot))
