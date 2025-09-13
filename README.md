🎮 Free Games Watcher (Discord Bot)

Announces games temporarily discounted to free on Epic Games Store and Steam, and lists what’s free right now — excluding titles that are always free. Region‑aware, channel‑configurable, owner/admin‑only controls. Built with discord.py + SQLite.

✨ Features

- 🔔 Announcements: Posts new freebies to a channel you choose
- 🆓 Paid → Free only: Filters out permanently free titles
- 🌍 Region aware: Per‑guild country code (e.g., US, GB, DE)
- 🛡️ Owner/Admin only: Settings restricted to trusted users
- 💾 Lightweight storage: SQLite de‑dupes and persists deals
- ⏱️ Polling: Periodic fetch of Epic + Steam feeds

🧩 Slash Commands

- `/freelist` — Show currently free paid games in your configured region
- `/freelist_region [code]` — Set or view the region (owner/admin; ISO 3166‑1 alpha‑2)
- `/freelist_channel #channel` — Set the announcement channel (owner/admin)
- `/freelist_poll_now` — Force a fetch + announce now (owner/admin)
- `/freelist_debug` — Show fetch diagnostics (owner/admin)

🧠 How It Detects Freebies

- Epic Games Store: Active promo window flagged in the feed; counts a title as free when the promo is live and the original price was > $0 (Epic often reports `discountPercentage: 0` during free weeks; we rely on the promo window, not listed price).
 - Steam: Confirms via appdetails that it's a game, was originally paid (`price_overview.initial > 0`), and is currently free by any of these signals: `discount_percent == 100`, `final == 0`, or `final_formatted == 'Free'`. This avoids excluding promos that momentarily set `is_free = true` while on a 100% discount.

🛠️ Setup

- Requirements: Python 3.13+ and a Discord bot token
- Install: `pip install -r requirements.txt`
- Configure env: copy `.env.example` to `.env`, then set `DISCORD_TOKEN` and optionally `POLL_MINUTES`
- Run: `python bot.py`
- First‑time in your server (owner/admin): `/freelist_region code: US`, `/freelist_channel channel: #your-channel`, then `/freelist`

📦 Environment (.env)

- The bot auto‑loads `.env` via `python-dotenv`.
- Example:
  - `DISCORD_TOKEN=YOUR_BOT_TOKEN`
  - `POLL_MINUTES=30`

🐍 Python Version

- Recommended: Python 3.13+ (requirements include the necessary backport for clean installs).

🔗 Invite URL

Use this URL to invite your bot. Replace `YOUR_APP_ID` with your application’s ID from the Discord Developer Portal (General Information page). Do not use your bot token here.

`https://discord.com/api/oauth2/authorize?client_id=YOUR_APP_ID&scope=bot%20applications.commands&permissions=84992`

- `client_id`: your Application ID (a numeric ID), not the token.
- `scope`: keeps slash commands and bot permissions.
- `permissions=84992`: View Channels (1024) + Send Messages (2048) + Embed Links (16384) + Read Message History (65536). Adjust if you need more.

🐳 Docker (Optional)

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

Windows PowerShell helper:

- Use the included `Start-Docker.ps1` script to build and run:
  - `./Start-Docker.ps1 -Rebuild` — build image (or reuse) and run detached
  - `./Start-Docker.ps1 -Rebuild -PersistDb` — also mount `./data` and persist the SQLite DB

Bash helper (Linux/macOS/WSL):

- Make it executable: `chmod +x ./start-docker.sh`
- Build and run:
  - `./start-docker.sh -r`
  - `./start-docker.sh -r -p` — mount `./data` and persist the SQLite DB

ℹ️ Notes

- Data is stored in `free_deals.sqlite3` in the repo directory.
- The poller runs every `POLL_MINUTES` minutes (set in env).
- Steam “free to keep” promos are rarer than Epic’s weekly freebies; zero results for Steam can be normal.

🙋 Troubleshooting

- Commands not showing? Global slash commands can take minutes to appear after first sync. If needed, re‑invite or restart the bot.
- “Message content intent missing” warning is safe to ignore (this bot uses slash commands).
- Seeing no freebies? Try `/freelist_debug` to confirm feed counts and sample titles. Epic weekends vary and Steam promos are sporadic.
