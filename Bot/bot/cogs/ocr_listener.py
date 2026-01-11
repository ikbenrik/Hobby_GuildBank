"""
bot/cogs/ocr_listener.py

Discord Cog responsible for:
- Listening for image uploads in the configured donation/activity channel
- Running OCR on supported image attachments (png/jpg/jpeg)
- Extracting item lines from OCR text
- Presenting a confirmation/edit UI to the submitting user
- Handing off confirmed results to the SheetsService (Google Sheets persistence)

Notes:
- This cog intentionally ignores messages outside the configured channel.
- Permission gating is applied: only authorized members can trigger OCR flows,
  but donation query commands are still allowed for non-authorized users.
"""

import discord
from discord.ext import commands
from PIL import Image
from io import BytesIO
import pytesseract

from config import SETTINGS
from bot.services.sheets_service import SheetsService
from bot.services.ocr_service import preprocess_image, scan_items
from bot.ui.views import OCRReviewButton
from bot.utils.permissions import is_valid_channel, is_authorized_member
from bot.utils.formatting import format_preview


class OCRListener(commands.Cog):
    """
    Cog that processes donation screenshots posted in the donation channel.

    Flow overview:
    1) Validate message (not from bot, correct channel, permissions)
    2) Ensure the message has image attachments
    3) Require a donator mention (first mention in the message)
    4) Run OCR (raw first, then fallback to preprocessed)
    5) If items found: show a preview + confirmation UI button view
    """

    def __init__(self, bot: commands.Bot):
        # Store bot instance for later use (commands processing, shared state, etc.)
        self.bot = bot

        # Sheets service is created once per cog instance and reused for all events
        self.sheets = SheetsService(SETTINGS.spreadsheet_url, SETTINGS.credentials_file)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ------------------------------------------------------------
        # 1) Basic message filters
        # ------------------------------------------------------------
        if message.author.bot:
            # Ignore bot messages to prevent feedback loops.
            return

        if not is_valid_channel(message.channel, SETTINGS.donation_channel_name):
            # Only operate inside the configured donation/activity channel.
            return

        # ------------------------------------------------------------
        # 2) Permission gating (with command exceptions)
        # ------------------------------------------------------------
        # Allow non-authorized members to run donation query commands,
        # but require authorization for OCR / banking operations.
        allowed_commands = ("!d", "!donations")
        if not (is_authorized_member(message.author) or message.content.lower().startswith(allowed_commands)):
            return

        # ------------------------------------------------------------
        # 3) Avoid interfering with edit-confirmation flows
        # ------------------------------------------------------------
        # If this message is registered as part of a special "edit flow",
        # ignore it to avoid re-triggering OCR logic.
        if message.id in getattr(self.bot, "edit_flow_ids", set()):
            return

        # If the message is a reply to a bot confirmation prompt, ignore it
        # so normal conversation doesn't retrigger OCR.
        if message.reference:
            try:
                ref = await message.channel.fetch_message(message.reference.message_id)
                if ref.author.id == self.bot.user.id and "Please confirm" in ref.content:
                    return
            except Exception:
                # If reference fetch fails, do not hard-fail the whole listener.
                pass

        # Ensure command processing still works alongside this listener.
        await self.bot.process_commands(message)

        # ------------------------------------------------------------
        # 4) OCR is only triggered by image attachments
        # ------------------------------------------------------------
        if not message.attachments:
            return

        for attachment in message.attachments:
            # Only handle common image formats used for screenshots.
            if not attachment.filename.lower().endswith((".png", ".jpg", ".jpeg")):
                continue

            # --------------------------------------------------------
            # 5) Determine donator/banker identities
            # --------------------------------------------------------
            # Current convention:
            # - Donator is the first mentioned user in the message
            # - Banker defaults to the message author
            mentions = message.mentions
            donator = mentions[0] if mentions else None
            banker = message.author

            # Require a valid Discord Member mention for donator.
            # (Prevents None / invalid mention objects from breaking downstream flows.)
            if not isinstance(donator, discord.Member):
                await message.reply(
                    "📛 Please mention the **donator** using `@Name` to proceed with this image.",
                    mention_author=True
                )
                return

            # Names are stored as display names (server nicknames where applicable).
            donator_name = donator.display_name
            banker_name = banker.display_name

            # --------------------------------------------------------
            # 6) Read attachment into a PIL image
            # --------------------------------------------------------
            img_bytes = await attachment.read()
            image = Image.open(BytesIO(img_bytes)).convert("RGB")

            # --------------------------------------------------------
            # 7) OCR pass #1 (raw)
            # --------------------------------------------------------
            data_raw = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            detected_items = await scan_items(image, data_raw)

            # --------------------------------------------------------
            # 8) OCR fallback (preprocessing) if raw OCR finds nothing
            # --------------------------------------------------------
            if not detected_items:
                processed = preprocess_image(image)
                data_processed = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)
                detected_items = await scan_items(processed, data_processed)

            # If still nothing, inform user and stop processing this attachment.
            if not detected_items:
                await message.channel.send("No items found.")
                return

            # --------------------------------------------------------
            # 9) Preview + interactive confirmation UI
            # --------------------------------------------------------
            # Convert detected tuples into a human-readable preview block.
            preview = format_preview(detected_items)

            # Create a View with Confirm/Edit actions.
            # The view is responsible for pushing final results into SheetsService.
            view = OCRReviewButton(
                detected_items,
                donator_name,
                banker_name,
                self.sheets,
                message.author
            )

            await message.channel.send(
                f"📋 **Detected Items from {donator.mention}:**\n```{preview}```",
                view=view
            )


async def setup(bot: commands.Bot):
    """Discord.py extension entrypoint."""
    await bot.add_cog(OCRListener(bot))
