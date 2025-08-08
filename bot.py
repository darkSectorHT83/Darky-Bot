import discord
from discord.ext import commands
import json
import os
from aiohttp import web

intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True
intents.guild_reactions = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

REACTION_FILE = 'reaction_roles.json'
ID_FILE = 'Reaction.ID.txt'
ALL_SERVER_ALLOW_FILE = 'all_server_allow.txt'
COMMANDS_ALLOW_FILE = 'commands.allow.txt'
COMMANDS_RANK_FILE = 'commands_rank.txt'

def load_reactions():
    if os.path.exists(REACTION_FILE):
        with open(REACTION_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_reactions(data):
    with open(REACTION_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def load_allowed_guilds():
    if os.path.exists(ID_FILE):
        with open(ID_FILE, 'r') as f:
            return [int(line.strip()) for line in f if line.strip().isdigit()]
    return []

def is_all_server_allowed():
    if os.path.exists(ALL_SERVER_ALLOW_FILE):
        with open(ALL_SERVER_ALLOW_FILE, 'r') as f:
            return f.read().strip() == '1'
    return False

def is_command_allowed(member):
    if not os.path.exists(COMMANDS_ALLOW_FILE):
        return member.guild_permissions.administrator
    with open(COMMANDS_ALLOW_FILE, 'r') as f:
        if f.read().strip() == '0':
            return member.guild_permissions.administrator

    if os.path.exists(COMMANDS_RANK_FILE):
        with open(COMMANDS_RANK_FILE, 'r') as f:
            allowed_roles = [line.strip() for line in f if line.strip()]
            for role in member.roles:
                if role.name in allowed_roles:
                    return True
    return member.guild_permissions.administrator

@bot.event
async def on_ready():
    print(f'Bejelentkezve: {bot.user.name}')

@bot.command()
async def dbactivate(ctx):
    reactions = load_reactions()
    for message_id, data in reactions.items():
        channel = bot.get_channel(int(data['channel_id']))
        if channel:
            try:
                message = await channel.fetch_message(int(message_id))
                for emoji in data['roles']:
                    await message.add_reaction(emoji)
            except:
                pass
    await ctx.send("✅ **Reakciók aktiválva!**")

@bot.command()
async def addreaction(ctx, message_id: int, emoji: str, role: discord.Role):
    if not is_command_allowed(ctx.author):
        return

    if not is_all_server_allowed() and ctx.guild.id not in load_allowed_guilds():
        return await ctx.send("⛔ Ez a szerver nincs engedélyezve!")

    reactions = load_reactions()
    channel_id = ctx.channel.id

    if str(message_id) not in reactions:
        reactions[str(message_id)] = {'channel_id': str(channel_id), 'roles': {}}
    reactions[str(message_id)]['roles'][emoji] = role.id
    save_reactions(reactions)

    message = await ctx.channel.fetch_message(message_id)
    await message.add_reaction(emoji)
    await ctx.send(f"✅ Hozzáadva: {emoji} → {role.mention}")

@bot.command()
async def removereaction(ctx, message_id: int, emoji: str):
    if not is_command_allowed(ctx.author):
        return

    if not is_all_server_allowed() and ctx.guild.id not in load_allowed_guilds():
        return await ctx.send("⛔ Ez a szerver nincs engedélyezve!")

    reactions = load_reactions()
    if str(message_id) in reactions and emoji in reactions[str(message_id)]['roles']:
        del reactions[str(message_id)]['roles'][emoji]
        if not reactions[str(message_id)]['roles']:
            del reactions[str(message_id)]
        save_reactions(reactions)
        await ctx.send(f"🗑️ Eltávolítva: {emoji}")
    else:
        await ctx.send("⚠️ Nincs ilyen reakció bejegyezve.")

@bot.command()
async def listreactions(ctx):
    if not is_command_allowed(ctx.author):
        return

    reactions = load_reactions()
    if not reactions:
        return await ctx.send("ℹ️ Nincs elérhető reakció.")

    msg = "📋 **Reakció lista:**
"
    for message_id, data in reactions.items():
        for emoji, role_id in data['roles'].items():
            msg += f"**{message_id}** → {emoji} → `<@&{role_id}>`
"
    await ctx.send(msg)

@bot.command()
async def dbhelp(ctx):
    help_text = (
        "**Darky Bot Segítség**

"
        "`!addreaction <üzenet_id> <emoji> <@szerep>` - Reakció hozzáadása
"
        "`!removereaction <üzenet_id> <emoji>` - Reakció eltávolítása
"
        "`!listreactions` - Összes bejegyzés listázása
"
        "`!dbactivate` - Reakciók újraaktiválása
"
        "`!dbhelp` - Segítség megjelenítése"
    )
    await ctx.send(f"```{help_text}```")

@bot.event
async def on_raw_reaction_add(payload):
    if payload.member is None or payload.member.bot:
        return

    if not is_all_server_allowed() and payload.guild_id not in load_allowed_guilds():
        return

    reactions = load_reactions()
    data = reactions.get(str(payload.message_id))
    if data and payload.emoji.name in data['roles']:
        guild = bot.get_guild(payload.guild_id)
        if guild:
            role = guild.get_role(data['roles'][payload.emoji.name])
            if role:
                member = guild.get_member(payload.user_id)
                if member:
                    await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    if not is_all_server_allowed() and payload.guild_id not in load_allowed_guilds():
        return

    reactions = load_reactions()
    data = reactions.get(str(payload.message_id))
    if data and payload.emoji.name in data['roles']:
        guild = bot.get_guild(payload.guild_id)
        if guild:
            role = guild.get_role(data['roles'][payload.emoji.name])
            if role:
                member = guild.get_member(payload.user_id)
                if member:
                    await member.remove_roles(role)

# Webserver a Render támogatásához
async def handle(request):
    return web.Response(text="Darky Bot v1.2.3 fut!")

async def json_handler(request):
    reactions = load_reactions()
    return web.json_response(reactions)

app = web.Application()
app.router.add_get('/', handle)
app.router.add_get('/json', json_handler)

import asyncio
async def start_web():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()

@bot.event
async def on_ready():
    print(f'Bot elindult: {bot.user}')
    await start_web()

# Token betöltése környezeti változóból
import os
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ Hiányzó DISCORD_BOT_TOKEN környezeti változó.")
