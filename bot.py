import discord
from discord.ext import commands
import os
import json
from aiohttp import web
import asyncio
import aiohttp

# Tokenek Render environment-ből
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_ACCESS_TOKEN = os.getenv("TWITCH_ACCESS_TOKEN")

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

# Mentés
def save_reaction_roles():
    with open(REACTION_ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump({
            str(gid): {str(mid): em for mid, em in msgs.items()}
            for gid, msgs in reaction_roles.items()
        }, f, ensure_ascii=False, indent=4)

# Twitch csatorna-stremer párosítás betöltése
def load_twitch_channels():
    if not os.path.exists(TWITCH_CHANNELS_FILE):
        return {}
    with open(TWITCH_CHANNELS_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return {int(k): {int(ch): v for ch, v in vs.items()} for k, vs in data.items()}
        except json.JSONDecodeError:
            return {}

def save_twitch_channels(data):
    with open(TWITCH_CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump({str(k): {str(ch): v for ch, v in vs.items()} for k, vs in data.items()}, f, ensure_ascii=False, indent=4)

twitch_channels = load_twitch_channels()

# Globális parancsellenőrzés (kivéve !dbactivate)
@bot.check
async def guild_permission_check(ctx):
    if ctx.command.name == "dbactivate":
        return True
    return ctx.guild and ctx.guild.id in allowed_guilds

@bot.event
async def on_ready():
    print(f"✅ Bejelentkezett: {bot.user.name}")

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
# Reakciós és egyéb meglévő parancsok
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

@bot.command()
async def dbhelp(ctx):
    help_text = """```
📌 Elérhető parancsok:
!addreaction <üzenet_id> <emoji> <szerepkör>   - Reakció hozzáadása
!removereaction <üzenet_id> <emoji>           - Reakció eltávolítása
!listreactions                                - Reakciók listázása
!addtwitch <streamer_név> <szerepkör> <csatorna_id> - Twitch csatorna hozzáadása értesítéshez
!removetwitch <streamer_név> <csatorna_id>   - Twitch csatorna eltávolítása
!listtwitch                                  - Twitch csatornák listázása
!dbactivate <igen/nem>                        - Bot aktiválásának beállítása
!g <szöveg>                                  - Gemini AI szöveges válasz
!gpic <szöveg>                               - Gemini AI kép generálás
!gpt <szöveg>                                - ChatGPT szöveges válasz
!gptpic <szöveg>                             - ChatGPT kép generálás
```"""
    await ctx.send(help_text)

# ------------------------
# Twitch értesítések kezelése
# ------------------------

async def is_stream_live(streamer_name):
    url = f"https://api.twitch.tv/helix/streams?user_login={streamer_name}"
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            data = await resp.json()
            streams = data.get("data", [])
            return len(streams) > 0

# Tároljuk, hogy mely streamek élnek jelenleg, hogy ne spameljünk
live_streams_cache = {}

async def twitch_notify_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        for guild_id, channels in twitch_channels.items():
            guild = bot.get_guild(guild_id)
            if not guild:
                continue
            for channel_id, streamer_name in channels.items():
                channel = guild.get_channel(channel_id)
                if not channel:
                    continue
                try:
                    live = await is_stream_live(streamer_name)
                except Exception as e:
                    print(f"Twitch API hiba: {e}")
                    live = False

                # Ha most él és még nem jeleztük
                if live and not live_streams_cache.get((guild_id, channel_id), False):
                    await channel.send(f"🔴 **{streamer_name}** most élőben van! Nézd meg: https://twitch.tv/{streamer_name}")
                    live_streams_cache[(guild_id, channel_id)] = True

                # Ha nem él, de korábban élőnek volt jelölve, frissítjük
                if not live and live_streams_cache.get((guild_id, channel_id), False):
                    live_streams_cache[(guild_id, channel_id)] = False

        await asyncio.sleep(300)  # 5 percenként ellenőrzés

@bot.command()
@commands.has_permissions(administrator=True)
async def addtwitch(ctx, streamer_name: str, role_name: str, channel_id: int):
    guild_id = ctx.guild.id
    if guild_id not in twitch_channels:
        twitch_channels[guild_id] = {}
    twitch_channels[guild_id][channel_id] = streamer_name
    save_twitch_channels(twitch_channels)
    await ctx.send(f"Twitch csatorna hozzáadva: {streamer_name} - Értesítő csatorna ID: {channel_id}")

@bot.command()
@commands.has_permissions(administrator=True)
async def removetwitch(ctx, streamer_name: str, channel_id: int):
    guild_id = ctx.guild.id
    if guild_id in twitch_channels and channel_id in twitch_channels[guild_id]:
        if twitch_channels[guild_id][channel_id] == streamer_name:
            del twitch_channels[guild_id][channel_id]
            if not twitch_channels[guild_id]:
                del twitch_channels[guild_id]
            save_twitch_channels(twitch_channels)
            await ctx.send(f"Twitch csatorna eltávolítva: {streamer_name} - Csatorna ID: {channel_id}")
            return
    await ctx.send("Nem található ilyen Twitch értesítés.")

@bot.command()
async def listtwitch(ctx):
    guild_id = ctx.guild.id
    if guild_id not in twitch_channels or not twitch_channels[guild_id]:
        await ctx.send("Nincsenek Twitch értesítések beállítva ebben a szerverben.")
        return
    msg = "📺 Twitch értesítések:\n"
    for channel_id, streamer in twitch_channels[guild_id].items():
        msg += f"Csatorna ID: `{channel_id}` - Streamer: `{streamer}`\n"
    await ctx.send(msg)

# ------------------------
# Bot aktiválásának beállítása
# ------------------------

@bot.command()
@commands.has_permissions(administrator=True)
async def dbactivate(ctx, val: str):
    val = val.lower()
    if val not in ("igen", "nem"):
        await ctx.send("Hibás érték! Csak 'igen' vagy 'nem' lehet.")
        return
    with open(ACTIVATE_INFO_FILE, "w", encoding="utf-8") as f:
        f.write(val)
    await ctx.send(f"Bot aktiválás beállítva: {val}")

# ------------------------
# Reaction role események
# ------------------------

@bot.event
async def on_raw_reaction_add(payload):
    guild_id = payload.guild_id
    if guild_id not in reaction_roles:
        return
    if payload.message_id not in reaction_roles[guild_id]:
        return
    emoji = str(payload.emoji)
    if emoji not in reaction_roles[guild_id][payload.message_id]:
        return

    guild = bot.get_guild(guild_id)
    if not guild:
        return

    role_name = reaction_roles[guild_id][payload.message_id][emoji]
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        return

    member = guild.get_member(payload.user_id)
    if not member:
        return

    try:
        await member.add_roles(role)
    except Exception as e:
        print(f"Role hozzárendelési hiba: {e}")

@bot.event
async def on_raw_reaction_remove(payload):
    guild_id = payload.guild_id
    if guild_id not in reaction_roles:
        return
    if payload.message_id not in reaction_roles[guild_id]:
        return
    emoji = str(payload.emoji)
    if emoji not in reaction_roles[guild_id][payload.message_id]:
        return

    guild = bot.get_guild(guild_id)
    if not guild:
        return

    role_name = reaction_roles[guild_id][payload.message_id][emoji]
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        return

    member = guild.get_member(payload.user_id)
    if not member:
        return

    try:
        await member.remove_roles(role)
    except Exception as e:
        print(f"Role eltávolítási hiba: {e}")

# ------------------------
# Twitch értesítő loop indítása
# ------------------------

bot.loop.create_task(twitch_notify_loop())

# ------------------------
# Bot indítása
# ------------------------

bot.run(DISCORD_TOKEN)
