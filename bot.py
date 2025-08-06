import discord
from discord.ext import commands

# Prefix
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# Token (saját bot tokened)
TOKEN = "SAJAT_TOKENED_IDE"

# Szerver ID-k betöltése a Reaction.ID.txt-ből
with open("Reaction.ID.txt", "r") as f:
    allowed_guilds = []
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            # Csak a számrészt vesszük a sor elejéről
            parts = line.split("#")[0].strip()
            if parts.isdigit():
                allowed_guilds.append(int(parts))

# Ellenőrző dekorátor
def is_guild_allowed():
    async def predicate(ctx):
        if ctx.guild and ctx.guild.id in allowed_guilds:
            return True
        raise commands.CheckFailure("Ez a szerver nincs engedélyezve.")
    return commands.check(predicate)

# Hibakezelő csak a CheckFailure-re
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send(
            "❌ Ez a szerver nincs engedélyezve.\n"
            "Látogasson el ide: https://www.darksector.hu"
        )
    else:
        # Más hibákat csak logolunk konzolra, nem küldünk üzenetet
        print(f"Hiba: {error}")

# Parancsok - CSAK akkor futnak, ha engedélyezett a szerver
@bot.command()
@is_guild_allowed()
async def listreactions(ctx):
    await ctx.send("ℹ️ Nincsenek beállított reakciók ebben a szerverben.")

# További parancs például:
@bot.command()
@is_guild_allowed()
async def addreaction(ctx, emoji: str):
    await ctx.send(f"✅ Reakció hozzáadva: {emoji}")

@bot.command()
@is_guild_allowed()
async def removereaction(ctx, emoji: str):
    await ctx.send(f"❌ Reakció eltávolítva: {emoji}")

# Bot indítása
bot.run(TOKEN)
