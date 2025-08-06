import os
import discord
from discord.ext import commands
import json
import asyncio
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

ALLOWED_GUILDS_FILE = "Reaction.ID.txt"
REACTION_ROLES_FILE = "reaction_roles.json"

# Betöltés
if os.path.exists(ALLOWED_GUILDS_FILE):
    with open(ALLOWED_GUILDS_FILE, "r", encoding="utf-8") as f:
        allowed_guilds = {
            int(line.split("#")[0].strip())
            for line in f
            if line.strip() and not line.strip().startswith("#")
        }
else:
    allowed_guilds = set()

if os.path.exists(REACTION_ROLES_FILE):
    with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
        reaction_roles = json.load(f)
        reaction_roles = {
            int(g): {int(m): v for m, v in msgs.items()}
            for g, msgs in reaction_roles.items()
        }
else:
    reaction_roles = {}

def save_reaction_roles():
    with open(REACTION_ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump({
            str(g): {str(m): v for m, v in msgs.items()}
            for g, msgs in reaction_roles.items()
        }, f, ensure_ascii=False, indent=4)

def is_guild_allowed():
    async def predicate(ctx):
        if ctx.guild and ctx.guild.id in allowed_guilds:
            return True
        raise commands.CheckFailure("Ez a szerver nincs engedélyezve.")
    return commands.check(predicate)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send(
            "❌ Ez a szerver nincs engedélyezve.\n"
            "Látogasson el ide: https://www.darksector.hu"
        )
    else:
        print(f"Hiba: {error}")

@bot.event
async def on_ready():
    print(f'✅ Bot bejelentkezett: {bot.user.name}')

@bot.command()
@commands.has_permissions(administrator=True)
@is_guild_allowed()
async def listreactions(ctx):
    guild_id = ctx.guild.id
    if guild_id not in reaction_roles or not reaction_roles[guild_id]:
        await ctx.send("ℹ️ Nincsenek beállított reakciók ebben a szerverben.")
        return
    msg = ""
    for mid, emap in reaction_roles[guild_id].items():
        msg += f"📩 Üzenet ID: `{mid}`\n"
        for em, rolenm in emap.items():
            msg += f"   {em} → `{rolenm}`\n"
    await ctx.send(msg)

@bot.command()
@commands.has_permissions(administrator=True)
@is_guild_allowed()
async def addreaction(ctx, message_id: int, emoji: str, *, role_name: str):
    gid = ctx.guild.id
    if gid not in reaction_roles:
        reaction_roles[gid] = {}
    reaction_roles[gid][message_id] = reaction_roles[gid].get(message_id, {})
    reaction_roles[gid][message_id][emoji] = role_name
    save_reaction_roles()
    try:
        msg = await ctx.channel.fetch_message(message_id)
        await msg.add_reaction(emoji)
    except Exception as e:
        await ctx.send(f'⚠️ Hiba: {e}')
    else:
        await ctx.send(f'🔧 Emoji `{emoji}` ranghoz `{role_name}` rendelve.')

@bot.command()
@commands.has_permissions(administrator=True)
@is_guild_allowed()
async def removereaction(ctx, message_id: int, emoji: str):
    gid = ctx.guild.id
    if gid in reaction_roles and message_id in reaction_roles[gid] and emoji in reaction_roles[gid][message_id]:
        del reaction_roles[gid][message_id][emoji]
        if not reaction_roles[gid][message_id]:
            del reaction_roles[gid][message_id]
        if not reaction_roles[gid]:
            del reaction_roles[gid]
        save_reaction_roles()
        await ctx.send(f'❌ `{emoji}` eltávolítva (üzenet: {message_id}).')
    else:
        await ctx.send('⚠️ Nincs ilyen párosítás.')

@bot.event
async def on_raw_reaction_add(payload):
    if payload.guild_id not in allowed_guilds or payload.user_id == bot.user.id:
        return
    role = reaction_roles.get(payload.guild_id, {}).get(payload.message_id, {}).get(str(payload.emoji))
    if role:
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        role_obj = discord.utils.get(guild.roles, name=role)
        if member and role_obj:
            await member.add_roles(role_obj)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.guild_id not in allowed_guilds:
        return
    role = reaction_roles.get(payload.guild_id, {}).get(payload.message_id, {}).get(str(payload.emoji))
    if role:
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        role_obj = discord.utils.get(guild.roles, name=role)
        if member and role_obj:
            await member.remove_roles(role_obj)

async def handle(request):
    return web.Response(text="✅ DarkyBot online!", content_type='text/html')

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

asyncio.run(main())
