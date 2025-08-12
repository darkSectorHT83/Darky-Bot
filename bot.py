# [Darky Bot v3.0.2 - Frissített parancsok és rangnevek]
import discord
from discord.ext import commands
import os
import json
from aiohttp import web
import asyncio
import aiohttp
import traceback
from datetime import datetime

# ------------------------
# ENV / Konfiguráció
# ------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_ACCESS_TOKEN = os.getenv("TWITCH_ACCESS_TOKEN")  # OAuth token vagy app token (ami nálad van)

# Fájlnevek
ALLOWED_GUILDS_FILE = "Reaction.ID.txt"
REACTION_ROLES_FILE = "reaction_roles.json"
ACTIVATE_INFO_FILE = "activateinfo.txt"
TWITCH_FILE = "twitch_streams.json"  # <- ide írod a párosításokat
TWITCH_INTERNAL_FILE = "twitch_streams_state.json"  # opcionális belső állapotmentés (nem kötelező)

# Áttetszőség beállítás (0-100) a státusz oldalon
TRANSPARENCY = 100

# ------------------------
# Intents és Bot osztály
# ------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

class MyBot(commands.Bot):
    async def setup_hook(self):
        # Indítsd itt aszinkron a watcher-t, így Render alatt nem lesz loop attribútum hiba
        self.loop.create_task(twitch_watcher())
        # Ha akarsz még egyéb initet (pl. cogs), ide jöhet

bot = MyBot(command_prefix='!', intents=intents)

# ------------------------
# Helper: Engedélyezett szerverek betöltése
# ------------------------
def load_allowed_guilds():
    if not os.path.exists(ALLOWED_GUILDS_FILE):
        return set()
    with open(ALLOWED_GUILDS_FILE, "r", encoding="utf-8") as f:
        return set(int(line.strip()) for line in f if line.strip().isdigit())

allowed_guilds = load_allowed_guilds()

# ------------------------
# Jogosultság check (admin vagy megadott rang)
# ------------------------
def admin_or_role(role_name):
    async def predicate(ctx):
        try:
            has_admin = ctx.author.guild_permissions.administrator
            has_role = discord.utils.get(ctx.author.roles, name=role_name) is not None
            return has_admin or has_role
        except Exception:
            return False
    return commands.check(predicate)

# ------------------------
# Reaction roles betöltése / mentése
# ------------------------
if os.path.exists(REACTION_ROLES_FILE):
    with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
        try:
            reaction_roles = json.load(f)
            # konvertáljuk szám típusra a kulcsokat (későbbi használathoz)
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

