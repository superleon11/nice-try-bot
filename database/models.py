"""
SQLAlchemy ORM models for Discord Bot database schema.
"""

from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, String, Text, Integer, Boolean,
    DateTime, ForeignKey, Index, func
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    """Store Discord user information."""
    __tablename__ = 'users'

    id = Column(BigInteger, primary_key=True)  # Discord user ID
    username = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    messages = relationship("Message", back_populates="author", cascade="all, delete-orphan")
    voice_sessions = relationship("VoiceSession", back_populates="user", cascade="all, delete-orphan")
    activity_summary = relationship("UserActivitySummary", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"


class Message(Base):
    """Store Discord messages for activity tracking and throwback feature."""
    __tablename__ = 'messages'
    __table_args__ = (
        Index('idx_guild_channel', 'guild_id', 'channel_id'),
        Index('idx_user_created', 'user_id', 'created_at'),
        Index('idx_created_guild', 'created_at', 'guild_id'),
    )

    id = Column(BigInteger, primary_key=True)  # Discord message ID
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    channel_id = Column(BigInteger, nullable=False)  # Discord channel ID
    guild_id = Column(BigInteger, nullable=False)    # Discord guild ID
    content = Column(Text)
    created_at = Column(DateTime, nullable=False)
    is_bot = Column(Boolean, default=False)

    # Relationships
    author = relationship("User", back_populates="messages")

    def __repr__(self):
        return f"<Message(id={self.id}, user_id={self.user_id}, guild_id={self.guild_id})>"


class VoiceSession(Base):
    """Track voice channel join/leave events for activity tracking."""
    __tablename__ = 'voice_sessions'
    __table_args__ = (
        Index('idx_user_guild', 'user_id', 'guild_id'),
        Index('idx_duration_guild', 'guild_id', 'duration_seconds'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    guild_id = Column(BigInteger, nullable=False)
    channel_id = Column(BigInteger, nullable=False)
    joined_at = Column(DateTime, nullable=False)
    left_at = Column(DateTime)  # NULL if still in channel
    duration_seconds = Column(Integer)  # Calculated on leave
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="voice_sessions")

    def __repr__(self):
        return f"<VoiceSession(id={self.id}, user_id={self.user_id}, duration={self.duration_seconds}s)>"


class UserActivitySummary(Base):
    """Materialized summary of user activity for fast leaderboard queries."""
    __tablename__ = 'user_activity_summary'
    __table_args__ = (
        Index('idx_guild_messages', 'guild_id', 'total_messages', postgresql_desc=['total_messages']),
        Index('idx_guild_voice', 'guild_id', 'total_voice_seconds', postgresql_desc=['total_voice_seconds']),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    guild_id = Column(BigInteger, nullable=False)
    total_messages = Column(Integer, default=0)
    total_voice_seconds = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Add unique constraint to prevent duplicates
    __table_args__ = (
        Index('idx_user_guild_unique', 'user_id', 'guild_id', unique=True),
        Index('idx_guild_messages', 'guild_id', 'total_messages', postgresql_desc=['total_messages']),
        Index('idx_guild_voice', 'guild_id', 'total_voice_seconds', postgresql_desc=['total_voice_seconds']),
    )

    # Relationships
    user = relationship("User", back_populates="activity_summary")

    def __repr__(self):
        return f"<UserActivitySummary(user_id={self.user_id}, messages={self.total_messages}, voice={self.total_voice_seconds}s)>"


class ReplyResponse(Base):
    """Store fun bot reply responses with categories and keywords."""
    __tablename__ = 'reply_responses'

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50), nullable=False)  # 'sarcastic', 'meme', 'wholesome'
    response = Column(Text, nullable=False)
    keywords = Column(Text)  # JSON array of trigger keywords
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ReplyResponse(id={self.id}, category='{self.category}')>"


class FunReplyTracking(Base):
    """Track rate limiting for fun replies per channel."""
    __tablename__ = 'fun_reply_tracking'
    __table_args__ = (
        Index('idx_channel_time', 'channel_id', 'last_reply_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, nullable=False)
    last_reply_at = Column(DateTime, nullable=False)
    response_category = Column(String(50))  # For tracking which category was used

    def __repr__(self):
        return f"<FunReplyTracking(channel_id={self.channel_id}, last_reply_at={self.last_reply_at})>"
