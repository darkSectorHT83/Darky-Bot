import discord
from discord.ext import commands
import os
import json
from aiohttp import web
import asyncio

# Tokenek közvetlenül környezeti változóként Render-ben vannak beállítva
TOKEN = os.environ.get("TOKEN")

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Engedélyezett szerverek fájl
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

# Reakciós fájl
REACTION_ROLES_FILE = "reaction_roles.json"

if os.path.exists(REACTION_ROLES_FILE):
    with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
        reaction_roles = json.load(f)
        reaction_roles = {
            int(guild_id): {
                int(msg_id): msg_roles
                for msg_id, msg_roles in guild_data.items()
            }
            for guild_id, guild_data in reaction_roles.items()
        }
else:
    reaction_roles = {}

def save_reaction_roles():
    with open(REACTION_ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump({
            str(gid): {str(mid): emoji_roles for mid, emoji_roles in msgs.items()}
            for gid, msgs in reaction_roles.items()
        }, f, ensure_ascii=False, indent=4)

@bot.event
async def on_ready():
    print(f'✅ Bot bejelentkezett: {bot.user.name}')

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
        await ctx.send(f'⚠️ Emoji hozzárendelve, de nem sikerült reagálni az üzenetre: {e}')
    else:
        await ctx.send(f'🔧 Emoji `{emoji}` hozzárendelve ranghoz: `{role_name}` (üzenet ID: `{message_id}`)')

@bot.command()
@commands.has_permissions(administrator=True)
async def removereaction(ctx, message_id: int, emoji: str):
    guild_id = ctx.guild.id
    if (guild_id in reaction_roles and
        message_id in reaction_roles[guild_id] and
        emoji in reaction_roles[guild_id][message_id]):

        del reaction_roles[guild_id][message_id][emoji]
        if not reaction_roles[guild_id][message_id]:
            del reaction_roles[guild_id][message_id]
        if not reaction_roles[guild_id]:
            del reaction_roles[guild_id]
        save_reaction_roles()
        await ctx.send(f'❌ Emoji `{emoji}` eltávolítva az üzenetből: `{message_id}`.')
    else:
        await ctx.send('⚠️ Nincs ilyen emoji vagy üzenet ID a rendszerben.')

@bot.command()
@commands.has_permissions(administrator=True)
async def listreactions(ctx):
    guild_id = ctx.guild.id
    if guild_id not in reaction_roles or not reaction_roles[guild_id]:
        await ctx.send("ℹ️ Nincsenek beállított reakciók ebben a szerverben.")
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
    if payload.guild_id not in allowed_guilds:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    message_id = payload.message_id
    emoji = str(payload.emoji)
    roles_for_message = reaction_roles.get(payload.guild_id, {}).get(message_id)
    if not roles_for_message:
        return

    role_name = roles_for_message.get(emoji)
    if not role_name:
        return

    role = discord.utils.get(guild.roles, name=role_name)
    member = guild.get_member(payload.user_id)
    if role and member:
        await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.guild_id not in allowed_guilds:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    message_id = payload.message_id
    emoji = str(payload.emoji)
    roles_for_message = reaction_roles.get(payload.guild_id, {}).get(message_id)
    if not roles_for_message:
        return

    role_name = roles_for_message.get(emoji)
    if not role_name:
        return

    role = discord.utils.get(guild.roles, name=role_name)
    member = guild.get_member(payload.user_id)
    if role and member:
        await member.remove_roles(role)

# ==== Web server setup ====
async def handle_status(request):
    return web.Response(text="✅ DarkyBot él!", content_type="text/html")

async def handle_json(request):
    try:
        with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
            data = f.read()
        return web.Response(text=data, content_type="application/json")
    except Exception as e:
        return web.Response(text=f"Hiba: {e}", status=500)

app = web.Application()
app.router.add_get("/", handle_status)
app.router.add_get("/reaction_roles.json", handle_json)

async def start_web():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

async def main():
    await start_web()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
