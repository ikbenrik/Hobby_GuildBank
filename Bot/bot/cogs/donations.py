# ==========================================
# bot/cogs/donations.py
# Donation history lookup commands
#
# Responsibilities:
# - Provide !d / !donations text command
# - Filter donation logs by user and/or time window
# - Present results in paginated Discord messages
#
# Notes:
# - This cog is read-only (no mutations)
# - Data is sourced from Google Sheets via SheetsService
# ==========================================

from discord.ext import commands
from datetime import datetime, timedelta, timezone
import re

from config import SETTINGS
from bot.services.sheets_service import SheetsService
from bot.utils.permissions import is_valid_channel


class DonationsCog(commands.Cog):
    """
    Cog providing donation history lookup commands.

    Users can query:
    - Recent donations (default: last 1 day)
    - Donations by a specific user
    - Donations within a custom time window
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # SheetsService handles all Google Sheets access
        self.sheets = SheetsService(
            SETTINGS.spreadsheet_url,
            SETTINGS.credentials_file
        )

    # --------------------------------------
    # Text command: !d / !donations
    # --------------------------------------
    @commands.command(name="d", aliases=["donations"])
    async def donations(self, ctx: commands.Context, *, args: str = ""):
        """
        Query donation history.

        Usage examples:
        - !d
        - !d 3d
        - !d rik
        - !d @rik 1w

        Supported duration suffixes:
        d = days, w = weeks, m = months (30d), y = years (365d)
        """

        # Restrict command usage to the donation log channel
        if not is_valid_channel(ctx.channel, SETTINGS.donation_channel_name):
            await ctx.send("🚫 Please use this command in the donation channel.")
            return

        # ----------------------------------
        # Helper: parse duration tokens
        # ----------------------------------
        def parse_duration(duration_str: str):
            """
            Parse duration tokens like '3d', '2w', '1m', '1y'
            into a timedelta object.
            """
            m = re.fullmatch(r"(\d+)([dwmy])", duration_str.strip().lower())
            if not m:
                return None

            num, unit = int(m.group(1)), m.group(2)
            return {
                "d": timedelta(days=num),
                "w": timedelta(weeks=num),
                "m": timedelta(days=30 * num),
                "y": timedelta(days=365 * num),
            }[unit]

        # ----------------------------------
        # Default filters
        # ----------------------------------
        user_filter = None
        time_filter = timedelta(days=1)  # default: last 24h
        now = datetime.now(timezone.utc)

        # ----------------------------------
        # Parse command arguments
        # ----------------------------------
        parts = args.split()
        for part in parts:
            # Duration token (e.g. 3d, 1w)
            dur = parse_duration(part)
            if dur:
                time_filter = dur
                continue

            # User filter (mention or name fragment)
            if part.startswith("<@") and part.endswith(">"):
                user_id = re.sub(r"[<@!>]", "", part)
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    if user:
                        user_filter = user.name.lower()
                except Exception:
                    user_filter = None
            else:
                user_filter = part.lower()

        # Compute cutoff timestamp (start of day, UTC)
        cutoff_time = (now - time_filter).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # ----------------------------------
        # Query donations from Sheets
        # ----------------------------------
        filtered = await self.sheets.query_donations(user_filter, cutoff_time)
        if not filtered:
            await ctx.send("📭 No donations found in that time window.")
            return

        # ----------------------------------
        # Paginate and display results
        # ----------------------------------
        PAGE_SIZE = 10
        total_pages = (len(filtered) - 1) // PAGE_SIZE + 1

        for i in range(0, len(filtered), PAGE_SIZE):
            page = filtered[i:i + PAGE_SIZE]

            lines = [
                f"{r['Donator']} donated {r['Amount']} × {r['Item']} "
                f"({r['Quality']}) at {r['Timestamp']}"
                for r in page
            ]

            await ctx.send(
                f"📦 **Donations ({i // PAGE_SIZE + 1}/{total_pages}):**\n"
                "```" + "\n".join(lines) + "```"
            )


async def setup(bot: commands.Bot):
    """
    Required setup hook for discord.py extension loading.
    """
    await bot.add_cog(DonationsCog(bot))
