import discord
from discord.ext import commands, tasks
import os
import json
import asyncio
import aiohttp

# ───── Beállítások ─────
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

ALLOWED_SERVERS_FILE = "Reaction.ID.txt"
TWITCH_DATA_FILE = "twitch.json"

# ───── Twitch API beállítások ─────
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_TOKEN = None
TWITCH_HEADERS = {}
STREAM_STATUS = {}

# ───── Segédfüggvények ─────

def is_server_allowed(server_id):
    try:
        with open(ALLOWED_SERVERS_FILE, "r") as f:
            allowed_ids = [line.strip() for line in f.readlines()]
            return str(server_id) in allowed_ids
    except FileNotFoundError:
        return False

def load_twitch_data():
    if not os.path.exists(TWITCH_DATA_FILE):
        return {}
    with open(TWITCH_DATA_FILE, "r") as f:
        return json.load(f)

def save_twitch_data(data):
    with open(TWITCH_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

async def get_twitch_app_token():
    global TWITCH_TOKEN, TWITCH_HEADERS
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, params=params) as resp:
            data = await resp.json()
            TWITCH_TOKEN = data["access_token"]
            TWITCH_HEADERS = {
                "Client-ID": TWITCH_CLIENT_ID,
                "Authorization": f"Bearer {TWITCH_TOKEN}"
            }

async def is_stream_live(username):
    url = f"https://api.twitch.tv/helix/streams?user_login={username}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=TWITCH_HEADERS) as resp:
            data = await resp.json()
            return len(data["data"]) > 0

# ───── Parancsok ─────

@bot.event
async def on_ready():
    print(f"A bot bejelentkezett: {bot.user}")
    await get_twitch_app_token()
    check_twitch_streams.start()

@bot.command()
async def listreactions(ctx):
    if not is_server_allowed(ctx.guild.id):
        await ctx.send("❌ Ez a szerver nincs engedélyezve a bot használatára.")
        return

    file_path = f"reactions_{ctx.guild.id}.json"
    if not os.path.exists(file_path):
        await ctx.send("ℹ️ Nincsenek beállított reakciók ebben a szerverben.")
        return

    with open(file_path, "r") as f:
        data = json.load(f)

    if not data:
        await ctx.send("ℹ️ Nincsenek beállított reakciók ebben a szerverben.")
        return

    msg = "**📋 Reakciók listája:**\n"
    for emoji, role_id in data.items():
        role = ctx.guild.get_role(role_id)
        if role:
            msg += f"{emoji} → {role.name}\n"
        else:
            msg += f"{emoji} → *(ismeretlen szerep)*\n"

    await ctx.send(msg)

@bot.command()
async def addtwitch(ctx, twitch_name: str):
    if not is_server_allowed(ctx.guild.id):
        await ctx.send("❌ Ez a szerver nincs engedélyezve a bot használatára.")
        return

    data = load_twitch_data()
    channel_id = str(ctx.channel.id)

    if channel_id not in data:
        data[channel_id] = []

    if twitch_name.lower() in [x.lower() for x in data[channel_id]]:
        await ctx.send(f"⚠️ A(z) **{twitch_name}** már hozzá van adva ehhez a szobához.")
        return

    data[channel_id].append(twitch_name)
    save_twitch_data(data)

    await ctx.send(f"✅ A(z) **{twitch_name}** Twitch csatorna hozzáadva ehhez a szobához.")

# ───── Twitch figyelő ─────

@tasks.loop(seconds=60)
async def check_twitch_streams():
    data = load_twitch_data()
    for channel_id, twitch_names in data.items():
        for twitch_name in twitch_names:
            username = twitch_name.lower()
            was_live = STREAM_STATUS.get(username, False)
            try:
                now_live = await is_stream_live(username)
            except:
                now_live = False

            if now_live and not was_live:
                STREAM_STATUS[username] = True
                channel = bot.get_channel(int(channel_id))
                if channel:
                    embed = discord.Embed(
                        title="🔴 Élő adás kezdődött!",
                        description=f"**{twitch_name}** elkezdett streamelni!",
                        color=discord.Color.purple()
                    )
                    await channel.send(embed=embed)
            elif not now_live and was_live:
                STREAM_STATUS[username] = False

# ───── Futtatás ─────

bot.run(os.getenv("DISCORD_TOKEN"))
