"""
Main Discord Bot entry point.
Initializes the bot client and loads all cogs.
"""

import logging
import asyncio
import discord
from discord.ext import commands

from bot.utils.config import Config, setup_logging
from bot.utils.db import DatabaseManager

# Set up logging
setup_logging(Config.LOG_LEVEL)
logger = logging.getLogger(__name__)


class DiscordBot(commands.Bot):
    """Custom Discord bot class with database integration."""

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize the bot.

        Args:
            db_manager: DatabaseManager instance for database operations
        """
        # Set up intents
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read message content
        intents.voice_states = True     # Required for voice channel tracking

        super().__init__(
            command_prefix=Config.BOT_PREFIX,
            intents=intents,
            help_command=commands.DefaultHelpCommand()
        )

        self.db = db_manager
        self.synced = False

    async def setup_hook(self):
        """Called before the bot logs in."""
        logger.info("Bot setup_hook called")

        # Initialize database
        await self.db.initialize()
        logger.info("Database initialized")

        # Load cogs
        await self.load_cogs()
        logger.info("Cogs loaded")

        # Sync commands with Discord
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
            self.synced = True
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

    async def load_cogs(self):
        """Load all cogs from the cogs directory."""
        cogs_to_load = [
            'bot.cogs.activity_tracking',
            'bot.cogs.fun_replies',
            'bot.cogs.stats_commands',
            'bot.cogs.throwback',
        ]

        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}")

    async def on_ready(self):
        """Called when the bot is ready."""
        logger.info(f'Bot logged in as {self.user}')
        logger.info(f'Bot ID: {self.user.id}')
        if self.synced:
            logger.info('Commands synced with Discord')


async def main():
    """Main entry point for the bot."""
    # Validate configuration
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return

    # Create database manager
    db_manager = DatabaseManager(Config.DATABASE_URL)

    # Create and run bot
    bot = DiscordBot(db_manager)

    try:
        async with bot:
            await bot.start(Config.DISCORD_TOKEN)
    except discord.errors.LoginFailure:
        logger.error("Invalid Discord token. Please check your DISCORD_TOKEN in .env")
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        await db_manager.close()


if __name__ == '__main__':
    asyncio.run(main())
