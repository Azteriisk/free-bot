Free Games Watcher Discord Bot

This Discord bot announces games temporarily discounted to free on Epic Games Store and Steam, and provides a /freelist command. It excludes titles that are always free and supports per-guild region and channel settings (owner/admin only).

Quick Start

- Requirements: Python 3.11+, a Discord bot token
- Install deps: `pip install -r requirements.txt`
- Env vars: set `DISCORD_TOKEN` (and optional `POLL_MINUTES`, default 30)
- Run: `python bot.py`

Slash Commands

- /freelist: Show currently free paid games in the configured region
- /freelist_region [code]: Owner/Admin only. Set or view the region (ISO 3166-1 alpha-2, e.g., US, GB, DE)
- /freelist_channel #channel: Owner/Admin only. Set the announcement channel
- /freelist_poll_now: Owner/Admin only. Force a fetch + announce for this server
- /freelist_debug: Owner/Admin only. Show fetch diagnostics (counts and sample titles)

Notes

- Deals are tracked in `free_deals.sqlite3` in the repo directory.
- The poller posts new free games to the configured channel every `POLL_MINUTES` minutes.
- Minimum bot permissions: Send Messages, Embed Links, Read Message History.

Python version

- Recommended: Python 3.11 or 3.12.
- If using Python 3.13, install the audioop backport to avoid an import error from discord.py's voice module:
  `pip install audioop-lts`

Using a .env file

- Create a file named `.env` in the project root (you can copy `.env.example`).
- Add your variables, e.g.:

  `DISCORD_TOKEN=YOUR_BOT_TOKEN`

  `POLL_MINUTES=30`

- The bot automatically loads `.env` via `python-dotenv`.

Publishing to GitHub

1) Initialize and commit (done if you followed this repo; shown for reference):
   `git init && git add . && git commit -m "feat: free-bot initial"`
2) Create a repo named `free-bot` on GitHub (web UI) or with GitHub CLI:
   `gh repo create free-bot --public --source . --remote origin --push`
3) If created via web UI, add the remote and push:
   `git remote add origin https://github.com/USERNAME/free-bot.git`
   `git branch -M main`
   `git push -u origin main`
