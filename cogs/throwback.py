"""Throwback of the Day.

Once a day the bot reads a random 30-day slice of ONE channel's history straight from Discord and
forgets it again afterwards. If the AI is on, it reads a pool of candidate messages (the most
reacted plus a random sample), picks the funniest or most interesting one, adds a one-line comment
in its own voice, and illustrates it with a generated image. Without the AI (or if it fails or the
cost cap is hit) it picks one of the most-reacted messages instead.
"""

import asyncio
import io
import logging
import os
import random
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from archive import PICK_FROM, find_pool
from helpers import pick_run_time, truncate
from llm import BudgetExceeded, LLMError
from throwback_ai import judge_pool

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
        # The daily post happens at a random moment between these hours, in this time zone.
        self.start_hour = _env_int("THROWBACK_START_HOUR", 10) % 24
        self.end_hour = _env_int("THROWBACK_END_HOUR", 15) % 24
        if self.end_hour <= self.start_hour:
            log.warning("THROWBACK_END_HOUR must be later than THROWBACK_START_HOUR, using 10 and 15")
            self.start_hour, self.end_hour = 10, 15
        tz_name = os.getenv("THROWBACK_TIMEZONE", "").strip() or "Europe/London"
        try:
            self.tz = ZoneInfo(tz_name)
        except Exception:
            log.warning("Unknown or unavailable time zone %r, using UTC", tz_name)
            self.tz = timezone.utc
        self._runner: asyncio.Task | None = None
        self._lock = asyncio.Lock()  # one scan at a time
        self.ai_pick = os.getenv("THROWBACK_AI_PICK", "true").strip().lower() not in ("0", "false", "no", "off")
        self.with_image = os.getenv("THROWBACK_IMAGE", "true").strip().lower() not in ("0", "false", "no", "off")
        self.judge_model = os.getenv("LLM_THROWBACK_MODEL", "").strip() or "claude-sonnet-5-5"

    async def cog_load(self) -> None:
        if self.channel_id:
            self._runner = asyncio.create_task(self._schedule())
        else:
            log.warning("THROWBACK_CHANNEL_ID not set: the throwback is disabled")

    async def cog_unload(self) -> None:
        if self._runner is not None:
            self._runner.cancel()

    # ---- daily job ------------------------------------------------------

    async def _posted_today(self) -> bool:
        """Did the bot already post a throwback today (local date)? Survives restarts by looking
        at the channel itself instead of remembering."""
        channel = self.bot.get_channel(self.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return False
        today = datetime.now(self.tz).date()
        try:
            async for m in channel.history(limit=30):
                if m.author.id == self.bot.user.id and any(
                        (e.title or "").endswith("Throwback of the Day") for e in m.embeds):
                    return m.created_at.astimezone(self.tz).date() == today
        except discord.HTTPException:
            log.warning("Could not check whether today's throwback was already posted", exc_info=True)
        return False

    async def _schedule(self) -> None:
        await self.bot.wait_until_ready()
        posted_today = await self._posted_today()
        while True:
            run_at = pick_run_time(datetime.now(timezone.utc), self.tz, self.start_hour, self.end_hour,
                                   posted_today)
            wait = (run_at - datetime.now(timezone.utc)).total_seconds()
            log.info("Next throwback at %s (in %.1f hours)", run_at.astimezone(self.tz).strftime("%a %d %b %H:%M %Z"),
                     wait / 3600)
            await asyncio.sleep(max(0.0, wait))
            try:
                problem = await self.post_throwback()
                if problem:
                    log.error("Daily throwback not posted: %s", problem)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Daily throwback failed")   # never let one failure stop the schedule
            posted_today = True   # whatever happened, the next attempt is tomorrow

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
            pool = await find_pool(source.guild, [source], self.bot.command_prefix, self.window_days)
        if not pool:
            return "I couldn't find anything good to post this time."

        found, comment, image_prompt = None, "", ""
        brain = self.bot.get_cog("Brain")
        llm = getattr(brain, "llm", None)
        if self.ai_pick and llm is not None:
            try:
                verdict = await judge_pool(llm, self.judge_model, brain.persona, pool)
            except BudgetExceeded as exc:
                log.info("Throwback AI skipped, budget reached: %s", exc)
                verdict = None
            except LLMError:
                log.exception("Throwback AI pick failed, falling back to the most-reacted messages")
                verdict = None
            if verdict is not None:
                found, comment, image_prompt = verdict.candidate, verdict.comment, verdict.image_prompt
        if found is None:
            found = random.choice(pool[:PICK_FROM])

        file = None
        images = getattr(self.bot.get_cog("ImageGen"), "client", None)
        if self.with_image and image_prompt and images is not None:
            try:
                data, ext = await images.generate(image_prompt)
                file = discord.File(io.BytesIO(data), filename=f"throwback.{ext}")
            except BudgetExceeded as exc:
                log.info("Throwback image skipped, budget reached: %s", exc)
            except LLMError as exc:
                log.warning("Throwback image failed, posting without it: %s", exc)

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
        if comment:
            embed.add_field(name="The bot's verdict", value=truncate(comment, 1000), inline=False)
        embed.add_field(name="​", value=f"[Jump to message]({m.jump_url})", inline=False)
        if file is not None:
            embed.set_image(url=f"attachment://{file.filename}")
            await target.send(embed=embed, file=file)
        else:
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
