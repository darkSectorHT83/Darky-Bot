# Darky Bot v1.3.0 - Twitch figyeléssel bővítve

import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import json
import os
import datetime

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_ACCESS_TOKEN = os.getenv("TWITCH_ACCESS_TOKEN")
HEADERS = {
    "Client-ID": TWITCH_CLIENT_ID,
    "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}"
}

REACTION_FILE = "reaction_roles.json"
SERVER_FILE = "Reaction.ID.txt"
ALLOW_FILE = "all_server_allow.txt"
COMMANDS_ALLOW = "commands.allow.txt"
COMMANDS_RANK = "commands_rank.txt"
TWITCH_FILE = "twitch.json"

# === Segédfüggvények ===
def load_json(file):
    try:
        with open(file, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_json(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=2)

def check_server_permission(guild_id):
    if os.path.exists(ALLOW_FILE):
        with open(ALLOW_FILE, 'r') as f:
            allow = f.read().strip()
            if allow == "1":
                return True
    if os.path.exists(SERVER_FILE):
        with open(SERVER_FILE, 'r') as f:
            return str(guild_id) in f.read().splitlines()
    return False

def check_command_permission(ctx):
    if ctx.author.guild_permissions.administrator:
        return True
    if os.path.exists(COMMANDS_ALLOW):
        with open(COMMANDS_ALLOW, 'r') as f:
            if f.read().strip() == "1":
                if os.path.exists(COMMANDS_RANK):
                    with open(COMMANDS_RANK, 'r') as rankfile:
                        ranks = [r.strip().lower() for r in rankfile.readlines() if r.strip()]
                        if not ranks:
                            return False
                        user_roles = [role.name.lower() for role in ctx.author.roles]
                        return any(rank in user_roles for rank in ranks)
    return False

# === Twitch stream figyelés ===
stream_online = set()

@tasks.loop(seconds=60)
async def check_twitch_streams():
    twitch_data = load_json(TWITCH_FILE)
    if not twitch_data:
        return
    for channel_id, streamers in twitch_data.items():
        for streamer in streamers:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.twitch.tv/helix/streams?user_login={streamer}", headers=HEADERS) as resp:
                    data = await resp.json()
                    if 'data' in data and data['data']:
                        if streamer not in stream_online:
                            stream_online.add(streamer)
                            channel = bot.get_channel(int(channel_id))
                            if channel:
                                await channel.send(f"🔴 **{streamer}** élőben van: https://twitch.tv/{streamer}")
                    else:
                        stream_online.discard(streamer)

# === Twitch Parancsok ===
@bot.command()
async def addstreamer(ctx, streamer_name):
    if not check_server_permission(ctx.guild.id) or not check_command_permission(ctx):
        return
    twitch_data = load_json(TWITCH_FILE)
    channel_id = str(ctx.channel.id)
    twitch_data.setdefault(channel_id, [])
    if streamer_name.lower() not in twitch_data[channel_id]:
        twitch_data[channel_id].append(streamer_name.lower())
        save_json(TWITCH_FILE, twitch_data)
        await ctx.send(f"✅ A(z) `{streamer_name}` streamer hozzáadva a szobához.")
    else:
        await ctx.send(f"⚠️ Ez a streamer már hozzá van adva.")

@bot.command()
async def removestreamer(ctx, streamer_name):
    if not check_server_permission(ctx.guild.id) or not check_command_permission(ctx):
        return
    twitch_data = load_json(TWITCH_FILE)
    channel_id = str(ctx.channel.id)
    if channel_id in twitch_data and streamer_name.lower() in twitch_data[channel_id]:
        twitch_data[channel_id].remove(streamer_name.lower())
        save_json(TWITCH_FILE, twitch_data)
        await ctx.send(f"🗑️ A(z) `{streamer_name}` streamer eltávolítva.")
    else:
        await ctx.send(f"❌ A streamer nem szerepelt a listában.")

@bot.command()
async def liststreamers(ctx):
    twitch_data = load_json(TWITCH_FILE)
    channel_id = str(ctx.channel.id)
    streamers = twitch_data.get(channel_id, [])
    if streamers:
        await ctx.send("📺 Twitch csatornák:
" + "\n".join(f"- {s}" for s in streamers))
    else:
        await ctx.send("🔇 Ehhez a szobához nincs streamer társítva.")

# === Események, indulás ===
@bot.event
async def on_ready():
    check_twitch_streams.start()
    print(f"Bot elindult: {bot.user}")

# === Futás ===
if __name__ == "__main__":
    import web
    import sys
    import logging
    from aiohttp import web as aiohttp_web

    logging.basicConfig(level=logging.INFO)
    app = aiohttp_web.Application()

    async def handle_root(request):
        return aiohttp_web.Response(text="Darky Bot v1.3.0 Fut")

    async def handle_json(request):
        data = load_json(REACTION_FILE)
        return aiohttp_web.json_response(data)

    app.router.add_get('/', handle_root)
    app.router.add_get('/data', handle_json)

    async def start():
        runner = aiohttp_web.AppRunner(app)
        await runner.setup()
        site = aiohttp_web.TCPSite(runner, '0.0.0.0', 8080)
        await site.start()

    async def main():
        await start()
        await bot.start(os.getenv("DISCORD_BOT_TOKEN"))

    asyncio.run(main())
