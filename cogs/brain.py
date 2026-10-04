"""LLM features.

1. Chat: when someone mentions the bot (or replies to it), it answers with an AI-written reply that
   can use the notes it has about the people involved.
2. Learning: it buffers what people say TO it (or everything, see LLM_LEARN_SCOPE) in memory only,
   and once a day asks the model to turn that into short notes about each person. The raw messages
   are then thrown away: only the notes are kept.

Every call goes through llm.LLMClient, which enforces the daily and monthly spending caps.
"""

import asyncio
import logging
import os
import random
import time
from datetime import time as dtime, timezone

import discord
from discord.ext import commands, tasks

from addressing import is_addressed
from envutil import env_float, env_int
from helpers import (
    MEMORY_SYSTEM, format_memory_prompt, parse_memory_update, pick_mention_reply, pick_reply, truncate,
)
from llm import BudgetExceeded, LLMClient, LLMError

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # cheapest current model; see LLM_CHAT_MODEL to change

DEFAULT_PERSONA = (
    "You are the Discord bot of a small server of long-time Scottish friends. Your manner is polite, "
    "articulate and a little formal, with dry understated wit, like a well-spoken gentleman who happens "
    "to find everyone's antics very funny. Sprinkle in Scottish words and phrases naturally, but only "
    "one or two per reply, for example aye, wee, och, braw, dinnae, cannae, ken, bampot, gonnae, "
    "bairn, canny, crabbit, the morn. Keep the spelling mostly standard; never write in thick phonetic "
    "dialect and don't overdo it. "
    "Reply in 1-3 short sentences. Do NOT use Gen Z slang (no 'no cap', 'fr', 'bruh', 'slay', 'sus', "
    "'vibes', 'lowkey', 'bestie'), no hashtags, and at most the occasional emoji. "
    "You are given notes about the people involved: use them for inside jokes and callbacks, "
    "naturally and sparingly, and never recite them like a list or mention that you have notes. "
    "Stay in character as the server's bot, not an assistant."
)

MIN_MESSAGES = 3             # a person needs at least this many buffered messages to be processed
BATCH_USERS = 15             # people per memory call
MAX_BUFFER_PER_USER = 300    # buffered messages kept per person (oldest dropped)
MESSAGES_PER_USER_IN_PROMPT = 25
MAX_AUTO_NOTES = 30          # AI-written notes kept per person (manual notes are never trimmed)


