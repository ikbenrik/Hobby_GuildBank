"""
bot/utils/parsing.py

Text parsing utilities for the Guild Bank bot.

Responsibilities:
- Parse free-form user text into structured item tuples
- Normalize item quality inputs (shortcuts and full names)
- Support flexible input formats used across commands, modals, and OCR edits

This module is purely computational:
- No Discord logic
- No Google Sheets logic
- Safe to reuse across services and UI
"""

import re
from typing import List, Tuple

from bot.utils.formatting import QUALITY_SHORTCUTS


# Canonical item tuple used throughout the codebase
# (item name, quality, amount)
ItemTuple = Tuple[str, str, int]


def parse_quality(token: str) -> str:
    """
    Normalize a quality token into a canonical quality name.

    Supports:
    - Shortcuts (e.g. r, e, h)
    - Full names (e.g. epic, legendary)
    - Empty or missing values (defaults to Common)

    Args:
        token: Raw quality token from user input

    Returns:
        Canonical quality string (title-cased)
    """
    q = token.strip().lower()
    if not q:
        return "Common"
    if q[0] in QUALITY_SHORTCUTS:
        return QUALITY_SHORTCUTS[q[0]]
    return q.title()


def parse_user_lines(lines: List[str]) -> List[ItemTuple]:
    """
    Parse user-provided item lines into structured item tuples.

    Accepted formats include:
    - "10 x Oak Wood (Epic)"
    - "10 oak wood e"
    - "oak wood e"          (defaults amount = 1)
    - Multiple items separated by commas, semicolons, or plus signs

    Args:
        lines: List of raw text lines entered by the user

    Returns:
        List of parsed (item, quality, amount) tuples
    """
    parsed: List[ItemTuple] = []

    for line in lines:
        # Allow multiple items per line, separated by delimiters
        parts = re.split(r"[,+;]", line.strip())
        for part in parts:
            segment = part.strip()
            if not segment:
                continue

            # Strip leading non-alphanumeric characters
            segment = re.sub(r"^[^\w\d]+", "", segment)

            # Strict format: "10 x Item Name (Quality)"
            m = re.match(
                r"^(\d+)\s*[x×]\s*(.+?)\s*\((.+?)\)$",
                segment,
                re.IGNORECASE
            )
            if m:
                amount = int(m.group(1))
                item = m.group(2).strip().title()
                quality = parse_quality(
                    re.sub(r"[^\w]", "", m.group(3))
                )
                parsed.append((item, quality, amount))
                continue

            tokens = segment.split()
            if not tokens:
                continue

            # Detect explicit amount token
            if tokens[0].isdigit():
                amount = int(tokens[0])
                rest = tokens[1:]
            else:
                amount = 1
                rest = tokens

            if not rest:
                continue

            # Detect quality as last token
            quality_candidate = rest[-1].lower()
            if (
                quality_candidate
                and (
                    quality_candidate[0] in QUALITY_SHORTCUTS
                    or quality_candidate in [
                        "common",
                        "uncommon",
                        "rare",
                        "heroic",
                        "epic",
                        "legendary",
                    ]
                )
            ):
                quality = parse_quality(quality_candidate)
                item_tokens = rest[:-1]
            else:
                quality = "Common"
                item_tokens = rest

            item = " ".join(item_tokens).strip().title()
            if item:
                parsed.append((item, quality, amount))

    return parsed


def parse_audit_lines(lines: List[str]) -> List[ItemTuple]:
    """
    Parse audit edit lines into structured item tuples.

    This parser is intentionally stricter than parse_user_lines,
    as audit edits are expected to be precise.

    Accepted formats include:
    - "10 x Oak Wood (Epic)"
    - "10 Oak Wood Epic"

    Args:
        lines: List of raw audit edit lines

    Returns:
        List of parsed (item, quality, amount) tuples
    """
    parsed: List[ItemTuple] = []

    for line in lines:
        # Remove leading punctuation or symbols
        line = re.sub(r"^[^\w\d]+", "", line.strip())
        if not line:
            continue

        # Strict parenthesized format
        strict = re.match(
            r"^(\d+)\s*[x×]\s*(.+?)\s*\((Common|Uncommon|Rare|Heroic|Epic|Legendary)\)$",
            line,
            re.IGNORECASE
        )
        if strict:
            amt = int(strict.group(1))
            item = strict.group(2).strip().title()
            quality = strict.group(3).title()
            parsed.append((item, quality, amt))
            continue

        tokens = re.split(r"\s+", line)
        if len(tokens) < 2:
            continue

        amt_token = tokens[0].rstrip("x×")
        if not amt_token.isdigit():
            continue
        amt = int(amt_token)

        last = tokens[-1].lower()
        if (
            last in QUALITY_SHORTCUTS
            or last in [
                "common",
                "uncommon",
                "rare",
                "heroic",
                "epic",
                "legendary",
            ]
        ):
            quality = parse_quality(last)
            item_tokens = tokens[1:-1]
        else:
            quality = "Common"
            item_tokens = tokens[1:]

        item = " ".join(item_tokens).strip().title()
        if item:
            parsed.append((item, quality, amt))

    return parsed
