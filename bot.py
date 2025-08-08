import discord
from discord.ext import commands
import json
import os
from aiohttp import web

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

REACTION_ROLE_FILE = 'reaction_roles.json'
ALLOWED_GUILDS_FILE = 'Reaction.ID.txt'
ALL_SERVER_ALLOW_FILE = 'all_server_allow.txt'
COMMANDS_ALLOW_FILE = 'commands.allow.txt'
COMMANDS_RANK_FILE = 'commands_rank.txt'

def load_reaction_roles():
    if not os.path.exists(REACTION_ROLE_FILE):
        with open(REACTION_ROLE_FILE, 'w') as f:
            json.dump({}, f)
    with open(REACTION_ROLE_FILE, 'r') as f:
        return json.load(f)

def save_reaction_roles(data):
    with open(REACTION_ROLE_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def load_allowed_guilds():
    if not os.path.exists(ALLOWED_GUILDS_FILE):
        return []
    with open(ALLOWED_GUILDS_FILE, 'r') as f:
        return [int(line.strip()) for line in f if line.strip().isdigit()]

def is_all_server_allowed():
    if not os.path.exists(ALL_SERVER_ALLOW_FILE):
        return False
    with open(ALL_SERVER_ALLOW_FILE, 'r') as f:
        return f.read().strip() == '1'

def is_command_allowed_for_user(ctx):
    if not os.path.exists(COMMANDS_ALLOW_FILE):
        return ctx.author.guild_permissions.administrator
    with open(COMMANDS_ALLOW_FILE, 'r') as f:
        mode = f.read().strip()
    if mode == '0':
        return ctx.author.guild_permissions.administrator
    elif mode == '1':
        if not os.path.exists(COMMANDS_RANK_FILE):
            return False
        with open(COMMANDS_RANK_FILE, 'r') as f:
            allowed_roles = [line.strip() for line in f if line.strip()]
        user_roles = [role.name for role in ctx.author.roles]
        return any(role in allowed_roles for role in user_roles) or ctx.author.guild_permissions.administrator
    return False

@bot.check
async def globally_check(ctx):
    if ctx.command.name == 'dbactivate':
        return True
    if not is_all_server_allowed() and ctx.guild.id not in load_allowed_guilds():
        await ctx.send("❌ Ez a szerver nincs engedélyezve a bot használatához.")
        return False
    if not is_command_allowed_for_user(ctx):
        await ctx.send("⛔ Nincs jogosultságod ehhez a parancshoz.")
        return False
    return True

@bot.event
async def on_ready():
    print(f'✅ Bejelentkezve mint {bot.user}')

@bot.event
async def on_raw_reaction_add(payload):
    if not is_all_server_allowed() and payload.guild_id not in load_allowed_guilds():
        return
    data = load_reaction_roles()
    guild_data = data.get(str(payload.guild_id), {})
    message_data = guild_data.get(str(payload.message_id), {})
    emoji = str(payload.emoji)
    role_id = message_data.get(emoji)
    if role_id:
        guild = bot.get_guild(payload.guild_id)
        if guild:
            role = guild.get_role(role_id)
            member = guild.get_member(payload.user_id)
            if role and member:
                await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    if not is_all_server_allowed() and payload.guild_id not in load_allowed_guilds():
        return
    data = load_reaction_roles()
    guild_data = data.get(str(payload.guild_id), {})
    message_data = guild_data.get(str(payload.message_id), {})
    emoji = str(payload.emoji)
    role_id = message_data.get(emoji)
    if role_id:
        guild = bot.get_guild(payload.guild_id)
        if guild:
            role = guild.get_role(role_id)
            member = guild.get_member(payload.user_id)
            if role and member:
                await member.remove_roles(role)

@bot.command()
async def addreaction(ctx, message_id: int, emoji: str, role: discord.Role):
    data = load_reaction_roles()
    guild_data = data.setdefault(str(ctx.guild.id), {})
    message_data = guild_data.setdefault(str(message_id), {})
    message_data[emoji] = role.id
    save_reaction_roles(data)
    await ctx.send(f"✅ Hozzáadva: {emoji} -> {role.name}")

@bot.command()
async def removereaction(ctx, message_id: int, emoji: str):
    data = load_reaction_roles()
    guild_data = data.get(str(ctx.guild.id), {})
    message_data = guild_data.get(str(message_id), {})
    if emoji in message_data:
        del message_data[emoji]
        if not message_data:
            guild_data.pop(str(message_id), None)
        save_reaction_roles(data)
        await ctx.send(f"🗑️ Eltávolítva: {emoji}")
    else:
        await ctx.send("⚠️ Nem található ilyen emoji ehhez az üzenethez.")

@bot.command()
async def listreactions(ctx):
    data = load_reaction_roles()
    guild_data = data.get(str(ctx.guild.id), {})
    if not guild_data:
        await ctx.send("📭 Nincsenek elmentett reakciók.")
        return
    msg = ""
    for msg_id, emojis in guild_data.items():
        msg += f"
📨 Üzenet ID: {msg_id}"
        for emoji, role_id in emojis.items():
            role = ctx.guild.get_role(role_id)
            if role:
                msg += f"
   {emoji} -> {role.name}"
    await ctx.send(f"```
{msg}
```")

@bot.command()
async def dbactivate(ctx):
    if ctx.guild.id not in load_allowed_guilds():
        with open(ALLOWED_GUILDS_FILE, 'a') as f:
            f.write(f"{ctx.guild.id}
")
        await ctx.send("✅ Szerver hozzáadva az engedélyezett listához.")
    else:
        await ctx.send("ℹ️ Ez a szerver már engedélyezve van.")

@bot.command()
async def dbhelp(ctx):
    help_msg = (
        "**📘 Darky Bot Súgó**

"
        "`!addreaction <üzenet_id> <emoji> <@szerep>` - Reakció hozzárendelése
"
        "`!removereaction <üzenet_id> <emoji>` - Reakció törlése
"
        "`!listreactions` - Összes szerepkör kilistázása
"
        "`!dbactivate` - Szerver engedélyezése a bothoz
"
        "`!dbhelp` - Ez a súgó üzenet"
    )
    await ctx.send(f"```
{help_msg}
```")

# Webserver a Render támogatásához
async def handle_root(request):
    return web.Response(text="Darky Bot fut! 🚀")

async def handle_json(request):
    data = load_reaction_roles()
    return web.json_response(data)

app = web.Application()
app.router.add_get('/', handle_root)
app.router.add_get('/json', handle_json)

if __name__ == "__main__":
    import asyncio
    import threading

    def start_web_app():
        web.run_app(app, port=3000)

    threading.Thread(target=start_web_app).start()
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    asyncio.run(bot.start(TOKEN))