class Brain(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.enabled = bool(key)
        self.chat_model = os.getenv("LLM_CHAT_MODEL", "").strip() or DEFAULT_MODEL
        self.memory_model = os.getenv("LLM_MEMORY_MODEL", "").strip() or DEFAULT_MODEL
        self.learn_all = os.getenv("LLM_LEARN_SCOPE", "addressed").strip().lower() == "all"
        self.persona = os.getenv("LLM_PERSONA", "").strip() or DEFAULT_PERSONA
        # Unprompted replies: chance per message, minimum gap per channel, optional channel whitelist.
        self.random_chance = min(1.0, max(0.0, env_float("LLM_RANDOM_REPLY_CHANCE", 0.05)))
        self.random_cooldown = max(0.0, env_float("LLM_RANDOM_COOLDOWN_SECONDS", 300))
        self.random_channels = {int(x) for x in os.getenv("LLM_RANDOM_CHANNEL_IDS", "").replace(" ", "").split(",")
                                if x.isdigit()}
        self._last_random: dict[int, float] = {}   # channel id -> time.monotonic() of the last attempt
        # Follow-ups: after the bot replies to someone, their next messages in that channel within
        # this many seconds count as talking to the bot, no @ needed. 0 switches it off.
        self.convo_window = max(0.0, env_float("LLM_CONVO_WINDOW_SECONDS", 180))
        self._convos: dict[tuple[int, int], float] = {}   # (channel, user) -> time.monotonic() of last exchange
        self.llm: LLMClient | None = None
        if self.enabled:
            self.llm = LLMClient(
                bot.db, key,
                daily_cap=env_float("LLM_DAILY_BUDGET_USD", 0.50),
                monthly_cap=env_float("LLM_MONTHLY_BUDGET_USD", 10.0),
            )
        bot.brain_active = self.enabled  # tells the Fun cog to leave mentions to us
        bot.brain_random = self.enabled and self.random_chance > 0  # ...and the keyword replies too
        bot.brain_claims = self.is_for_me  # lets other cogs ask 'is the brain handling this message?'
        self.buffer: dict[tuple[int, int], list[str]] = {}   # (guild, user) -> recent messages
        self.names: dict[tuple[int, int], str] = {}
        self._learn_lock = asyncio.Lock()
        hour = env_int("LLM_MEMORY_HOUR_UTC", 4) % 24
        self.learn_daily.change_interval(time=dtime(hour=hour, tzinfo=timezone.utc))

    async def cog_load(self) -> None:
        if not self.enabled:
            log.warning("ANTHROPIC_API_KEY not set: AI features are off")
            return
        self.learn_daily.start()
        log.info("AI on: chat model %s, memory model %s, learning from %s, caps $%.2f/day $%.2f/month, "
                 "unprompted replies %.0f%% (cooldown %ds, %s), follow-up window %ds",
                 self.chat_model, self.memory_model, "everything" if self.learn_all else "messages to the bot",
                 self.llm.daily_cap, self.llm.monthly_cap, self.random_chance * 100, self.random_cooldown,
                 f"{len(self.random_channels)} channel(s)" if self.random_channels else "all channels",
                 self.convo_window)

    async def cog_unload(self) -> None:
        self.learn_daily.cancel()
        if self.llm is not None:
            await self.llm.close()

    # ---- chat -----------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not self.enabled or message.author.bot or message.guild is None or not message.content:
            return
        if message.content.startswith(self.bot.command_prefix):
            return
        image_claims = getattr(self.bot, "image_claims", None)
        if image_claims and image_claims(message):
            return   # an "generate me an image" request: the image cog handles it
        addressed = self.is_for_me(message)
        if addressed or self.learn_all:
            self._remember(message)
        if addressed:
            await self._respond(message)
        elif self._should_chime_in(message):
            await self._chime_in(message)

    def is_for_me(self, message: discord.Message) -> bool:
        """Is this message talking to the bot? (a mention, a reply to the bot, or a follow-up)"""
        return is_addressed(message, self.bot.user) or self._in_conversation(message)

    def _in_conversation(self, message: discord.Message) -> bool:
        """A follow-up from someone the bot just talked to, in the same channel, without an @."""
        if self.convo_window <= 0:
            return False
        last = self._convos.get((message.channel.id, message.author.id))
        if last is None or time.monotonic() - last > self.convo_window:
            return False
        if any(not m.bot for m in message.mentions):
            return False   # they are talking to somebody else
        ref = message.reference.resolved if message.reference else None
        if isinstance(ref, discord.Message) and ref.author.id != self.bot.user.id:
            return False   # a Discord reply to somebody else's message
        return True

    def _mark_conversation(self, message: discord.Message) -> None:
        """Start or extend the follow-up window for this person in this channel."""
        now = time.monotonic()
        self._convos[(message.channel.id, message.author.id)] = now
        if len(self._convos) > 200:   # forget stale entries
            self._convos = {k: t for k, t in self._convos.items() if now - t <= self.convo_window}

    def _remember(self, message: discord.Message) -> None:
        text = " ".join(message.clean_content.split())
        text = text.replace(f"@{message.guild.me.display_name}", "").strip()
        if len(text) < 3:
            return
        key = (message.guild.id, message.author.id)
        msgs = self.buffer.setdefault(key, [])
        msgs.append(truncate(text, 300))
        if len(msgs) > MAX_BUFFER_PER_USER:
            del msgs[: len(msgs) - MAX_BUFFER_PER_USER]
        self.names[key] = message.author.display_name

    async def _send(self, message: discord.Message, text: str) -> None:
        try:
            await message.reply(text, mention_author=False, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            log.warning("Could not reply in channel %s", message.channel.id, exc_info=True)

    async def _respond(self, message: discord.Message) -> None:
        """Answer a message that was addressed to the bot."""
        try:
            async with message.channel.typing():
                text = await self._chat(message)
        except BudgetExceeded as exc:
            log.info("AI budget reached, using a canned reply: %s", exc)
            text = pick_mention_reply()
        except LLMError:
            log.exception("AI call failed, using a canned reply")
            text = pick_mention_reply()
        except Exception:
            log.exception("Unexpected error while chatting")
            return
        await self._send(message, text)
        self._mark_conversation(message)

    def _should_chime_in(self, message: discord.Message) -> bool:
        """Should the bot jump into this (unaddressed) message? Cheap checks first, the dice last."""
        if self.random_chance <= 0 or len(message.content.strip()) < 10:
            return False
        if self.random_channels and message.channel.id not in self.random_channels:
            return False
        last = self._last_random.get(message.channel.id, float("-inf"))
        if time.monotonic() - last < self.random_cooldown:
            return False
        return random.random() < self.random_chance

    async def _chime_in(self, message: discord.Message) -> None:
        """Reply to a message nobody asked the bot about, if it has something good to say."""
        # The cooldown starts at the attempt, so a "nothing to add" answer still limits spending.
        self._last_random[message.channel.id] = time.monotonic()
        try:
            text = await self._chat(message, unprompted=True)
        except (BudgetExceeded, LLMError) as exc:
            log.info("No AI chime-in (%s), trying a canned keyword reply", exc)
            text = pick_reply(message.content)   # None when no keyword matches: stay quiet
        except Exception:
            log.exception("Unexpected error while chiming in")
            return
        if text:
            await self._send(message, text)
            self._mark_conversation(message)   # if they answer back, carry on talking

    async def _chat(self, message: discord.Message, unprompted: bool = False) -> str:
        text = " ".join(message.clean_content.split()).replace(f"@{message.guild.me.display_name}", "").strip()
        parts = []
        notes = await self._notes_block(message)
        if notes:
            parts.append("What you know about the people involved (for jokes and callbacks; "
                         "never recite it like a list):\n" + notes)
        context = await self._recent_context(message)
        if context:
            parts.append("Recent chat (oldest first):\n" + context)
        if unprompted:
            parts.append(f"{message.author.display_name} just said this in the chat (nobody asked you anything): {text}\n\n"
                         "Chime in with one short, funny remark only if you have something genuinely good "
                         "to add. If you don't, reply with exactly: SKIP")
        else:
            parts.append(f"{message.author.display_name} says to you: {text or '(just pinged you)'}")
        reply = await self.llm.complete(
            model=self.chat_model, system=self.persona, prompt="\n\n".join(parts),
            max_tokens=300, purpose="chime-in" if unprompted else "chat",
        )
        if unprompted:
            return "" if (not reply or reply.strip().upper().startswith("SKIP")) else truncate(reply, 1900)
        return truncate(reply, 1900) if reply else pick_mention_reply()

    async def _notes_block(self, message: discord.Message) -> str:
        db, guild_id = self.bot.db, message.guild.id
        sections = []
        own = await db.get_notes(guild_id, message.author.id, 12)
        if own:
            sections.append(f"About {message.author.display_name} (the person talking to you):\n"
                            + "\n".join(f"- {r['note']}" for r in own))
        seen = {message.author.id}
        for member in message.mentions:
            if member.bot or member.id in seen or len(seen) > 3:
                continue
            seen.add(member.id)
            rows = await db.get_notes(guild_id, member.id, 8)
            if rows:
                sections.append(f"About {member.display_name}:\n" + "\n".join(f"- {r['note']}" for r in rows))
        return "\n\n".join(sections)

    async def _recent_context(self, message: discord.Message) -> str:
        lines = []
        try:
            async for m in message.channel.history(limit=8, before=message):
                if not m.content:
                    continue
                who = "You" if m.author.id == self.bot.user.id else m.author.display_name
                lines.append(f"{who}: {truncate(' '.join(m.clean_content.split()), 200)}")
        except discord.HTTPException:
            return ""
        return "\n".join(reversed(lines))

    # ---- learning -------------------------------------------------------

    @tasks.loop(time=dtime(hour=4, tzinfo=timezone.utc))
    async def learn_daily(self) -> None:
        try:
            people, notes = await self.run_learning()
            log.info("Daily learning done: %d people processed, %d notes added", people, notes)
        except Exception:
            log.exception("Daily learning failed")

    @learn_daily.before_loop
    async def _before_learn(self) -> None:
        await self.bot.wait_until_ready()

    def _restore(self, guild_id: int, batch: list[tuple[int, list[str]]]) -> None:
        """Put messages back in the buffer (ahead of anything newer) so they are tried again later."""
        for user_id, msgs in batch:
            current = self.buffer.setdefault((guild_id, user_id), [])
            current[:0] = msgs
            if len(current) > MAX_BUFFER_PER_USER:
                del current[: len(current) - MAX_BUFFER_PER_USER]

    async def run_learning(self) -> tuple[int, int]:
        """Turn buffered messages into notes. Returns (people processed, notes added)."""
        if not self.enabled:
            return 0, 0
        async with self._learn_lock:
            snapshot, self.buffer = self.buffer, {}
            by_guild: dict[int, list[tuple[int, list[str]]]] = {}
            for (guild_id, user_id), msgs in snapshot.items():
                if len(msgs) >= MIN_MESSAGES:
                    by_guild.setdefault(guild_id, []).append((user_id, msgs))
                else:
                    self._restore(guild_id, [(user_id, msgs)])  # not enough yet, keep collecting
            processed = added = 0
            budget_hit = False
            for guild_id, users in by_guild.items():
                for i in range(0, len(users), BATCH_USERS):
                    batch = users[i:i + BATCH_USERS]
                    if budget_hit:
                        self._restore(guild_id, batch)
                        continue
                    try:
                        added += await self._learn_batch(guild_id, batch)
                        processed += len(batch)
                    except BudgetExceeded as exc:
                        log.info("Learning paused, budget reached: %s", exc)
                        budget_hit = True
                        self._restore(guild_id, batch)
                    except Exception:
                        log.exception("Learning batch failed")
            return processed, added

    async def _learn_batch(self, guild_id: int, batch: list[tuple[int, list[str]]]) -> int:
        db = self.bot.db
        people, valid, existing = [], {}, {}
        for user_id, msgs in batch:
            rows = await db.get_notes(guild_id, user_id, 40)
            people.append({
                "user_id": user_id,
                "name": self.names.get((guild_id, user_id), str(user_id)),
                "notes": [(r["id"], r["source"], r["note"]) for r in rows],
                "messages": msgs[-MESSAGES_PER_USER_IN_PROMPT:],
            })
            valid[user_id] = {r["id"] for r in rows if r["source"] == "auto"}
            existing[user_id] = {r["note"].strip().lower() for r in rows}

        raw = await self.llm.complete(
            model=self.memory_model, system=MEMORY_SYSTEM, prompt=format_memory_prompt(people),
            max_tokens=1500, purpose="memory",
        )
        added = 0
        for user_id, (adds, removes) in parse_memory_update(raw, valid).items():
            await db.delete_auto_notes(guild_id, user_id, removes)
            name = self.names.get((guild_id, user_id))
            for note in adds:
                if note.lower() in existing[user_id]:
                    continue
                await db.add_note(guild_id, user_id, name, note, "auto")
                existing[user_id].add(note.lower())
                added += 1
            await db.trim_auto_notes(guild_id, user_id, MAX_AUTO_NOTES)
        return added

    # ---- commands -------------------------------------------------------

    @commands.command(name="learnnow")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def learnnow(self, ctx: commands.Context) -> None:
        """Update the notes from what the bot has seen so far (normally this happens daily)."""
        if not self.enabled:
            await ctx.send("ANTHROPIC_API_KEY isn't set, so the AI features are off.")
            return
        if self._learn_lock.locked():
            await ctx.send("I'm already updating the notes, give me a moment.")
            return
        async with ctx.typing():
            people, notes = await self.run_learning()
        await ctx.send(f"Looked at {people} people and added {notes} new notes. "
                       "People with too few messages so far are kept for next time.")

    @commands.command(name="llmusage")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def llmusage(self, ctx: commands.Context) -> None:
        """Show AI spending against the caps."""
        if not self.enabled:
            await ctx.send("ANTHROPIC_API_KEY isn't set, so the AI features are off.")
            return
        today, month = await self.llm.spent_today(), await self.llm.spent_this_month()
        waiting = sum(len(v) for v in self.buffer.values())
        await ctx.send(
            f"Today: ${today:.4f} of ${self.llm.daily_cap:.2f}\n"
            f"This month: ${month:.4f} of ${self.llm.monthly_cap:.2f}\n"
            f"Models: chat `{self.chat_model}`, notes `{self.memory_model}`\n"
            f"Messages waiting to be turned into notes: {waiting}"
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Brain(bot))
