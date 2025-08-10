import discord
from discord.ext import commands, tasks
import os
import json
from aiohttp import web
import asyncio
import aiohttp

# Tokenek Render environment-ből
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TWITCH_ACCESS_TOKEN = os.getenv("TWITCH_ACCESS_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

# Bot példány
bot = commands.Bot(command_prefix='!', intents=intents)

# Fájlok
ALLOWED_GUILDS_FILE = "Reaction.ID.txt"
REACTION_ROLES_FILE = "reaction_roles.json"
ACTIVATE_INFO_FILE = "activateinfo.txt"
TWITCH_CHANNELS_FILE = "twitch_channels.json"

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

def save_reaction_roles():
    with open(REACTION_ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump({
            str(gid): {str(mid): em for mid, em in msgs.items()}
            for gid, msgs in reaction_roles.items()
        }, f, ensure_ascii=False, indent=4)

# Twitch csatornák betöltése
if os.path.exists(TWITCH_CHANNELS_FILE):
    with open(TWITCH_CHANNELS_FILE, "r", encoding="utf-8") as f:
        try:
            twitch_channels = json.load(f)
            twitch_channels = {
                int(gid): {int(cid): chans for cid, chans in chans_map.items()}
                for gid, chans_map in twitch_channels.items()
            }
        except json.JSONDecodeError:
            twitch_channels = {}
else:
    twitch_channels = {}

def save_twitch_channels():
    with open(TWITCH_CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            str(gid): {str(cid): chans for cid, chans in chans_map.items()}
            for gid, chans_map in twitch_channels.items()
        }, f, ensure_ascii=False, indent=4)

# Globális parancsellenőrzés (kivéve !dbactivate)
@bot.check
async def guild_permission_check(ctx):
    if ctx.command.name == "dbactivate":
        return True
    return ctx.guild and ctx.guild.id in allowed_guilds

@bot.event
async def on_ready():
    print(f"✅ Bejelentkezett: {bot.user.name}")
    twitch_checker.start()

# ------------------------
# AI PARANCSOK
# ------------------------

async def gemini_text(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            result = await resp.json()
            try:
                return result["candidates"][0]["content"]["parts"][0]["text"]
            except:
                return "⚠️ Gemini hiba történt."

async def gemini_image(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            result = await resp.json()
            try:
                return result["candidates"][0]["content"]["parts"][0]["text"]
            except:
                return "⚠️ Gemini kép generálási hiba."

async def gpt_text(prompt):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"}
    data = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            result = await resp.json()
            try:
                return result["choices"][0]["message"]["content"]
            except:
                return "⚠️ ChatGPT hiba történt."

async def gpt_image(prompt):
    url = "https://api.openai.com/v1/images/generations"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"}
    data = {"model": "gpt-image-1", "prompt": prompt, "size": "1024x1024"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            result = await resp.json()
            try:
                return result["data"][0]["url"]
            except:
                return "⚠️ ChatGPT kép generálási hiba."

@bot.command()
async def g(ctx, *, prompt: str):
    if ctx.guild.id not in allowed_guilds:
        return await ctx.send("❌ Ez a parancs csak engedélyezett szervereken érhető el.")
    await ctx.send("⏳ Válasz készül...")
    response = await gemini_text(prompt)
    await ctx.send(response)

@bot.command()
async def gpic(ctx, *, prompt: str):
    if ctx.guild.id not in allowed_guilds:
        return await ctx.send("❌ Ez a parancs csak engedélyezett szervereken érhető el.")
    await ctx.send("⏳ Kép készül...")
    response = await gemini_image(prompt)
    await ctx.send(response)

@bot.command()
async def gpt(ctx, *, prompt: str):
    if ctx.guild.id not in allowed_guilds:
        return await ctx.send("❌ Ez a parancs csak engedélyezett szervereken érhető el.")
    await ctx.send("⏳ Válasz készül...")
    response = await gpt_text(prompt)
    await ctx.send(response)

@bot.command()
async def gptpic(ctx, *, prompt: str):
    if ctx.guild.id not in allowed_guilds:
        return await ctx.send("❌ Ez a parancs csak engedélyezett szervereken érhető el.")
    await ctx.send("⏳ Kép készül...")
    image_url = await gpt_image(prompt)
    await ctx.send(image_url)

# ------------------------
# Reakciós parancsok
# ------------------------

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

# ------------------------
# Twitch parancsok
# ------------------------

@bot.command()
@commands.has_permissions(administrator=True)
async def addtwitch(ctx, streamer_name: str):
    guild_id = ctx.guild.id
    channel_id = ctx.channel.id

    if guild_id not in twitch_channels:
        twitch_channels[guild_id] = {}
    if channel_id not in twitch_channels[guild_id]:
        twitch_channels[guild_id][channel_id] = []

    if streamer_name.lower() not in [s.lower() for s in twitch_channels[guild_id][channel_id]]:
        twitch_channels[guild_id][channel_id].append(streamer_name)
        save_twitch_channels()
        await ctx.send(f"✅ Twitch csatorna hozzáadva: `{streamer_name}` ehhez a szobához.")
    else:
        await ctx.send("⚠️ Ez a streamer már hozzá van adva ehhez a szobához.")

@bot.command()
@commands.has_permissions(administrator=True)
async def removetwitch(ctx, streamer_name: str):
    guild_id = ctx.guild.id
    channel_id = ctx.channel.id

    if (
        guild_id in twitch_channels and
        channel_id in twitch_channels[guild_id] and
        streamer_name in twitch_channels[guild_id][channel_id]
    ):
        twitch_channels[guild_id][channel_id].remove(streamer_name)
        if not twitch_channels[guild_id][channel_id]:
            del twitch_channels[guild_id][channel_id]
        if not twitch_channels[guild_id]:
            del twitch_channels[guild_id]
        save_twitch_channels()
        await ctx.send(f"❌ Twitch csatorna eltávolítva: `{streamer_name}`")
    else:
        await ctx.send("⚠️ Nem található ez a streamer ebben a szobában.")

@bot.command()
@commands.has_permissions(administrator=True)
async def listtwitch(ctx):
    guild_id = ctx.guild.id
    if guild_id not in twitch_channels or not twitch_channels[guild_id]:
        await ctx.send("ℹ️ Nincs Twitch csatorna beállítva ebben a szerverben.")
        return

    msg = ""
    for cid, streamers in twitch_channels[guild_id].items():
        channel_mention = bot.get_channel(cid).mention if bot.get_channel(cid) else f"`{cid}`"
        msg += f"📺 Szoba: {channel_mention}\n"
        for s in streamers:
            msg += f"   - `{s}`\n"
    await ctx.send(msg)

# ------------------------
# Súgó
# ------------------------

@bot.command()
async def dbhelp(ctx):
    help_text = """```
📌 Elérhető parancsok:
!addreaction <üzenet_id> <emoji> <szerepkör>   - Reakció hozzáadása
!removereaction <üzenet_id> <emoji>           - Reakció eltávolítása
!listreactions                                - Reakciók listázása
!addtwitch <streamer>                         - Twitch csatorna hozzáadása
!removetwitch <streamer>                      - Twitch csatorna eltávolítása
!listtwitch                                   - Twitch csatornák listázása
!dbactivate                                   - Aktivációs infó megtekintése
!dbhelp                                       - Ez a súgó
!g <szöveg>                                   - Gemini szöveg
!gpic <szöveg>                                - Gemini kép
!gpt <szöveg>                                 - ChatGPT szöveges válasz
!gptpic <szöveg>                              - ChatGPT kép
```"""
    await ctx.send(help_text)

# ------------------------
# Twitch figyelő
# ------------------------

last_live_status = {}

@tasks.loop(seconds=60)
async def twitch_checker():
    if not twitch_channels:
        return
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}"
    }
    async with aiohttp.ClientSession() as session:
        for guild_id, chans_map in twitch_channels.items():
            for channel_id, streamers in chans_map.items():
                for streamer in streamers:
                    url = f"https://api.twitch.tv/helix/streams?user_login={streamer}"
                    async with session.get(url, headers=headers) as resp:
                        data = await resp.json()
                        is_live = bool(data.get("data"))
                        key = f"{guild_id}-{channel_id}-{streamer.lower()}"
                        if is_live and not last_live_status.get(key):
                            chan = bot.get_channel(channel_id)
                            if chan:
                                await chan.send(f"🔴 **{streamer}** most élőben van a Twitch-en!\nhttps://twitch.tv/{streamer}")
                        last_live_status[key] = is_live

# ------------------------
# Activate info
# ------------------------

@bot.command()
async def dbactivate(ctx):
    if not os.path.exists(ACTIVATE_INFO_FILE):
        await ctx.send("⚠️ Az activateinfo.txt fájl nem található.")
        return

    with open(ACTIVATE_INFO_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        await ctx.send("⚠️ Az activateinfo.txt fájl üres.")
        return

    await ctx.send(content)

# ------------------------
# Reaction események
# ------------------------

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

# ------------------------
# Webszerver
# ------------------------

async def handle(request):
    return web.Response(text="✅ DarkyBot él!", content_type='text/html')

async def get_json(request):
    if not os.path.exists(REACTION_ROLES_FILE):
        return web.json_response({}, status=200, dumps=lambda x: json.dumps(x, ensure_ascii=False, indent=4))

    with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {}
    return web.json_response(data, status=200, dumps=lambda x: json.dumps(x, ensure_ascii=False, indent=4))

app = web.Application()
app.router.add_get("/", handle)
app.router.add_get("/reaction_roles.json", get_json)

async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# ------------------------
# Main
# ------------------------

async def main():
    print("✅ Bot indítás folyamatban...")
    print("DISCORD_TOKEN:", "✅ beállítva" if DISCORD_TOKEN else "❌ HIÁNYZIK")
    await start_webserver()
    try:
        await bot.start(DISCORD_TOKEN)
    except Exception
