# ==========================================
# bot/cogs/backup.py
# Automated and manual backup management
#
# Responsibilities:
# - Automatically export Google Sheets to XLSX (daily)
# - Upload backups to a dedicated Discord channel
# - Allow administrators to restore backups via UI
#
# Security considerations:
# - Restore command is ADMIN-ONLY
# - Restore actions notify the server owner
#
# All spreadsheet I/O is delegated to BackupService.
# ==========================================

import os
import discord
from discord.ext import commands, tasks

from config import SETTINGS
from bot.services.sheets_service import SheetsService
from bot.services.backup_service import BackupService, RestoreTarget
from bot.ui.views import BackupSelect


class BackupCog(commands.Cog):
    """
    Cog responsible for:
    - Scheduled Google Sheets backups
    - Manual restore flow via Discord UI

    This cog runs mostly autonomously once loaded.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Service handling direct access to Google Sheets
        self.sheets = SheetsService(
            SETTINGS.spreadsheet_url,
            SETTINGS.credentials_file
        )

        # BackupService handles XLSX export and restore logic
        self.backup = BackupService(
            self.sheets.sheets.spreadsheet.id,
            SETTINGS.credentials_file
        )

    # --------------------------------------
    # Lifecycle: start background tasks
    # --------------------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        """
        Start the daily backup task once the bot is ready.
        """
        if not self.daily_backup.is_running():
            self.daily_backup.start()

    # --------------------------------------
    # Scheduled task: daily Google Sheets backup
    # --------------------------------------
    @tasks.loop(hours=24)
    async def daily_backup(self):
        """
        Once per day:
        - Export the Google Sheets document as XLSX
        - Upload it to the configured backup channel
        - Delete the temporary file from disk
        """
        await self.bot.wait_until_ready()

        channel = discord.utils.get(
            self.bot.get_all_channels(),
            name=SETTINGS.backup_channel_name
        )

        if not channel:
            print("❌ Backup channel not found.")
            return

        try:
            filename = self.backup.export_xlsx()

            await channel.send(
                f"📦 Backup from Google Sheets: `{filename}`",
                file=discord.File(filename)
            )

            # Clean up temporary file
            os.remove(filename)
            print(f"✅ Backup {filename} sent to Discord.")

        except Exception as e:
            print(f"❌ Error during backup: {e}")

    # --------------------------------------
    # Admin command: restore backup
    # --------------------------------------
    @commands.command(name="restore")
    @commands.has_permissions(administrator=True)
    async def restore_backup(self, ctx: commands.Context):
        """
        Restore a previous XLSX backup from Discord.

        Flow:
        1. Scan backup channel for XLSX files
        2. Present them in a dropdown UI
        3. Restore selected backup into Google Sheets
        4. Notify server owner of the restore event
        """

        channel = discord.utils.get(
            ctx.guild.channels,
            name=SETTINGS.backup_channel_name
        )

        if not channel:
            await ctx.send("❌ Could not find backup channel.")
            return

        # Fetch recent messages and extract XLSX backups
        messages = [m async for m in channel.history(limit=50)]
        backup_files = [
            m for m in messages
            if m.attachments
            and m.attachments[0].filename.lower().endswith(".xlsx")
        ]

        if not backup_files:
            await ctx.send("📭 No backups found in the channel.")
            return

        # ----------------------------------
        # Restore callback (triggered by UI)
        # ----------------------------------
        async def restore_callback(
            interaction: discord.Interaction,
            msg: discord.Message,
            requester: discord.Member
        ):
            """
            Handles restoring the selected backup file.
            """
            attachment = msg.attachments[0]
            filename = "GuildBankBot_restore.xlsx"

            # Download backup locally
            await attachment.save(filename)

            try:
                # Define which worksheets are restored
                targets = [
                    RestoreTarget("Guild Bank Inventory", self.sheets.sheets.guild_inventory),
                    RestoreTarget("Banker Inventory", self.sheets.sheets.banker_inventory),
                    RestoreTarget("Donations", self.sheets.sheets.donation_log),
                    RestoreTarget("Artisan", self.sheets.sheets.artisan_log),
                    RestoreTarget("Priorities", self.sheets.sheets.priorities),
                ]

                # Perform restore
                self.backup.restore_xlsx_to_sheets(filename, targets)

            finally:
                # Always clean up local file
                try:
                    os.remove(filename)
                except Exception:
                    pass

            # Notify server owner for audit/security purposes
            server_owner = interaction.guild.owner
            try:
                await server_owner.send(
                    f"📁 **Backup Restored!**\n"
                    f"• Restored by: {requester.mention} ({requester.name})\n"
                    f"• Backup: `{attachment.filename}`\n"
                )
            except Exception as e:
                print(f"❌ Could not DM server owner: {e}")

            await interaction.followup.send(
                f"✅ Restored backup from Discord: `{attachment.filename}`",
                ephemeral=True
            )

        # Present backup selection UI
        view = BackupSelect(
            requester=ctx.author,
            backup_files=backup_files,
            restore_callback=restore_callback
        )
        view.set_options()

        await ctx.send("📁 Select a backup to restore:", view=view)


async def setup(bot: commands.Bot):
    """
    Required setup hook for discord.py extension loader.
    """
    await bot.add_cog(BackupCog(bot))
