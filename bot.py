import discord
from discord.ext import commands, tasks
import json
import os
import aiohttp
import asyncio

# ----- Fájlnevek -----
REACTION_FILE = "Reaction.ID.txt"
TWITCH_FILE = "twitch.json"

# ----- Discord Bot Token & Twitch API Kulcsok (Render-en állítsd be) -----
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

# ----- Intents & Bot Inicializálása -----
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ----- Twitch adatbázis betöltése -----
if os.path.exists(TWITCH_FILE):
    with open(TWITCH_FILE, "r") as f:
        twitch_data = json.load(f)
else:
    twitch_data = {}

# ----- Jogosult szerverek betöltése -----
def load_allowed_servers():
    if not os.path.exists(REACTION_FILE):
        return []
    with open(REACTION_FILE, "r") as f:
        return [line.strip() for line in f if line.strip().isdigit()]

allowed_servers = load_allowed_servers()

# ----- Helper: Jogosultság ellenőrzése -----
def is_allowed(ctx):
    return str(ctx.guild.id) in allowed_servers

# ----- Helper: Twitch token lekérés -----
async def get_twitch_token():
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, params=params) as resp:
            data = await resp.json()
            return data.get("access_token")

# ----- Helper: Ellenőrzi hogy live-e -----
async def is_stream_live(user_login, token):
    url = f"https://api.twitch.tv/helix/streams?user_login={user_login}"
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            data = await resp.json()
            return data["data"][0] if data["data"] else None

# ----- Parancs: Twitch hozzáadása -----
@bot.command()
async def addtwitch(ctx, twitch_name):
    if not is_allowed(ctx):
        await ctx.send("❌ Ez a szerver nincs engedélyezve a bot használatára.")
        return

    server_id = str(ctx.guild.id)
    channel_id = str(ctx.channel.id)

    if twitch_name not in twitch_data:
        twitch_data[twitch_name] = []

    if channel_id not in twitch_data[twitch_name]:
        twitch_data[twitch_name].append(channel_id)

        with open(TWITCH_FILE, "w") as f:
            json.dump(twitch_data, f, indent=2)

        await ctx.send(f"✅ `{twitch_name}` hozzáadva az értesítésekhez ebbe a szobába.")
    else:
        await ctx.send(f"ℹ️ `{twitch_name}` már figyelve van ebben a szobában.")

# ----- Parancs: Twitch törlése -----
@bot.command()
async def removetwitch(ctx, twitch_name):
    if not is_allowed(ctx):
        await ctx.send("❌ Ez a szerver nincs engedélyezve a bot használatára.")
        return

    channel_id = str(ctx.channel.id)

    if twitch_name in twitch_data and channel_id in twitch_data[twitch_name]:
        twitch_data[twitch_name].remove(channel_id)
        if not twitch_data[twitch_name]:
            del twitch_data[twitch_name]  # töröld, ha már sehol nem figyelik

        with open(TWITCH_FILE, "w") as f:
            json.dump(twitch_data, f, indent=2)

        await ctx.send(f"✅ `{twitch_name}` eltávolítva ebből a szobából.")
    else:
        await ctx.send(f"⚠️ `{twitch_name}` nincs figyelve ebben a szobában.")

# ----- Parancs: Twitch listázása -----
@bot.command()
async def listtwitch(ctx):
    if not is_allowed(ctx):
        await ctx.send("❌ Ez a szerver nincs engedélyezve a bot használatára.")
        return

    channel_id = str(ctx.channel.id)
    tracked = [name for name, chans in twitch_data.items() if channel_id in chans]

    if tracked:
        msg = "📺 Figyelt Twitch csatornák:\n" + "\n".join(f"- {name}" for name in tracked)
    else:
        msg = "ℹ️ Ebben a szobában nincs figyelt Twitch csatorna."

    await ctx.send(msg)

# ----- Stream figyelő háttérfolyamat -----
live_cache = set()

@tasks.loop(seconds=60)
async def check_twitch_streams():
    token = await get_twitch_token()
    for twitch_name, channels in twitch_data.items():
        stream = await is_stream_live(twitch_name, token)
        if stream and twitch_name not in live_cache:
            live_cache.add(twitch_name)
            title = stream['title']
            url = f"https://twitch.tv/{twitch_name}"
            msg = f"🔴 **{twitch_name} élőben van!**\n🎮 **{title}**\n👉 {url}"
            for channel_id in channels:
                channel = bot.get_channel(int(channel_id))
                if channel:
                    await channel.send(msg)
        elif not stream and twitch_name in live_cache:
            live_cache.remove(twitch_name)

# ----- Bot események -----
@bot.event
async def on_ready():
    print(f"✅ Bejelentkezve: {bot.user}")
    check_twitch_streams.start()

# ----- Indítás -----
bot.run(DISCORD_TOKEN)
