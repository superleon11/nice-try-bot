"""Throwback of the Day, with a human in the loop.

Every day around THROWBACK_SCAN_HOUR (10am) the bot reads a random slice of the source channel's
history and sends 3 candidate messages to a private moderation channel. The moderator reacts:

    1️⃣ 2️⃣ 3️⃣   approve that message. The bot holds on to it and posts it in the main throwback
                channel at a random time between THROWBACK_START_HOUR (11am) and THROWBACK_END_HOUR (3pm).
    ❌          none are good enough: the bot digs up 3 more (up to THROWBACK_MAX_ROUNDS a day).

If nothing is approved before the end of the window, there is no throwback that day. The state lives in
the database (table throwback_rounds: message IDs only), so a restart loses nothing. When the approved
message is posted, the AI (if on) adds a one-line comment and an illustration.
"""

import asyncio
import io
import json
import logging
import os
import random
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from archive import PICK_FROM, Candidate, find_pool
from envutil import env_bool, env_int
from helpers import pick_run_time, throwback_action, truncate
from llm import BudgetExceeded, LLMError
from throwback_ai import judge_pool, judge_top

log = logging.getLogger(__name__)

NUMBERS = ["1️⃣", "2️⃣", "3️⃣"]
REJECT = "❌"
CANDIDATES_PER_ROUND = 3
TICK_SECONDS = 60
RETRY_SECONDS = 900      # wait this long after a failed search before trying again
MAX_SEARCH_FAILURES = 3  # per day


