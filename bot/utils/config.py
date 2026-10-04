"""
Configuration module for loading environment variables and bot settings.
"""

import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Bot configuration loaded from environment variables."""

    # Discord
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN', '')
    GUILD_ID = int(os.getenv('GUILD_ID', 0))
    THROWBACK_CHANNEL_ID = int(os.getenv('THROWBACK_CHANNEL_ID', 0))

    # Database
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://localhost/discord_bot')

    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # Bot
    BOT_PREFIX = os.getenv('BOT_PREFIX', '!')

    # Fun Replies
    FUN_REPLY_MIN_INTERVAL_SECONDS = 300  # 5 minutes between replies per channel
    FUN_REPLY_ENABLED = True

    # Activity Tracking
    ACTIVITY_TRACKING_ENABLED = True

    # Throwback
    THROWBACK_ENABLED = True
    THROWBACK_HOUR = 2  # Daily at 2 AM UTC
    THROWBACK_MINUTE = 0

    @staticmethod
    def validate():
        """Validate required configuration."""
        errors = []

        if not Config.DISCORD_TOKEN:
            errors.append("DISCORD_TOKEN not set in .env")

        if Config.GUILD_ID == 0:
            errors.append("GUILD_ID not set in .env")

        if Config.THROWBACK_CHANNEL_ID == 0:
            errors.append("THROWBACK_CHANNEL_ID not set in .env")

        if not Config.DATABASE_URL:
            errors.append("DATABASE_URL not set in .env")

        if errors:
            for error in errors:
                logging.error(f"Configuration Error: {error}")
            raise ValueError("Configuration validation failed")

        logging.info("Configuration validated successfully")


def setup_logging(log_level: str = 'INFO'):
    """Set up logging configuration."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('bot.log'),
            logging.StreamHandler()
        ]
    )

    # Reduce verbosity of discord.py logger
    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.WARNING)
