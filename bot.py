import discord
from discord.ext import commands
import os
import json
from aiohttp import web, ClientSession
import asyncio

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

ALLOWED_GUILDS_FILE = "Reaction.ID.txt"
REACTION_ROLES_FILE = "reaction_roles.json"
ACTIVATE_INFO_FILE = "activateinfo.txt"
FNNEW_FILE = "fnnew.txt"

def load_allowed_guilds():
    if not os.path.exists(ALLOWED_GUILDS_FILE):
        return set()
    with open(ALLOWED_GUILDS_FILE, "r", encoding="utf-8") as f:
        return set(int(line.strip()) for line in f if line.strip().isdigit())

allowed_guilds = load_allowed_guilds()

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

@bot.check
async def guild_permission_check(ctx):
    if ctx.command.name == "dbactivate":
        return True
    return ctx.guild and ctx.guild.id in allowed_guilds

@bot.event
async def on_ready():
    print(f"✅ Bejelentkezett: {bot.user.name}")

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
!dbactivate                                   - Aktivációs infó megtekintése
!fnnew                                        - Fortnite Shop új itemek
!fncn                                         - Fortnite Shop új itemek beágyazva
!dbhelp                                       - Ez a súgó
```"""
    await ctx.send(help_text)

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

@bot.command()
async def fnnew(ctx):
    if ctx.guild and ctx.guild.id not in allowed_guilds:
        return

    if not os.path.exists(FNNEW_FILE):
        await ctx.send("⚠️ A fnnew.txt fájl nem található.")
        return

    with open(FNNEW_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        await ctx.send("ℹ️ A fnnew.txt fájl üres.")
        return

    await ctx.send(content)

# ✅ VÉGLEGESEN JAVÍTOTT !fncn PARANCS (Shop kiemelt itemekkel)
@bot.command()
async def fncn(ctx):
    if ctx.guild and ctx.guild.id not in allowed_guilds:
        return

    url = "https://fortnite-api.com/v2/shop/br"

    async with ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                await ctx.send("⚠️ Hiba történt az API lekérésekor.")
                return

            data = await resp.json()

    shop_entries = data.get("data", {}).get("featured", {}).get("entries", [])
    if not shop_entries:
        await ctx.send("ℹ️ Nem található kiemelt shop item.")
        return

    embed = discord.Embed(
        title="🛍️ Fortnite Shop új itemek beágyazva",
        description="Kiemelt shop itemek listája:",
        color=discord.Color.green()
    )

    for entry in shop_entries[:10]:  # legfeljebb 10 item
        items = entry.get("items", [])
        for item in items:
            name = item.get("name", "Névtelen")
            item_type = item.get("type", {}).get("value", "Ismeretlen")
            embed.add_field(name=name, value=f"Típus: {item_type}", inline=True)

    await ctx.send(embed=embed)

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
