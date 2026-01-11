"""
bot/ui/views.py

Discord UI Views (buttons, selects, confirmation panels) used by the Guild Bank bot.

Responsibilities:
- Provide interactive button-based command panels
- Handle audit confirmation / editing flows
- Provide backup restore selection UI
- Drive OCR confirmation and editing workflows

This module contains UI logic only.
All data mutations are delegated to services.
"""

import discord
from discord.ui import View, Button

from bot.ui.modals import (
    BankSearchModal,
    ManualAddModal,
    CraftProcessModal,
    EditPrioritiesModal,
    ModifyPrioritiesModal,
    AuditEditModal,
)
from bot.utils.permissions import is_authorized_member
from bot.utils.formatting import chunk_message_blocks


class ChooseLogView(View):
    """
    Placeholder view for selecting which activity log to view.

    Currently acts as a stub and can be extended later
    with full donation / artisan log viewers.
    """

    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="🧾 Donations Log", style=discord.ButtonStyle.primary)
    async def donations_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            "Log viewer not wired in this refactor yet.",
            ephemeral=True
        )

    @discord.ui.button(label="🛠️ Artisan Log", style=discord.ButtonStyle.primary)
    async def artisan_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            "Log viewer not wired in this refactor yet.",
            ephemeral=True
        )


class AuditChunkView(View):
    """
    View used during audits to allow a banker to
    confirm or edit a chunk of audited items.
    """

    def __init__(self, banker_name: str, items, sheets_service):
        super().__init__(timeout=300)
        self.banker_name = banker_name
        self.items = items
        self.sheets = sheets_service

    @discord.ui.button(label="✏️ Edit", style=discord.ButtonStyle.blurple)
    async def edit(self, interaction: discord.Interaction, button: Button):
        # Only the owning banker may edit their audit section
        if interaction.user.display_name != self.banker_name:
            await interaction.response.send_message(
                "❌ Only the banker can edit this section.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            AuditEditModal(self.items, self.banker_name, self.sheets)
        )

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        # Only the owning banker may confirm their audit section
        if interaction.user.display_name != self.banker_name:
            await interaction.response.send_message(
                "❌ Only the banker can confirm.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        await self.sheets.apply_audit_for_banker(self.banker_name, self.items)
        await interaction.followup.send(
            "✅ Audit updated successfully.",
            ephemeral=True
        )
        self.stop()


class BackupSelect(View):
    """
    Select-based UI allowing administrators to choose
    which backup file to restore.
    """

    def __init__(self, requester: discord.Member, backup_files, restore_callback):
        super().__init__(timeout=180)
        self.requester = requester
        self.backup_files = backup_files
        self.restore_callback = restore_callback

        self.select = discord.ui.Select(
            placeholder="Select a backup to restore",
            options=[]
        )
        self.select.callback = self._on_select
        self.add_item(self.select)

    def set_options(self):
        """
        Populate select options from available backup messages.
        """
        self.select.options = [
            discord.SelectOption(
                label=m.attachments[0].filename[:100],
                value=str(idx)
            )
            for idx, m in enumerate(self.backup_files[:25])
        ]

    async def _on_select(self, interaction: discord.Interaction):
        # Only administrators may restore backups
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Only admins can restore backups.",
                ephemeral=True
            )
            return

        idx = int(self.select.values[0])
        await interaction.response.defer(ephemeral=True)
        await self.restore_callback(
            interaction,
            self.backup_files[idx],
            self.requester
        )
        self.stop()


