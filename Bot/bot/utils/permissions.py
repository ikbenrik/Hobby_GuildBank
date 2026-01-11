"""
bot/utils/permissions.py

Centralized permission and channel validation helpers.

This module defines small, reusable checks that enforce:
- Who is allowed to perform banker/admin actions
- Where sensitive commands are allowed to be used

Keeping these checks here avoids duplication across cogs
and ensures consistent permission behavior.
"""

import discord


def is_authorized_member(member: discord.Member) -> bool:
    """
    Determine whether a guild member is authorized to perform
    banker-level or administrative actions.

    Authorization is granted if the member is:
    - The server owner
    - A server administrator
    - Assigned the "Banker" role

    Args:
        member: Discord guild member to check

    Returns:
        True if the member is authorized, otherwise False
    """
    # Server owner always has full permissions
    if member == member.guild.owner:
        return True

    # Administrators bypass all role checks
    if member.guild_permissions.administrator:
        return True

    # Explicit banker role check
    if discord.utils.get(member.roles, name="Banker"):
        return True

    return False


def is_valid_channel(channel: discord.abc.GuildChannel, donation_channel_name: str) -> bool:
    """
    Validate whether a command is being executed in the correct channel.

    This is primarily used to restrict donation, OCR, and audit
    interactions to a dedicated log channel.

    Args:
        channel: The channel where the interaction occurred
        donation_channel_name: Expected channel name

    Returns:
        True if the channel name matches the expected one, otherwise False
    """
    return getattr(channel, "name", "") == donation_channel_name
