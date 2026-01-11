# main.py
# -------------------------------------------------
# Application entry point for the GuildBank Discord bot.
#
# Responsibilities of this file:
# - Configure global dependencies (OCR / environment)
# - Create the Discord bot instance
# - Load all bot extensions (cogs)
# - Start and gracefully shut down the bot
#
# This file should NOT contain:
# - Discord command logic
# - Business logic (Sheets, OCR, parsing, etc.)
# -------------------------------------------------

import asyncio

from config import SETTINGS, configure_tesseract
from bot_factory import create_bot


async def main():
    """
    Main async entrypoint for the bot.

    Flow:
    1. Configure external dependencies (e.g. Tesseract OCR)
    2. Create the bot instance
    3. Load all required cogs/extensions
    4. Start the bot and handle graceful shutdown
    """

    # Configure Tesseract OCR path and environment
    # (kept here so OCR is ready before any cogs use it)
    configure_tesseract()

    # Create the Discord bot with intents, command tree, etc.
    bot = create_bot()

    # -------------------------
    # Core / infrastructure cogs
    # -------------------------

    # Core lifecycle events (on_ready, sync commands, etc.)
    await bot.load_extension("bot.cogs.core")

    # OCR listener (image intake, OCR parsing, review UI)
    await bot.load_extension("bot.cogs.ocr_listener")

    # -------------------------
    # Bank-related features
    # -------------------------

    # Main bank UI panel (buttons & modals entrypoint)
    await bot.load_extension("bot.cogs.bank_panel")

    # Slash / text commands related to bank actions
    await bot.load_extension("bot.cogs.bank_commands")

    # Donation lookup commands (e.g. !d history)
    await bot.load_extension("bot.cogs.donations")

    # Audit tools (banker inventory correction)
    await bot.load_extension("bot.cogs.audit")

    # Automated and manual backups (scheduled + restore UI)
    await bot.load_extension("bot.cogs.backup")

    # -------------------------
    # Bot startup / shutdown
    # -------------------------
    try:
        # Connect to Discord and start processing events
        await bot.start(SETTINGS.token)

    except KeyboardInterrupt:
        # Allows clean Ctrl+C shutdown without noisy stacktraces
        pass

    finally:
        # Ensure aiohttp session and websocket are closed properly
        if not bot.is_closed():
            await bot.close()


# Standard Python entrypoint guard
# Ensures this file is only executed directly
if __name__ == "__main__":
    asyncio.run(main())
