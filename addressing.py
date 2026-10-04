"""Is a message talking to the bot?"""

import discord


def is_addressed(message, bot_user) -> bool:
    """True if the message mentions the bot or is a reply to one of the bot's own messages."""
    if bot_user in message.mentions:
        return True
    ref = message.reference.resolved if message.reference else None
    return isinstance(ref, discord.Message) and ref.author.id == bot_user.id