class Throwback(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Where approved throwbacks are posted, where candidates go for approval, and which channel's
        # history is searched (defaults to the posting channel).
        self.channel_id = env_int("THROWBACK_CHANNEL_ID", 0)
        self.mod_channel_id = env_int("THROWBACK_MOD_CHANNEL_ID", 0)
        self.source_id = env_int("THROWBACK_SOURCE_CHANNEL_ID", 0) or self.channel_id
        self.window_days = max(1, env_int("THROWBACK_WINDOW_DAYS", 60))
        self.min_messages = max(1, env_int("THROWBACK_MIN_MESSAGES", 10))
        self.max_attempts = max(1, env_int("THROWBACK_MAX_ATTEMPTS", 40))
        self.max_rounds = max(1, env_int("THROWBACK_MAX_ROUNDS", 5))
        # Candidates go out at scan_hour; the approved one is posted between start_hour and end_hour.
        self.scan_hour = env_int("THROWBACK_SCAN_HOUR", 10) % 24
        self.start_hour = env_int("THROWBACK_START_HOUR", 11) % 24
        self.end_hour = env_int("THROWBACK_END_HOUR", 15) % 24
        if not (self.scan_hour <= self.start_hour < self.end_hour):
            log.warning("Throwback hours must satisfy SCAN <= START < END, using 10, 11 and 15")
            self.scan_hour, self.start_hour, self.end_hour = 10, 11, 15
        tz_name = os.getenv("THROWBACK_TIMEZONE", "").strip() or "Europe/London"
        try:
            self.tz = ZoneInfo(tz_name)
        except Exception:
            log.warning("Unknown or unavailable time zone %r, using UTC", tz_name)
            self.tz = timezone.utc
        self.ai_pick = env_bool("THROWBACK_AI_PICK", True)
        self.with_image = env_bool("THROWBACK_IMAGE", True)
        self.judge_model = os.getenv("LLM_THROWBACK_MODEL", "").strip() or "claude-sonnet-5-5"
        self._runner: asyncio.Task | None = None
        self._lock = asyncio.Lock()           # one state change at a time
        self._failures: dict = {}             # local date -> failed searches today
        self._retry_at = 0.0                  # time.monotonic() before which we don't search again
        self._limit_told: set = set()         # dates we already said "that's enough rounds" for

    async def cog_load(self) -> None:
        if not self.channel_id:
            log.warning("THROWBACK_CHANNEL_ID not set: the throwback is disabled")
        elif not self.mod_channel_id:
            log.warning("THROWBACK_MOD_CHANNEL_ID not set: the throwback is disabled "
                        "(nothing is posted without being approved first)")
        else:
            self._runner = asyncio.create_task(self._loop())

    async def cog_unload(self) -> None:
        if self._runner is not None:
            self._runner.cancel()

    # ---- the daily state machine ----------------------------------------------------------------

    def _today(self):
        return datetime.now(self.tz).date()

    async def _loop(self) -> None:
        await self.bot.wait_until_ready()
        for label, cid in (("throwback channel", self.channel_id), ("moderation channel", self.mod_channel_id),
                           ("source channel", self.source_id)):
            channel = self.bot.get_channel(cid)
            if channel is None:
                log.error("Throwback: can't find the %s (ID %s). Is the ID right, and can the bot see it?", label, cid)
            else:
                log.info("Throwback: %s is #%s", label, getattr(channel, "name", cid))
        log.info("Throwback: candidates go out from %02d:00, approved posts between %02d:00 and %02d:00 (%s)",
                 self.scan_hour, self.start_hour, self.end_hour, self.tz)
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Throwback check failed")   # never let one failure stop the loop
            await asyncio.sleep(TICK_SECONDS)

    async def tick(self) -> str | None:
        """Look at today's rounds and do whatever is due. Returns the action taken (for tests)."""
        import time as _time
        async with self._lock:
            day = self._today()
            rounds = await self.bot.db.rounds_for_day(day)
            action = throwback_action(datetime.now(timezone.utc), self.tz, rounds, self.scan_hour,
                                      self.end_hour, self.max_rounds)
            if action == "publish":
                await self._publish(next(r for r in rounds if r["status"] == "approved"))
            elif action == "expire_approved":
                for r in rounds:
                    if r["status"] == "approved":
                        await self.bot.db.change_round_status(r["id"], "approved", "expired")
                await self._tell_mods("The approved throwback missed its time (I was probably offline), "
                                      "so there's no throwback today.")
            elif action == "expire_open":
                for r in rounds:
                    if r["status"] == "open":
                        await self.bot.db.change_round_status(r["id"], "open", "expired")
                await self._tell_mods("Nothing was approved in time, so there's no throwback today.")
            elif action == "propose":
                if _time.monotonic() < self._retry_at or self._failures.get(day, 0) >= MAX_SEARCH_FAILURES:
                    return None
                try:
                    problem = await self._propose(day, len(rounds) + 1)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.exception("Throwback search crashed")
                    problem = f"something went wrong ({type(exc).__name__}: {exc})."
                if problem:
                    self._failures[day] = self._failures.get(day, 0) + 1
                    self._retry_at = _time.monotonic() + RETRY_SECONDS
                    log.error("Throwback candidates not sent: %s", problem)
                    await self._tell_mods(f"I couldn't put together candidates: {problem}"
                                          + (" I'll try again in a few minutes."
                                             if self._failures[day] < MAX_SEARCH_FAILURES else
                                             " I've tried enough times today, so there's no throwback today."))
            elif action == "limit":
                if day not in self._limit_told:
                    self._limit_told.add(day)
                    await self._tell_mods(f"That's {self.max_rounds} rounds with nothing approved, so no "
                                          "throwback today.")
            return action

    async def _tell_mods(self, text: str) -> None:
        channel = self.bot.get_channel(self.mod_channel_id)
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                log.warning("Could not write to the moderation channel", exc_info=True)

    # ---- sending candidates ---------------------------------------------------------------------

    def _check_channels(self):
        """(main channel, mod channel, source channel) or a problem string."""
        target = self.bot.get_channel(self.channel_id)
        mod = self.bot.get_channel(self.mod_channel_id)
        source = self.bot.get_channel(self.source_id)
        if not isinstance(target, discord.TextChannel):
            return f"I can't find the throwback channel ({self.channel_id}). Is the ID right, and is the bot in that server?"
        if not isinstance(mod, discord.TextChannel):
            return f"I can't find the moderation channel ({self.mod_channel_id})."
        if not isinstance(source, discord.TextChannel):
            return f"I can't find the channel to read history from ({self.source_id})."
        if source.is_nsfw() and not target.is_nsfw():
            return ("The channel I read from is NSFW but the one I post in is not, "
                    "so I won't repost its messages there.")
        perms = source.permissions_for(source.guild.me)
        if not (perms.view_channel and perms.read_message_history):
            return f"I don't have View Channel + Read Message History permission in #{source.name}."
        return target, mod, source

    async def _propose(self, day, round_no: int) -> str | None:
        """Search the archive and send 3 candidates to the moderation channel. None on success."""
        checked = self._check_channels()
        if isinstance(checked, str):
            return checked
        target, mod, source = checked

        db = self.bot.db
        recent = await db.recent_throwback_windows(30)
        posted = await db.posted_throwback_ids()
        seen = posted | await db.proposed_throwback_ids()     # never offer the same message twice
        kwargs = dict(max_attempts=self.max_attempts, min_eligible=self.min_messages)
        pool = await find_pool(source.guild, [source], self.bot.command_prefix, self.window_days,
                               recent=recent, exclude=seen, **kwargs)
        if not pool and seen - posted:
            log.info("Every usable message was offered before: offering earlier rejects again")
            pool = await find_pool(source.guild, [source], self.bot.command_prefix, self.window_days,
                                   recent=recent, exclude=posted, **kwargs)
        if not pool:
            return "I couldn't find anything good in the archive."
        window = pool.window if pool.window else (None, None)

        chosen, ai = [], False
        brain = self.bot.get_cog("Brain")
        llm = getattr(brain, "llm", None)
        if self.ai_pick and llm is not None:
            try:
                chosen = await judge_top(llm, self.judge_model, brain.persona, pool, CANDIDATES_PER_ROUND)
                ai = bool(chosen)
            except BudgetExceeded as exc:
                log.info("Throwback shortlist AI skipped, budget reached: %s", exc)
            except LLMError:
                log.exception("Throwback shortlist AI failed, using the most-reacted messages")
        if not chosen:
            chosen = random.sample(pool[:PICK_FROM], min(CANDIDATES_PER_ROUND, len(pool[:PICK_FROM])))

        embeds = []
        for i, c in enumerate(chosen):
            m = c.message
            e = discord.Embed(title=f"{i + 1}", description=truncate(c.text, 1500), colour=discord.Colour.gold())
            e.add_field(name="From", value=discord.utils.escape_markdown(m.author.display_name))
            e.add_field(name="In", value=f"<#{m.channel.id}>")
            e.add_field(name="When", value=discord.utils.format_dt(m.created_at, "D"))
            if c.reactions:
                e.add_field(name="Reactions", value=f"⭐ {c.reactions}")
            e.add_field(name="​", value=f"[Jump to message]({m.jump_url})", inline=False)
            embeds.append(e)
        header = (f"📼 **Throwback candidates for {day.strftime('%A %d %B')}** (round {round_no}). "
                  f"React {' '.join(NUMBERS[:len(chosen)])} to approve one, or {REJECT} if none are good enough.")

        round_id = await db.add_round(
            day, round_no, json.dumps([{"id": c.message.id, "channel_id": c.message.channel.id} for c in chosen]),
            window_start=window[0], window_end=window[1], eligible=getattr(pool, "eligible", None),
            attempts=getattr(pool, "attempts", None), channel_days=getattr(pool, "channel_days", None),
            whole_channel=getattr(pool, "whole_channel", None), ai_pick=ai,
            windows_tried=json.dumps(list(getattr(pool, "tried", ()))))
        try:
            sent = await mod.send(header, embeds=embeds, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as exc:
            await db.change_round_status(round_id, "open", "failed")
            return f"I couldn't post in the moderation channel ({exc})."
        await db.set_round_mod_message(round_id, sent.id)
        try:
            for emoji in [*NUMBERS[:len(chosen)], REJECT]:
                await sent.add_reaction(emoji)
        except discord.HTTPException:
            log.warning("Could not add reactions in the moderation channel (needs Add Reactions)", exc_info=True)
            await self._tell_mods("I couldn't add the reaction buttons. React with 1️⃣ 2️⃣ 3️⃣ or ❌ yourself.")
        return None

    # ---- the moderator's choice ----------------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload) -> None:
        if payload.channel_id != self.mod_channel_id or not self.mod_channel_id:
            return
        if payload.user_id == self.bot.user.id:
            return
        emoji = str(payload.emoji)
        if emoji not in NUMBERS and emoji != REJECT:
            return
        round_ = await self.bot.db.round_by_mod_message(payload.message_id)
        if round_ is None or round_["status"] != "open":
            return
        if emoji == REJECT:
            if await self.bot.db.change_round_status(round_["id"], "open", "rejected"):
                await self._tell_mods("Okay, finding some more…")
                await self.tick()    # starts the next round straight away
            return
        candidates = json.loads(round_["candidates"])
        index = NUMBERS.index(emoji)
        if index >= len(candidates):
            return
        async with self._lock:
            now = datetime.now(timezone.utc)
            post_at = pick_run_time(now, self.tz, self.start_hour, self.end_hour, False)
            if post_at.astimezone(self.tz).date() != self._today():
                await self._tell_mods("It's too late in the day for a throwback now, so I'll leave it for today.")
                return
            chosen = candidates[index]
            if not await self.bot.db.change_round_status(round_["id"], "open", "approved", chosen_id=chosen["id"],
                                                         chosen_channel_id=chosen["channel_id"], post_at=post_at):
                return
        await self._tell_mods(f"✅ Number {index + 1} is approved. I'll post it at "
                              f"{post_at.astimezone(self.tz).strftime('%H:%M')}.")

    # ---- posting the approved message ------------------------------------------------------------

    async def _publish(self, round_: dict) -> None:
        """Post the approved message in the main channel (with the AI's comment and image)."""
        db = self.bot.db
        checked = self._check_channels()
        if isinstance(checked, str):
            log.error("Approved throwback can't be posted: %s", checked)
            await db.change_round_status(round_["id"], "approved", "failed")
            await self._tell_mods(f"I couldn't post the approved throwback: {checked}")
            return
        target, mod, source = checked

        channel = self.bot.get_channel(round_["chosen_channel_id"]) or source
        try:
            m = await channel.fetch_message(round_["chosen_id"])
        except discord.HTTPException:
            m = None
        if m is None or not m.content:
            await db.change_round_status(round_["id"], "approved", "failed")
            await self._tell_mods("The approved message seems to have been deleted, so I'll find more.")
            return
        found = Candidate(m, m.content, sum(r.count for r in m.reactions))

        comment, image_prompt = "", ""
        brain = self.bot.get_cog("Brain")
        llm = getattr(brain, "llm", None)
        if self.ai_pick and llm is not None:
            try:
                verdict = await judge_pool(llm, self.judge_model, brain.persona, [found], min_pool=1)
            except BudgetExceeded as exc:
                log.info("Throwback comment skipped, budget reached: %s", exc)
                verdict = None
            except LLMError:
                log.exception("Throwback comment failed, posting without it")
                verdict = None
            if verdict is not None:
                comment, image_prompt = verdict.comment, verdict.image_prompt

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

        embed = discord.Embed(title="📼 Throwback of the Day", description=truncate(found.text, 1500),
                              colour=discord.Colour.gold())
        embed.add_field(name="From", value=discord.utils.escape_markdown(m.author.display_name))
        if m.channel.id != target.id:
            embed.add_field(name="In", value=f"<#{m.channel.id}>")
        embed.add_field(name="When", value=discord.utils.format_dt(m.created_at, "D"))
        if found.reactions:
            embed.add_field(name="Reactions", value=f"⭐ {found.reactions}")
        if comment:
            embed.add_field(name="The bot's verdict", value=truncate(comment, 1000), inline=False)
        embed.add_field(name="​", value=f"[Jump to message]({m.jump_url})", inline=False)
        kwargs = {"embed": embed, "allowed_mentions": discord.AllowedMentions.none()}
        if file is not None:
            embed.set_image(url=f"attachment://{file.filename}")
            kwargs["file"] = file
        try:
            await target.send(**kwargs)
        except discord.HTTPException as exc:
            await db.change_round_status(round_["id"], "approved", "failed")
            await self._tell_mods(f"I couldn't post in the throwback channel ({exc}).")
            return
        await db.change_round_status(round_["id"], "approved", "posted")
        try:
            await db.add_throwback(
                m.id, round_.get("window_start"), round_.get("window_end"), eligible=round_.get("eligible"),
                attempts=round_.get("attempts"), channel_days=round_.get("channel_days"),
                whole_channel=round_.get("whole_channel"), ai_pick=round_.get("ai_pick"),
                windows_tried=round_.get("windows_tried"))
        except Exception:
            log.exception("Could not record the throwback in the database")

    # ---- command ----------------------------------------------------------------------------------

    @commands.command(name="throwback")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def throwback(self, ctx: commands.Context) -> None:
        """Send a fresh set of 3 candidates to the moderation channel right now."""
        if not (self.channel_id and self.mod_channel_id):
            await ctx.send("THROWBACK_CHANNEL_ID and THROWBACK_MOD_CHANNEL_ID both need to be set.")
            return
        if self._lock.locked():
            await ctx.send("I'm busy with the throwback, give me a moment.")
            return
        await ctx.send("📼 Digging through the archives… the candidates will appear in the moderation channel.")
        async with self._lock:
            day = self._today()
            rounds = await self.bot.db.rounds_for_day(day)
            for r in rounds:     # a manual request replaces any set still waiting for a choice
                if r["status"] == "open":
                    await self.bot.db.change_round_status(r["id"], "open", "expired")
            problem = await self._propose(day, len(rounds) + 1)
        if problem:
            await ctx.send(problem)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Throwback(bot))
