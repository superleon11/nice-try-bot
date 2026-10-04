"""Image generation: "generate me an image of ..." (or !imagine ...) makes a picture with OpenAI.

Needs OPENAI_API_KEY. Without it the cog does nothing. Spending goes through images.ImageClient,
which enforces the daily/monthly caps.
"""

import io
import logging
import os

import discord
from discord.ext import commands

from envutil import env_float
from helpers import parse_image_request, truncate
from images import ImageClient
from llm import BudgetExceeded, LLMError

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-image-2.5-flare"


class ImageGen(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        key = os.getenv("OPENAI_API_KEY", "").strip()
        self.enabled = bool(key)
        self.client: ImageClient | None = None
        if self.enabled:
            self.client = ImageClient(
                bot.db, key,
                model=os.getenv("IMAGE_MODEL", "").strip() or DEFAULT_MODEL,
                quality=os.getenv("IMAGE_QUALITY", "").strip() or "medium",
                size=os.getenv("IMAGE_SIZE", "").strip() or "1024x1024",
                reserve_usd=env_float("IMAGE_MAX_COST_USD", 0.25),
                daily_cap=env_float("IMAGE_DAILY_BUDGET_USD", 1.0),
                total_daily_cap=env_float("LLM_DAILY_BUDGET_USD", 0.50),
                total_monthly_cap=env_float("LLM_MONTHLY_BUDGET_USD", 10.0),
            )
        bot.image_claims = self.is_image_request if self.enabled else None

    async def cog_load(self) -> None:
        if not self.enabled:
            log.warning("OPENAI_API_KEY not set: image generation is off")
            return
        c = self.client
        log.info("Images on: %s, quality %s, size %s, reserve $%.2f/image, caps $%.2f/day images, "
                 "$%.2f/day and $%.2f/month overall", c.model, c.quality, c.size, c.reserve,
                 c.daily_cap, c.total_daily_cap, c.total_monthly_cap)

    async def cog_unload(self) -> None:
        self.bot.image_claims = None
        if self.client is not None:
            await self.client.close()

    # ---- detecting requests ---------------------------------------------

    def _text(self, message: discord.Message) -> str:
        text = " ".join(message.clean_content.split())
        if message.guild is not None:
            text = text.replace(f"@{message.guild.me.display_name}", "")
        return text.strip()

    def is_image_request(self, message: discord.Message) -> bool:
        return parse_image_request(self._text(message)) is not None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not self.enabled or message.author.bot or message.guild is None or not message.content:
            return
        if message.content.startswith(self.bot.command_prefix):
            return
        what = parse_image_request(self._text(message))
        if what is None:
            return
        await self._make(message, what)

    @commands.command(name="imagine")
    @commands.guild_only()
    async def imagine(self, ctx: commands.Context, *, description: str = "") -> None:
        """Make an image: !imagine a corgi astronaut"""
        if not self.enabled:
            await ctx.send("OPENAI_API_KEY isn't set, so image generation is off.")
            return
        await self._make(ctx.message, " ".join(description.split()))

    # ---- generating -----------------------------------------------------

    async def _make(self, message: discord.Message, what: str) -> None:
        if not what:
            await self._reply(message, "Generate what? Tell me what the image should show, "
                                       "e.g. `generate me an image of a cat in a wizard hat`.")
            return
        try:
            async with message.channel.typing():
                data, ext = await self.client.generate(what)
        except BudgetExceeded as exc:
            log.info("Image refused, budget reached: %s", exc)
            await self._reply(message, "I've hit my image budget for now, try again later.")
            return
        except LLMError as exc:
            log.warning("Image generation failed: %s", exc)
            await self._reply(message, "I couldn't make that one. The image service said no or had a problem. "
                                       "Try rewording it.")
            return
        except Exception:
            log.exception("Unexpected error while generating an image")
            return

        limit = message.guild.filesize_limit if message.guild else 8 * 1024 * 1024
        if len(data) > limit:
            await self._reply(message, "That image came out too big to upload here, sorry.")
            return
        file = discord.File(io.BytesIO(data), filename=f"image.{ext}")
        try:
            await message.reply(truncate(f"🎨 {what}", 300), file=file, mention_author=False,
                                allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            log.warning("Could not post the image in channel %s", message.channel.id, exc_info=True)

    async def _reply(self, message: discord.Message, text: str) -> None:
        try:
            await message.reply(text, mention_author=False, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            log.warning("Could not reply in channel %s", message.channel.id, exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ImageGen(bot))
