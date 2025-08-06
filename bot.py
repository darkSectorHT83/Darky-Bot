import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Reakció-szerepkör adatbázis
reaction_roles = {}

# A Reaction.ID.txt fájl betöltése
ALLOWED_SERVERS_FILE = "Reaction.ID.txt"

def load_allowed_servers():
    if not os.path.exists(ALLOWED_SERVERS_FILE):
        return []
    with open(ALLOWED_SERVERS_FILE, "r") as f:
        return [int(line.strip()) for line in f if line.strip().isdigit()]

def is_guild_allowed(ctx):
    allowed_servers = load_allowed_servers()
    return ctx.guild.id in allowed_servers

@bot.event
async def on_ready():
    print(f"Bejelentkezve: {bot.user}")

@bot.command()
@commands.has_permissions(administrator=True)
async def addreaction(ctx, message_id: int, emoji: str, role: discord.Role):
    if not is_guild_allowed(ctx):
        await ctx.send("❌ Ez a szerver nincs engedélyezve a bot használatára.")
        return

    guild_id = ctx.guild.id
    if guild_id not in reaction_roles:
        reaction_roles[guild_id] = {}
    if message_id not in reaction_roles[guild_id]:
        reaction_roles[guild_id][message_id] = {}

    reaction_roles[guild_id][message_id][emoji] = role.name

    channel = ctx.channel
    try:
        msg = await channel.fetch_message(message_id)
        await msg.add_reaction(emoji)
        await ctx.send(f"✅ Hozzáadva: {emoji} → `{role.name}`")
    except discord.NotFound:
        await ctx.send("❌ Nem található az üzenet ID.")
    except discord.HTTPException:
        await ctx.send("❌ Nem sikerült hozzáadni a reakciót.")

@bot.command()
@commands.has_permissions(administrator=True)
async def listreactions(ctx):
    if not is_guild_allowed(ctx):
        await ctx.send("❌ Ez a szerver nincs engedélyezve a bot használatára.")
        return

    guild_id = ctx.guild.id
    if guild_id not in reaction_roles or not reaction_roles[guild_id]:
        await ctx.send("ℹ️ Nincsenek beállított reakciók ebben a szerverben.")
        return

    msg = ""
    for msg_id, emoji_map in reaction_roles[guild_id].items():
        msg += f"📩 **Üzenet ID:** `{msg_id}`\n"
        for emoji, role in emoji_map.items():
            msg += f"   {emoji} → `{role}`\n"
    await ctx.send(msg)

@bot.command()
@commands.has_permissions(administrator=True)
async def removereaction(ctx, message_id: int, emoji: str):
    if not is_guild_allowed(ctx):
        await ctx.send("❌ Ez a szerver nincs engedélyezve a bot használatára.")
        return

    guild_id = ctx.guild.id
    if guild_id in reaction_roles and message_id in reaction_roles[guild_id]:
        if emoji in reaction_roles[guild_id][message_id]:
            del reaction_roles[guild_id][message_id][emoji]
            await ctx.send(f"❌ Törölve: {emoji}")
        else:
            await ctx.send("❌ Ez a reakció nincs beállítva.")
    else:
        await ctx.send("❌ Nincs ilyen üzenethez rendelve reakció.")

@bot.event
async def on_raw_reaction_add(payload):
    if payload.guild_id is None:
        return

    allowed_servers = load_allowed_servers()
    if payload.guild_id not in allowed_servers:
        return

    if payload.guild_id in reaction_roles:
        if payload.message_id in reaction_roles[payload.guild_id]:
            emoji = str(payload.emoji)
            if emoji in reaction_roles[payload.guild_id][payload.message_id]:
                role_name = reaction_roles[payload.guild_id][payload.message_id][emoji]
                guild = bot.get_guild(payload.guild_id)
                role = discord.utils.get(guild.roles, name=role_name)
                if role:
                    member = guild.get_member(payload.user_id)
                    if member:
                        await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.guild_id is None:
        return

    allowed_servers = load_allowed_servers()
    if payload.guild_id not in allowed_servers:
        return

    if payload.guild_id in reaction_roles:
        if payload.message_id in reaction_roles[payload.guild_id]:
            emoji = str(payload.emoji)
            if emoji in reaction_roles[payload.guild_id][paylo]()_]()_
