"""
bot/utils/formatting.py

Shared formatting utilities for the Guild Bank bot.

Responsibilities:
- Define visual representations for item qualities
- Provide helper functions for safely formatting long messages
- Generate human-readable previews for inventory and OCR results

This module contains no Discord or Google Sheets logic.
It is safe to import anywhere.
"""

from typing import Iterable, List


# --------------------------------------------------
# Item quality display configuration
# --------------------------------------------------
# Maps item quality names to their corresponding emoji
# used throughout the bot UI and previews.
QUALITY_EMOJIS = {
    "Common": "⚪",
    "Uncommon": "🟢",
    "Rare": "🔵",
    "Heroic": "🟡",
    "Epic": "🟣",
    "Legendary": "🟠"
}

# Short-hand quality inputs accepted from users
# (used in parsing text commands and modals)
QUALITY_SHORTCUTS = {
    "c": "Common",
    "u": "Uncommon",
    "r": "Rare",
    "h": "Heroic",
    "e": "Epic",
    "l": "Legendary",
}


def chunk_message_blocks(blocks: List[str], max_chars: int = 1900) -> List[str]:
    """
    Split a list of pre-formatted message blocks into
    Discord-safe message chunks.

    This ensures messages stay below Discord's character limit
    while preserving block boundaries where possible.

    Args:
        blocks: List of already-formatted string blocks
        max_chars: Maximum characters per Discord message

    Returns:
        List of message chunks ready to be sent
    """
    chunks = []
    current = []
    current_len = 0

    for b in blocks:
        blen = len(b) + 1  # account for newline
        if current_len + blen > max_chars:
            chunks.append("\n".join(current))
            current = [b]
            current_len = blen
        else:
            current.append(b)
            current_len += blen

    if current:
        chunks.append("\n".join(current))

    return chunks


def format_preview(items: Iterable[tuple[str, str, int]]) -> str:
    """
    Format a list of item tuples into a human-readable preview.

    Used for:
    - OCR confirmation messages
    - Donation previews
    - Manual entry confirmations

    Args:
        items: Iterable of (item_name, quality, amount)

    Returns:
        Multi-line formatted string suitable for Discord messages
    """
    lines = []
    for item, quality, amount in items:
        q = quality or "Common"
        lines.append(f"{QUALITY_EMOJIS.get(q, '•')} {amount} × {item} ({q})")

    return "\n".join(lines)
