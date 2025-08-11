import discord
from discord.ext import commands
import os
import json
from aiohttp import web
import asyncio
import aiohttp
import traceback

# ------------------------
# ENV / Konfiguráció
# ------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_ACCESS_TOKEN = os.getenv("TWITCH_ACCESS_TOKEN")

# Fájlnevek
ALLOWED_GUILDS_FILE = "Reaction.ID.txt"
REACTION_ROLES_FILE = "reaction_roles.json"
ACTIVATE_INFO_FILE = "activateinfo.txt"
TWITCH_FILE = "twitch_streams.json"
TWITCH_INTERNAL_FILE = "twitch_streams_state.json"

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
        self.loop.create_task(twitch_watcher())

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
# Jogosultság checkek
# ------------------------
def admin_or_role(role_name):
    async def predicate(ctx):
        return ctx.author.guild_permissions.administrator or \
               discord.utils.get(ctx.author.roles, name=role_name)
    return commands.check(predicate)

# ------------------------
# Reaction roles betöltése / mentése
# ------------------------
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

# ------------------------
# Twitch streamerek betöltése / mentése
# ------------------------
def load_twitch_streamers():
    if not os.path.exists(TWITCH_FILE):
        return []
    with open(TWITCH_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            if isinstance(data, dict) and "streamers" in data:
                return data["streamers"]
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            return []

def save_twitch_streamers(list_obj):
    with open(TWITCH_FILE, "w", encoding="utf-8") as f:
        json.dump(list_obj, f, ensure_ascii=False, indent=4)
    # Mentés ideiglenes fájlba is
    with open(TWITCH_INTERNAL_FILE, "w", encoding="utf-8") as f:
        json.dump(list_obj, f, ensure_ascii=False, indent=4)

def build_twitch_state_from_file():
    arr = load_twitch_streamers()
    state = {}
    for item in arr:
        try:
            uname = item.get("username", "").lower()
            cid = int(item.get("channel_id"))
            if uname:
                state[uname] = {"channel_id": cid, "live": False}
        except:
            continue
    return state

twitch_streams = build_twitch_state_from_file()

# ------------------------
# Twitch API lekérdezés
# ------------------------
async def is_twitch_live(username):
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
                    return False, None
                data = await resp.json()
                if data.get("data"):
                    return True, data["data"][0]
                return False, None
    except:
        return False, None

# ------------------------
# Twitch watcher
# ------------------------
async def twitch_watcher():
    await bot.wait_until_ready()
    print("🔁 Twitch watcher elindult.")
    global twitch_streams
    twitch_streams = build_twitch_state_from_file()
    while not bot.is_closed():
        for username, info in list(twitch_streams.items()):
            live, stream_data = await is_twitch_live(username)
            if live and not info.get("live", False):
                channel = bot.get_channel(info["channel_id"])
                if channel:
                    title = stream_data.get("title", "Ismeretlen cím")
                    user_name = stream_data.get("user_name", username)
                    game_name = stream_data.get("game_name", "Ismeretlen játék")
                    viewer_count = stream_data.get("viewer_count", 0)
                    thumbnail = stream_data.get("thumbnail_url", "").replace("{width}", "1280").replace("{height}", "720")

                    embed = discord.Embed(
                        title=f"{user_name} most élő a Twitch-en!",
                        description=f"**{title}**\nhttps://twitch.tv/{user_name}",
                        color=0x9146FF
                    )
                    embed.add_field(name="Játék", value=game_name, inline=True)
                    embed.add_field(name="Nézők", value=str(viewer_count), inline=True)
                    if thumbnail:
                        embed.set_image(url=thumbnail)
                    await channel.send(embed=embed)
                twitch_streams[username]["live"] = True
            elif not live and info.get("live", False):
                twitch_streams[username]["live"] = False
        await asyncio.sleep(60)

# ------------------------
# Twitch parancsok (Admin vagy LightSector II)
# ------------------------
@bot.command()
@admin_or_role("LightSector II")
async def twitchadd(ctx, username: str, channel_id: int):
    username = username.lower()
    arr = load_twitch_streamers()
    for item in arr:
        if item.get("username", "").lower() == username:
            item["channel_id"] = channel_id
            save_twitch_streamers(arr)
            twitch_streams[username] = {"channel_id": channel_id, "live": False}
            await ctx.send(f"Frissítve: {username} → <#{channel_id}>")
            return
    arr.append({"username": username, "channel_id": channel_id})
    save_twitch_streamers(arr)
    twitch_streams[username] = {"channel_id": channel_id, "live": False}
    await ctx.send(f"Hozzáadva: {username} → <#{channel_id}>")

@bot.command()
@admin_or_role("LightSector II")
async def twitchremove(ctx, username: str):
    username = username.lower()
    arr = load_twitch_streamers()
    new_arr = [i for i in arr if i.get("username", "").lower() != username]
    if len(new_arr) == len(arr):
        await ctx.send("Nincs ilyen streamer.")
        return
    save_twitch_streamers(new_arr)
    twitch_streams.pop(username, None)
    await ctx.send(f"Törölve: {username}")

@bot.command()
@admin_or_role("LightSector II")
async def twitchlist(ctx):
    arr = load_twitch_streamers()
    if not arr:
        await ctx.send("Nincs figyelt Twitch csatorna.")
        return
    msg = "**Figyelt Twitch csatornák:**\n" + "\n".join(
        f"🎮 **{i['username']}** → <#{i['channel_id']}>" for i in arr
    )
    await ctx.send(msg)

# ------------------------
# Reaction Role parancsok (Admin vagy LightSector III)
# ------------------------
@bot.command()
@admin_or_role("LightSector III")
async def addreaction(ctx, message_id: int, emoji: str, *, role_name: str):
    guild_id = ctx.guild.id
    if guild_id not in reaction_roles:
        reaction_roles[guild_id] = {}
    if message_id not in reaction_roles[guild_id]:
        reaction_roles[guild_id][message_id] = {}
    reaction_roles[guild_id][message_id][emoji] = role_name
    save_reaction_roles()
    message = await ctx.channel.fetch_message(message_id)
    await message.add_reaction(emoji)
    await ctx.send(f"{emoji} → {role_name} hozzáadva.")

@bot.command()
@admin_or_role("LightSector III")
async def removereaction(ctx, message_id: int, emoji: str):
    guild_id = ctx.guild.id
    if guild_id in reaction_roles and message_id in reaction_roles[guild_id]:
        reaction_roles[guild_id][message_id].pop(emoji, None)
        save_reaction_roles()
        await ctx.send(f"{emoji} eltávolítva.")
    else:
        await ctx.send("Nem található.")

@bot.command()
@admin_or_role("LightSector III")
async def listreactions(ctx):
    guild_id = ctx.guild.id
    if guild_id not in reaction_roles:
        await ctx.send("Nincs beállított reakció.")
        return
    msg = "\n".join(
        f"Üzenet {mid}: " + ", ".join(f"{em}→{role}" for em, role in ems.items())
        for mid, ems in reaction_roles[guild_id].items()
    )
    await ctx.send(msg)

# ------------------------
# dbhelp és dbactivate
# ------------------------
@bot.command()
async def dbhelp(ctx):
    if not os.path.exists("help.txt"):
        await ctx.send("⚠️ A help.txt nem található.")
        return
    with open("help.txt", "r", encoding="utf-8") as f:
        help_text = f.read()
    await ctx.send(f"```{help_text}```")

@bot.command()
async def dbactivate(ctx):
    if not os.path.exists(ACTIVATE_INFO_FILE):
        await ctx.send("⚠️ Az activateinfo.txt nem található.")
        return
    with open(ACTIVATE_INFO_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    await ctx.send(content)

# ------------------------
# Webserver
# ------------------------
async def handle(request):
    return web.Response(text="Darky Bot: ONLINE", content_type="text/html")

app = web.Application()
app.router.add_get("/", handle)

async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# ------------------------
# Main
# ------------------------
async def main():
    await start_webserver()
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
