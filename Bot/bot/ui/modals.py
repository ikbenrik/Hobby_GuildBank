"""
bot/ui/modals.py

Discord UI Modals used throughout the Guild Bank bot.

This module contains:
- Search and display modals for bank inventory
- Manual item entry
- Crafting and processing workflows
- Donation log search
- Priority list management
- Audit editing

All modals are UI-only and delegate data mutations to services.
"""

import discord
from discord.ui import Modal, TextInput
from datetime import datetime, timedelta, timezone
import re
from collections import defaultdict

from bot.utils.parsing import parse_user_lines, parse_audit_lines
from bot.utils.formatting import QUALITY_SHORTCUTS


# Optional quality emojis used for full-bank visual output
QUALITY_EMOJIS = {
    "Common": "⚪",
    "Uncommon": "🟢",
    "Rare": "🔵",
    "Heroic": "🟡",
    "Epic": "🟣",
    "Legendary": "🟠",
}


def _chunk_message_blocks(blocks, max_chars=1900):
    """
    Split a list of pre-formatted message blocks into
    Discord-safe message chunks.

    Args:
        blocks: List of formatted string blocks
        max_chars: Maximum characters per Discord message

    Returns:
        List of message strings within Discord limits
    """
    chunks = []
    current = []
    current_len = 0

    for b in blocks:
        blen = len(b) + 1
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


class BankSearchModal(Modal, title="Search the Guild Bank"):
    """
    Modal for searching the guild bank.

    Supports:
    - Specific item searches (with optional quality)
    - Full bank overview when user enters 'all'
    """

    def __init__(self, sheets_service):
        super().__init__()
        self.sheets = sheets_service

        self.search_items = TextInput(
            label="Item(s) to search (quality optional)",
            placeholder="e.g. copper r, oak wood e, tin or all",
            required=True
        )
        self.add_item(self.search_items)

    async def on_submit(self, interaction: discord.Interaction):
        args = (self.search_items.value or "").strip()
        await interaction.response.defer(ephemeral=True)

        # Full guild bank overview
        if not args or args.lower() == "all":
            totals = await self.sheets.get_full_guild_bank_totals()

            if not totals:
                await interaction.followup.send("📭 Guild Bank is empty.", ephemeral=True)
                return

            # Group inventory by item, then quality
            item_blocks = defaultdict(list)
            for (item, quality), amt in sorted(
                totals.items(),
                key=lambda x: (x[0][0].lower(), x[0][1].lower())
            ):
                q = str(quality).title()
                it = str(item).title()
                emoji = QUALITY_EMOJIS.get(q, "•")
                item_blocks[it].append(f"{emoji} {amt}× {q}")

            # Build one code block per item
            blocks = []
            for item, lines in item_blocks.items():
                block = (
                    "```\n"
                    f"{item}:\n"
                    + "\n".join(lines)
                    + "\n```"
                )
                blocks.append(block)

            # Send results in Discord-safe chunks
            chunks = _chunk_message_blocks(blocks, max_chars=1900)
            for chunk in chunks:
                await interaction.followup.send(chunk, ephemeral=True)

            return

        # Item-specific search mode
        raw_items = re.split(r"[,+;]", args)
        search_items = [x.strip() for x in raw_items if x.strip()]
        if not search_items:
            await interaction.followup.send("🔍 No valid items provided.", ephemeral=True)
            return

        for raw in search_items:
            parts = raw.split()
            if len(parts) > 1 and parts[-1].lower() in QUALITY_SHORTCUTS:
                quality_query = QUALITY_SHORTCUTS[parts[-1].lower()]
                item_query = " ".join(parts[:-1]).strip()
            else:
                quality_query = None
                item_query = raw.strip()

            matches = await self.sheets.search_banker_holdings(item_query, quality_query)

            if not matches:
                await interaction.followup.send(
                    f"🔍 No matches found for `{item_query}`.",
                    ephemeral=True
                )
                continue

            # Aggregate results per banker and quality
            holder = {}
            total = 0
            for r in matches:
                q = str(r["Quality"]).title()
                b = str(r["Banker"])
                amt = int(r.get("Amount", 0))
                holder.setdefault(q, {})
                holder[q][b] = holder[q].get(b, 0) + amt
                total += amt

            # Build output lines
            lines = [f"{item_query.title()} (Quality: {quality_query or 'All'}) — Total: {total}"]
            for q, bankers in holder.items():
                q_total = sum(bankers.values())
                lines.append(f"{q_total}× {q}")
                for banker, amt in bankers.items():
                    lines.append(f"  • {banker}: {amt}")

            await interaction.followup.send(
                "```" + "\n".join(lines) + "```",
                ephemeral=True
            )


class ManualAddModal(Modal, title="Manual Item Add"):
    """
    Modal allowing bankers or admins to manually add items
    directly into the bank inventory.
    """

    def __init__(self, sheets_service):
        super().__init__()
        self.sheets = sheets_service

        self.donator = TextInput(
            label="Donator Name (optional)",
            required=False,
            max_length=100
        )
        self.items = TextInput(
            label="Items (one per line: amount item quality)",
            style=discord.TextStyle.paragraph,
            placeholder="e.g.\n5 oak wood r\n3 copper heroic",
            required=True
        )
        self.add_item(self.donator)
        self.add_item(self.items)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        name = self.donator.value.strip() or interaction.user.display_name
        parsed = parse_user_lines(self.items.value.strip().splitlines())

        if not parsed:
            await interaction.followup.send("❌ No valid items found.", ephemeral=True)
            return

        # Manual adds are treated as self-donations
        await self.sheets.apply_donation(parsed, donator_name=name, banker_name=name)

        preview = "\n".join(f"{a} × {i} ({q})" for i, q, a in parsed)
        await interaction.followup.send(
            f"✅ Added to `{name}`:\n```{preview}```",
            ephemeral=True
        )


