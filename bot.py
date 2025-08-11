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

# ------------------------
# Bot osztály a setup_hook használatához
# ------------------------
class MyBot(commands.Bot):
    async def setup_hook(self):
        self.loop.create_task(twitch_watcher())

bot = MyBot(command_prefix='!', intents=intents)

# Fájlok
ALLOWED_GUILDS_FILE = "Reaction.ID.txt"
REACTION_ROLES_FILE = "reaction_roles.json"
ACTIVATE_INFO_FILE = "activateinfo.txt"
TWITCH_FILE = "twitch_streams.json"

# Áttetszőség beállítás (0-100)
TRANSPARENCY = 100

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

# Twitch figyelési adatok betöltése
if os.path.exists(TWITCH_FILE):
    with open(TWITCH_FILE, "r", encoding="utf-8") as f:
        try:
            twitch_streams = json.load(f)
        except json.JSONDecodeError:
            twitch_streams = {}
else:
    twitch_streams = {}

# Twitch adatok mentése
def save_twitch_data():
    with open(TWITCH_FILE, "w", encoding="utf-8") as f:
        json.dump(twitch_streams, f, ensure_ascii=False, indent=4)

# Twitch API hívás: ellenőrzi, hogy élő-e
async def is_twitch_live(username):
    url = f"https://api.twitch.tv/helix/streams?user_login={username}"
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            data = await resp.json()
            if "data" in data and len(data["data"]) > 0:
                return True, data["data"][0]
            return False, None

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
# TWITCH PARANCSOK
# ------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def twitchadd(ctx, username: str, channel_id: int):
    twitch_streams[username.lower()] = {
        "channel_id": channel_id,
        "live": False
    }
    save_twitch_data()
    await ctx.send(f"✅ Twitch figyelés hozzáadva: **{username}** → <#{channel_id}>")

@bot.command()
@commands.has_permissions(administrator=True)
async def twitchremove(ctx, username: str):
    if username.lower() in twitch_streams:
        del twitch_streams[username.lower()]
        save_twitch_data()
        await ctx.send(f"❌ Twitch figyelés törölve: **{username}**")
    else:
        await ctx.send("⚠️ Nincs ilyen figyelt csatorna.")

@bot.command()
async def twitchlist(ctx):
    if not twitch_streams:
        await ctx.send("ℹ️ Jelenleg nincs figyelt Twitch csatorna.")
        return
    msg = "**Figyelt Twitch csatornák:**\n"
    for user, info in twitch_streams.items():
        msg += f"🎮 **{user}** → <#{info['channel_id']}>\n"
    await ctx.send(msg)

async def twitch_watcher():
    await bot.wait_until_ready()
    while not bot.is_closed():
        for username, info in twitch_streams.items():
            live, stream_data = await is_twitch_live(username)
            if live and not info.get("live", False):
                channel = bot.get_channel(info["channel_id"])
                if channel:
                    title = stream_data.get("title", "Ismeretlen cím")
                    url = f"https://twitch.tv/{username}"
                    game = stream_data.get("game_name", "Ismeretlen játék")
                    await channel.send(
                        f"🔴 **{username}** élőben van!\n"
                        f"🎯 Játék: {game}\n"
                        f"📌 Cím: {title}\n"
                        f"👉 Nézd meg: {url}"
                    )
                twitch_streams[username]["live"] = True
                save_twitch_data()
            elif not live and info.get("live", False):
                twitch_streams[username]["live"] = False
                save_twitch_data()
        await asyncio.sleep(60)

# ------------------------
# Reakciós és egyéb parancsok
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
    await ctx.send(f"```{help_text}```")

# --- (a többi parancs ugyanaz, nem változott) ---

# Webszerver: gyökér
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

app = web.Application()
app.router.add_get("/", handle)
app.router.add_get("/reaction_roles.json", get_json)

async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

async def main():
    print("✅ Bot indítás folyamatban...")
    print("DISCORD_TOKEN:", "✅ beállítva" if DISCORD_TOKEN else "❌ HIÁNYZIK")
    await start_webserver()
    try:
        await bot.start(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ Hiba a bot indításakor: {e}")

if __name__ == "__main__":
    asyncio.run(main())
