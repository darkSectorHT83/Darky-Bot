import discord
from discord.ext import commands, tasks
from aiohttp import web
import json, os, asyncio
from dotenv import load_dotenv

# Fájlnevek
REACTION_FILE = "reaction_roles.json"
ID_FILE = "Reaction.ID.txt"
ALLOW_FILE = "all_server_allow.txt"
COMMAND_ALLOW_FILE = "commands.allow.txt"
COMMAND_RANK_FILE = "commands_rank.txt"
TWITCH_FILE = "twitch.json"

# Betöltés környezeti változókból
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_ACCESS_TOKEN = os.getenv("TWITCH_ACCESS_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.reactions = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Webserver aiohttp
app = web.Application()

@app.route("/")
async def index(request):
    return web.Response(text="Darky Bot v1.3.1 működik!", content_type='text/html')

@app.route("/reactions")
async def get_reactions(request):
    with open(REACTION_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return web.json_response(data)

# Segédfüggvények
def is_server_allowed(guild_id):
    if not os.path.exists(ALLOW_FILE) or not os.path.exists(ID_FILE):
        return False
    with open(ALLOW_FILE, "r") as f:
        if f.read().strip() == "1":
            return True
    with open(ID_FILE, "r") as f:
        return str(guild_id) in f.read().splitlines()

def is_user_authorized(ctx):
    if not os.path.exists(COMMAND_ALLOW_FILE):
        return ctx.author.guild_permissions.administrator
    with open(COMMAND_ALLOW_FILE, "r") as f:
        if f.read().strip() == "0":
            return ctx.author.guild_permissions.administrator
    if ctx.author.guild_permissions.administrator:
        return True
    if not os.path.exists(COMMAND_RANK_FILE):
        return False
    with open(COMMAND_RANK_FILE, "r", encoding="utf-8") as f:
        allowed_roles = [r.strip() for r in f if r.strip()]
    if not allowed_roles:
        return False
    return any(role.name in allowed_roles for role in ctx.author.roles)

def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# === REACTION ROLE PARANCSOK ===
@bot.command()
async def addreaction(ctx, message_id: int, emoji: str, role: discord.Role):
    if not is_server_allowed(ctx.guild.id) or not is_user_authorized(ctx):
        return
    data = load_json(REACTION_FILE)
    guild_data = data.setdefault(str(ctx.guild.id), {})
    msg_data = guild_data.setdefault(str(message_id), {})
    msg_data[emoji] = role.id
    save_json(data, REACTION_FILE)
    await ctx.send(f"✅ Reakció hozzáadva: {emoji} → {role.name}")

@bot.command()
async def removereaction(ctx, message_id: int, emoji: str):
    if not is_server_allowed(ctx.guild.id) or not is_user_authorized(ctx):
        return
    data = load_json(REACTION_FILE)
    try:
        del data[str(ctx.guild.id)][str(message_id)][emoji]
        save_json(data, REACTION_FILE)
        await ctx.send(f"❌ Reakció eltávolítva: {emoji}")
    except KeyError:
        await ctx.send("❗ Nem található a megadott reakció.")

@bot.command()
async def listreactions(ctx):
    if not is_server_allowed(ctx.guild.id) or not is_user_authorized(ctx):
        return
    data = load_json(REACTION_FILE).get(str(ctx.guild.id), {})
    if not data:
        await ctx.send("❌ Nincs elérhető reakció.")
        return
    msg = "📋 Reakciók:\n"
    for msg_id, reactions in data.items():
        msg += f"Üzenet {msg_id}:\n"
        for emoji, role_id in reactions.items():
            role = ctx.guild.get_role(role_id)
            msg += f"  {emoji} → {role.name if role else 'ismeretlen szerep'}\n"
    await ctx.send(f"```{msg}```")

@bot.command()
async def dbactivate(ctx):
    if not is_server_allowed(ctx.guild.id):
        return await ctx.send("❌ Ez a szerver nincs engedélyezve a bot használatához.")
    await ctx.send("✅ Darky Bot aktiválva ezen a szerveren!")

@bot.command()
async def dbhelp(ctx):
    help_text = """
📘 **Darky Bot Súgó**

**Reakció parancsok:**
!addreaction [üzenet_id] [emoji] [@szerep]
!removereaction [üzenet_id] [emoji]
!listreactions

**Twitch parancsok:**
!addtwitch [@szoba] [twitch_csatorna_nev]
!removetwitch [@szoba] [twitch_csatorna_nev]
!listtwitch
"""
    await ctx.send(f"```{help_text}```")

# === TWITCH PARANCSOK ===
@bot.command()
async def addtwitch(ctx, channel: discord.TextChannel, twitch_name: str):
    if not is_server_allowed(ctx.guild.id) or not is_user_authorized(ctx):
        return
    data = load_json(TWITCH_FILE)
    ch_id = str(channel.id)
    if ch_id not in data:
        data[ch_id] = []
    if twitch_name not in data[ch_id]:
        data[ch_id].append(twitch_name)
    save_json(data, TWITCH_FILE)
    await ctx.send(f"✅ Twitch csatorna hozzáadva: {twitch_name} → {channel.mention}")

@bot.command()
async def removetwitch(ctx, channel: discord.TextChannel, twitch_name: str):
    if not is_server_allowed(ctx.guild.id) or not is_user_authorized(ctx):
        return
    data = load_json(TWITCH_FILE)
    ch_id = str(channel.id)
    if ch_id in data and twitch_name in data[ch_id]:
        data[ch_id].remove(twitch_name)
        if not data[ch_id]:
            del data[ch_id]
        save_json(data, TWITCH_FILE)
        await ctx.send(f"❌ Twitch csatorna eltávolítva: {twitch_name}")
    else:
        await ctx.send("❗ Nem található ez a Twitch csatorna ebben a szobában.")

@bot.command()
async def listtwitch(ctx):
    if not is_server_allowed(ctx.guild.id) or not is_user_authorized(ctx):
        return
    data = load_json(TWITCH_FILE)
    if not data:
        await ctx.send("❌ Nincs mentett Twitch csatorna.")
        return
    msg = "📺 Twitch csatornák:\n"
    for ch_id, names in data.items():
        msg += f"Szoba <#{ch_id}>: {', '.join(names)}\n"
    await ctx.send(msg)

# === FŐ ===
async def main():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=8080)
    await site.start()
    await bot.start(TOKEN)

asyncio.run(main())