# ------------------------
# Twitch streamerek betöltése / mentése (egyszerű párosítás)
# Formátum: [ { "username": "streamer1", "channel_id": 123... }, ... ]
# ------------------------
def load_twitch_streamers():
    if not os.path.exists(TWITCH_FILE):
        return []
    with open(TWITCH_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            # Ha a fájl egy objektumot tartalmaz (korábbi formátum), támogassuk azt:
            if isinstance(data, dict) and "streamers" in data and isinstance(data["streamers"], list):
                return data["streamers"]
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            return []

def save_twitch_streamers(list_obj):
    # Eredeti JSON mentése
    with open(TWITCH_FILE, "w", encoding="utf-8") as f:
        json.dump(list_obj, f, ensure_ascii=False, indent=4)
    # Ideiglenes állapot mentése webre (ez a fájl lesz elérhető a /twitch_streams_state.json útvonalon)
    try:
        with open(TWITCH_INTERNAL_FILE, "w", encoding="utf-8") as f:
            json.dump(list_obj, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"⚠️ Nem sikerült menteni {TWITCH_INTERNAL_FILE}: {e}")

# belső runtime állapot: username.lower() -> {"channel_id": int, "live": bool}
# ezt minden indításkor újratöltjük a TWITCH_FILE alapján
def build_twitch_state_from_file():
    arr = load_twitch_streamers()
    state = {}
    for item in arr:
        try:
            uname = item.get("username", "").lower()
            cid = int(item.get("channel_id"))
            if uname:
                state[uname] = {"channel_id": cid, "live": False}
        except Exception:
            continue
    return state

twitch_streams = build_twitch_state_from_file()

# Ha nincs még ideiglenes fájl, hozzuk létre egyszer (biztosítja, hogy a weben legyen mit olvasni)
try:
    if not os.path.exists(TWITCH_INTERNAL_FILE):
        save_twitch_streamers(load_twitch_streamers())
except Exception:
    pass

# ------------------------
# Twitch helper: lekérdezi, hogy él-e a streamer (helix streams endpoint)
# Feltételezi: TWITCH_CLIENT_ID és TWITCH_ACCESS_TOKEN be vannak állítva
# ------------------------
async def is_twitch_live(username):
    """Visszaad: (live: bool, stream_data: dict|None)"""
    if not TWITCH_CLIENT_ID or not TWITCH_ACCESS_TOKEN:
        return False, None
    url = f"https://api.twitch.tv/helix/streams?user_login={username}"
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status != 200:
                    # opcionális: logoljuk a hibát
                    text = await resp.text()
                    print(f"[Twitch API] Nem 200 a válasz: {resp.status} - {text}")
                    return False, None
                data = await resp.json()
                if "data" in data and len(data["data"]) > 0:
                    return True, data["data"][0]
                return False, None
    except Exception as e:
        print(f"[Twitch API hiba] {e}")
        return False, None

# Ha szükséged van arra, hogy felhasználónévből user_id-t kérjen: (nem feltétlen kell jelen implementációhoz)
async def get_twitch_user_id(username):
    if not TWITCH_CLIENT_ID or not TWITCH_ACCESS_TOKEN:
        return None
    url = f"https://api.twitch.tv/helix/users?login={username}"
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if "data" in data and len(data["data"]) > 0:
                    return data["data"][0].get("id")
                return None
    except Exception:
        return None

# ------------------------
# Twitch watcher (indul a setup_hook-ban)
# ------------------------
async def twitch_watcher():
    await bot.wait_until_ready()
    print("🔁 Twitch watcher elindult.")
    # rebuild állapot induláskor a fájlból (ha közben deploy-olsz, újra beolvas)
    global twitch_streams
    twitch_streams = build_twitch_state_from_file()

    while not bot.is_closed():
        try:
            for username, info in list(twitch_streams.items()):
                try:
                    live, stream_data = await is_twitch_live(username)
                    # stream_data tartalmaz: id, user_id, user_name, game_id, game_name, title, viewer_count, started_at, language, thumbnail_url, etc.
                    if live and not info.get("live", False):
                        # Stream újonnan élő -> küldj egyszeri SZÖVEGES üzenetet a channel_id-be
                        channel_id = info.get("channel_id")
                        channel = bot.get_channel(channel_id)
                        if channel:
                            title = stream_data.get("title", "Ismeretlen cím")
                            user_name = stream_data.get("user_name", username)
                            game_name = stream_data.get("game_name", "Ismeretlen játék")
                            # SZÖVEGES üzenet (nem embed)
                            msg = (
                                f"🎥 **{user_name}** élőben van a Twitch-en!\n"
                                f"📌 Mit streamel: {game_name}\n"
                                f"🔗 https://twitch.tv/{user_name}\n"
                                f"📝 Cím: {title}"
                            )
                            try:
                                await channel.send(msg)
                                print(f"➡️ Szöveges értesítés elküldve: {user_name} -> {channel_id}")
                            except Exception as e:
                                print(f"⚠️ Nem sikerült értesítést küldeni {user_name} -> {channel_id}: {e}")
                        else:
                            print(f"⚠️ Nem található csatorna (ID: {channel_id}) a guildben.")
                        twitch_streams[username]["live"] = True
                    elif not live and info.get("live", False):
                        # Stream lezárt -> állapot reset
                        twitch_streams[username]["live"] = False
                    # runtime állapot, nem írjuk ideiglenes fájlba itt (a dbtwitch add/remove mentik a listát)
                except Exception as inner:
                    print(f"[twitch_watcher belső hiba] {inner}")
                    traceback.print_exc()
            await asyncio.sleep(60)  # ellenőrzés gyakorisága (másodperc)
        except Exception as e:
            print(f"[twitch_watcher főhiba] {e}")
            traceback.print_exc()
            await asyncio.sleep(60)

# ------------------------
# Globális parancsellenőrzés (kivéve !dbactivate)
# ------------------------
@bot.check
async def guild_permission_check(ctx):
    if ctx.command and ctx.command.name == "dbactivate":
        return True
    return ctx.guild and ctx.guild.id in allowed_guilds

# ------------------------
# Bot ready
# ------------------------
@bot.event
async def on_ready():
    print(f"✅ Bejelentkezett: {bot.user} (ID: {bot.user.id})")

# ------------------------
# AI: Gemini + OpenAI (ahogy eredetileg)
# ------------------------
async def gemini_text(prompt):
    if not GEMINI_API_KEY:
        return "⚠️ Nincs GEMINI_API_KEY beállítva."
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=30) as resp:
                result = await resp.json()
                try:
                    return result["candidates"][0]["content"]["parts"][0]["text"]
                except:
                    return "⚠️ Gemini hiba történt."
    except Exception as e:
        return f"⚠️ Gemini hiba: {e}"

