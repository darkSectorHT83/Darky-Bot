import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import json
from aiohttp import web
import asyncio
from git import Repo

# .env betöltése
load_dotenv()
TOKEN = os.getenv("TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO_URL = "https://github.com/darkSectorHT83/Darky-Bot.git"

# Git push funkció
def git_push(file_path):
    try:
        repo = Repo(os.getcwd())
        repo.git.add(file_path)
        repo.index.commit("🔄 reaction_roles.json automatikus frissítés")
        repo.remote(name="origin").set_url(f"https://{GITHUB_TOKEN}@github.com/darkSectorHT83/Darky-Bot.git")
        repo.git.push("origin", "main")
        print("✅ Sikeres push a GitHub-ra.")
    except Exception as e:
        print(f"⚠️ Git push hiba: {e}")

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Engedélyezett szerverek betöltése
ALLOWED_GUILDS_FILE = "Reaction.ID.txt"
def load_allowed_guilds():
    if not os.path.exists(ALLOWED_GUILDS_FILE):
        return set()
    with open(ALLOWED_GUILDS_FILE, "r", encoding="utf-8") as f:
        return set(int(line.strip()) for line in f if line.strip().isdigit())
allowed_guilds = load_allowed_guilds()

@bot.check
async def guild_permission_check(ctx):
    return ctx.guild and ctx.guild.id in allowed_guilds

# Reakció rang fájl
REACTION_ROLES_FILE = "reaction_roles.json"
if os.path.exists(REACTION_ROLES_FILE):
    with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
        reaction_roles = json.load(f)
        reaction_roles = {
            int(gid): {
                int(mid): roles for mid, roles in msgs.items()
            } for gid, msgs in reaction_roles.items()
        }
else:
    reaction_roles = {}

def save_reaction_roles():
    with open(REACTION_ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump({
            str(gid): {str(mid): data for mid, data in msgs.items()}
            for gid, msgs in reaction_roles.items()
        }, f, ensure_ascii=False, indent=4)
    git_push(REACTION_ROLES_FILE)

# Bot események és parancsok
@bot.event
async def on_ready():
    print(f'✅ Bejelentkezett: {bot.user.name}')

@bot.command()
@commands.has_permissions(administrator=True)
async def addreaction(ctx, message_id: int, emoji: str, *, role_name: str):
    guild_id = ctx.guild.id
    if guild_id not in reaction_roles:
        reaction_roles[guild_id] = {}
    if message_id not in reaction_roles[guild_id]:
        reaction_roles[guild_id][message_id] = {}
    reaction_roles[guild_id][message_id][emoji] = role_name
    save_reaction_roles()

    try:
        message = await ctx.channel.fetch_message(message_id)
        await message.add_reaction(emoji)
    except Exception as e:
        await ctx.send(f'⚠️ Hiba: {e}')
    else:
        await ctx.send(f'🔧 `{emoji}` → `{role_name}` hozzáadva (üzenet: `{message_id}`)')

@bot.command()
@commands.has_permissions(administrator=True)
async def removereaction(ctx, message_id: int, emoji: str):
    gid = ctx.guild.id
    if gid in reaction_roles and message_id in reaction_roles[gid] and emoji in reaction_roles[gid][message_id]:
        del reaction_roles[gid][message_id][emoji]
        if not reaction_roles[gid][message_id]:
            del reaction_roles[gid][message_id]
        if not reaction_roles[gid]:
            del reaction_roles[gid]
        save_reaction_roles()
        await ctx.send(f'❌ `{emoji}` törölve az üzenetből: `{message_id}`')
    else:
        await ctx.send('⚠️ Nincs ilyen párosítás.')

@bot.command()
@commands.has_permissions(administrator=True)
async def listreactions(ctx):
    gid = ctx.guild.id
    if gid not in reaction_roles:
        await ctx.send("ℹ️ Nincs adat.")
        return
    msg = ""
    for mid, data in reaction_roles[gid].items():
        msg += f"\n📩 **Üzenet ID:** `{mid}`\n"
        for emoji, role in data.items():
            msg += f"  {emoji} → `{role}`\n"
    await ctx.send(msg)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id or payload.guild_id not in allowed_guilds:
        return
    guild = bot.get_guild(payload.guild_id)
    role_name = reaction_roles.get(payload.guild_id, {}).get(payload.message_id, {}).get(str(payload.emoji))
    if role_name:
        role = discord.utils.get(guild.roles, name=role_name)
        member = guild.get_member(payload.user_id)
        if role and member:
            await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.guild_id not in allowed_guilds:
        return
    guild = bot.get_guild(payload.guild_id)
    role_name = reaction_roles.get(payload.guild_id, {}).get(payload.message_id, {}).get(str(payload.emoji))
    if role_name:
        role = discord.utils.get(guild.roles, name=role_name)
        member = guild.get_member(payload.user_id)
        if role and member:
            await member.remove_roles(role)

# Uptime/html válasz
async def handle(request):
    return web.Response(text="✅ DarkyBot online!", content_type='text/html')

app = web.Application()
app.router.add_get("/", handle)
async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()

# Main futás
async def main():
    await start_webserver()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
