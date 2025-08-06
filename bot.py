import discord
from discord.ext import commands
import os
import json
import asyncio
from aiohttp import web

# Token a Render környezeti változóból
TOKEN = os.getenv("DISCORD_TOKEN")

# Discord jogosultságok
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

REACTION_ROLES_FILE = "reaction_roles.json"

# Reakció szerepkörök betöltése
if os.path.exists(REACTION_ROLES_FILE):
    try:
        with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
            reaction_roles = json.load(f)
    except json.JSONDecodeError:
        reaction_roles = {}
else:
    reaction_roles = {}

# Mentés fájlba
def save_reaction_roles():
    with open(REACTION_ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump(reaction_roles, f, ensure_ascii=False, indent=4)

# Bot készen áll
@bot.event
async def on_ready():
    print(f"✅ Bejelentkezve mint: {bot.user.name}")

# Parancs új reakció hozzárendelésére
@bot.command()
@commands.has_permissions(administrator=True)
async def addreaction(ctx, message_id: int, emoji: str, *, role_name: str):
    guild_id = str(ctx.guild.id)
    if guild_id not in reaction_roles:
        reaction_roles[guild_id] = {}
    if str(message_id) not in reaction_roles[guild_id]:
        reaction_roles[guild_id][str(message_id)] = {}
    reaction_roles[guild_id][str(message_id)][emoji] = role_name
    save_reaction_roles()

    message = await ctx.channel.fetch_message(message_id)
    await message.add_reaction(emoji)
    await ctx.send(f"🔧 `{emoji}` hozzáadva `{role_name}` ranghoz.")

# Parancs reakció eltávolítására
@bot.command()
@commands.has_permissions(administrator=True)
async def removereaction(ctx, message_id: int, emoji: str):
    guild_id = str(ctx.guild.id)
    if (guild_id in reaction_roles and
        str(message_id) in reaction_roles[guild_id] and
        emoji in reaction_roles[guild_id][str(message_id)]):
        del reaction_roles[guild_id][str(message_id)][emoji]
        if not reaction_roles[guild_id][str(message_id)]:
            del reaction_roles[guild_id][str(message_id)]
        if not reaction_roles[guild_id]:
            del reaction_roles[guild_id]
        save_reaction_roles()
        await ctx.send(f"❌ Reakció eltávolítva: `{emoji}`.")
    else:
        await ctx.send("⚠️ Nincs ilyen reakció.")

# Parancs listázásra
@bot.command()
@commands.has_permissions(administrator=True)
async def listreactions(ctx):
    guild_id = str(ctx.guild.id)
    if guild_id not in reaction_roles or not reaction_roles[guild_id]:
        await ctx.send("ℹ️ Nincsenek beállított reakciók.")
        return

    msg = ""
    for msg_id, emoji_map in reaction_roles[guild_id].items():
        msg += f"📩 **Üzenet ID:** `{msg_id}`\n"
        for emoji, role in emoji_map.items():
            msg += f"   {emoji} → `{role}`\n"
    await ctx.send(msg)

# Reakció hozzáadás kezelése
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    guild_id = str(payload.guild_id)
    message_id = str(payload.message_id)
    emoji = str(payload.emoji)

    if (guild_id in reaction_roles and
        message_id in reaction_roles[guild_id] and
        emoji in reaction_roles[guild_id][message_id]):

        guild = bot.get_guild(payload.guild_id)
        if guild is None:
            return

        role_name = reaction_roles[guild_id][message_id][emoji]
        role = discord.utils.get(guild.roles, name=role_name)
        member = guild.get_member(payload.user_id)

        if role and member:
            await member.add_roles(role)

# Reakció eltávolítás kezelése
@bot.event
async def on_raw_reaction_remove(payload):
    guild_id = str(payload.guild_id)
    message_id = str(payload.message_id)
    emoji = str(payload.emoji)

    if (guild_id in reaction_roles and
        message_id in reaction_roles[guild_id] and
        emoji in reaction_roles[guild_id][message_id]):

        guild = bot.get_guild(payload.guild_id)
        if guild is None:
            return

        role_name = reaction_roles[guild_id][message_id][emoji]
        role = discord.utils.get(guild.roles, name=role_name)
        member = guild.get_member(payload.user_id)

        if role and member:
            await member.remove_roles(role)

# Webszerver Renderhez
async def handle(request):
    return web.Response(text="✅ DarkyBot él!", content_type="text/html")

app = web.Application()
app.router.add_get("/", handle)

async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

async def main():
    await start_webserver()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