class CraftProcessModal(Modal, title="Craft / Process Items"):
    """
    Modal for handling crafting and processing actions.

    Enforces:
    - Materials must be specified
    - Exactly one of processing or crafting must be used
    """

    def __init__(self, sheets_service):
        super().__init__()
        self.sheets = sheets_service

        self.materials = TextInput(
            label="Materials used (required)",
            required=True,
            placeholder="e.g. 50 Oak Wood e"
        )
        self.processing = TextInput(
            label="Processed / crafted items added",
            required=False,
            placeholder="e.g. 9 Oak Board e"
        )
        self.crafting = TextInput(
            label="Crafting output (no return to bank)",
            required=False,
            placeholder="e.g. Journeyman Pickaxe"
        )
        self.add_item(self.materials)
        self.add_item(self.processing)
        self.add_item(self.crafting)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        mats = self.materials.value.strip()
        proc = self.processing.value.strip()
        craft = self.crafting.value.strip()

        if not mats:
            await interaction.followup.send("❌ You must specify materials used.", ephemeral=True)
            return
        if (not proc and not craft) or (proc and craft):
            await interaction.followup.send(
                "❌ Fill exactly one of Processing or Crafting.",
                ephemeral=True
            )
            return

        banker_name = interaction.user.display_name
        materials = parse_user_lines(mats.splitlines())
        outputs = parse_user_lines((proc or craft).splitlines()) if proc else []

        try:
            await self.sheets.craft_or_process(
                banker_name=banker_name,
                materials=materials,
                outputs=outputs,
                is_processing=bool(proc),
            )
            await interaction.followup.send(
                f"✅ {'Processed' if proc else 'Crafted'} by `{banker_name}` — inventory updated.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class DonationSearchModal(Modal, title="Search Donations"):
    """
    Modal for querying the donation log by user and/or time range.
    """

    def __init__(self):
        super().__init__()
        self.user_or_name = TextInput(
            label="Username or @mention",
            required=False,
            placeholder="e.g. @rikito or rik"
        )
        self.duration = TextInput(
            label="Duration (e.g. 1d, 1w, 1m)",
            required=False,
            placeholder="Defaults to 1 day"
        )
        self.add_item(self.user_or_name)
        self.add_item(self.duration)


class EditPrioritiesModal(Modal, title="Replace All Priority Items"):
    """
    Modal that fully replaces the priority item list.
    """

    def __init__(self, sheets_service):
        super().__init__()
        self.sheets = sheets_service
        self.input = TextInput(
            label="Each line: amount item quality",
            style=discord.TextStyle.paragraph,
            placeholder="400 oak wood e\n1000 droppings l\n200 obsidian h",
            required=True
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        rows = []
        for line in self.input.value.strip().splitlines():
            try:
                parts = line.strip().split()
                amount = int(parts[0])
                quality = parts[-1]
                item = " ".join(parts[1:-1]).title()
                q = QUALITY_SHORTCUTS.get(quality.lower(), quality.title())
                rows.append([item, q, amount])
            except Exception:
                await interaction.followup.send(
                    f"❌ Error parsing: `{line}`",
                    ephemeral=True
                )
                return

        await self.sheets.replace_priorities(rows)
        await interaction.followup.send("✅ Priority list replaced!", ephemeral=True)


class ModifyPrioritiesModal(Modal, title="Add/Remove Priority Items"):
    """
    Modal allowing incremental add/remove operations
    on the priority list.
    """

    def __init__(self, sheets_service):
        super().__init__()
        self.sheets = sheets_service

        self.add_items = TextInput(
            label="Add (amount item quality)",
            style=discord.TextStyle.paragraph,
            required=False
        )
        self.remove_items = TextInput(
            label="Remove (amount item quality)",
            style=discord.TextStyle.paragraph,
            required=False
        )

        self.add_item(self.add_items)
        self.add_item(self.remove_items)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        add = parse_user_lines(self.add_items.value.strip().splitlines()) if self.add_items.value else []
        rem = parse_user_lines(self.remove_items.value.strip().splitlines()) if self.remove_items.value else []

        await self.sheets.modify_priorities(add, rem)
        await interaction.followup.send(
            "✅ Priorities updated successfully!",
            ephemeral=True
        )


class AuditEditModal(Modal, title="Edit Audit Items"):
    """
    Modal used during audits to correct item quantities
    for a specific banker.
    """

    def __init__(self, items, banker_name: str, sheets_service):
        super().__init__()
        self.items = items
        self.banker_name = banker_name
        self.sheets = sheets_service

        default_text = "\n".join(
            f"{amt} × {item} ({quality})"
            for item, quality, amt in self.items
        )
        self.item_input = TextInput(
            label="Edit only these items",
            style=discord.TextStyle.paragraph,
            default=default_text
        )
        self.add_item(self.item_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        parsed = parse_audit_lines(self.item_input.value.strip().splitlines())
        if not parsed:
            await interaction.followup.send(
                "❌ No valid items parsed.",
                ephemeral=True
            )
            return

        await self.sheets.apply_audit_for_banker(self.banker_name, parsed)
        await interaction.followup.send(
            "✅ Audit changes applied!",
            ephemeral=True
        )
