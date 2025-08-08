import os
import discord
from discord.ext import commands, tasks
from aiohttp import web
import aiohttp, json, asyncio

# Környezeti változók
TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_ACCESS_TOKEN = os.getenv("TWITCH_ACCESS_TOKEN")
HEADERS = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}"}

# Fájlnevek
REACTION_FILE = "reaction_roles.json"
SERVER_FILE = "Reaction.ID.txt"
ALLOW_FILE = "all_server_allow.txt"
COMMANDS_ALLOW = "commands.allow.txt"
COMMANDS_RANK = "commands_rank.txt"
TWITCH_FILE = "twitch.json"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.reactions = True
bot = commands.Bot(command_prefix="!", intents=intents)

# A webserver
app = web.Application()
@app.get("/")
async def root(req): return web.Response(text="Darky Bot v1.3.2 működik!")
@app.get("/reactions")
async def reactions_data(req):
    data = json.load(open(REACTION_FILE, "r", encoding="utf-8")) if os.path.exists(REACTION_FILE) else {}
    return web.json_response(data)

# Segédfüggvények: server & user jogosultság
def is_server_allowed(guild_id):
    if os.path.exists(ALLOW_FILE) and open(ALLOW_FILE).read().strip() == "1":
        return True
    return os.path.exists(SERVER_FILE) and str(guild_id) in open(SERVER_FILE).read().splitlines()

def is_user_authorized(ctx):
    if ctx.author.guild_permissions.administrator:
        return True
    if os.path.exists(COMMANDS_ALLOW) and open(COMMANDS_ALLOW).read().strip()=="1":
        if os.path.exists(COMMANDS_RANK):
            ranks = [line.strip() for line in open(COMMANDS_RANK, "r", encoding="utf-8") if line.strip()]
            if not ranks:
                return False
            return any(r.name in ranks for r in ctx.author.roles)
    return False

def load_json(path): return json.load(open(path, "r", encoding="utf-8")) if os.path.exists(path) else {}
def save_json(path, data): json.dump(data, open(path,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

# Twitch checking
live_streams = set()

@tasks.loop(seconds=60)
async def twitch_checker():
    tw_data = load_json(TWITCH_FILE)
    for ch_id, names in tw_data.items():
        for name in names:
            async with aiohttp.ClientSession() as session:
                resp = await session.get(f"https://api.twitch.tv/helix/streams?user_login={name}", headers=HEADERS)
                jd = await resp.json()
                if jd.get("data"):
                    if name not in live_streams:
                        live_streams.add(name)
                        ch = bot.get_channel(int(ch_id))
                        if ch:
                            await ch.send(f"🔴 **{name}** élőben van: https://twitch.tv/{name}")
                else:
                    live_streams.discard(name)

@bot.command()
async def addstreamer(ctx, streamer: str):
    if not is_server_allowed(ctx.guild.id) or not is_user_authorized(ctx):
        return
    tw_data = load_json(TWITCH_FILE)
    tw_data.setdefault(str(ctx.channel.id), [])
    if streamer.lower() not in tw_data[str(ctx.channel.id)]:
        tw_data[str(ctx.channel.id)].append(streamer.lower())
        save_json(TWITCH_FILE, tw_data)
        return await ctx.send(f"✅ **{streamer}** hozzáadva.")
    await ctx.send("⚠ Már hozzá van adva.")

@bot.command()
async def removestreamer(ctx, streamer: str):
    if not is_server_allowed(ctx.guild.id) or not is_user_authorized(ctx):
        return
    tw_data = load_json(TWITCH_FILE)
    ch = str(ctx.channel.id)
    if ch in tw_data and streamer.lower() in tw_data[ch]:
        tw_data[ch].remove(streamer.lower())
        if not tw_data[ch]: del tw_data[ch]
        save_json(TWITCH_FILE, tw_data)
        return await ctx.send(f"❌ **{streamer}** eltávolítva.")
    await ctx.send("❌ Nincs a listában.")

@bot.command()
async def liststreamers(ctx):
    if not is_server_allowed(ctx.guild.id) or not is_user_authorized(ctx):
        return
    tw_data = load_json(TWITCH_FILE).get(str(ctx.channel.id), [])
    if tw_data:
        await ctx.send("📺 Twitch csatornák:\n" + "\n".join(f"- {name}" for name in tw_data))
    else:
        await ctx.send("🔇 Nincsenek streamerek ebben a szobában.")

@bot.event
async def on_ready():
    twitch_checker.start()
    runner = web.AppRunner(app); await runner.setup(); await web.TCPSite(runner, "0.0.0.0", 8080).start()
    print(f"Bot elindult: {bot.user}")

bot.run(TOKEN)
