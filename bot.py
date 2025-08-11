import discord
from discord.ext import commands
import asyncio
import aiohttp
import json
import os

# Twitch API adatok (Render environment variables)
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_ACCESS_TOKEN = os.getenv("TWITCH_ACCESS_TOKEN")
TWITCH_LINKS_FILE = "twitch_links.json"

# Twitch linkek betöltése
if os.path.exists(TWITCH_LINKS_FILE):
    with open(TWITCH_LINKS_FILE, "r", encoding="utf-8") as f:
        try:
            twitch_links = json.load(f)  # {guild_id: {twitch_username: channel_id}}
        except json.JSONDecodeError:
            twitch_links = {}
else:
    twitch_links = {}

# Twitch linkek mentése
def save_twitch_links():
    with open(TWITCH_LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(twitch_links, f, ensure_ascii=False, indent=4)

# Twitch stream státusz tárolása
twitch_live_status = {}  # {(guild_id, twitch_username): bool}


async def check_twitch_streams(bot):
    """Időszakos Twitch stream ellenőrzés."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        for guild_id, user_map in twitch_links.items():
            for username, channel_id in user_map.items():
                url = f"https://api.twitch.tv/helix/streams?user_login={username}"
                headers = {
                    "Client-ID": TWITCH_CLIENT_ID,
                    "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}"
                }
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, headers=headers) as resp:
                            data = await resp.json()
                except Exception as e:
                    print(f"⚠️ Twitch API hiba: {e}")
                    continue

                is_live = False
                title = ""
                if "data" in data and len(data["data"]) > 0:
                    is_live = True
                    title = data["data"][0]["title"]

                key = (guild_id, username)
                was_live = twitch_live_status.get(key, False)

                # Ha most lett élő
                if is_live and not was_live:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        await channel.send(
                            f"🔴 **{username}** most élőben van a Twitch-en!\n"
                            f"🎯 Cím: {title}\n"
                            f"👉 https://twitch.tv/{username}"
                        )

                twitch_live_status[key] = is_live

        await asyncio.sleep(60)  # 1 percenként ellenőrzés


# Bot osztály, hogy setup_hook-ban indítsuk a Twitch figyelést
class MyBot(commands.Bot):
    async def setup_hook(self):
        self.loop.create_task(check_twitch_streams(self))


# Bot inicializálás
intents = discord.Intents.default()
intents.message_content = True
bot = MyBot(command_prefix="!", intents=intents)


# Twitch parancs
@bot.command()
@commands.has_permissions(administrator=True)
async def twitchlink(ctx, channel_id: int, twitch_username: str):
    """Összekapcsol egy Discord csatornát egy Twitch felhasználóval."""
    guild_id = str(ctx.guild.id)
    if guild_id not in twitch_links:
        twitch_links[guild_id] = {}
    twitch_links[guild_id][twitch_username.lower()] = channel_id
    save_twitch_links()
    await ctx.send(f"✅ Twitch értesítés beállítva: `{twitch_username}` → <#{channel_id}>")

@bot.command()
@commands.has_permissions(administrator=True)
async def twitchlist(ctx):
    """Kilistázza a beállított Twitch figyeléseket."""
    guild_id = str(ctx.guild.id)
    if guild_id not in twitch_links or not twitch_links[guild_id]:
        await ctx.send("ℹ️ Nincs beállított Twitch figyelés ezen a szerveren.")
        return
    msg = "\n".join(
        f"🎥 `{user}` → <#{channel_id}>"
        for user, channel_id in twitch_links[guild_id].items()
    )
    await ctx.send(f"📜 Twitch figyelések:\n{msg}")


# Token betöltése és indítás
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(DISCORD_TOKEN)
