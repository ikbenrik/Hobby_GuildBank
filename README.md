# Guild Bank Bot (Discord + Google Sheets + OCR)

A Discord bot that helps your guild track bank inventory, donations, artisan activity, audits, priorities (needed items), and daily backups — using **Google Sheets** as the database and **OCR (Tesseract)** to read donation screenshots.

---

## Features

### 📦 Bank / Inventory
- **Guild Bank Inventory** stored in Google Sheets
- **Banker Inventory** (per banker holdings)
- Search items by name + optional quality
- View full bank grouped by item and quality

### 🧾 Donations
- OCR reads screenshots and extracts:
  - Item name
  - Quantity
  - Item quality (via text color / hue detection)
- Banker confirms or edits OCR output via Discord UI
- Donations are appended to a **Donations** log sheet

### 🛠️ Artisan (Process / Craft)
- Banker can log materials used and outputs made
- Updates banker + guild totals
- Logged to an **Artisan** sheet

### ✅ Priorities (Needed Items)
- Maintains a list of required items/qualities/amounts
- Shows progress vs current bank totals
- Admin/banker can edit the list via modal UI

### 🧾 Audit
- Banker can generate a list of all items recorded under their name
- Can edit in chunks via modal (to avoid Discord length limits)
- Updates banker inventory + guild totals
- Logs changes to an **Audit Log** sheet

### 💾 Backups
- Daily XLSX export of the full Google Sheet to a Discord backup channel
- Admin can restore from a posted XLSX backup

---
