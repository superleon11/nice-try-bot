"""
Database connection and query helper utilities.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine, AsyncPool
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError

from database.models import Base, User, Message, VoiceSession, UserActivitySummary, ReplyResponse, FunReplyTracking

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and provides query helpers."""

    def __init__(self, database_url: str):
        """
        Initialize database manager.

        Args:
            database_url: PostgreSQL connection string
                Format: postgresql+asyncpg://user:password@host:port/database
        """
        self.database_url = database_url
        self.engine = None
        self.session_maker = None

    async def initialize(self):
        """Initialize the database engine and create tables."""
        try:
            # Create async engine with connection pooling
            self.engine = create_async_engine(
                self.database_url,
                poolclass=AsyncPool,
                pool_size=10,
                max_overflow=20,
                echo=False  # Set to True for SQL debugging
            )

            # Create session factory
            self.session_maker = sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            # Create all tables
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    @asynccontextmanager
    async def get_session(self):
        """
        Context manager for database sessions.

        Usage:
            async with db.get_session() as session:
                # Use session
        """
        session = self.session_maker()
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()

    # ==================== USER OPERATIONS ====================

    async def upsert_user(self, user_id: int, username: str) -> User:
        """Create or update a user."""
        try:
            async with self.get_session() as session:
                stmt = select(User).where(User.id == user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()

                if user:
                    user.username = username
                else:
                    user = User(id=user_id, username=username)
                    session.add(user)

                await session.commit()
                return user
        except IntegrityError:
            logger.warning(f"User {user_id} already exists")
            return await self.get_user(user_id)

    async def get_user(self, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        async with self.get_session() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    # ==================== MESSAGE OPERATIONS ====================

    async def add_message(self, message_id: int, user_id: int, channel_id: int,
                         guild_id: int, content: str, created_at) -> Message:
        """Add a new message to the database."""
        try:
            async with self.get_session() as session:
                msg = Message(
                    id=message_id,
                    user_id=user_id,
                    channel_id=channel_id,
                    guild_id=guild_id,
                    content=content,
                    created_at=created_at,
                    is_bot=False
                )
                session.add(msg)
                await session.commit()
                return msg
        except IntegrityError:
            logger.debug(f"Message {message_id} already exists")

    async def get_random_message(self, guild_id: int, exclude_bot: bool = True):
        """Get a random message from a guild."""
        try:
            async with self.get_session() as session:
                query = select(Message).where(Message.guild_id == guild_id)

                if exclude_bot:
                    query = query.where(Message.is_bot == False)

                # Order by random and get first
                query = query.order_by(func.random()).limit(1)
                result = await session.execute(query)
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting random message: {e}")
            return None

    async def get_message_count(self, user_id: int, guild_id: int) -> int:
        """Get message count for a user in a guild."""
        async with self.get_session() as session:
            stmt = select(func.count(Message.id)).where(
                (Message.user_id == user_id) & (Message.guild_id == guild_id)
            )
            result = await session.execute(stmt)
            return result.scalar() or 0

    # ==================== VOICE SESSION OPERATIONS ====================

    async def start_voice_session(self, user_id: int, guild_id: int,
                                  channel_id: int, joined_at) -> VoiceSession:
        """Create a new voice session."""
        try:
            async with self.get_session() as session:
                session_obj = VoiceSession(
                    user_id=user_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    joined_at=joined_at
                )
                session.add(session_obj)
                await session.commit()
                return session_obj
        except Exception as e:
            logger.error(f"Error creating voice session: {e}")
            return None

    async def end_voice_session(self, user_id: int, guild_id: int, left_at) -> Optional[int]:
        """End a voice session and return duration in seconds."""
        try:
            async with self.get_session() as session:
                # Find active session
                stmt = select(VoiceSession).where(
                    (VoiceSession.user_id == user_id) &
                    (VoiceSession.guild_id == guild_id) &
                    (VoiceSession.left_at == None)
                ).order_by(VoiceSession.joined_at.desc()).limit(1)

                result = await session.execute(stmt)
                voice_session = result.scalar_one_or_none()

                if voice_session:
                    voice_session.left_at = left_at
                    duration = (left_at - voice_session.joined_at).total_seconds()
                    voice_session.duration_seconds = int(duration)
                    await session.commit()
                    return int(duration)
                return None
        except Exception as e:
            logger.error(f"Error ending voice session: {e}")
            return None

    async def get_voice_duration(self, user_id: int, guild_id: int) -> int:
        """Get total voice duration in seconds for a user in a guild."""
        async with self.get_session() as session:
            stmt = select(func.sum(VoiceSession.duration_seconds)).where(
                (VoiceSession.user_id == user_id) &
                (VoiceSession.guild_id == guild_id) &
                (VoiceSession.duration_seconds != None)
            )
            result = await session.execute(stmt)
            total = result.scalar()
            return total or 0

    # ==================== ACTIVITY SUMMARY OPERATIONS ====================

    async def update_activity_summary(self, user_id: int, guild_id: int):
        """Update user activity summary from raw message and voice data."""
        try:
            async with self.get_session() as session:
                # Get message count
                msg_count = await self.get_message_count(user_id, guild_id)
                voice_seconds = await self.get_voice_duration(user_id, guild_id)

                # Get or create summary
                stmt = select(UserActivitySummary).where(
                    (UserActivitySummary.user_id == user_id) &
                    (UserActivitySummary.guild_id == guild_id)
                )
                result = await session.execute(stmt)
                summary = result.scalar_one_or_none()

                if summary:
                    summary.total_messages = msg_count
                    summary.total_voice_seconds = voice_seconds
                else:
                    summary = UserActivitySummary(
                        user_id=user_id,
                        guild_id=guild_id,
                        total_messages=msg_count,
                        total_voice_seconds=voice_seconds
                    )
                    session.add(summary)

                await session.commit()
                return summary
        except IntegrityError:
            logger.debug(f"Summary for user {user_id} in guild {guild_id} already exists")
        except Exception as e:
            logger.error(f"Error updating activity summary: {e}")

    async def get_leaderboard(self, guild_id: int, metric: str = "messages", limit: int = 10):
        """
        Get activity leaderboard for a guild.

        Args:
            guild_id: Discord guild ID
            metric: 'messages', 'voice', or 'combined'
            limit: Number of results to return

        Returns:
            List of (User, activity_value) tuples
        """
        try:
            async with self.get_session() as session:
                if metric == "messages":
                    order_by = UserActivitySummary.total_messages.desc()
                elif metric == "voice":
                    order_by = UserActivitySummary.total_voice_seconds.desc()
                else:  # combined
                    # Simple combination: messages + (voice_seconds / 60 as a proxy for engagement)
                    order_by = (UserActivitySummary.total_messages +
                               (UserActivitySummary.total_voice_seconds / 60)).desc()

                stmt = select(User, UserActivitySummary).join(
                    UserActivitySummary
                ).where(UserActivitySummary.guild_id == guild_id).order_by(
                    order_by
                ).limit(limit)

                result = await session.execute(stmt)
                return result.all()
        except Exception as e:
            logger.error(f"Error getting leaderboard: {e}")
            return []

    async def get_user_stats(self, user_id: int, guild_id: int):
        """Get complete activity stats for a user in a guild."""
        try:
            async with self.get_session() as session:
                stmt = select(UserActivitySummary).where(
                    (UserActivitySummary.user_id == user_id) &
                    (UserActivitySummary.guild_id == guild_id)
                )
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return None

    async def get_user_rank(self, user_id: int, guild_id: int, metric: str = "messages") -> Optional[int]:
        """Get a user's rank in a guild leaderboard."""
        try:
            async with self.get_session() as session:
                if metric == "messages":
                    order_by = UserActivitySummary.total_messages.desc()
                elif metric == "voice":
                    order_by = UserActivitySummary.total_voice_seconds.desc()
                else:
                    order_by = (UserActivitySummary.total_messages +
                               (UserActivitySummary.total_voice_seconds / 60)).desc()

                # Count how many users have higher values
                user_summary = await self.get_user_stats(user_id, guild_id)
                if not user_summary:
                    return None

                if metric == "messages":
                    target_value = user_summary.total_messages
                    compare = UserActivitySummary.total_messages > target_value
                elif metric == "voice":
                    target_value = user_summary.total_voice_seconds
                    compare = UserActivitySummary.total_voice_seconds > target_value
                else:
                    return None

                stmt = select(func.count()).select_from(UserActivitySummary).where(
                    (UserActivitySummary.guild_id == guild_id) & compare
                )
                result = await session.execute(stmt)
                rank_offset = result.scalar() or 0
                return rank_offset + 1  # Rank is 1-indexed
        except Exception as e:
            logger.error(f"Error getting user rank: {e}")
            return None

    # ==================== FUN REPLY OPERATIONS ====================

    async def get_reply_responses(self, category: Optional[str] = None) -> list:
        """Get fun reply responses, optionally filtered by category."""
        async with self.get_session() as session:
            stmt = select(ReplyResponse).where(ReplyResponse.enabled == True)

            if category:
                stmt = stmt.where(ReplyResponse.category == category)

            result = await session.execute(stmt)
            return result.scalars().all()

    async def check_rate_limit(self, channel_id: int, min_interval_seconds: int = 300) -> bool:
        """Check if enough time has passed since last fun reply in channel."""
        try:
            from datetime import datetime, timedelta

            async with self.get_session() as session:
                stmt = select(FunReplyTracking).where(
                    FunReplyTracking.channel_id == channel_id
                ).order_by(FunReplyTracking.last_reply_at.desc()).limit(1)

                result = await session.execute(stmt)
                tracking = result.scalar_one_or_none()

                if not tracking:
                    return True

                time_since_reply = (datetime.utcnow() - tracking.last_reply_at).total_seconds()
                return time_since_reply >= min_interval_seconds
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return True  # Allow reply if error

    async def update_reply_tracking(self, channel_id: int, category: str, replied_at):
        """Update or create rate limit tracking for a channel."""
        try:
            async with self.get_session() as session:
                # Try to find existing tracking
                stmt = select(FunReplyTracking).where(
                    FunReplyTracking.channel_id == channel_id
                ).order_by(FunReplyTracking.last_reply_at.desc()).limit(1)

                result = await session.execute(stmt)
                tracking = result.scalar_one_or_none()

                if tracking:
                    tracking.last_reply_at = replied_at
                    tracking.response_category = category
                else:
                    tracking = FunReplyTracking(
                        channel_id=channel_id,
                        last_reply_at=replied_at,
                        response_category=category
                    )
                    session.add(tracking)

                await session.commit()
        except Exception as e:
            logger.error(f"Error updating reply tracking: {e}")

    # ==================== CLEANUP OPERATIONS ====================

    async def cleanup_old_tracking(self, days: int = 7):
        """Clean up old fun reply tracking records."""
        try:
            from datetime import datetime, timedelta

            async with self.get_session() as session:
                cutoff = datetime.utcnow() - timedelta(days=days)

                stmt = update(FunReplyTracking).where(
                    FunReplyTracking.last_reply_at < cutoff
                ).values(last_reply_at=None)

                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.error(f"Error cleaning up tracking: {e}")

    async def close(self):
        """Close database connection."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connection closed")
