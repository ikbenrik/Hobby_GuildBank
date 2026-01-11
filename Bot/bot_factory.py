# bot_factory.py
# -------------------------------------------------
# Factory module responsible for creating the Discord bot instance.
#
# Responsibilities:
# - Instantiate commands.Bot with correct intents
# - Apply global bot-level configuration
#
# This file exists to:
# - Keep bot creation logic in one place
# - Avoid duplication across main/tests
# - Make future changes (prefix, intents, subclassing) trivial
#
# This file should NOT:
# - Load cogs/extensions
# - Contain command logic
# -------------------------------------------------

from discord.ext import commands
from config import INTENTS


def create_bot() -> commands.Bot:
    """
    Create and return the configured Discord bot instance.

    Centralizing bot creation allows:
    - consistent configuration across the app
    - easy future migration to a custom Bot subclass
    - cleaner main.py
    """

    # Create the bot with command prefix and gateway intents
    bot = commands.Bot(
        command_prefix="!",
        intents=INTENTS,
    )

    # Custom attribute used by OCR flow to track in-progress edits
    # (kept here to preserve existing behavior)
    bot.edit_flow_ids = set()

    return bot
