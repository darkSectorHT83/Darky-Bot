import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import json
from aiohttp import web
import asyncio

# .env betöltése
load_dotenv()
TOKEN = os.getenv("TOKEN")

# Engedélyezett szerverek betöltése
def load_allowed_guilds(file_path="Reaction.ID.txt"):
    allowed = set()
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        allowed.add(int(line.split("#")[0].strip()))
                    except ValueError:
                        continue
    return allowed

allowed_guilds = load_allowed_guilds()

# Intents beállítása
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

# Bot példány
bot = commands.Bot(command_prefix='!', intents=intents)

# Reaction roles fájl
REACTION_ROLES_FILE = "reaction_roles.json"

# Reaction roles betöltése fájlból
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

# Fájlba mentés
def save_reaction_roles():
    with open(REACTION_ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump({
            str(gid): {str(mid): emoji_roles for mid, emoji_roles in msgs.items()}
            for gid, msgs in reaction_roles.items()
        }, f, ensure_ascii=False, indent=4)

# Check dekorátor engedélyezett szerverekhez
def is_guild_allowed():
    async def predicate(ctx):
        return ctx.guild and ctx.guild.id in allowed_guilds
    return commands.check(predicate)

# Bot készen áll
@bot.event
async def on_ready():
    print(f'✅ Bot bejelentkezett: {bot.user.name}')

# Emoji–szerep hozzárendelés parancs
@bot.command()
@commands.has_permissions(administrator=True)
@is_guild_allowed()
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

# Emoji–szerep törlés parancs
@bot.command()
@commands.has_permissions(administrator=True)
@is_guild_allowed()
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

# Reakció lista lekérdezés
@bot.command()
@commands.has_permissions(administrator=True)
@is_guild_allowed()
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

# Reakció hozzáadás
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
        print(f"⚠️ Ismeretlen emoji: {emoji} (üzenet ID: {message_id})")
        return

    role = discord.utils.get(guild.roles, name=role_name)
    member = guild.get_member(payload.user_id)

    if role and member:
        await member.add_roles(role)
        print(f"✅ {member} kapott szerepet: {role.name}")

# Reakció eltávolítás
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
        print(f"❌ {member} elveszítette a szerepet: {role.name}")

# Parancshibák kezelése
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        if ctx.guild and ctx.guild.id not in allowed_guilds:
            await ctx.send("❌ Ez a szerver nincs engedélyezve. Látogasson el ide: https://www.darksector.hu")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("🚫 Nincs jogosultságod a parancs használatához.")
    else:
        print(f"Hiba: {error}")

# HTML válasz OBS + Replit webnézethez
async def handle(request):
    html_content = """
    <html>
    <head>
        <style>
            body {
                background-color: transparent;
                color: #00eeff;
                font-family: Arial, sans-serif;
                font-size: 32px;
                text-align: center;
                margin-top: 30vh;
            }
        </style>
    </head>
    <body>
        ✅ DarkyBot online!
    </body>
    </html>
    """
    return web.Response(text=html_content, content_type='text/html')

# Webszerver indítása (UptimeRobot, OBS)
app = web.Application()
app.router.add_get("/", handle)

async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# Discord bot + webserver futtatása
async def main():
    await start_webserver()
    await bot.start(TOKEN)

asyncio.run(main())
