"""
bot/services/ocr_service.py

OCR processing utilities for the Guild Bank bot.

Responsibilities:
- Preprocess images to improve OCR accuracy
- Detect item quality based on color (HSV analysis)
- Parse OCR word data into structured item tuples

This module is:
- Discord-agnostic
- Stateless
- Used by the OCR listener cog only
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
import numpy as np
from PIL import Image
import pytesseract
from skimage.color import rgb2hsv
import re

from bot.utils.parsing import ItemTuple


# ------------------------------------------------------------
# Quality color detection configuration
# ------------------------------------------------------------
# Hue ranges are expressed in degrees (0–360) and mapped
# to in-game item quality tiers.
QUALITY_HUE_RANGES = {
    "Common": None,
    "Uncommon": (95, 140),
    "Rare": (190, 240),
    "Heroic": (40, 70),
    "Epic": (260, 310),
    "Legendary": (20, 50),
}


def preprocess_image(img: Image.Image) -> Image.Image:
    """
    Apply basic preprocessing to an image to improve OCR results.

    Current strategy:
    - Convert to grayscale
    - Apply a binary threshold to increase text contrast

    Args:
        img: Original PIL Image

    Returns:
        A preprocessed PIL Image suitable for OCR
    """
    gray = img.convert("L")
    bw = gray.point(lambda x: 0 if x < 150 else 255, "1")
    return bw


def detect_quality_hsv(region: Image.Image, sat_thresh=0.3, val_thresh=0.2) -> str:
    """
    Detect item quality by analyzing the dominant hue of an image region.

    Strategy:
    - Convert RGB region to HSV
    - Mask out low-saturation / low-value pixels
    - Compute the median hue of remaining pixels
    - Match against predefined hue ranges

    Args:
        region: Cropped image region containing the item name
        sat_thresh: Saturation threshold for valid pixels
        val_thresh: Brightness threshold for valid pixels

    Returns:
        Detected quality name (defaults to 'Common')
    """
    arr = np.array(region).astype(np.float32) / 255.0
    hsv = rgb2hsv(arr)
    h = hsv[..., 0] * 360
    s = hsv[..., 1]
    v = hsv[..., 2]

    # Filter pixels that are too desaturated or dark
    mask = (s > sat_thresh) & (v > val_thresh)
    if not mask.any():
        return "Common"

    # Use median hue to reduce noise sensitivity
    hue_mode = float(np.median(h[mask]))

    # Match hue against configured quality ranges
    for qual, hrange in QUALITY_HUE_RANGES.items():
        if not hrange:
            continue
        lo, hi = hrange
        if lo <= hi:
            if lo <= hue_mode <= hi:
                return qual
        else:
            # Wrap-around hue range (e.g. 300–20)
            if hue_mode >= lo or hue_mode <= hi:
                return qual

    return "Common"


async def scan_items(image: Image.Image, data: dict) -> List[ItemTuple]:
    """
    Parse OCR word data and extract detected item entries.

    The function looks for keywords such as 'acquired' or 'removed'
    and then groups subsequent words into item names, quantities,
    and bounding boxes for quality detection.

    Args:
        image: Original (or preprocessed) image
        data: pytesseract.image_to_data output dictionary

    Returns:
        List of (item_name, quality, amount) tuples
    """
    results: List[ItemTuple] = []
    num_words = len(data["text"])
    i = 0

    # Iterate through OCR word stream
    while i < num_words:
        word = data["text"][i].strip().lower().rstrip(":")
        if word not in ("acquired", "removed"):
            i += 1
            continue

        j = i + 1
        item_words, amount, boxes = [], 1, []

        # Collect item name words and bounding boxes
        while j < num_words:
            w = data["text"][j].strip()
            if not w or w.lower().strip().rstrip(":") in ("acquired", "removed"):
                break

            # Quantity marker (e.g. x5)
            if w.startswith("x") and w[1:].isdigit():
                amount = int(w[1:])
                j += 1
                break

            item_words.append(w)
            boxes.append({
                "left": data["left"][j],
                "top": data["top"][j],
                "width": data["width"][j],
                "height": data["height"][j],
            })
            j += 1

        if not item_words:
            i = j
            continue

        # Normalize extracted item name
        raw_name = " ".join(item_words).strip()
        item_name = re.sub(
            r"^[^\w\d\(\)]+|[^\w\d\(\)]+$",
            "",
            raw_name
        ).strip("[](){}")

        if not item_name:
            i = j
            continue

        # Fallback bounding box if OCR provided none
        if not boxes:
            boxes = [{
                "left": 0,
                "top": 0,
                "width": image.width,
                "height": image.height
            }]

        # Crop region for color-based quality detection
        region = image.crop((
            max(min(b["left"] for b in boxes) - 4, 0),
            max(min(b["top"] for b in boxes) - 2, 0),
            min(max(b["left"] + b["width"] for b in boxes) + 4, image.width),
            min(max(b["top"] + b["height"] for b in boxes) + 2, image.height)
        ))

        quality = detect_quality_hsv(region)
        results.append((item_name.title(), quality, amount))
        i = j

    return results