class CommandPanel(View):
    """
    Primary button panel shown to users.

    Acts as the main navigation hub for:
    - Viewing bank inventory
    - Viewing priorities
    - Manual item operations
    - Crafting / processing
    - Backup restore (admins)
    """

    def __init__(self, interaction: discord.Interaction, sheets_service, backup_open_callback):
        super().__init__(timeout=180)
        self.user = interaction.user
        self.sheets = sheets_service
        self.backup_open_callback = backup_open_callback

    @discord.ui.button(label="🪓 What We Need", style=discord.ButtonStyle.primary)
    async def view_priorities(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        summary = await self.sheets.get_priority_summary()
        await interaction.followup.send(summary, ephemeral=True)

    @discord.ui.button(label="📦 View Bank", style=discord.ButtonStyle.primary)
    async def view_bank(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(
            BankSearchModal(self.sheets)
        )

    @discord.ui.button(label="📊 View Activity", style=discord.ButtonStyle.secondary)
    async def view_activity(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            "Choose log to view:",
            view=ChooseLogView(),
            ephemeral=True
        )

    @discord.ui.button(label="➕ Manual Add", style=discord.ButtonStyle.success)
    async def manual_add(self, interaction: discord.Interaction, button: Button):
        if not is_authorized_member(interaction.user):
            await interaction.response.send_message(
                "❌ Only admins/bankers can use this.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            ManualAddModal(self.sheets)
        )

    @discord.ui.button(label="🛠️ Process / Craft", style=discord.ButtonStyle.primary)
    async def craft_process(self, interaction: discord.Interaction, button: Button):
        if not is_authorized_member(interaction.user):
            await interaction.response.send_message(
                "❌ Only admins/bankers can use this.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            CraftProcessModal(self.sheets)
        )

    @discord.ui.button(label="✏️ Edit Needed Items", style=discord.ButtonStyle.primary)
    async def edit_priorities(self, interaction: discord.Interaction, button: Button):
        if not is_authorized_member(interaction.user):
            await interaction.response.send_message(
                "❌ Only admins/bankers can edit priorities.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            EditPrioritiesModal(self.sheets)
        )

    @discord.ui.button(label="➕/➖ Modify Needed Items", style=discord.ButtonStyle.secondary)
    async def modify_priorities(self, interaction: discord.Interaction, button: Button):
        if not is_authorized_member(interaction.user):
            await interaction.response.send_message(
                "❌ Only admins/bankers can edit priorities.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            ModifyPrioritiesModal(self.sheets)
        )

    @discord.ui.button(label="♻️ Restore Backup", style=discord.ButtonStyle.danger)
    async def restore_backup(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Only administrators can restore.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        await self.backup_open_callback(interaction)


# --------------------------------------------------
# OCR confirmation / editing UI
# --------------------------------------------------

import re
from discord.ui import Modal, TextInput
from bot.utils.parsing import parse_user_lines
from bot.utils.formatting import format_preview


class OCRReviewModal(Modal, title="Review Detected Items"):
    """
    Modal allowing the image sender to edit OCR-detected items
    before committing them to the bank.
    """

    def __init__(self, ocr_items, donator_name: str, banker_name: str, sheets_service):
        super().__init__()
        self.ocr_items = ocr_items
        self.donator_name = donator_name
        self.banker_name = banker_name
        self.sheets = sheets_service

        default_text = "\n".join(
            f"{amt} × {name} ({q})"
            for name, q, amt in ocr_items
        )

        self.item_lines = TextInput(
            label="Detected Items (edit if needed)",
            style=discord.TextStyle.paragraph,
            default=default_text,
            required=True,
            max_length=4000,
        )
        self.add_item(self.item_lines)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        lines = self.item_lines.value.strip().splitlines()
        parsed = parse_user_lines(lines)

        # Ensure qualities are always defined
        parsed_clean = []
        for item, quality, amount in parsed:
            if not quality:
                quality = "Common"
            parsed_clean.append((item, quality, amount))

        if not parsed_clean:
            await interaction.followup.send(
                "❌ No valid items found.",
                ephemeral=True
            )
            return

        # Apply edited donation
        await self.sheets.apply_donation(
            parsed_clean,
            donator_name=self.donator_name,
            banker_name=self.banker_name
        )

        preview = format_preview(parsed_clean)
        await interaction.followup.send(
            "✅ Updated from edited list.",
            ephemeral=True
        )

        # Public confirmation message
        await interaction.channel.send(
            f"📦 **Items from {self.donator_name} (confirmed by {self.banker_name}):**\n```{preview}```"
        )


class OCRReviewButton(View):
    """
    Button-based OCR confirmation view.

    Allows the image sender to:
    - Confirm detected items immediately
    - Open the edit modal for manual correction
    """

    def __init__(self, ocr_items, donator_name: str, banker_name: str, sheets_service, author: discord.Member):
        super().__init__(timeout=180)
        self.ocr_items = ocr_items
        self.donator_name = donator_name
        self.banker_name = banker_name
        self.sheets = sheets_service
        self.author = author

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        # Only the original image sender may confirm
        if interaction.user != self.author:
            await interaction.response.send_message(
                "❌ Only the image sender can confirm.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        cleaned = []
        for item, quality, amount in self.ocr_items:
            if not quality:
                quality = "Common"
            cleaned.append((item, quality, amount))

        await self.sheets.apply_donation(
            cleaned,
            donator_name=self.donator_name,
            banker_name=self.banker_name
        )

        preview = format_preview(cleaned)

        await interaction.channel.send(
            f"📦 **Items from {self.donator_name} (confirmed by {self.banker_name}):**\n```{preview}```"
        )

        # Remove preview message with buttons
        try:
            await interaction.message.delete()
        except Exception:
            pass

        self.stop()

    @discord.ui.button(label="✏️ Edit", style=discord.ButtonStyle.blurple)
    async def edit(self, interaction: discord.Interaction, button: Button):
        # Only the original image sender may edit
        if interaction.user != self.author:
            await interaction.response.send_message(
                "❌ Only the image sender can edit.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            OCRReviewModal(
                self.ocr_items,
                self.donator_name,
                self.banker_name,
                self.sheets
            )
        )
