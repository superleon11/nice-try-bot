"""Database layer: plain asyncpg, plain SQL. Tables are created automatically on startup.

Only per-user counters are stored (message count, voice seconds). Message TEXT is never stored.
"""

import logging

import asyncpg

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_activity (
    guild_id      BIGINT NOT NULL,
    user_id       BIGINT NOT NULL,
    username      TEXT   NOT NULL,
    messages      BIGINT NOT NULL DEFAULT 0,
    voice_seconds BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);
"""

# Whitelist so a metric name can never be used for SQL injection.
# "combined" = messages + minutes spent in voice.
_METRIC_COLUMNS = {
    "messages": "messages",
    "voice": "voice_seconds",
    "combined": "(messages + voice_seconds / 60)",
}


class Database:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "Database":
        # asyncpg accepts both postgresql:// and postgres:// URLs, which is what Railway provides.
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA)
        log.info("Database ready")
        return cls(pool)

    async def close(self) -> None:
        await self.pool.close()

    # ---- activity -------------------------------------------------------

    async def record_message(self, *, guild_id: int, user_id: int, username: str) -> None:
        """Add one to a user's message counter."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO user_activity (guild_id, user_id, username, messages)
                   VALUES ($1, $2, $3, 1)
                   ON CONFLICT (guild_id, user_id)
                   DO UPDATE SET messages = user_activity.messages + 1,
                                 username = EXCLUDED.username""",
                guild_id, user_id, username,
            )

    async def add_voice_seconds(self, guild_id: int, user_id: int, username: str, seconds: int) -> None:
        if seconds <= 0:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO user_activity (guild_id, user_id, username, voice_seconds)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (guild_id, user_id)
                   DO UPDATE SET voice_seconds = user_activity.voice_seconds + EXCLUDED.voice_seconds,
                                 username = EXCLUDED.username""",
                guild_id, user_id, username, seconds,
            )

    # ---- stats ----------------------------------------------------------

    async def user_stats(self, guild_id: int, user_id: int):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """SELECT a.messages, a.voice_seconds,
                          (SELECT COUNT(*) + 1 FROM user_activity b
                            WHERE b.guild_id = a.guild_id AND b.messages > a.messages) AS message_rank,
                          (SELECT COUNT(*) + 1 FROM user_activity b
                            WHERE b.guild_id = a.guild_id AND b.voice_seconds > a.voice_seconds) AS voice_rank
                   FROM user_activity a
                   WHERE a.guild_id = $1 AND a.user_id = $2""",
                guild_id, user_id,
            )

    async def leaderboard(self, guild_id: int, metric: str, limit: int = 10):
        column = _METRIC_COLUMNS[metric]  # KeyError for unknown metric by design
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""SELECT user_id, username, messages, voice_seconds
                    FROM user_activity
                    WHERE guild_id = $1 AND {column} > 0
                    ORDER BY {column} DESC
                    LIMIT $2""",
                guild_id, limit,
            )
