# ==========================================
# bot/cogs/audit.py
# Audit command for banker inventory correction
#
# Responsibilities:
# - Allow bankers to review their recorded inventory
# - Present inventory in editable chunks
# - Apply corrected values back to Google Sheets
#
# This cog is intentionally RESTRICTED:
# - Only allowed users
# - Only allowed channels
#
# All data persistence is handled by SheetsService.
# ==========================================

from discord.ext import commands
from collections import defaultdict

from config import SETTINGS
from bot.services.sheets_service import SheetsService
from bot.ui.views import AuditChunkView
from bot.utils.permissions import is_valid_channel, is_authorized_member
from bot.utils.parsing import parse_audit_lines
from bot.utils.formatting import chunk_message_blocks, QUALITY_EMOJIS


class AuditCog(commands.Cog):
    """
    Cog providing the `!audit` command.

    The audit flow allows a banker to:
    - View all items currently registered under their name
    - Edit those values via interactive Discord UI
    - Commit corrected totals back to the database (Google Sheets)
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # SheetsService handles all Google Sheets reads/writes
        self.sheets = SheetsService(
            SETTINGS.spreadsheet_url,
            SETTINGS.credentials_file
        )

    # --------------------------------------
    # Text command: !audit
    # --------------------------------------
    @commands.command(name="audit")
    async def audit(self, ctx: commands.Context):
        """
        Entry point for the audit process.

        Security checks:
        - Must be used in the configured donation/audit channel
        - User must have the appropriate role

        The command:
        - Fetches all items owned by the invoking banker
        - Displays them in editable chunks
        - Attaches UI views to apply corrections
        """

        # Permission & channel validation
        if (
            not is_valid_channel(ctx.channel, SETTINGS.donation_channel_name)
            or not is_authorized_member(ctx.author)
        ):
            await ctx.send("🚫 You are not allowed to use this command here or without proper role.")
            return

        banker_name = ctx.author.display_name

        # Load all banker inventory rows
        rows = self.sheets.sheets.banker_inventory.get_all_records()

        # Filter inventory to only items owned by this banker
        owned = [
            (r["Item"], r["Quality"], int(r["Amount"]))
            for r in rows
            if str(r["Banker"]).strip() == banker_name
        ]

        if not owned:
            await ctx.send("❌ You have no items recorded in the bank.")
            return

        # Format inventory lines for display
        lines = [
            f"{QUALITY_EMOJIS.get(q, '•')} {amt} × {item} ({q})"
            for item, q, amt in sorted(owned)
        ]

        # Split output into Discord-safe chunks
        chunks = chunk_message_blocks(lines, max_chars=1800)

        # Send each chunk with an interactive audit view
        for chunk in chunks:
            # Parse displayed text back into structured data
            # so the view knows which items it is editing
            parsed_items = parse_audit_lines(chunk.splitlines())

            view = AuditChunkView(
                banker_name,
                parsed_items,
                self.sheets
            )

            await ctx.send(
                "```\n" + chunk + "\n```",
                view=view
            )


async def setup(bot: commands.Bot):
    """
    Required setup function for discord.py extension loading.
    """
    await bot.add_cog(AuditCog(bot))
