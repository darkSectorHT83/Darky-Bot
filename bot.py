import discord
from discord.ext import commands
import os
import json
from aiohttp import web
import asyncio

# Token közvetlen környezeti változóból (Render beállítás)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

# Bot példány
bot = commands.Bot(command_prefix='!', intents=intents)

# Fájlnevek
ALLOWED_GUILDS_FILE = "Reaction.ID.txt"
REACTION_ROLES_FILE = "reaction_roles.json"

# Engedélyezett szerverek betöltése
def load_allowed_guilds():
    if not os.path.exists(ALLOWED_GUILDS_FILE):
        return set()
    with open(ALLOWED_GUILDS_FILE, "r", encoding="utf-8") as f:
        return set(int(line.strip()) for line in f if line.strip().isdigit())

allowed_guilds = load_allowed_guilds()

# Reaction roles betöltése
if os.path.exists(REACTION_ROLES_FILE):
    with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
        try:
            reaction_roles = json.load(f)
            reaction_roles = {
                int(gid): {int(mid): em for mid, em in msgs.items()}
                for gid, msgs in reaction_roles.items()
            }
        except json.JSONDecodeError:
            reaction_roles = {}
else:
    reaction_roles = {}

# Reaction roles mentése
def save_reaction_roles():
    with open(REACTION_ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump({
            str(gid): {str(mid): em for mid, em in msgs.items()}
            for gid, msgs in reaction_roles.items()
        }, f, ensure_ascii=False, indent=4)

# Engedélyezés parancsokhoz
@bot.check
async def guild_permission_check(ctx):
    return ctx.guild and ctx.guild.id in allowed_guilds

# Bejelentkezés
@bot.event
async def on_ready():
    print(f"✅ Bejelentkezve: {bot.user.name}")

# Reakció hozzáadása parancs
@bot.command()
@commands.has_permissions(administrator=True)
async def addreaction(ctx, message_id: int, emoji: str, *, role_name: str):
    guild_id = ctx.guild.id
    channel = ctx.channel

    if guild_id not in reaction_roles:
        reaction_roles[guild_id] = {}
    if message_id not in reaction_roles[guild_id]:
        reaction_roles[guild_id][message_id] = {}
    reaction_roles[guild_id][message_id][emoji] = role_name
    save_reaction_roles()

    try:
        message = await channel.fetch_message(message_id)
        await message.add_reaction(emoji)
    except Exception as e:
        await ctx.send(f"Hozzáadva, de nem sikerült reagálni: {e}")
    else:
        await ctx.send(f"🔧 `{emoji}` → `{role_name}` (üzenet ID: `{message_id}`)")

# Reakció eltávolítása
@bot.command()
@commands.has_permissions(administrator=True)
async def removereaction(ctx, message_id: int, emoji: str):
    guild_id = ctx.guild.id
    if (
        guild_id in reaction_roles and
        message_id in reaction_roles[guild_id] and
        emoji in reaction_roles[guild_id][message_id]
    ):
        del reaction_roles[guild_id][message_id][emoji]
        if not reaction_roles[guild_id][message_id]:
            del reaction_roles[guild_id][message_id]
        if not reaction_roles[guild_id]:
            del reaction_roles[guild_id]
        save_reaction_roles()
        await ctx.send(f"❌ `{emoji}` eltávolítva (üzenet: `{message_id}`)")
    else:
        await ctx.send("⚠️ Nem található az emoji vagy üzenet.")

# Lista parancs
@bot.command()
@commands.has_permissions(administrator=True)
async def listreactions(ctx):
    guild_id = ctx.guild.id
    if guild_id not in reaction_roles or not reaction_roles[guild_id]:
        await ctx.send("ℹ️ Nincs beállított reakció ebben a szerverben.")
        return

    msg = ""
    for msg_id, emoji_map in reaction_roles[guild_id].items():
        msg += f"📩 Üzenet ID: `{msg_id}`\n"
        for emoji, role in emoji_map.items():
            msg += f"   {emoji} → `{role}`\n"
    await ctx.send(msg)

# Reakció hozzáadás esemény
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    if payload.guild_id not in allowed_guilds:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    emoji = str(payload.emoji)
    roles = reaction_roles.get(payload.guild_id, {}).get(payload.message_id)
    role_name = roles.get(emoji) if roles else None

    if role_name:
        role = discord.utils.get(guild.roles, name=role_name)
        member = guild.get_member(payload.user_id)
        if role and member:
            await member.add_roles(role)
            print(f"✅ {member} kapta: {role.name}")

# Reakció eltávolítás esemény
@bot.event
async def on_raw_reaction_remove(payload):
    if payload.guild_id not in allowed_guilds:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    emoji = str(payload.emoji)
    roles = reaction_roles.get(payload.guild_id, {}).get(payload.message_id)
    role_name = roles.get(emoji) if roles else None

    if role_name:
        role = discord.utils.get(guild.roles, name=role_name)
        member = guild.get_member(payload.user_id)
        if role and member:
            await member.remove_roles(role)
            print(f"❌ {member} elvesztette: {role.name}")

# Webszerver válasz
async def handle(request):
    return web.Response(text="✅ DarkyBot él!", content_type='text/html')

# JSON kilistázása (raw formátum)
async def get_json(request):
    if os.path.exists(REACTION_ROLES_FILE):
        with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
            return web.Response(text=f.read(), content_type="application/json")
    else:
        return web.Response(text="{}", content_type="application/json")

# Webszerver indítása
app = web.Application()
app.router.add_get("/", handle)
app.router.add_get("/reaction_roles.json", get_json)

async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# 🆕 dbhelp parancs (súgó)
@bot.command()
async def dbhelp(ctx):
    try:
        with open("help.txt", "r", encoding="utf-8") as f:
            help_text = f.read()
        await ctx.send(f"📘 **Súgó:**\n```{help_text}```")
    except Exception as e:
        await ctx.send(f"⚠️ Nem sikerült megjeleníteni a súgót: {e}")

# Fő futtatás
async def main():
    await start_webserver()
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
