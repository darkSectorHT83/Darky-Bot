import discord
from discord.ext import commands
import os, json, asyncio
from aiohttp import web

# Token
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Intents
intents = discord.Intents.default()
intents.message_content = intents.reactions = intents.guilds = intents.members = True

# Bot
bot = commands.Bot(command_prefix='!', intents=intents)

# Fájlnevek
ALLOWED_GUILDS_FILE = "Reaction.ID.txt"
REACTION_ROLES_FILE = "reaction_roles.json"
ACTIVATE_INFO_FILE = "activateinfo.txt"

# Engedélyezett szerverek
def load_allowed_guilds():
    if not os.path.exists(ALLOWED_GUILDS_FILE): return set()
    with open(ALLOWED_GUILDS_FILE, "r", encoding="utf-8") as f:
        return {int(line.strip()) for line in f if line.strip().isdigit()}
allowed_guilds = load_allowed_guilds()

# Reakció szerepkörök betöltése
def load_reaction_roles():
    if os.path.exists(REACTION_ROLES_FILE):
        try:
            with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
                return {int(gid): {int(mid): em for mid, em in msgs.items()} for gid, msgs in json.load(f).items()}
        except json.JSONDecodeError:
            pass
    return {}
reaction_roles = load_reaction_roles()

def save_reaction_roles():
    with open(REACTION_ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump({str(gid): {str(mid): em for mid, em in msgs.items()} for gid, msgs in reaction_roles.items()}, f, ensure_ascii=False, indent=4)

# Globális engedélyellenőrzés (!dbactivate kivétel)
@bot.check
async def guild_check(ctx):
    return ctx.command.name == "dbactivate" or (ctx.guild and ctx.guild.id in allowed_guilds)

@bot.event
async def on_ready():
    print(f"✅ Bejelentkezve: {bot.user} ({bot.user.id})")

# --- Parancsok ---

@bot.command()
@commands.has_permissions(administrator=True)
async def addreaction(ctx, message_id: int, emoji: str, *, role_name: str):
    gid = ctx.guild.id
    reaction_roles.setdefault(gid, {}).setdefault(message_id, {})[emoji] = role_name
    save_reaction_roles()

    try:
        msg = await ctx.channel.fetch_message(message_id)
        await msg.add_reaction(emoji)
    except Exception as e:
        await ctx.send(f"✅ Hozzáadva, de nem sikerült reagálni: {e}")
    else:
        await ctx.send(f"🔧 `{emoji}` → `{role_name}` (ID: `{message_id}`)")

@bot.command()
@commands.has_permissions(administrator=True)
async def removereaction(ctx, message_id: int, emoji: str):
    gid = ctx.guild.id
    if gid in reaction_roles and message_id in reaction_roles[gid] and emoji in reaction_roles[gid][message_id]:
        del reaction_roles[gid][message_id][emoji]
        if not reaction_roles[gid][message_id]: del reaction_roles[gid][message_id]
        if not reaction_roles[gid]: del reaction_roles[gid]
        save_reaction_roles()
        await ctx.send(f"❌ `{emoji}` eltávolítva (ID: `{message_id}`)")
    else:
        await ctx.send("⚠️ Nem található az emoji vagy üzenet.")

@bot.command()
@commands.has_permissions(administrator=True)
async def listreactions(ctx):
    data = reaction_roles.get(ctx.guild.id, {})
    if not data:
        return await ctx.send("ℹ️ Nincs beállított reakció ebben a szerverben.")
    msg = "\n".join(
        f"📩 Üzenet ID: `{mid}`\n" + "\n".join(f"   {e} → `{r}`" for e, r in em.items())
        for mid, em in data.items()
    )
    await ctx.send(msg)

@bot.command()
async def dbhelp(ctx):
    await ctx.send("""```
📌 Elérhető parancsok:
!addreaction <üzenet_id> <emoji> <szerepkör>   - Reakció hozzáadása
!removereaction <üzenet_id> <emoji>           - Reakció eltávolítása
!listreactions                                - Reakciók listázása
!dbactivate                                   - Aktivációs infó megtekintése
!dbhelp                                       - Ez a súgó
```""")

@bot.command()
async def dbactivate(ctx):
    if not os.path.exists(ACTIVATE_INFO_FILE):
        return await ctx.send("⚠️ Az activateinfo.txt fájl nem található.")
    with open(ACTIVATE_INFO_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
    await ctx.send(content or "⚠️ Az activateinfo.txt fájl üres.")

# --- Reakció események ---

async def handle_reaction(payload, add=True):
    if payload.user_id == bot.user.id or payload.guild_id not in allowed_guilds:
        return
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id) if guild else None
    emoji = str(payload.emoji)
    role_name = reaction_roles.get(payload.guild_id, {}).get(payload.message_id, {}).get(emoji)
    role = discord.utils.get(guild.roles, name=role_name) if guild else None
    if member and role:
        await (member.add_roles(role) if add else member.remove_roles(role))
        print(f"{'✅' if add else '❌'} {member} {'kapta meg' if add else 'elvesztette'}: {role.name}")

@bot.event
async def on_raw_reaction_add(payload):
    await handle_reaction(payload, add=True)

@bot.event
async def on_raw_reaction_remove(payload):
    await handle_reaction(payload, add=False)

# --- Webserver ---

async def handle_root(request):
    return web.Response(text="✅ DarkyBot él!", content_type='text/html')

async def handle_json(request):
    try:
        with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    return web.json_response(data, dumps=lambda x: json.dumps(x, ensure_ascii=False, indent=4))

app = web.Application()
app.router.add_get("/", handle_root)
app.router.add_get("/reaction_roles.json", handle_json)

async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()

# --- Főfüggvény ---
async def main():
    print("✅ Bot indítása...")
    await start_webserver()
    if DISCORD_TOKEN:
        await bot.start(DISCORD_TOKEN)
    else:
        print("❌ Nincs DISCORD_TOKEN beállítva!")

if __name__ == "__main__":
    asyncio.run(main())
