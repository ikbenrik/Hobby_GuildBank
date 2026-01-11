"""
bot/services/sheets_service.py

Service layer responsible for **all Google Sheets interactions** for the Guild Bank bot.

Responsibilities:
- Read and write guild-wide inventory totals
- Track per-banker inventory
- Apply donations (OCR + manual)
- Handle crafting / processing flows
- Maintain priorities and audits
- Provide read-only views for bank queries and donation history

Design notes:
- This module contains NO Discord-specific logic.
- All values are normalized internally to avoid duplicates caused by casing/punctuation.
- Each public method represents a single business operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime, timezone
import re
from typing import Any

import gspread

from bot.utils.parsing import ItemTuple, parse_user_lines


# --------------------------------------------------
# Display helpers (used by UI / views)
# --------------------------------------------------
QUALITY_EMOJIS = {
    "Common": "⚪",
    "Uncommon": "🟢",
    "Rare": "🔵",
    "Heroic": "🟡",
    "Epic": "🟣",
    "Legendary": "🟠",
}


def chunk_message_blocks(blocks: list[str], max_chars: int = 1900) -> list[str]:
    """
    Group pre-formatted text blocks into Discord-safe message chunks.

    Each block is kept intact when possible. Chunks are joined with newlines
    and guaranteed to stay below the max character limit.
    """
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for b in blocks:
        blen = len(b) + 1  # newline
        if current and current_len + blen > max_chars:
            chunks.append("\n".join(current))
            current = [b]
            current_len = blen
        else:
            current.append(b)
            current_len += blen

    if current:
        chunks.append("\n".join(current))

    return chunks


# --------------------------------------------------
# Google Sheets container
# --------------------------------------------------
@dataclass
class Sheets:
    """
    Typed container holding references to all worksheets
    used by the Guild Bank bot.
    """
    spreadsheet: Any
    guild_inventory: Any
    banker_inventory: Any
    donation_log: Any
    artisan_log: Any
    priorities: Any
    audit_log: Any


class SheetsService:
    """
    High-level service providing all guild bank data operations.

    This class is the single source of truth for:
    - Inventory mutations
    - Totals reconciliation
    - Audits and logging
    """

    def __init__(self, spreadsheet_url: str, creds_file: str):
        # Authenticate and open spreadsheet
        self.client = gspread.service_account(filename=creds_file)
        spreadsheet = self.client.open_by_url(spreadsheet_url)

        # Cache worksheet references
        self.sheets = Sheets(
            spreadsheet=spreadsheet,
            guild_inventory=spreadsheet.worksheet("Guild Bank Inventory"),
            banker_inventory=spreadsheet.worksheet("Banker Inventory"),
            donation_log=spreadsheet.worksheet("Donations"),
            artisan_log=spreadsheet.worksheet("Artisan"),
            priorities=spreadsheet.worksheet("Priorities"),
            audit_log=spreadsheet.worksheet("Audit Log"),
        )

    # --------------------------------------------------
    # Normalization helpers
    # --------------------------------------------------
    @staticmethod
    def _norm_text(s: str) -> str:
        """Normalize text for consistent key comparisons."""
        return re.sub(r"[^\w\s]", "", str(s)).strip().lower()

    @classmethod
    def _norm_item_key(cls, item: str, quality: str) -> tuple[str, str]:
        """Normalized key for guild-wide item totals."""
        return (cls._norm_text(item), cls._norm_text(quality))

    @classmethod
    def _norm_banker_key(cls, item: str, quality: str, banker: str) -> tuple[str, str, str]:
        """Normalized key for banker-owned inventory rows."""
        return (cls._norm_text(item), cls._norm_text(quality), cls._norm_text(banker))

    @staticmethod
    def utc_now_str() -> str:
        """Current UTC timestamp formatted for Google Sheets."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # --------------------------------------------------
    # Donations (OCR / Manual)
    # --------------------------------------------------
    async def apply_donation(self, items: list[ItemTuple], donator_name: str, banker_name: str) -> None:
        """
        Apply a donation event.

        Effects:
        - Update banker inventory
        - Update guild inventory totals
        - Append donation log entries
        """
        ws_b = self.sheets.banker_inventory
        ws_g = self.sheets.guild_inventory
        ws_d = self.sheets.donation_log
        now = self.utc_now_str()

        # Stack items by normalized (item, quality, banker)
        stacked = defaultdict(int)
        for item, quality, amount in items:
            stacked[self._norm_banker_key(item, quality, banker_name)] += int(amount)

        # Load existing banker inventory
        banker_data = ws_b.get_all_records()
        banker_lookup = {
            self._norm_banker_key(r["Item"], r["Quality"], r["Banker"]): (i + 2, int(r["Amount"]))
            for i, r in enumerate(banker_data)
        }

        updated_rows: dict[int, int] = {}
        new_rows: list[list[Any]] = []
        donation_rows: list[list[Any]] = []

        for (item_k, quality_k, banker_k), amount in stacked.items():
            donation_rows.append([donator_name, item_k.title(), quality_k.title(), amount, now])

            if (item_k, quality_k, banker_k) in banker_lookup:
                row_num, current = banker_lookup[(item_k, quality_k, banker_k)]
                updated_rows[row_num] = current + amount
            else:
                new_rows.append([item_k.title(), quality_k.title(), banker_name, amount])

        # Rewrite banker inventory sheet atomically
        existing = ws_b.get_all_values()
        headers = existing[0]
        rows = existing[1:]

        for row_num, new_amt in updated_rows.items():
            rows[row_num - 2][3] = str(new_amt)

        for item, quality, banker, amount in new_rows:
            rows.append([item, quality, banker, str(amount)])

        ws_b.clear()
        ws_b.update("A1", [headers] + rows)

        # Append donation log entries
        if donation_rows:
            start_row = len(ws_d.get_all_values()) + 1
            ws_d.update(range_name=f"A{start_row}", values=donation_rows)

        # Incrementally update guild totals
        guild_data = ws_g.get_all_records()
        guild_lookup = {
            self._norm_item_key(r["Item"], r["Quality"]): (i + 2, int(r["Amount"]))
            for i, r in enumerate(guild_data)
        }

        delta_totals = defaultdict(int)
        for (item_k, quality_k, _), amount in stacked.items():
            delta_totals[(item_k, quality_k)] += amount

        for (item_k, quality_k), delta in delta_totals.items():
            if (item_k, quality_k) in guild_lookup:
                row_num, current_amt = guild_lookup[(item_k, quality_k)]
                ws_g.update_cell(row_num, 3, current_amt + delta)
            else:
                ws_g.append_row([item_k.title(), quality_k.title(), delta])

    async def manual_add(self, donator_name: str, items: list[ItemTuple]) -> None:
        """Manual donation shortcut (donator == banker)."""
        await self.apply_donation(items, donator_name=donator_name, banker_name=donator_name)

    # --------------------------------------------------
    # Bank view / search
    # --------------------------------------------------
    async def get_full_guild_bank_totals(self) -> dict[tuple[str, str], int]:
        """Return aggregated guild inventory totals."""
        rows = self.sheets.guild_inventory.get_all_records()
        totals: dict[tuple[str, str], int] = defaultdict(int)

        for r in rows:
            item = str(r.get("Item", "")).strip().title()
            quality = str(r.get("Quality", "")).strip().title()
            try:
                amt = int(r.get("Amount", 0))
            except Exception:
                continue
            totals[(item, quality)] += amt

        return dict(totals)

    async def get_full_guild_bank_chunks(self) -> list[str]:
        """
        Return formatted, chunked strings representing
        the entire guild bank inventory.
        """
        totals = await self.get_full_guild_bank_totals()
        if not totals:
            return ["📭 Guild Bank is empty."]

        item_blocks = defaultdict(list)
        for (item, quality), amt in sorted(totals.items()):
            emoji = QUALITY_EMOJIS.get(quality, "")
            item_blocks[item].append(f"{emoji} {amt}× {quality}")

        blocks: list[str] = []
        for item, lines in item_blocks.items():
            blocks.append("```\n" + f"{item}:\n" + "\n".join(lines) + "\n```")

        return chunk_message_blocks(blocks, max_chars=1900)

    async def search_banker_holdings(self, item_query: str, quality_query: str | None = None) -> list[dict[str, Any]]:
        """Search banker inventory for a specific item (optionally filtered by quality)."""
        banker_rows = self.sheets.banker_inventory.get_all_records()
        item_q = item_query.strip().lower()
        q_q = quality_query.strip().lower() if quality_query else None

        matches = []
        for r in banker_rows:
            if str(r.get("Item", "")).strip().lower() != item_q:
                continue
            if q_q and str(r.get("Quality", "")).strip().lower() != q_q:
                continue
            matches.append(r)

        return matches

    # --------------------------------------------------
    # Priorities
    # --------------------------------------------------
    async def get_priority_summary(self) -> str:
        """Return a human-readable summary of current guild priorities."""
        priorities = self.sheets.priorities.get_all_records()
        bank = self.sheets.guild_inventory.get_all_records()

        item_totals = defaultdict(lambda: defaultdict(int))
        for row in bank:
            item = str(row["Item"]).lower()
            quality = str(row["Quality"])
            amount = int(row["Amount"])
            item_totals[item][quality] += amount

        lines = ["📋 **Current Guild Needs:**"]
        for row in priorities:
            item = str(row["Items"]).lower()
            quality = str(row["Quality"])
            target = int(row["Needed"])
            current = item_totals[item][quality] if quality in item_totals[item] else 0
            status = "✅" if current >= target else "🔄"
            lines.append(f"{status} {item.title()} ({quality}) → {current} / {target}")

        return "\n".join(lines)

    async def replace_priorities(self, rows: list[list[Any]]) -> None:
        """Replace the entire priorities sheet."""
        ws = self.sheets.priorities
        ws.clear()
        ws.append_row(["Items", "Quality", "Needed"])
        if rows:
            ws.append_rows(rows)

    async def modify_priorities(self, add: list[ItemTuple], remove: list[ItemTuple]) -> None:
        """Incrementally add or remove priority targets."""
        ws = self.sheets.priorities
        data = ws.get_all_values()
        headers, *rows = data
        current = {(r[0].lower(), r[1].lower()): int(r[2]) for r in rows if len(r) >= 3}

        for item, quality, amount in add:
            key = (item.lower(), quality.lower())
            current[key] = current.get(key, 0) + int(amount)

        for item, quality, amount in remove:
            key = (item.lower(), quality.lower())
            if key in current:
                current[key] = max(current[key] - int(amount), 0)
                if current[key] == 0:
                    del current[key]

        ws.clear()
        ws.append_row(["Items", "Quality", "Needed"])
        for (item, quality), needed in current.items():
            ws.append_row([item.title(), quality.title(), needed])

    # --------------------------------------------------
    # Craft / Process
    # --------------------------------------------------
    async def craft_or_process(self, banker_name: str, materials: list[ItemTuple], outputs: list[ItemTuple], is_processing: bool) -> None:
        """
        Apply crafting or processing actions.

        Materials are always subtracted.
        Outputs are added only when processing (not crafting).
        """
        ws_b = self.sheets.banker_inventory
        ws_g = self.sheets.guild_inventory
        ws_a = self.sheets.artisan_log
        now = self.utc_now_str()

        def bkey(item, quality, banker): return self._norm_banker_key(item, quality, banker)
        def gkey(item, quality): return self._norm_item_key(item, quality)

        # Load banker inventory map
        all_banker_rows = ws_b.get_all_records()
        banker_map = {
            bkey(r["Item"], r["Quality"], r["Banker"]): (i + 2, int(r["Amount"]))
            for i, r in enumerate(all_banker_rows)
        }

        # Subtract materials
        for item, quality, amount in materials:
            key = bkey(item, quality, banker_name)
            if key not in banker_map:
                raise ValueError(f"{item} ({quality}) not found under {banker_name}")
            row_idx, current = banker_map[key]
            new_amt = max(current - int(amount), 0)
            ws_b.update_cell(row_idx, 4, new_amt)
            banker_map[key] = (row_idx, new_amt)

        # Add outputs (processing only)
        if is_processing:
            for item, quality, amount in outputs:
                key = bkey(item, quality, banker_name)
                if key in banker_map:
                    row_idx, current = banker_map[key]
                    ws_b.update_cell(row_idx, 4, current + int(amount))
                else:
                    ws_b.append_row([item.title(), quality.title(), banker_name, int(amount)])

        # Apply guild delta
        delta = defaultdict(int)
        for item, quality, amount in materials:
            delta[gkey(item, quality)] -= int(amount)
        if is_processing:
            for item, quality, amount in outputs:
                delta[gkey(item, quality)] += int(amount)

        guild_rows = ws_g.get_all_records()
        guild_map = {gkey(r["Item"], r["Quality"]): (i + 2, int(r["Amount"])) for i, r in enumerate(guild_rows)}

        for (item_k, quality_k), d in delta.items():
            if d == 0:
                continue
            if (item_k, quality_k) in guild_map:
                row_idx, current = guild_map[(item_k, quality_k)]
                ws_g.update_cell(row_idx, 3, max(current + d, 0))
            elif d > 0:
                ws_g.append_row([item_k.title(), quality_k.title(), d])

        used_str = ", ".join(f"{a} {i} {q}" for i, q, a in materials)
        made_str = ", ".join(f"{a} {i} {q}" for i, q, a in outputs) if outputs else ""
        ws_a.append_row([banker_name, used_str, made_str, now])

    # --------------------------------------------------
    # Audit
    # --------------------------------------------------
    async def apply_audit_for_banker(self, banker_name: str, updated_items: list[ItemTuple]) -> None:
        """
        Replace a single banker's inventory with audited values
        and reconcile guild totals accordingly.
        """
        ws_b = self.sheets.banker_inventory
        ws_g = self.sheets.guild_inventory
        ws_audit = self.sheets.audit_log
        timestamp = self.utc_now_str()

        def gkey(item, quality): return self._norm_item_key(item, quality)

        updated_map = defaultdict(int)
        for item, quality, amt in updated_items:
            updated_map[gkey(item, quality)] += int(amt)

        all_rows = ws_b.get_all_records()
        result_rows = []
        old_map = defaultdict(int)

        for r in all_rows:
            if str(r["Banker"]).strip() == banker_name:
                old_map[gkey(r["Item"], r["Quality"])] += int(r["Amount"])
            else:
                result_rows.append([r["Item"], r["Quality"], r["Banker"], r["Amount"]])

        for (item_k, quality_k), amt in updated_map.items():
            result_rows.append([item_k.title(), quality_k.title(), banker_name, amt])

        ws_b.clear()
        ws_b.update("A1", [["Item", "Quality", "Banker", "Amount"]] + result_rows)

        delta_totals = defaultdict(int)
        for key in set(updated_map) | set(old_map):
            delta_totals[key] = updated_map.get(key, 0) - old_map.get(key, 0)

        guild_rows = ws_g.get_all_records()
        guild_lookup = {gkey(r["Item"], r["Quality"]): (i + 2, int(r["Amount"])) for i, r in enumerate(guild_rows)}

        for (item_k, quality_k), delta in delta_totals.items():
            if delta == 0:
                continue
            if (item_k, quality_k) in guild_lookup:
                row_num, current_amt = guild_lookup[(item_k, quality_k)]
                ws_g.update_cell(row_num, 3, max(current_amt + delta, 0))
            elif delta > 0:
                ws_g.append_row([item_k.title(), quality_k.title(), delta])

        def fmt_map(m: dict[tuple[str, str], int]) -> str:
            lines = []
            for (i, q), a in sorted(m.items()):
                lines.append(f"{a} × {i.title()} ({q.title()})")
            return "\n".join(lines)

        ws_audit.append_row([timestamp, banker_name, fmt_map(old_map), fmt_map(updated_map)])

    # --------------------------------------------------
    # Donation search
    # --------------------------------------------------
    async def query_donations(self, user_filter: str | None, cutoff_time_utc) -> list[dict[str, Any]]:
        """Query donation log entries with optional user and time filters."""
        rows = self.sheets.donation_log.get_all_values()
        if not rows or len(rows) < 2:
            return []

        out = []
        for row in rows[1:]:
            try:
                donator = str(row[0]).strip()
                item = str(row[1]).strip()
                quality = str(row[2]).strip()
                amount = int(row[3])
                ts = datetime.strptime(str(row[4]), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                continue

            if ts < cutoff_time_utc:
                continue
            if user_filter:
                uf = user_filter.lower()
                if uf not in donator.lower() and uf not in donator.replace(" ", "").lower():
                    continue

            out.append({
                "Donator": donator,
                "Item": item,
                "Quality": quality,
                "Amount": amount,
                "Timestamp": ts.strftime("%Y-%m-%d %H:%M:%S")
            })

        return out
