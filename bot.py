import discord
from discord.ext import commands
import aiohttp
import os
import json
from aiohttp import web

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

FORTNITE_API_KEY = os.getenv("FORTNITE_API_KEY")
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Betöltés reaction_roles.json-ból
reaction_roles = {}
if os.path.exists("reaction_roles.json"):
    with open("reaction_roles.json", "r") as f:
        reaction_roles = json.load(f)

# Engedélyezett szerverek betöltése
engedelyezett_szerverek = []
if os.path.exists("engedelyezett_szerverek.txt"):
    with open("engedelyezett_szerverek.txt", "r") as f:
        engedelyezett_szerverek = [int(sor.strip()) for sor in f.readlines() if sor.strip().isdigit()]

@bot.event
async def on_ready():
    print(f'✅ {bot.user} sikeresen elindult!')

@bot.command()
async def dbhelp(ctx):
    embed = discord.Embed(title="📜 Parancslista", color=0x00ff00)
    embed.add_field(name="!dbhelp", value="Parancslista megjelenítése", inline=False)
    embed.add_field(name="!fnshop", value="Mai Fortnite shop megtekintése", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def fnshop(ctx):
    if ctx.guild.id not in engedelyezett_szerverek:
        await ctx.send("❌ Ez a parancs ezen a szerveren nem engedélyezett.")
        return

    url = "https://fortniteapi.io/v2/shop?lang=hu"
    headers = {
        "Authorization": FORTNITE_API_KEY
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 401:
                await ctx.send("❌ Hibás API kulcs (401 Unauthorized).")
                return
            elif response.status == 404:
                await ctx.send("❌ Nem található a shop adat (404).")
                return
            elif response.status == 500:
                await ctx.send("❌ Szerverhiba (500). Próbáld meg később újra.")
                return
            elif response.status == 503:
                await ctx.send("❌ Az API jelenleg nem elérhető (503).")
                return
            elif response.status != 200:
                await ctx.send(f"❌ Ismeretlen hiba történt: {response.status}")
                return

            data = await response.json()

            if "shop" not in data:
                await ctx.send("❌ Nem sikerült lekérni a Fortnite shopot.")
                return

            embed = discord.Embed(
                title="🎮 Mai Fortnite Item Shop",
                description="Néhány kiemelt ajánlat:",
                color=0x00ffcc
            )

            count = 0
            for item in data["shop"]:
                if "displayName" in item and "mainImage" in item:
                    embed.add_field(
                        name=item["displayName"],
                        value=f"**Ritkaság:** {item.get('rarity', {}).get('value', 'Ismeretlen')}",
                        inline=True
                    )
                    embed.set_image(url=item["mainImage"])
                    count += 1
                if count >= 5:
                    break

            await ctx.send(embed=embed)

# Reakció szerepkiosztás (egyszerűsített)
@bot.event
async def on_raw_reaction_add(payload):
    if str(payload.message_id) in reaction_roles:
        emoji_roles = reaction_roles[str(payload.message_id)]
        if payload.emoji.name in emoji_roles:
            guild = bot.get_guild(payload.guild_id)
            if guild:
                role = guild.get_role(emoji_roles[payload.emoji.name])
                member = guild.get_member(payload.user_id)
                if role and member:
                    await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    if str(payload.message_id) in reaction_roles:
        emoji_roles = reaction_roles[str(payload.message_id)]
        if payload.emoji.name in emoji_roles:
            guild = bot.get_guild(payload.guild_id)
            if guild:
                role = guild.get_role(emoji_roles[payload.emoji.name])
                member = guild.get_member(payload.user_id)
                if role and member:
                    await member.remove_roles(role)

# Webserver Renderhez
async def handle(request):
    return web.Response(text="Darky Bot működik.")

app = web.Application()
app.router.add_get("/", handle)

# Webserver indítása háttérben
async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=8080)
    await site.start()

bot.loop.create_task(start_webserver())

# Bot indítása
bot.run(TOKEN)
