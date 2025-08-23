import discord
from discord.ext import commands, tasks
import os
import json
import asyncio
import aiohttp
from aiohttp import web
from dotenv import load_dotenv
import feedparser

# .env betöltése
load_dotenv()
TOKEN = os.getenv("TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

# Bot példány
bot = commands.Bot(command_prefix='!', intents=intents)

# Engedélyezett szerverek fájl
ALLOWED_SERVERS_FILE = "Reaction.ID.txt"
if os.path.exists(ALLOWED_SERVERS_FILE):
    with open(ALLOWED_SERVERS_FILE, "r", encoding="utf-8") as f:
        allowed_servers = [int(line.strip()) for line in f if line.strip().isdigit()]
else:
    allowed_servers = []

# Reaction roles fájl
REACTION_ROLES_FILE = "reaction_roles.json"
REACTION_ROLES_STATE_FILE = "reaction_roles_state.json"

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
        json.dump({str(gid): {str(mid): emoji_roles for mid, emoji_roles in msgs.items()} for gid, msgs in reaction_roles.items()}, f, ensure_ascii=False, indent=4)
    with open(REACTION_ROLES_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(reaction_roles, f, ensure_ascii=False, indent=4)

# Twitch fájlok
TWITCH_STREAMS_FILE = "twitch_streams.json"
TWITCH_STREAMS_STATE_FILE = "twitch_streams_state.json"

if os.path.exists(TWITCH_STREAMS_FILE):
    with open(TWITCH_STREAMS_FILE, "r", encoding="utf-8") as f:
        twitch_streams = json.load(f)
else:
    twitch_streams = {}

def save_twitch_streams():
    with open(TWITCH_STREAMS_FILE, "w", encoding="utf-8") as f:
        json.dump(twitch_streams, f, ensure_ascii=False, indent=4)
    with open(TWITCH_STREAMS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(twitch_streams, f, ensure_ascii=False, indent=4)

# YouTube fájlok
YOUTUBE_STREAMS_FILE = "youtube_streams.json"
YOUTUBE_STREAMS_STATE_FILE = "youtube_streams_state.json"

if os.path.exists(YOUTUBE_STREAMS_FILE):
    with open(YOUTUBE_STREAMS_FILE, "r", encoding="utf-8") as f:
        youtube_streams = json.load(f)
else:
    youtube_streams = {}

def save_youtube_streams():
    with open(YOUTUBE_STREAMS_FILE, "w", encoding="utf-8") as f:
        json.dump(youtube_streams, f, ensure_ascii=False, indent=4)
    with open(YOUTUBE_STREAMS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(youtube_streams, f, ensure_ascii=False, indent=4)

# Bot ready event
@bot.event
async def on_ready():
    print(f'✅ Bot bejelentkezett: {bot.user.name}')
    check_youtube_rss.start()

# ---------------- Reaction Roles Parancsok ----------------

@bot.command()
@commands.has_permissions(administrator=True)
async def addreaction(ctx, message_id: int, emoji: str, *, role_name: str):
    if ctx.guild.id not in allowed_servers:
        return await ctx.send("❌ Ez a szerver nincs engedélyezve a bot használatára.")

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
        await ctx.send(f'⚠️ Emoji hozzárendelve, de nem sikerült reagálni: {e}')
    else:
        await ctx.send(f'🔧 Emoji `{emoji}` hozzárendelve ranghoz: `{role_name}` (üzenet ID: `{message_id}`)')

@bot.command()
@commands.has_permissions(administrator=True)
async def removereaction(ctx, message_id: int, emoji: str):
    if ctx.guild.id not in allowed_servers:
        return await ctx.send("❌ Ez a szerver nincs engedélyezve a bot használatára.")
    guild_id = ctx.guild.id
    if (guild_id in reaction_roles and message_id in reaction_roles[guild_id] and emoji in reaction_roles[guild_id][message_id]):
        del reaction_roles[guild_id][message_id][emoji]
        if not reaction_roles[guild_id][message_id]:
            del reaction_roles[guild_id][message_id]
        if not reaction_roles[guild_id]:
            del reaction_roles[guild_id]
        save_reaction_roles()
        await ctx.send(f'❌ Emoji `{emoji}` eltávolítva az üzenetből: `{message_id}`.')
    else:
        await ctx.send('⚠️ Nincs ilyen emoji vagy üzenet ID.')

@bot.command()
@commands.has_permissions(administrator=True)
async def listreactions(ctx):
    if ctx.guild.id not in allowed_servers:
        return await ctx.send("❌ Ez a szerver nincs engedélyezve a bot használatára.")
    guild_id = ctx.guild.id
    if guild_id not in reaction_roles or not reaction_roles[guild_id]:
        return await ctx.send("ℹ️ Nincsenek beállított reakciók.")
    msg = ""
    for msg_id, emoji_map in reaction_roles[guild_id].items():
        msg += f"📩 **Üzenet ID:** `{msg_id}`\n"
        for emoji, role in emoji_map.items():
            msg += f"   {emoji} → `{role}`\n"
    await ctx.send(msg)

# Reaction események
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild or payload.guild_id not in allowed_servers:
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
    guild = bot.get_guild(payload.guild_id)
    if not guild or payload.guild_id not in allowed_servers:
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

# ---------------- YouTube RSS Figyelő ----------------

last_youtube_videos = {}

@tasks.loop(minutes=5)
async def check_youtube_rss():
    for guild_id, channels in youtube_streams.items():
        for channel_id, channel_data in channels.items():
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                continue
            latest = feed.entries[0]
            video_id = latest.yt_videoid
            if channel_id in last_youtube_videos and last_youtube_videos[channel_id] == video_id:
                continue
            last_youtube_videos[channel_id] = video_id
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            title = latest.title
            channel_name = latest.author
            channel = bot.get_channel(channel_data["channel_id"])
            if channel:
                await channel.send(f"📺 Új videó a YouTube-on!\n**{channel_name}** feltöltötte: **{title}**\n👉 {video_url}")

# ---------------- Webserver ----------------

async def handle_reaction_roles(request):
    return web.json_response(reaction_roles)

async def handle_twitch_streams(request):
    return web.json_response(twitch_streams)

async def handle_youtube_streams(request):
    return web.json_response(youtube_streams)

app = web.Application()
app.router.add_get("/reaction_roles_state.json", handle_reaction_roles)
app.router.add_get("/twitch_streams_state.json", handle_twitch_streams)
app.router.add_get("/youtube_streams_state.json", handle_youtube_streams)

async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# ---------------- Main ----------------

async def main():
    await start_webserver()
    await bot.start(TOKEN)

asyncio.run(main())
