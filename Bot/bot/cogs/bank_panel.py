# ==========================================
# bot/cogs/bank_panel.py
# Main interactive control panel for the Guild Bank bot
#
# Responsibilities:
# - Provide the /bank slash command
# - Serve as the primary user entry point
# - Attach interactive UI views (buttons & modals)
#
# Important:
# - This cog does NOT implement logic itself
# - It delegates all behavior to UI views and services
# ==========================================

from discord.ext import commands
import discord

from config import SETTINGS
from bot.services.sheets_service import SheetsService
from bot.ui.views import CommandPanel


class BankPanelCog(commands.Cog):
    """
    Cog exposing the `/bank` slash command.

    This command opens the main control panel view,
    from which users can access all bank-related actions:
    - View bank inventory
    - Add donations
    - Search items
    - Trigger audits and backups (if authorized)
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # SheetsService handles all Google Sheets access
        # Instantiated once per cog to be shared across views
        self.sheets = SheetsService(
            SETTINGS.spreadsheet_url,
            SETTINGS.credentials_file
        )

    # --------------------------------------
    # Slash command: /bank
    # --------------------------------------
    @discord.app_commands.command(
        name="bank",
        description="📋 Open bank panel with all commands"
    )
    async def bank_panel(self, interaction: discord.Interaction):
        """
        Opens the interactive Guild Bank control panel.

        The panel itself is implemented in bot.ui.views.CommandPanel
        and contains all user-facing actions.
        """
        await interaction.response.defer(ephemeral=True)

        # Callback passed into the panel for restore actions.
        # The Backup cog owns the actual restore command;
        # here we only guide the user if restore is requested.
        async def open_restore_picker(inter: discord.Interaction):
            await inter.followup.send(
                "Use `!restore` in the server (admin only) to open the restore picker.",
                ephemeral=True
            )

        # Create the main command panel view
        view = CommandPanel(
            interaction,
            self.sheets,
            backup_open_callback=open_restore_picker
        )

        # Send the panel to the user (ephemeral = only visible to them)
        await interaction.followup.send(
            "🛠️ **Guild Bank Panel:** Choose a function below:",
            view=view,
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    """
    Required setup hook for discord.py extension loading.
    """
    await bot.add_cog(BankPanelCog(bot))
