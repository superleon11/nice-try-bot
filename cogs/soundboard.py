"""Occasionally joins a long-running voice call, plays a soundboard clip, then leaves.

Timing, per voice channel:
  1. The channel must have had at least SOUND_MIN_HUMANS people in it, without dropping below that,
     for SOUND_MIN_CALL_MINUTES (default 15).
  2. After that, the bot waits a random SOUND_MIN_DELAY_MINUTES..SOUND_MAX_DELAY_MINUTES (default 15-45),
     joins, plays one random soundboard clip, and leaves.
  3. If the call is still going, step 2 repeats.
If the channel drops below the minimum number of people, everything resets.
"""

import asyncio
import logging
import os
import random

import discord
from discord.ext import commands

log = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        log.warning("%s=%r is not a number, using %s", name, raw, default)
        return default


class SoundVisits(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.enabled = os.getenv("SOUND_VISITS_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")
        self.min_call = _env_float("SOUND_MIN_CALL_MINUTES", 15) * 60
        self.min_delay = _env_float("SOUND_MIN_DELAY_MINUTES", 15) * 60
        self.max_delay = max(self.min_delay, _env_float("SOUND_MAX_DELAY_MINUTES", 45) * 60)
        self.min_humans = max(1, int(_env_float("SOUND_MIN_HUMANS", 2)))
        self.settle_seconds = 1.0  # pause after connecting, before sending the clip
        self.listen_seconds = 6.0  # soundboard clips are at most ~5 seconds long
        self.tasks: dict[int, asyncio.Task] = {}  # voice channel id -> its scheduler task
        self._seeded = False

    # ---- scheduling -----------------------------------------------------

    @staticmethod
    def _humans(channel: discord.VoiceChannel) -> int:
        return sum(1 for m in channel.members if not m.bot)

    def _refresh(self, channel) -> None:
        """Start or stop the scheduler for a channel depending on who is in it right now."""
        if not isinstance(channel, discord.VoiceChannel):
            return  # stage channels etc. are ignored
        task = self.tasks.get(channel.id)
        if self._humans(channel) >= self.min_humans:
            if task is None or task.done():
                self.tasks[channel.id] = asyncio.create_task(
                    self._run(channel), name=f"sound-visits-{channel.id}"
                )
        elif task is not None:
            del self.tasks[channel.id]
            task.cancel()

    async def _run(self, channel: discord.VoiceChannel) -> None:
        try:
            await asyncio.sleep(self.min_call)
            while True:
                await asyncio.sleep(random.uniform(self.min_delay, self.max_delay))
                try:
                    await self.visit(channel)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("Sound visit to #%s failed", channel.name)
        finally:
            if self.tasks.get(channel.id) is asyncio.current_task():
                del self.tasks[channel.id]

    # ---- the visit itself -----------------------------------------------

    async def _pick_sound(self, guild: discord.Guild):
        sounds = [s for s in getattr(guild, "soundboard_sounds", []) if s.available]
        if not sounds:  # server has no custom sounds: use Discord's built-in ones
            try:
                sounds = await self.bot.fetch_soundboard_default_sounds()
            except discord.HTTPException:
                log.warning("Could not fetch Discord's default soundboard sounds", exc_info=True)
                return None
        return random.choice(sounds) if sounds else None

    async def visit(self, channel: discord.VoiceChannel) -> bool:
        """Join, play one clip, leave. Returns False if it had to skip."""
        guild = channel.guild
        if guild.voice_client is not None:
            log.info("Skipping visit to #%s: already connected to voice in this server", channel.name)
            return False
        perms = channel.permissions_for(guild.me)
        if not (perms.connect and perms.speak):
            log.warning("Skipping visit to #%s: missing Connect/Speak permission", channel.name)
            return False
        send = getattr(channel, "send_sound", None) or getattr(channel, "send_soundboard_sound", None)
        if send is None:
            log.error("This discord.py version cannot send soundboard sounds")
            return False
        sound = await self._pick_sound(guild)
        if sound is None:
            log.warning("Skipping visit to #%s: no soundboard sounds available", channel.name)
            return False

        try:
            vc = await channel.connect(timeout=20.0, reconnect=False)
        except Exception:
            if guild.voice_client is not None:  # don't leave a half-open connection behind
                await guild.voice_client.disconnect(force=True)
            raise
        try:
            await asyncio.sleep(self.settle_seconds)
            await send(sound)
            log.info("Played soundboard sound %r in #%s", getattr(sound, "name", sound), channel.name)
            await asyncio.sleep(self.listen_seconds)
        finally:
            await vc.disconnect()
        return True

    # ---- events ---------------------------------------------------------

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._seeded or not self.enabled:
            return
        self._seeded = True
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                self._refresh(channel)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState, after: discord.VoiceState) -> None:
        if not self.enabled or member.bot:
            return
        touched = {c.id: c for c in (before.channel, after.channel) if c is not None}
        for channel in touched.values():
            self._refresh(channel)

    async def cog_unload(self) -> None:
        for task in list(self.tasks.values()):
            task.cancel()
        self.tasks.clear()
        for vc in list(self.bot.voice_clients):
            await vc.disconnect(force=True)

    # ---- test command ---------------------------------------------------

    @commands.command(name="soundtest")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def soundtest(self, ctx: commands.Context) -> None:
        """Join your current voice channel now, play a soundboard clip, and leave."""
        voice = ctx.author.voice
        if voice is None or not isinstance(voice.channel, discord.VoiceChannel):
            await ctx.send("Join a voice channel first, then run this again.")
            return
        await ctx.send("On my way!")
        try:
            ok = await self.visit(voice.channel)
        except Exception as exc:
            log.exception("!soundtest failed")
            await ctx.send(f"That didn't work: `{type(exc).__name__}: {exc}`. The logs have the details.")
            return
        if not ok:
            await ctx.send("I couldn't do it: missing Connect/Speak permission, no sounds available, "
                           "or I'm already in a call. The logs say which.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SoundVisits(bot))