async def gemini_image(prompt):
    if not GEMINI_API_KEY:
        return "⚠️ Nincs GEMINI_API_KEY beállítva."
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=30) as resp:
                result = await resp.json()
                try:
                    return result["candidates"][0]["content"]["parts"][0]["text"]
                except:
                    return "⚠️ Gemini kép generálási hiba."
    except Exception as e:
        return f"⚠️ Gemini hiba: {e}"

async def gpt_text(prompt):
    if not OPENAI_API_KEY:
        return "⚠️ Nincs OPENAI_API_KEY beállítva."
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"}
    data = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=30) as resp:
                result = await resp.json()
                try:
                    return result["choices"][0]["message"]["content"]
                except:
                    return "⚠️ ChatGPT hiba történt."
    except Exception as e:
        return f"⚠️ OpenAI hiba: {e}"

async def gpt_image(prompt):
    if not OPENAI_API_KEY:
        return "⚠️ Nincs OPENAI_API_KEY beállítva."
    url = "https://api.openai.com/v1/images/generations"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"}
    data = {"model": "gpt-image-1", "prompt": prompt, "size": "1024x1024"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=30) as resp:
                result = await resp.json()
                try:
                    return result["data"][0]["url"]
                except:
                    return "⚠️ ChatGPT kép generálási hiba."
    except Exception as e:
        return f"⚠️ OpenAI hiba: {e}"

# ------------------------
# AI parancsok
# ------------------------
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

def admin_or_role(role_name):
    async def predicate(ctx):
        # admin jog vagy megadott rang
        return ctx.author.guild_permissions.administrator or \
               discord.utils.get(ctx.author.roles, name=role_name)
    return commands.check(predicate)

@bot.command()
@admin_or_role("LightSector GPT")
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
# dbtwitch parancsok: add/remove/list (módosítják a twitch_streams.json fájlt)
# admin vagy LightSector TWITCH kell hozzájuk
# ------------------------
@bot.command(name="dbtwitchadd")
@admin_or_role("LightSector TWITCH")
async def dbtwitchadd(ctx, username: str, channel_id: int):
    """!dbtwitchadd <twitch_username> <discord_channel_id>"""
    username = username.lower()
    arr = load_twitch_streamers()
    # ellenőrizzük, hogy nincs-e már
    for item in arr:
        if item.get("username", "").lower() == username:
            item["channel_id"] = channel_id  # frissítjük a csatorna ID-t
            save_twitch_streamers(arr)
            # frissítsük runtime állapotot is
            twitch_streams[username] = {"channel_id": channel_id, "live": False}
            await ctx.send(f"🔧 Frissítve: **{username}** → <#{channel_id}>")
            return
    # hozzáadjuk újként
    arr.append({"username": username, "channel_id": channel_id})
    save_twitch_streamers(arr)
    twitch_streams[username] = {"channel_id": channel_id, "live": False}
    await ctx.send(f"✅ Twitch figyelés hozzáadva: **{username}** → <#{channel_id}>")

@bot.command(name="dbtwitchremove")
@admin_or_role("LightSector TWITCH")
async def dbtwitchremove(ctx, username: str):
    username = username.lower()
    arr = load_twitch_streamers()
    new_arr = [item for item in arr if item.get("username", "").lower() != username]
    if len(new_arr) == len(arr):
        await ctx.send("⚠️ Nincs ilyen figyelt streamer.")
        return
    save_twitch_streamers(new_arr)
    twitch_streams.pop(username, None)
    await ctx.send(f"❌ Twitch figyelés törölve: **{username}**")

@bot.command(name="dbtwitchlist")
@admin_or_role("LightSector TWITCH")
async def dbtwitchlist(ctx):
    arr = load_twitch_streamers()
    if not arr:
        await ctx.send("ℹ️ Jelenleg nincs figyelt Twitch csatorna.")
        return
    msg = "**Figyelt Twitch csatornák:**\n"
    for item in arr:
        uname = item.get("username")
        cid = item.get("channel_id")
        msg += f"🎮 **{uname}** → <#{cid}>\n"
    await ctx.send(msg)

# ------------------------
# Egyszerű dbtwitch parancs (kért: !dbtwitch <felhasználónév> -> küld egy Twitch linket)
# ------------------------
@bot.command(name="dbtwitch")
async def dbtwitch_cmd(ctx, username: str):
    """!dbtwitch <twitch_username> - küld egy Twitch linket (Discord előnézettel)."""
    if not username:
        return await ctx.send("⚠️ Add meg a Twitch felhasználónevet. Példa: `!dbtwitch shroud`")
    # egyszerű tisztítás: eltávolítjuk az @-ot vagy esetleges teljes URL-t
    uname = username.strip().lstrip('@').split('/')[-1]
    twitch_url = f"https://twitch.tv/{uname}"
    await ctx.send(twitch_url)

