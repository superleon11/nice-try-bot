"""Database layer: plain asyncpg, plain SQL. Tables are created automatically on startup.

Stored: per-user counters (message count, voice seconds), notes about people, and AI spend.
Message TEXT is never stored.
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

-- Notes the bot knows about people. Edit freely: UPDATE / INSERT / DELETE rows here and the bot
-- picks the changes up straight away. source 'manual' = yours (the AI never changes or removes
-- these); source 'auto' = written by the AI (it may tidy these up).
CREATE TABLE IF NOT EXISTS user_notes (
    id         SERIAL PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    username   TEXT,
    note       TEXT   NOT NULL,
    source     TEXT   NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_notes_user ON user_notes (guild_id, user_id);

-- One row per AI call, used for the spending cap.
CREATE TABLE IF NOT EXISTS llm_usage (
    id            BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    model         TEXT   NOT NULL,
    purpose       TEXT   NOT NULL,
    input_tokens  BIGINT NOT NULL,
    output_tokens BIGINT NOT NULL,
    cost_usd      DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_created ON llm_usage (created_at);
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

    # ---- notes about people ---------------------------------------------

    async def add_note(self, guild_id: int, user_id: int, username: str | None,
                       note: str, source: str = "manual") -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                """INSERT INTO user_notes (guild_id, user_id, username, note, source)
                   VALUES ($1, $2, $3, $4, $5) RETURNING id""",
                guild_id, user_id, username, note, source,
            )

    async def get_notes(self, guild_id: int, user_id: int, limit: int = 20):
        """Manual notes first, then the newest auto notes."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """SELECT id, note, source FROM user_notes
                   WHERE guild_id = $1 AND user_id = $2
                   ORDER BY (source = 'manual') DESC, id DESC
                   LIMIT $3""",
                guild_id, user_id, limit,
            )

    async def update_note(self, guild_id: int, note_id: int, note: str) -> bool:
        """Edit a note. An edited note becomes 'manual', so the AI will not remove it."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE user_notes SET note = $3, source = 'manual' WHERE id = $2 AND guild_id = $1",
                guild_id, note_id, note,
            )
        return int(result.split()[-1]) > 0

    async def delete_note(self, guild_id: int, note_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM user_notes WHERE id = $2 AND guild_id = $1", guild_id, note_id
            )
        return int(result.split()[-1]) > 0

    async def delete_auto_notes(self, guild_id: int, user_id: int, note_ids: list[int]) -> None:
        """Remove AI-written notes only (never manual ones)."""
        if not note_ids:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                """DELETE FROM user_notes
                   WHERE guild_id = $1 AND user_id = $2 AND source = 'auto' AND id = ANY($3::int[])""",
                guild_id, user_id, note_ids,
            )

    async def trim_auto_notes(self, guild_id: int, user_id: int, keep: int) -> None:
        """Keep only the newest `keep` AI-written notes for a person."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """DELETE FROM user_notes WHERE id IN (
                       SELECT id FROM user_notes
                       WHERE guild_id = $1 AND user_id = $2 AND source = 'auto'
                       ORDER BY id DESC OFFSET $3)""",
                guild_id, user_id, keep,
            )

    # ---- AI spend -------------------------------------------------------

    async def record_llm_usage(self, model: str, purpose: str, input_tokens: int,
                               output_tokens: int, cost_usd: float) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO llm_usage (model, purpose, input_tokens, output_tokens, cost_usd)
                   VALUES ($1, $2, $3, $4, $5)""",
                model, purpose, input_tokens, output_tokens, cost_usd,
            )

    async def llm_spend_since(self, since, purpose: str | None = None) -> float:
        async with self.pool.acquire() as conn:
            if purpose is None:
                total = await conn.fetchval(
                    "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_usage WHERE created_at >= $1", since
                )
            else:
                total = await conn.fetchval(
                    "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_usage WHERE created_at >= $1 AND purpose = $2",
                    since, purpose,
                )
        return float(total)
