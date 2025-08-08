import discord
from discord.ext import commands
import json
import os
from aiohttp import web

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

REACTION_FILE = "reaction_roles.json"
ID_FILE = "Reaction.ID.txt"
ALLOW_FILE = "all_server_allow.txt"
COMMANDS_ALLOW_FILE = "commands.allow.txt"
COMMANDS_RANK_FILE = "commands_rank.txt"

# ======== Jogosultságkezelés ========
def is_server_allowed(server_id):
    try:
        with open(ALLOW_FILE, "r") as f:
            if f.read().strip() == "1":
                return True
    except:
        pass
    try:
        with open(ID_FILE, "r") as f:
            return str(server_id) in f.read().splitlines()
    except:
        return False

def is_user_allowed(ctx):
    if ctx.author.guild_permissions.administrator:
        return True
    try:
        with open(COMMANDS_ALLOW_FILE, "r") as f:
            if f.read().strip() == "1":
                with open(COMMANDS_RANK_FILE, "r") as rf:
                    allowed_roles = [line.strip() for line in rf]
                    return any(role.name in allowed_roles for role in ctx.author.roles)
    except:
        pass
    return False

# ======== Reakciók betöltése ========
def load_reactions():
    if os.path.exists(REACTION_FILE):
        with open(REACTION_FILE, "r") as f:
            return json.load(f)
    return {}

def save_reactions(data):
    with open(REACTION_FILE, "w") as f:
        json.dump(data, f, indent=4)

reactions = load_reactions()

# ======== Parancsok ========
@bot.event
async def on_ready():
    print(f'Bejelentkezve: {bot.user}')

@bot.command()
async def dbactivate(ctx):
    await ctx.send("✅ **A Darky Bot aktív ezen a szerveren!**")

@bot.command()
async def dbhelp(ctx):
    if not is_server_allowed(ctx.guild.id):
        return
    embed = discord.Embed(title="📘 Darky Bot Súgó", description="Használható parancsok:", color=0x3498db)
    embed.add_field(name="!addreaction <üzenet_id> <emoji> <szerep>", value="Szerepkör hozzárendelése emojihoz", inline=False)
    embed.add_field(name="!removereaction <üzenet_id> <emoji>", value="Szerepkör törlése emojihoz", inline=False)
    embed.add_field(name="!listreactions", value="Összes regisztrált reakció megtekintése", inline=False)
    embed.add_field(name="!dbactivate", value="Bot aktiválása az adott szerveren", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def addreaction(ctx, message_id: int, emoji, role: discord.Role):
    if not is_server_allowed(ctx.guild.id) or not is_user_allowed(ctx):
        return
    channel = ctx.channel
    try:
        msg = await channel.fetch_message(message_id)
        await msg.add_reaction(emoji)
    except:
        await ctx.send("❌ Nem találom az üzenetet vagy az emoji hibás.")
        return
    guild_id = str(ctx.guild.id)
    if guild_id not in reactions:
        reactions[guild_id] = {}
    if str(message_id) not in reactions[guild_id]:
        reactions[guild_id][str(message_id)] = {}
    reactions[guild_id][str(message_id)][emoji] = role.id
    save_reactions(reactions)
    await ctx.send(f"✅ Hozzáadva: {emoji} → {role.name}")

@bot.command()
async def removereaction(ctx, message_id: int, emoji):
    if not is_server_allowed(ctx.guild.id) or not is_user_allowed(ctx):
        return
    guild_id = str(ctx.guild.id)
    if guild_id in reactions and str(message_id) in reactions[guild_id] and emoji in reactions[guild_id][str(message_id)]:
        del reactions[guild_id][str(message_id)][emoji]
        if not reactions[guild_id][str(message_id)]:
            del reactions[guild_id][str(message_id)]
        save_reactions(reactions)
        await ctx.send(f"❌ Törölve: {emoji}")
    else:
        await ctx.send("❌ Nem található a megadott emoji az üzenethez.")

@bot.command()
async def listreactions(ctx):
    if not is_server_allowed(ctx.guild.id) or not is_user_allowed(ctx):
        return
    guild_id = str(ctx.guild.id)
    if guild_id not in reactions:
        await ctx.send("ℹ️ Nincsenek elmentett reakciók.")
        return
    msg = "📋 **Reakció lista:**\n"
    for msg_id, emojis in reactions[guild_id].items():
        msg += f"Üzenet ID: {msg_id}\n"
        for emoji, role_id in emojis.items():
            role = ctx.guild.get_role(role_id)
            role_name = role.name if role else "Ismeretlen szerep"
            msg += f"  {emoji} → {role_name}\n"
    await ctx.send(msg)

# ======== Reakció események ========
@bot.event
async def on_raw_reaction_add(payload):
    if payload.guild_id is None:
        return
    guild_id = str(payload.guild_id)
    message_id = str(payload.message_id)
    emoji = str(payload.emoji)
    if guild_id in reactions and message_id in reactions[guild_id] and emoji in reactions[guild_id][message_id]:
        guild = bot.get_guild(payload.guild_id)
        role_id = reactions[guild_id][message_id][emoji]
        role = guild.get_role(role_id)
        member = guild.get_member(payload.user_id)
        if role and member:
            await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.guild_id is None:
        return
    guild_id = str(payload.guild_id)
    message_id = str(payload.message_id)
    emoji = str(payload.emoji)
    if guild_id in reactions and message_id in reactions[guild_id] and emoji in reactions[guild_id][message_id]:
        guild = bot.get_guild(payload.guild_id)
        role_id = reactions[guild_id][message_id][emoji]
        role = guild.get_role(role_id)
        member = guild.get_member(payload.user_id)
        if role and member:
            await member.remove_roles(role)

# ======== Webserver Renderhez ========
async def handle_root(request):
    return web.Response(text="Darky Bot fut! v1.2.4", content_type="text/html")

async def handle_json(request):
    try:
        with open(REACTION_FILE, "r") as f:
            data = json.load(f)
        return web.json_response(data)
    except:
        return web.json_response({"error": "Nem elérhető."}, status=500)

app = web.Application()
app.router.add_get("/", handle_root)
app.router.add_get("/reaction_roles.json", handle_json)

bot.loop.create_task(web._run_app(app, port=8080))

# ======== Bot indítása ========
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
