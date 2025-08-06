import discord
from discord.ext import commands
import os
import json
import asyncio
from aiohttp import web
from datetime import datetime
import base64
import aiohttp

# --- Tokenek környezeti változókból ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")  # Pl. "felhasznalo/repo"
GITHUB_EMAIL = os.getenv("GITHUB_EMAIL")

# --- Discord Intents ---
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- Engedélyezett szerverek ---
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

# --- Reaction Roles fájl ---
REACTION_ROLES_FILE = "reaction_roles.json"

if os.path.exists(REACTION_ROLES_FILE):
    with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
        reaction_roles = json.load(f)
        reaction_roles = {
            int(gid): {int(mid): roles for mid, roles in msgs.items()}
            for gid, msgs in reaction_roles.items()
        }
else:
    reaction_roles = {}

def save_reaction_roles():
    with open(REACTION_ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump({
            str(gid): {str(mid): roles for mid, roles in msgs.items()}
            for gid, msgs in reaction_roles.items()
        }, f, ensure_ascii=False, indent=4)

    asyncio.create_task(commit_to_github())

async def commit_to_github():
    """Mentés GitHubra automatikusan"""
    try:
        with open(REACTION_ROLES_FILE, "rb") as f:
            content = base64.b64encode(f.read()).decode()

        async with aiohttp.ClientSession() as session:
            # Get current file SHA
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{REACTION_ROLES_FILE}"
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json"
            }
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()
                sha = data.get("sha")

            # Prepare commit
            commit_data = {
                "message": f"Auto update: {datetime.utcnow().isoformat()}",
                "content": content,
                "sha": sha,
                "committer": {
                    "name": GITHUB_USERNAME,
                    "email": GITHUB_EMAIL
                }
            }

            async with session.put(url, json=commit_data, headers=headers) as resp:
                if resp.status == 200 or resp.status == 201:
                    print("✅ GitHub frissítve.")
                else:
                    print("⚠️ GitHub commit sikertelen:", resp.status)
    except Exception as e:
        print(f"❌ Hiba a GitHub mentésnél: {e}")

@bot.event
async def on_ready():
    print(f"✅ Bot bejelentkezett: {bot.user.name}")

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
        await ctx.send(f"⚠️ Hozzárendelve, de nem sikerült reagálni: {e}")
    else:
        await ctx.send(f"🔧 `{emoji}` hozzárendelve a `{role_name}` ranghoz.")

@bot.command()
@commands.has_permissions(administrator=True)
async def listreactions(ctx):
    guild_id = ctx.guild.id
    if guild_id not in reaction_roles or not reaction_roles[guild_id]:
        await ctx.send("ℹ️ Nincsenek beállított reakciók.")
        return

    msg = ""
    for msg_id, emoji_map in reaction_roles[guild_id].items():
        msg += f"📩 **Üzenet ID:** `{msg_id}`\n"
        for emoji, role in emoji_map.items():
            msg += f"   {emoji} → `{role}`\n"
    await ctx.send(msg)

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
        await ctx.send(f"❌ Emoji `{emoji}` törölve.")
    else:
        await ctx.send("⚠️ Nincs ilyen emoji vagy üzenet ID.")

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    if payload.guild_id not in allowed_guilds:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    message_id = payload.message_id
    emoji = str(payload.emoji)
    roles = reaction_roles.get(payload.guild_id, {}).get(message_id, {})
    role_name = roles.get(emoji)
    if not role_name:
        return
    role = discord.utils.get(guild.roles, name=role_name)
    member = guild.get_member(payload.user_id)
    if role and member:
        await member.add_roles(role)
        print(f"✅ {member.name} kapta: {role.name}")

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.guild_id not in allowed_guilds:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    message_id = payload.message_id
    emoji = str(payload.emoji)
    roles = reaction_roles.get(payload.guild_id, {}).get(message_id, {})
    role_name = roles.get(emoji)
    if not role_name:
        return
    role = discord.utils.get(guild.roles, name=role_name)
    member = guild.get_member(payload.user_id)
    if role and member:
        await member.remove_roles(role)
