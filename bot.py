import os
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional

import aiohttp
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dateutil import parser as dtparse
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

# ----------------- Config -----------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
POLL_MINUTES = int(os.getenv("POLL_MINUTES", "30"))
DB_PATH = "free_deals.sqlite3"

# Discord setup
INTENTS = discord.Intents.default()
BOT = commands.Bot(command_prefix="!", intents=INTENTS)
TREE = BOT.tree

# ----------------- DB -----------------

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # region-aware deals table (avoid cross-region collisions)
        await db.execute(
            """
        CREATE TABLE IF NOT EXISTS deals (
            platform TEXT NOT NULL,
            app_id TEXT NOT NULL,
            region TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            started_at TEXT,
            ends_at TEXT,
            PRIMARY KEY (platform, app_id, region)
        )"""
        )
        await db.execute(
            """
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            region TEXT DEFAULT 'US',
            channel_id INTEGER
        )"""
        )
        await db.commit()


async def upsert_deal(
    platform: str,
    app_id: str,
    region: str,
    title: str,
    url: str,
    started_at: Optional[str],
    ends_at: Optional[str],
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
        INSERT INTO deals (platform, app_id, region, title, url, started_at, ends_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(platform, app_id, region) DO UPDATE SET
          title=excluded.title,
          url=excluded.url,
          started_at=COALESCE(excluded.started_at, deals.started_at),
          ends_at=excluded.ends_at
        """,
            (platform, app_id, region, title, url, started_at, ends_at),
        )
        await db.commit()


async def get_all_deals_for_region(region: str):
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (
            await db.execute(
                "SELECT platform, app_id, title, url, started_at, ends_at "
                "FROM deals WHERE region=? ORDER BY platform, title",
                (region,),
            )
        ).fetchall()
    return [
        {
            "platform": r[0],
            "app_id": r[1],
            "title": r[2],
            "url": r[3],
            "started_at": r[4],
            "ends_at": r[5],
        }
        for r in rows
    ]


async def deal_exists(platform: str, app_id: str, region: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (
            await db.execute(
                "SELECT 1 FROM deals WHERE platform=? AND app_id=? AND region=?",
                (platform, app_id, region),
            )
        ).fetchone()
    return row is not None


async def get_guild_settings(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (
            await db.execute(
                "SELECT region, channel_id FROM guild_settings WHERE guild_id=?",
                (guild_id,),
            )
        ).fetchone()
    if row:
        return {"region": row[0], "channel_id": row[1]}
    return {"region": "US", "channel_id": None}


async def set_guild_region(guild_id: int, region: str):
    region = region.upper()
    if len(region) != 2:
        raise ValueError(
            "Region must be a 2-letter country code (ISO 3166-1 alpha-2)."
        )
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
        INSERT INTO guild_settings (guild_id, region) VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET region=excluded.region
        """,
            (guild_id, region),
        )
        await db.commit()


async def set_guild_channel(guild_id: int, channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
        INSERT INTO guild_settings (guild_id, channel_id) VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id
        """,
            (guild_id, channel_id),
        )
        await db.commit()


# ----------------- HTTP -----------------


async def fetch_json(session: aiohttp.ClientSession, url: str):
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as resp:
        resp.raise_for_status()
        return await resp.json()
    
async def try_fetch_json(session: aiohttp.ClientSession, url: str):
    try:
        return await fetch_json(session, url)
    except Exception as e:
        return {"__error__": str(e)}


# ----------------- Fetchers -----------------


async def get_epic_free_promos(session: aiohttp.ClientSession, region: str = "US"):
    """
    Returns list of dicts: {app_id, title, url, started_at, ends_at}
    Includes only promos that are 100% off within the current time window and originally paid (US-like logic).
    """
    url = (
        "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?"
        f"locale=en-US&country={region}&allowCountries={region}"
    )
    data = await fetch_json(session, url)

    # EGS returns either "searchStore.elements" or "catalogOffers.elements"
    games = (
        data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
    )
    if not games:
        games = (
            data.get("data", {})
            .get("Catalog", {})
            .get("catalogOffers", {})
            .get("elements", [])
        )

    results = []
    now = datetime.now(timezone.utc)

    for g in games:
        title = g.get("title")
        # Best-effort page slug extraction
        product_slug = (
            g.get("productSlug")
            or (g.get("offerMappings") or [{}])[0].get("pageSlug")
            or (g.get("catalogNs", {}).get("mappings", [{}])[0].get("pageSlug"))
            or g.get("urlSlug")
            or ""
        )
        app_id = g.get("id") or g.get("productId") or title or "unknown"

        # Price
        price = g.get("price", {})
        total = price.get("totalPrice", {})
        original = total.get("originalPrice", 0)  # cents
        discount = total.get("discountPrice", 0)  # cents

        # Promotions with 100% off, active now
        promos = g.get("promotions") or {}
        current = promos.get("promotionalOffers") or []
        active_zero = False
        start_iso = None
        end_iso = None

        if current:
            offers = current[0].get("promotionalOffers", [])
            for off in offers:
                try:
                    sd = dtparse.isoparse(off.get("startDate"))
                    ed = dtparse.isoparse(off.get("endDate"))
                except Exception:
                    continue
                ds = off.get("discountSetting") or {}
                # Epic marks freebies with discountPercentage == 0 in many cases
                if ds.get("discountType") == "PERCENTAGE" and int(ds.get("discountPercentage", 0)) == 0:
                    if sd <= now <= ed:
                        active_zero = True
                        start_iso = sd.isoformat()
                        end_iso = ed.isoformat()
                        break

        # Only include: originally paid, currently free (active promo window)
        # Do not rely on totalPrice.discountPrice being 0; Epic often leaves it as original.
        if active_zero and original > 0:
            url = (
                f"https://store.epicgames.com/en-US/p/{product_slug}"
                if product_slug
                else "https://store.epicgames.com/en-US/"
            )
            results.append(
                {
                    "app_id": str(app_id),
                    "title": title,
                    "url": url,
                    "started_at": start_iso,
                    "ends_at": end_iso,
                }
            )

    return results


async def get_steam_free_promos(session: aiohttp.ClientSession, region: str = "US"):
    """
    Returns list of dicts: {app_id, title, url, started_at(None), ends_at(None)}
    Strategy:
      1) Pull 'specials' from featured categories for region.
      2) For each item, confirm via appdetails (region) that:
         - type == 'game'
         - is_free == False
         - price_overview.initial > 0 and price_overview.final == 0
    """
    featured_url = (
        f"https://store.steampowered.com/api/featuredcategories?cc={region}&l=en"
    )
    data = await fetch_json(session, featured_url)
    specials = (data.get("specials") or {}).get("items", []) or []
    results = []

    async def fetch_details(appid: int):
        # Build without cc then add cc param to avoid double-cc
        base = f"https://store.steampowered.com/api/appdetails?appids={appid}"
        details = await fetch_json(session, f"{base}&cc={region}")
        return details

    for item in specials:
        appid = item.get("id")
        if not appid:
            continue

        try:
            details = await fetch_details(appid)
        except Exception:
            continue

        block = details.get(str(appid), {})
        if not block.get("success"):
            continue
        d = block.get("data") or {}

        if d.get("type") != "game":
            continue

        is_free = d.get("is_free", False)
        price = d.get("price_overview") or {}
        initial = price.get("initial")
        final = price.get("final")

        if isinstance(initial, int) and isinstance(final, int):
            if (not is_free) and initial > 0 and final == 0:
                title = d.get("name", f"App {appid}")
                url = f"https://store.steampowered.com/app/{appid}"
                results.append(
                    {
                        "app_id": str(appid),
                        "title": title,
                        "url": url,
                        "started_at": None,
                        "ends_at": None,
                    }
                )

    # De-dup
    seen = set()
    uniq = []
    for r in results:
        if r["app_id"] not in seen:
            seen.add(r["app_id"])
            uniq.append(r)
    return uniq


# ----------------- Admin Utilities -----------------


async def poll_once_for_guild(guild: discord.Guild):
    settings = await get_guild_settings(guild.id)
    region = settings.get("region", "US")
    channel_id = settings.get("channel_id")
    if not channel_id:
        return {"error": "No announcement channel set."}
    channel = guild.get_channel(channel_id)
    if channel is None:
        return {"error": "Configured channel not found."}

    async with aiohttp.ClientSession(headers={"User-Agent": "freewatch/1.0"}) as session:
        epic = await get_epic_free_promos(session, region)
        steam = await get_steam_free_promos(session, region)

    new_epic, new_steam = [], []
    for d in epic:
        exists = await deal_exists("epic", d["app_id"], region)
        await upsert_deal(
            "epic",
            d["app_id"],
            region,
            d["title"],
            d["url"],
            d.get("started_at"),
            d.get("ends_at"),
        )
        if not exists:
            new_epic.append(d)
    for d in steam:
        exists = await deal_exists("steam", d["app_id"], region)
        await upsert_deal(
            "steam",
            d["app_id"],
            region,
            d["title"],
            d["url"],
            d.get("started_at"),
            d.get("ends_at"),
        )
        if not exists:
            new_steam.append(d)

    await announce_new_deals(channel, new_epic, new_steam)
    return {
        "region": region,
        "found_epic": len(epic),
        "found_steam": len(steam),
        "announced_epic": len(new_epic),
        "announced_steam": len(new_steam),
    }


# ----------------- Discord Embeds -----------------


def epic_embed_item(d: Dict):
    ends = (
        f"Ends: <t:{int(dtparse.isoparse(d['ends_at']).timestamp())}:R>"
        if d.get("ends_at")
        else "Ends: unknown"
    )
    e = discord.Embed(title=d["title"], url=d["url"], description=ends)
    e.set_footer(text="Epic Games Store • $0.00")
    return e


def steam_embed_item(d: Dict):
    e = discord.Embed(title=d["title"], url=d["url"], description="Ends: unknown")
    e.set_footer(text="Steam • $0.00")
    return e


async def announce_new_deals(
    channel: discord.TextChannel, new_epic: List[Dict], new_steam: List[Dict]
):
    if not new_epic and not new_steam:
        return
    for d in new_epic:
        await channel.send(
            content="🎁 **New free game (EGS)**", embed=epic_embed_item(d)
        )
    for d in new_steam:
        await channel.send(
            content="🎁 **New free game (Steam)**", embed=steam_embed_item(d)
        )


# ----------------- Permissions Helpers -----------------


def is_owner_or_admin(interaction: discord.Interaction) -> bool:
    # Guild owner OR Administrator permission
    if interaction.guild is None:
        return False
    if interaction.user.id == interaction.guild.owner_id:
        return True
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and perms.administrator)


async def ensure_owner_admin(interaction: discord.Interaction):
    if not is_owner_or_admin(interaction):
        raise app_commands.AppCommandError(
            "Only the server owner or admins can use this command."
        )


# ----------------- Poller -----------------


@tasks.loop(minutes=POLL_MINUTES)
async def poll_deals():
    async with aiohttp.ClientSession(headers={"User-Agent": "freewatch/1.0"}) as session:
        for guild in BOT.guilds:
            try:
                settings = await get_guild_settings(guild.id)
                region = settings.get("region", "US")
                channel_id = settings.get("channel_id")
                if not channel_id:
                    continue
                channel = guild.get_channel(channel_id)
                if channel is None:
                    continue

                epic = await get_epic_free_promos(session, region)
                steam = await get_steam_free_promos(session, region)

                new_epic, new_steam = [], []
                for d in epic:
                    exists = await deal_exists("epic", d["app_id"], region)
                    await upsert_deal(
                        "epic",
                        d["app_id"],
                        region,
                        d["title"],
                        d["url"],
                        d.get("started_at"),
                        d.get("ends_at"),
                    )
                    if not exists:
                        new_epic.append(d)
                for d in steam:
                    exists = await deal_exists("steam", d["app_id"], region)
                    await upsert_deal(
                        "steam",
                        d["app_id"],
                        region,
                        d["title"],
                        d["url"],
                        d.get("started_at"),
                        d.get("ends_at"),
                    )
                    if not exists:
                        new_steam.append(d)

                await announce_new_deals(channel, new_epic, new_steam)
            except Exception as e:
                # Keep polling other guilds even if one fails
                print(f"[poll] guild {guild.id} error: {e}")


@poll_deals.before_loop
async def before_poll():
    await BOT.wait_until_ready()
    await init_db()


# ----------------- Slash Commands -----------------


@TREE.command(
    name="freelist",
    description="Show all currently free (formerly paid) games in your configured region",
)
async def freelist(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return

    settings = await get_guild_settings(interaction.guild.id)
    region = settings["region"]

    # Refresh latest for this guild's region
    async with aiohttp.ClientSession(headers={"User-Agent": "freewatch/1.0"}) as session:
        epic = await get_epic_free_promos(session, region)
        steam = await get_steam_free_promos(session, region)

    # Save so /freelist also updates DB
    for d in epic:
        await upsert_deal(
            "epic", d["app_id"], region, d["title"], d["url"], d.get("started_at"), d.get("ends_at")
        )
    for d in steam:
        await upsert_deal(
            "steam", d["app_id"], region, d["title"], d["url"], d.get("started_at"), d.get("ends_at")
        )

    deals = await get_all_deals_for_region(region)
    epic_list = [d for d in deals if d["platform"] == "epic"]
    steam_list = [d for d in deals if d["platform"] == "steam"]

    if not epic_list and not steam_list:
        await interaction.response.send_message(
            f"No free paid games found in **{region}** right now.", ephemeral=True
        )
        return

    embeds = []
    if epic_list:
        e = discord.Embed(
            title=f"Epic Games Store — Free Right Now ({region})", description=""
        )
        for d in epic_list:
            ends = (
                f" • Ends <t:{int(dtparse.isoparse(d['ends_at']).timestamp())}:R>"
                if d.get("ends_at")
                else ""
            )
            e.description += f"• [{d['title']}]({d['url']}){ends}\n"
        embeds.append(e)
    if steam_list:
        s = discord.Embed(
            title=f"Steam — Free Right Now ({region})", description=""
        )
        for d in steam_list:
            s.description += f"• [{d['title']}]({d['url']}) • Ends unknown\n"
        embeds.append(s)

    await interaction.response.send_message(embeds=embeds)


@TREE.command(name="freelist_region", description="Set or view the region (owner/admin only)")
@app_commands.describe(code="2-letter country code (ISO 3166-1 alpha-2), e.g., US, GB, DE")
async def freelist_region(interaction: discord.Interaction, code: Optional[str] = None):
    if interaction.guild is None:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return
    await ensure_owner_admin(interaction)

    if code:
        try:
            await set_guild_region(interaction.guild.id, code.upper())
            await interaction.response.send_message(
                f"✅ Region set to **{code.upper()}**", ephemeral=True
            )
        except ValueError as ve:
            await interaction.response.send_message(f"❌ {ve}", ephemeral=True)
    else:
        settings = await get_guild_settings(interaction.guild.id)
        await interaction.response.send_message(
            f"🌍 Current region: **{settings['region']}**", ephemeral=True
        )


@TREE.command(
    name="freelist_channel", description="Set the announcement channel (owner/admin only)"
)
@app_commands.describe(channel="Channel to send freebie announcements to")
async def freelist_channel(
    interaction: discord.Interaction, channel: discord.TextChannel
):
    if interaction.guild is None:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return
    await ensure_owner_admin(interaction)

    # Basic permission sanity check
    me = interaction.guild.me
    perms = channel.permissions_for(me) if me else None
    if not perms or not perms.send_messages:
        await interaction.response.send_message(
            f"❌ I can’t send messages in {channel.mention}. Please grant permission and try again.",
            ephemeral=True,
        )
        return

    await set_guild_channel(interaction.guild.id, channel.id)
    await interaction.response.send_message(
        f"✅ Announcements will go to {channel.mention}", ephemeral=True
    )


@TREE.command(name="freelist_poll_now", description="Force a fetch + announce for this server (owner/admin only)")
async def freelist_poll_now(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return
    await ensure_owner_admin(interaction)
    await interaction.response.defer(ephemeral=True)
    summary = await poll_once_for_guild(interaction.guild)
    if "error" in summary:
        await interaction.followup.send(f"❌ {summary['error']}", ephemeral=True)
        return
    await interaction.followup.send(
        (
            f"✅ Polled region {summary['region']}.\n"
            f"Epic: found {summary['found_epic']} (announced {summary['announced_epic']}).\n"
            f"Steam: found {summary['found_steam']} (announced {summary['announced_steam']})."
        ),
        ephemeral=True,
    )


@TREE.command(name="freelist_debug", description="Show current fetch diagnostics (owner/admin only)")
async def freelist_debug(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return
    await ensure_owner_admin(interaction)

    settings = await get_guild_settings(interaction.guild.id)
    region = settings.get("region", "US")
    await interaction.response.defer(ephemeral=True)

    async with aiohttp.ClientSession(headers={"User-Agent": "freewatch/1.0"}) as session:
        # Raw feed sizes for quick sanity
        egs_url = (
            "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?"
            f"locale=en-US&country={region}&allowCountries={region}"
        )
        raw = await try_fetch_json(session, egs_url)
        if isinstance(raw, dict) and "data" in raw:
            elems = (
                (raw.get("data", {}) or {})
                .get("Catalog", {})
                .get("searchStore", {})
                .get("elements", [])
            )
            raw_count = len(elems)
        else:
            raw_count = 0

        epic = await get_epic_free_promos(session, region)
        steam = await get_steam_free_promos(session, region)

    # Build ephemeral summary with a few sample titles
    epic_titles = ", ".join([d["title"] for d in epic[:5]]) or "(none)"
    steam_titles = ", ".join([d["title"] for d in steam[:5]]) or "(none)"
    msg = (
        f"Region: {region}\n"
        f"Epic feed elements: {raw_count} | matched freebies: {len(epic)}\n"
        f"Epic sample: {epic_titles}\n"
        f"Steam matched freebies: {len(steam)}\n"
        f"Steam sample: {steam_titles}"
    )
    await interaction.followup.send(msg, ephemeral=True)


# ----------------- Error handling -----------------


@BOT.event
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    try:
        msg = str(error) or "Something went wrong."
        await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
    except discord.InteractionResponded:
        await interaction.followup.send(f"❌ {error}", ephemeral=True)


# ----------------- Lifecycle -----------------


@BOT.event
async def on_ready():
    try:
        synced = await TREE.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print("Slash sync error:", e)
    if not poll_deals.is_running():
        poll_deals.start()
    print(f"Logged in as {BOT.user} (id: {BOT.user.id})")


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("Set DISCORD_TOKEN in your environment.")
    asyncio.run(init_db())
    BOT.run(DISCORD_TOKEN)