# ------------------------
# Reakciós parancsok (addreaction, removereaction, listreactions)
# admin vagy LightSector ROLE kell hozzájuk
# ------------------------
@bot.command()
@admin_or_role("LightSector ROLE")
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
        await ctx.send(f"🔧 {emoji} → {role_name} (üzenet ID: {message_id})")

@bot.command()
@admin_or_role("LightSector ROLE")
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
        await ctx.send(f"❌ {emoji} eltávolítva (üzenet: {message_id})")
    else:
        await ctx.send("⚠️ Nem található az emoji vagy üzenet.")

@bot.command()
@admin_or_role("LightSector ROLE")
async def listreactions(ctx):
    guild_id = ctx.guild.id
    if guild_id not in reaction_roles or not reaction_roles[guild_id]:
        await ctx.send("ℹ️ Nincs beállított reakció ebben a szerverben.")
        return
    msg = ""
    for msg_id, emoji_map in reaction_roles[guild_id].items():
        msg += f"📩 Üzenet ID: {msg_id}\n"
        for emoji, role in emoji_map.items():
            msg += f"   {emoji} → {role}\n"
    await ctx.send(msg)

# ------------------------
# Reaction add/remove események
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
            try:
                await member.add_roles(role)
                print(f"✅ {member} kapta: {role.name}")
            except Exception as e:
                print(f"⚠️ Nem sikerült szerepet adni: {e}")

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
            try:
                await member.remove_roles(role)
                print(f"❌ {member} elvesztette: {role.name}")
            except Exception as e:
                print(f"⚠️ Nem sikerült szerepet eltávolítani: {e}")

# ------------------------
# dbhelp és dbactivate parancsok (eredeti logikával)
# ------------------------
@bot.command()
async def dbhelp(ctx):
    if not os.path.exists("help.txt"):
        await ctx.send("⚠️ A help.txt fájl nem található.")
        return
    with open("help.txt", "r", encoding="utf-8") as f:
        help_text = f.read()
    if not help_text.strip():
        await ctx.send("⚠️ A help.txt fájl üres.")
        return
    # Code blockba küldjük
    await ctx.send(f"```{help_text}```")

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
# Web szerver (egyszerű status + reaction_roles.json + twitch state endpoint)
# ------------------------
async def handle(request):
    html_content = f"""
    <html>
    <head>
        <title>Darky Bot Status</title>
        <style>
            body {{
                background-color: transparent;
                text-align: center;
                margin-top: 50px;
            }}
            .container {{
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 20px;
            }}
            .status-text {{
                font-size: 80px;
                font-weight: bold;
                color: white;
                text-shadow: 2px 2px 5px black;
            }}
            .status-image {{
                width: 128px;
                height: 128px;
                opacity: {TRANSPARENCY / 100};
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <img class="status-image" src="https://kephost.net/p/MjAzODQ3OQ.png" alt="Bot Icon">
            <div class="status-text">Darky Bot: ONLINE</div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html_content, content_type='text/html')

async def get_json(request):
    if not os.path.exists(REACTION_ROLES_FILE):
        return web.json_response({}, status=200, dumps=lambda x: json.dumps(x, ensure_ascii=False, indent=4))
    with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {}
    return web.json_response(data, status=200, dumps=lambda x: json.dumps(x, ensure_ascii=False, indent=4))

async def get_twitch_state_json(request):
    if not os.path.exists(TWITCH_INTERNAL_FILE):
        return web.json_response([], status=200)
    with open(TWITCH_INTERNAL_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = []
    return web.json_response(data, status=200)

app = web.Application()
app.router.add_get("/", handle)
app.router.add_get("/reaction_roles.json", get_json)
app.router.add_get("/twitch_streams_state.json", get_twitch_state_json)

async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print("🌐 Webserver elindítva: http://0.0.0.0:8080/")

# ------------------------
# Main indítás (Render kompatibilis)
# ------------------------
async def main():
    print("✅ Bot indítás folyamatban...")
    print("DISCORD_TOKEN:", "✅ beállítva" if DISCORD_TOKEN else "❌ HIÁNYZIK")
    # web szerver indítása
    try:
        await start_webserver()
    except Exception as e:
        print(f"⚠️ Hiba a webserver indításakor: {e}")
    # A bot elindítása (setup_hook fogja elindítani a twitch_watcher-t)
    try:
        await bot.start(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ Hiba a bot indításakor: {e}")

if __name__ == "__main__":
    # futtatás asyncio.run-nal -> elkerüljük a loop attribute hibát Renderen
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🔌 Leállítás kézi megszakítással.")
    except Exception as e:
        print(f"❌ Fő hibakör: {e}")
