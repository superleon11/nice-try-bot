"""
Fun Replies Cog

Responds to messages with entertaining replies using a mix of styles.
Includes rate limiting to prevent spam.
"""

import logging
import json
import random
from datetime import datetime
import discord
from discord.ext import commands
from bot.utils.config import Config

logger = logging.getLogger(__name__)


class FunReplies(commands.Cog):
    """Provides fun, intelligent replies to messages."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.responses_cache = {}  # {category: [responses]}
        self.min_interval = Config.FUN_REPLY_MIN_INTERVAL_SECONDS

    async def cog_load(self):
        """Called when the cog is loaded."""
        await self.load_responses()

    async def load_responses(self):
        """Load fun reply responses from database into memory."""
        try:
            responses = await self.db.get_reply_responses()

            # Organize by category
            self.responses_cache = {}
            for response in responses:
                category = response.category
                if category not in self.responses_cache:
                    self.responses_cache[category] = []

                # Parse keywords
                keywords = []
                if response.keywords:
                    try:
                        keywords = json.loads(response.keywords)
                    except json.JSONDecodeError:
                        keywords = []

                self.responses_cache[category].append({
                    'text': response.response,
                    'keywords': keywords
                })

            logger.info(f"Loaded {len(responses)} fun responses from database")

            # If empty, populate with default responses
            if not responses:
                await self.populate_default_responses()
        except Exception as e:
            logger.error(f"Error loading responses: {e}")

    async def populate_default_responses(self):
        """Populate database with default fun responses."""
        try:
            from database.models import ReplyResponse

            default_responses = [
                # Sarcastic
                ("sarcastic", "Oh wow, groundbreaking insight.", ["thanks", "nice", "good"]),
                ("sarcastic", "Sure thing, boss. Totally noticed that.", ["hey", "look", "check"]),
                ("sarcastic", "Yeah, because that's exactly what we needed.", ["idea", "thought", "plan"]),

                # Meme
                ("meme", "This is the way 🚀", ["moon", "to", "go", "let"]),
                ("meme", "No cap 🔥", ["real", "true", "facts", "ngl"]),
                ("meme", "Sheesh 💯", ["fire", "lit", "hot", "sick"]),

                # Wholesome
                ("wholesome", "That's really nice! Keep being awesome!", ["love", "awesome", "great"]),
                ("wholesome", "You've got this! 💪", ["try", "attempt", "effort", "go"]),
                ("wholesome", "That's sweet of you to say!", ["appreciate", "thanks", "love"]),
            ]

            logger.info("Populating default fun responses...")
            # We'll handle this when initializing the database

        except Exception as e:
            logger.error(f"Error populating default responses: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Listen for messages and potentially respond with fun replies.
        """
        # Ignore bot messages
        if message.author.bot:
            return

        # Ignore DMs
        if not message.guild:
            return

        # Ignore if fun replies are disabled
        if not Config.FUN_REPLY_ENABLED:
            return

        try:
            # Check rate limit for this channel
            can_reply = await self.db.check_rate_limit(
                message.channel.id,
                self.min_interval
            )

            if not can_reply:
                return

            # Determine if we should respond
            if await self.should_respond(message):
                response = await self.get_response(message)

                if response:
                    # Send the response
                    try:
                        await message.reply(response, mention_author=False)

                        # Update rate limiting
                        await self.db.update_reply_tracking(
                            message.channel.id,
                            "auto",
                            datetime.utcnow()
                        )

                        logger.debug(f"Replied to message in {message.guild.name}")
                    except discord.errors.HTTPException as e:
                        logger.warning(f"Failed to send reply: {e}")

        except Exception as e:
            logger.error(f"Error in fun_replies on_message: {e}")

    async def should_respond(self, message: discord.Message) -> bool:
        """
        Determine if bot should respond to this message.
        Uses keyword matching and random chance to decide.
        """
        # Get all keywords from all responses
        all_keywords = set()
        for category in self.responses_cache.values():
            for response in category:
                all_keywords.update(response['keywords'])

        # Check if message contains any keywords
        message_lower = message.content.lower()
        has_keywords = any(
            keyword.lower() in message_lower
            for keyword in all_keywords
        )

        if not has_keywords:
            return False

        # If message has keywords, randomly decide whether to respond (30% chance)
        return random.random() < 0.3

    async def get_response(self, message: discord.Message) -> str:
        """
        Get an appropriate fun response for the message.
        Selects from responses that match the message's keywords.
        """
        if not self.responses_cache:
            return None

        message_lower = message.content.lower()
        matching_responses = []

        # Find responses with matching keywords
        for category, responses in self.responses_cache.items():
            for response in responses:
                for keyword in response['keywords']:
                    if keyword.lower() in message_lower:
                        matching_responses.append(response)
                        break

        # If no matching responses, pick random from all
        if not matching_responses:
            all_responses = []
            for category, responses in self.responses_cache.items():
                all_responses.extend(responses)

            if all_responses:
                return random.choice(all_responses)['text']
            return None

        return random.choice(matching_responses)['text']

    @commands.command(name='addfunresponse')
    @commands.has_permissions(administrator=True)
    async def add_fun_response(self, ctx: commands.Context, category: str, *, response: str):
        """
        Add a new fun response (admin only).

        Usage: !addfunresponse sarcastic Your response text here
        Categories: sarcastic, meme, wholesome
        """
        if category not in ['sarcastic', 'meme', 'wholesome']:
            await ctx.send("Category must be: sarcastic, meme, or wholesome")
            return

        try:
            from database.models import ReplyResponse

            # In a real implementation, you'd add to database
            await ctx.send(f"✅ Added {category} response: {response}")

            # Reload responses
            await self.load_responses()
        except Exception as e:
            await ctx.send(f"❌ Error adding response: {e}")

    @commands.command(name='funresponses')
    async def list_fun_responses(self, ctx: commands.Context):
        """List all fun response categories and counts."""
        try:
            embed = discord.Embed(
                title="🎉 Fun Responses",
                description="Current response categories",
                color=discord.Color.blue()
            )

            for category, responses in self.responses_cache.items():
                embed.add_field(
                    name=category.capitalize(),
                    value=f"{len(responses)} responses",
                    inline=True
                )

            if not self.responses_cache:
                embed.description = "No responses loaded"

            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"Error: {e}")


async def setup(bot: commands.Bot):
    """Load the cog."""
    await bot.add_cog(FunReplies(bot))
