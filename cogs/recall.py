"""Find old messages by asking the bot, in plain words.

    @bot find me a funny message @Dave has said in the past
    @bot what's the most embarrassing thing I've ever said
    @bot dig up something @Sam said about pizza

The bot reads the server's history live (newest first, within a time limit, only channels both it and
the asker can read), keeps the messages from the people asked about, and has the AI pick the one that
best fits the request. Nothing is stored.
"""

import asyncio
import json
import logging
import os
import random
import time

import discord
from discord.ext import commands

from envutil import env_float, env_int
from helpers import RECALL_RULES, format_recall_prompt, parse_judge_reply, parse_recall_request, truncate
from llm import BudgetExceeded, LLMError
from recall import search_history

log = logging.getLogger(__name__)


def _says_nothing_fits(raw: str) -> bool:
    """Did the model answer {"pick": 0}?"""
    try:
        data = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        return int(data["pick"]) == 0
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


class Recall(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.enabled = os.getenv("RECALL_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")
        self.seconds = max(5.0, env_float("RECALL_SCAN_SECONDS", 40))
        self.max_scanned = max(100, env_int("RECALL_MAX_MESSAGES", 30000))
        self.cooldown = max(0.0, env_float("RECALL_COOLDOWN_SECONDS", 30))
        self.model = os.getenv("LLM_RECALL_MODEL", "").strip() or "claude-sonnet-5-5"
        self._busy: set[int] = set()            # guilds with a scan in progress
        self._last: dict[int, float] = {}       # user id -> time.monotonic() of their last search
        bot.recall_claims = self.claims

    def _request(self, message):
        """(scope, topic) if this is a message to the bot asking to find something, else None."""
        if not self.enabled or message.author.bot or message.guild is None or not message.content:
            return None
        if message.content.startswith(self.bot.command_prefix):
            return None
        brain = self.bot.get_cog("Brain")
        if brain is None or not brain.enabled or not brain.is_for_me(message):
            return None
        humans = [m for m in message.mentions if not m.bot]
        return parse_recall_request(message.clean_content, bool(humans))

    def claims(self, message) -> bool:
        return self._request(message) is not None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        req = self._request(message)
        if req is not None:
            await self._handle(message, *req)

    async def _handle(self, message, scope: str, topic: list[str]) -> None:
        brain = self.bot.get_cog("Brain")
        guild = message.guild
        wait = self.cooldown - (time.monotonic() - self._last.get(message.author.id, float("-inf")))
        if wait > 0:
            await self._say(message, f"Give me {int(wait) + 1} seconds, then ask again.")
            return
        if guild.id in self._busy:
            await self._say(message, "I'm already digging through the archives, one at a time please.")
            return
        self._busy.add(guild.id)
        self._last[message.author.id] = time.monotonic()
        try:
            if scope == "mentioned":
                ids = [m.id for m in message.mentions if not m.bot]
            elif scope == "self":
                ids = [message.author.id]
            else:
                ids = []
            async with message.channel.typing():
                result = await search_history(guild, message.author, ids, topic, prefix=self.bot.command_prefix,
                                              seconds=self.seconds, max_scanned=self.max_scanned)
                log.info("Recall: scanned %d messages in %d/%d channels, %d usable from the target(s), pool %d",
                         result.scanned, result.channels_done, result.channels_total, result.matched,
                         len(result.pool))
                if not result.pool:
                    await self._say(message, "I couldn't find anything from them that I could use.")
                    return
                pick, comment = await self._choose(brain, message, result.pool)
            if pick is None:
                await self._say(message, "I looked, but nothing I found really fits that.")
                return
            await self._post(message, pick, comment, result)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Message search failed")
            await self._say(message, "Something went wrong while searching, sorry.")
        finally:
            self._busy.discard(guild.id)

    async def _choose(self, brain, message, pool):
        """(chosen Hit or None, comment). Falls back to a good message at random if the AI can't."""
        if len(pool) == 1:
            return pool[0], ""
        shuffled = list(pool)
        random.shuffle(shuffled)   # so list position can't bias the choice
        entries = [(h.message.author.display_name, h.message.created_at.strftime("%d %b %Y"),
                    h.reactions, truncate(h.text, 400)) for h in shuffled]
        request = " ".join(message.clean_content.split()).replace(f"@{message.guild.me.display_name}", "").strip()
        try:
            raw = await brain.llm.complete(
                model=self.model, system=brain.persona + "\n\n" + RECALL_RULES,
                prompt=format_recall_prompt(request, entries), max_tokens=300, purpose="recall")
        except BudgetExceeded as exc:
            log.info("Recall AI skipped, budget reached: %s", exc)
            return random.choice(pool[:5]), ""
        except LLMError:
            log.exception("Recall AI failed, picking without it")
            return random.choice(pool[:5]), ""
        if _says_nothing_fits(raw):
            return None, ""
        parsed = parse_judge_reply(raw, len(shuffled))
        if parsed is None:
            return random.choice(pool[:5]), ""
        return shuffled[parsed[0]], parsed[1]

    async def _post(self, message, hit, comment, result) -> None:
        m = hit.message
        embed = discord.Embed(description=truncate(hit.text, 1500), colour=discord.Colour.blurple())
        embed.add_field(name="From", value=discord.utils.escape_markdown(m.author.display_name))
        if m.channel.id != message.channel.id:
            embed.add_field(name="In", value=f"<#{m.channel.id}>")
        embed.add_field(name="When", value=discord.utils.format_dt(m.created_at, "D"))
        if hit.reactions:
            embed.add_field(name="Reactions", value=f"⭐ {hit.reactions}")
        embed.add_field(name="​", value=f"[Jump to message]({m.jump_url})", inline=False)
        if not result.complete and result.oldest is not None:
            embed.set_footer(text=f"I only had time to search back to {result.oldest.strftime('%d %b %Y')} "
                                  "in some channels.")
        try:
            await message.reply(comment or None, embed=embed, mention_author=False,
                                allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            log.warning("Could not post the search result", exc_info=True)

    async def _say(self, message, text: str) -> None:
        try:
            await message.reply(text, mention_author=False, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            log.warning("Could not reply in channel %s", message.channel.id, exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Recall(bot))
