import discord
from discord.ext import commands
import os
import json
from aiohttp import web
import asyncio
import subprocess

# Környezeti változók Renderből
TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_EMAIL = os.getenv("GITHUB_EMAIL")
GITHUB_REPO = os.getenv("GITHUB_REPO")

# Ellenőrzés
if not all([TOKEN, GITHUB_TOKEN, GITHUB_USERNAME, GITHUB_EMAIL, GITHUB_REPO]):
    print("❌ Hiányzik egy vagy több környezeti változó. Ellenőrizd Render-ben.")
    exit(1)

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Reaction roles fájl
REACTION_ROLES_FILE = "reaction_roles.json"

# Betöltés
if os.path.exists(REACTION_ROLES_FILE):
    with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
        try:
            reaction_roles = json.load(f)
        except json.JSONDecodeError:
            reaction_roles = {}
else:
    reaction_roles = {}

# Automatikus mentés GitHub repóba
def save_reaction_roles():
    with open(REACTION_ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump(reaction_roles, f, ensure_ascii=False, indent=4)

    try:
        subprocess.run(["git", "config", "--global", "user.name", GITHUB_USERNAME], check=True)
        subprocess.run(["git", "config", "--global", "user.email", GITHUB_EMAIL], check=True)
        subprocess.run(["git", "add", REACTION_ROLES_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "🔄 reaction_roles.json frissítve"], check=True)
        subprocess.run(["git", "push", f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"], check=True)
        print("✅ JSON mentve és feltöltve GitHub-ra.")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Hiba a Git push során: {e}")

@bot.event
async def on_ready():
    print(f"✅ Bejelentkezve mint: {bot.user.name}")

@bot.command()
@commands.has_permissions(administrator=True)
async def addreaction(ctx, message_id: int, emoji: str, *, role_name: str):
    guild_id = str(ctx.guild.id)
    message_id = str(message_id)

    if guild_id not in reaction_roles:
        reaction_roles[guild_id] = {}

    if message_id not in reaction_roles[guild_id]:
        reaction_roles[guild_id][message_id] = {}

    reaction_roles[guild_id][message_id][emoji] = role_name
    save_reaction_roles()

    try:
        message = await ctx.channel.fetch_message(int(message_id))
        await message.add_reaction(emoji)
    except Exception as e:
        await ctx.send(f"⚠️ Emoji mentve, de nem sikerült hozzárendelni: {e}")
    else:
        await ctx.send(f"✅ Emoji `{emoji}` hozzárendelve ranghoz: `{role_name}`")

@bot.command()
@commands.has_permissions(administrator=True)
async def removereaction(ctx, message_id: int, emoji: str):
    guild_id = str(ctx.guild.id)
    message_id = str(message_id)

    if (guild_id in reaction_roles and
        message_id in reaction_roles[guild_id] and
        emoji in reaction_roles[guild_id][message_id]):
        
        del reaction_roles[guild_id][message_id][emoji]
        
        if not reaction_roles[guild_id][message_id]:
            del reaction_roles[guild_id][message_id]
        if not reaction_roles[guild_id]:
            del reaction_roles[guild_id]
        
        save_reaction_roles()
        await ctx.send(f"❌ Emoji `{emoji}` eltávolítva.")
    else:
        await ctx.send("⚠️ Nem található ilyen emoji vagy üzenet ID.")

@bot.command()
@commands.has_permissions(administrator=True)
async def listreactions(ctx):
    guild_id = str(ctx.guild.id)

    if guild_id not in reaction_roles or not reaction_roles[guild_id]:
        await ctx.send("ℹ️ Nincsenek beállított reakciók.")
        return

    msg = ""
    for msg_id, emoji_map in reaction_roles[guild_id].items():
        msg += f"📩 **Üzenet ID:** `{msg_id}`\n"
        for emoji, role in emoji_map.items():
            msg += f"   {emoji} → `{role}`\n"
    await ctx.send(msg)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    guild_id = str(payload.guild_id)
    message_id = str(payload.message_id)
    emoji = str(payload.emoji)

    if guild_id not in reaction_roles:
        return

    if message_id not in reaction_roles[guild_id]:
        return

    role_name = reaction_roles[guild_id][message_id].get(emoji)
    if not role_name:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    role = discord.utils.get(guild.roles, name=role_name)
    member = guild.get_member(payload.user_id)

    if role and member:
        await member.add_roles(role)
        print(f"✅ {member.name} kapott szerepet: {role.name}")

@bot.event
async def on_raw_reaction_remove(payload):
    guild_id = str(payload.guild_id)
    message_id = str(payload.message_id)
    emoji = str(payload.emoji)

    if guild_id not in reaction_roles:
        return

    if message_id not in reaction_roles[guild_id]:
        return

    role_name = reaction_roles[guild_id][message_id].get(emoji)
    if not role_name:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    role = discord.utils.get(guild.roles, name=role_name)
    member = guild.get_member(payload.user_id)

    if role and member:
        await member.remove_roles(role)
        print(f"❌ {member.name} elvesztette a szerepet: {role.name}")

# Webszerver Render-hez / OBS-hez / UptimeRobot-hoz
async def handle(request):
    return web.Response(text="✅ DarkyBot él!", content_type="text/html")

app = web.Application()
app.router.add_get("/", handle)

async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

async def main():
    await start_webserver()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
