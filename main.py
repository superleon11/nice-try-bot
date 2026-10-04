"""Entry point: python main.py"""

import logging
import os
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv

from db import Database

load_dotenv()

log = logging.getLogger("funbot")

PREFIX = os.getenv("BOT_PREFIX", "!")
EXTENSIONS = ("cogs.activity", "cogs.fun", "cogs.stats", "cogs.throwback", "cogs.soundboard",
              "cogs.notes", "cogs.brain", "cogs.imagegen")


class FunBot(commands.Bot):
    def __init__(self, dsn: str):
        intents = discord.Intents.default()
        intents.message_content = True  # privileged: must also be enabled in the Developer Portal
        super().__init__(command_prefix=PREFIX, intents=intents)
        self.dsn = dsn
        self.db: Database | None = None

    async def setup_hook(self) -> None:
        self.db = await Database.connect(self.dsn)
        for ext in EXTENSIONS:
            await self.load_extension(ext)
            log.info("Loaded %s", ext)

    async def close(self) -> None:
        # Unloads cogs first (the activity cog saves open voice sessions), then closes the DB.
        await super().close()
        if self.db is not None:
            await self.db.close()

    async def on_ready(self) -> None:
        log.info("Logged in as %s (id %s) in %d server(s)", self.user, self.user.id, len(self.guilds))

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, (commands.MissingPermissions, commands.NoPrivateMessage)):
            await ctx.send(str(error))
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"Bad argument: {error}")
            return
        log.error("Error in command %s", ctx.command, exc_info=error)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    token = os.getenv("DISCORD_TOKEN")
    dsn = os.getenv("DATABASE_URL")
    missing = [name for name, value in (("DISCORD_TOKEN", token), ("DATABASE_URL", dsn)) if not value]
    if missing:
        sys.exit(f"Missing required environment variable(s): {', '.join(missing)}")

    # log_handler=None: we configured logging ourselves above.
    FunBot(dsn).run(token, log_handler=None)


if __name__ == "__main__":
    main()
