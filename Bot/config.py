# config.py
# -------------------------------------------------
# Central configuration module for the GuildBank bot.
#
# Responsibilities:
# - Load environment variables (.env)
# - Define strongly-typed application settings
# - Configure Discord intents
# - Configure external dependencies (Tesseract OCR)
#
# This file should ONLY contain configuration and setup.
# No business logic or Discord command logic belongs here.
# -------------------------------------------------

import os
import platform
from dataclasses import dataclass

import discord
from dotenv import load_dotenv


# Load environment variables from .env file (if present)
# This allows secrets like TOKEN to be kept out of source control
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """
    Immutable application configuration.

    Values are loaded from environment variables with safe defaults
    where appropriate.

    Using a frozen dataclass ensures:
    - settings cannot be modified at runtime
    - configuration remains predictable
    """
    token: str
    spreadsheet_url: str
    credentials_file: str
    donation_channel_name: str
    backup_channel_name: str


# Global settings instance used throughout the bot
# Accessed as: SETTINGS.token, SETTINGS.spreadsheet_url, etc.
SETTINGS = Settings(
    # Discord bot token (REQUIRED)
    token=os.getenv("TOKEN", ""),

    # Google Sheets document URL
    spreadsheet_url=os.getenv(
        "SPREADSHEET_URL", ""),

    # Service account credentials file for Google Sheets API
    credentials_file=os.getenv("GOOGLE_CREDS_FILE", "credentials.json"),

    # Channel where OCR donations are posted and logged
    donation_channel_name=os.getenv(
        "DONATION_CHANNEL_NAME",
        "📓┃donation-and-activity-log",
    ),

    # Channel used for automatic bank backups
    backup_channel_name=os.getenv(
        "BACKUP_CHANNEL_NAME",
        "💲┃bank-backup",
    ),
)


# -------------------------------------------------
# Discord Intents
# -------------------------------------------------
# Intents define which gateway events the bot receives.
# message_content is required for reading message text
# (OCR listener, text commands, etc.)

INTENTS = discord.Intents.default()
INTENTS.message_content = True


# -------------------------------------------------
# External dependency configuration
# -------------------------------------------------
def configure_tesseract():
    """
    Configure the Tesseract OCR executable path based on OS.

    This must be called BEFORE any OCR operations occur.
    Placed here so it is:
    - centralized
    - OS-aware
    - easy to change later
    """
    import pytesseract

    system = platform.system()

    if system == "Linux":
        pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

    elif system == "Windows":
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    # macOS users typically have tesseract available via PATH (brew),
    # so no explicit configuration is required.
