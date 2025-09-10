🎮 Free Games Watcher (Discord Bot)

Announces games temporarily discounted to free on Epic Games Store and Steam, and lists what’s free right now — excluding titles that are always free. Region-aware, channel-configurable, owner/admin‑only controls. Built with discord.py + SQLite.

✨ Features

- 🔔 Announcements: Posts new freebies to a channel you choose
- 🆓 Paid → Free only: Filters out permanently free titles
- 🌍 Region aware: Per‑guild country code (e.g., US, GB, DE)
- 🛡️ Owner/Admin only: Settings restricted to trusted users
- 💾 Lightweight storage: SQLite de‑dupes and persists deals
- ⏱️ Polling: Periodic fetch of Epic + Steam feeds

🚀 Quick Start

- Requirements: Python 3.13+ (recommended), a Discord bot token
- Install deps: `pip install -r requirements.txt`
- Configure env (see below) and run: `python bot.py`

🧩 Slash Commands

- `/freelist` — Show currently free paid games in your configured region
- `/freelist_region [code]` — Set or view the region (owner/admin; ISO 3166‑1 alpha‑2)
- `/freelist_channel #channel` — Set the announcement channel (owner/admin)
- `/freelist_poll_now` — Force a fetch + announce now (owner/admin)
- `/freelist_debug` — Show fetch diagnostics (owner/admin)

🛠️ Setup

1) Create a Discord application + bot (Developer Portal) and copy the bot token.
2) Invite with scopes: `applications.commands`, `bot` and permissions: Send Messages, Embed Links, Read Message History.
3) Environment variables (use `.env`):
   - `DISCORD_TOKEN=YOUR_BOT_TOKEN`
   - `POLL_MINUTES=30` (optional; default 30)
4) First run in your server (owner/admin):
   - `/freelist_region code: US` (or your country)
   - `/freelist_channel channel: #your-channel`
   - `/freelist` to view current freebies

📦 Environment (.env)

- Copy `.env.example` to `.env` and set values.
- The bot auto‑loads `.env` via `python-dotenv`.

🐍 Python Version

- Recommended: Python 3.13+.
- The requirements file includes `audioop-lts` conditionally for 3.13 so everything installs cleanly with `pip install -r requirements.txt`.

📡 Notes

- Data is stored in `free_deals.sqlite3` in the repo directory.
- The poller runs every `POLL_MINUTES` minutes (set in env).
- Steam “free to keep” promos are rarer than Epic’s weekly freebies; zero results for Steam can be normal.

🐳 Optional: Docker

Use this Dockerfile:

```
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["python", "bot.py"]
```

Build & run:

```
docker build -t free-bot .
docker run --env-file .env --name free-bot free-bot
```

🔗 Invite URL

Use this URL to invite your bot. Replace `YOUR_APP_ID` with your application’s ID from the Discord Developer Portal (General Information page). Do not use your bot token here.

`https://discord.com/api/oauth2/authorize?client_id=YOUR_APP_ID&scope=bot%20applications.commands&permissions=83968`

- `client_id`: your Application ID (a numeric ID), not the token.
- `scope`: keeps slash commands and bot permissions.
- `permissions=83968`: minimal set for Send Messages (2048) + Embed Links (16384) + Read Message History (65536). Adjust if you need more.

🙋 Troubleshooting

- Commands not showing? Global slash commands can take minutes to appear after first sync. If needed, re‑invite or restart the bot.
- “Message content intent missing” warning is safe to ignore (this bot uses slash commands).
- Seeing no freebies? Try `/freelist_debug` to confirm feed counts and sample titles. Epic weekends vary and Steam promos are sporadic.
