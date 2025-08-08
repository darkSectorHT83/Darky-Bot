import discord
from discord.ext import commands
from aiohttp import web
import json
import os

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# === SEGÉDFÜGGVÉNYEK ===

def is_server_allowed(guild_id):
    if os.path.exists("all_server_allow.txt"):
        with open("all_server_allow.txt", "r") as f:
            value = f.read().strip()
            if value == "1":
                return True

    if os.path.exists("Reaction.ID.txt"):
        with open("Reaction.ID.txt", "r") as f:
            allowed_ids = [line.strip() for line in f if line.strip().isdigit()]
        return str(guild_id) in allowed_ids

    return False

def is_user_allowed(ctx):
    if ctx.author.guild_permissions.administrator:
        return True

    if os.path.exists("commands.allow.txt"):
        with open("commands.allow.txt", "r") as f:
            value = f.read().strip()
            if value == "0":
                return ctx.author.guild_permissions.administrator

    if os.path.exists("commands_rank.txt"):
        with open("commands_rank.txt", "r") as f:
            ranks = [line.strip() for line in f if line.strip()]
        if not ranks:
            return ctx.author.guild_permissions.administrator
        user_roles = [role.name for role in ctx.author.roles]
        return any(role in user_roles for role in ranks)

    return False

def load_reactions():
    if not os.path.exists("reaction_roles.json"):
        return {}
    with open("reaction_roles.json", "r", encoding="utf-8") as f:
        return json.load(f)

def save_reactions(data):
    with open("reaction_roles.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# === PARANCSOK ===

@bot.command()
async def dbactivate(ctx):
    await ctx.send("✅ A bot aktív és fut!")

@bot.command()
async def addreaction(ctx, message_id: int, emoji: str, role: discord.Role):
    if not is_server_allowed(ctx.guild.id) or not is_user_allowed(ctx):
        return

    data = load_reactions()
    msg_id = str(message_id)
    if msg_id not in data:
        data[msg_id] = {}
    data[msg_id][emoji] = role.id
    save_reactions(data)
    await ctx.send(f"✅ Hozzáadva: {emoji} → {role.name}")

@bot.command()
async def removereaction(ctx, message_id: int, emoji: str):
    if not is_server_allowed(ctx.guild.id) or not is_user_allowed(ctx):
        return

    data = load_reactions()
    msg_id = str(message_id)
    if msg_id in data and emoji in data[msg_id]:
        del data[msg_id][emoji]
        if not data[msg_id]:
            del data[msg_id]
        save_reactions(data)
        await ctx.send(f"❌ Eltávolítva: {emoji}")
    else:
        await ctx.send("❗ Nem található az adott emoji a megadott üzenetnél.")

@bot.command()
async def listreactions(ctx):
    if not is_server_allowed(ctx.guild.id) or not is_user_allowed(ctx):
        return

    data = load_reactions()
    if not data:
        await ctx.send("📭 Nincsenek tárolt reakciók.")
        return

    msg = "**📋 Reakció lista:**
"
    for msg_id, emojis in data.items():
        msg += f"
Üzenet ID: `{msg_id}`
"
        for emoji, role_id in emojis.items():
            role = ctx.guild.get_role(role_id)
            role_name = role.name if role else "Ismeretlen szerepkör"
            msg += f"  {emoji} → {role_name}
"
    await ctx.send(msg)

@bot.command()
async def dbhelp(ctx):
    help_text = (
        "```
"
        "Parancsok:
"
        "!dbactivate – Ellenőrzi, hogy fut-e a bot
"
        "!addreaction <üzenet_id> <emoji> <@szerepkör> – Reakció hozzárendelés
"
        "!removereaction <üzenet_id> <emoji> – Reakció törlése
"
        "!listreactions – Összes hozzárendelt reakció megtekintése
"
        "!dbhelp – Ez a súgó
"
        "```"
    )
    await ctx.send(help_text)

# === REAKCIÓ FIGYELÉS ===

@bot.event
async def on_raw_reaction_add(payload):
    if payload.member.bot:
        return

    if not is_server_allowed(payload.guild_id):
        return

    data = load_reactions()
    msg_id = str(payload.message_id)
    emoji = str(payload.emoji)
    if msg_id in data and emoji in data[msg_id]:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(data[msg_id][emoji])
        if role:
            member = guild.get_member(payload.user_id)
            if member:
                await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    data = load_reactions()
    msg_id = str(payload.message_id)
    emoji = str(payload.emoji)
    if msg_id in data and emoji in data[msg_id]:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(data[msg_id][emoji])
        if role:
            member = guild.get_member(payload.user_id)
            if member:
                await member.remove_roles(role)

# === WEB SERVER RENDERHEZ ===

app = web.Application()

async def handle_root(request):
    return web.Response(text="Darky Bot v1.2.6 fut.")

async def handle_json(request):
    data = load_reactions()
    return web.json_response(data)

app.router.add_get("/", handle_root)
app.router.add_get("/reaction_roles.json", handle_json)

async def run_bot():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=8080)
    await site.start()
    await bot.start(os.environ["DISCORD_TOKEN"])

import asyncio
asyncio.run(run_bot())
