import discord
from discord.ext import commands
import os
import json
from aiohttp import web
import asyncio
import openai
from functools import partial

# Tokenek Render environment-ből
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# OpenAI beállítás
openai.api_key = OPENAI_API_KEY

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

# Bot példány
bot = commands.Bot(command_prefix='!', intents=intents)

# Fájlok
ALLOWED_GUILDS_FILE = "Reaction.ID.txt"
REACTION_ROLES_FILE = "reaction_roles.json"
ACTIVATE_INFO_FILE = "activateinfo.txt"

# Engedélyezett szerverek betöltése
def load_allowed_guilds():
    if not os.path.exists(ALLOWED_GUILDS_FILE):
        return set()
    with open(ALLOWED_GUILDS_FILE, "r", encoding="utf-8") as f:
        ids = set()
        for line in f:
            s = line.strip()
            if s.isdigit():
                ids.add(int(s))
        return ids

allowed_guilds = load_allowed_guilds()

# Reaction roles betöltése (robosztusabb)
if os.path.exists(REACTION_ROLES_FILE):
    with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
        try:
            raw = json.load(f)
            reaction_roles = {}
            for gid_s, msgs in raw.items():
                try:
                    gid = int(gid_s)
                except:
                    continue
                reaction_roles[gid] = {}
                if isinstance(msgs, dict):
                    for mid_s, emoji_map in msgs.items():
                        try:
                            mid = int(mid_s)
                        except:
                            continue
                        reaction_roles[gid][mid] = emoji_map
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

# Globális parancsellenőrzés (kivéve !dbactivate)
@bot.check
async def guild_permission_check(ctx):
    # Ha nincs parancs objektum (ritka), engedjük
    if ctx.command is None:
        return True
    # dbactivate mindenhol fusson
    if ctx.command.name == "dbactivate":
        return True
    # minden más parancs csak engedélyezett szervereken fusson
    return ctx.guild is not None and ctx.guild.id in allowed_guilds

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

# !dbhelp parancs – összes parancs listázása blokkszövegben
@bot.command()
async def dbhelp(ctx):
    help_text = """```
📌 Elérhető parancsok:
!addreaction <üzenet_id> <emoji> <szerepkör>   - Reakció hozzáadása (admin)
!removereaction <üzenet_id> <emoji>           - Reakció eltávolítása (admin)
!listreactions                                - Reakciók listázása (admin)
!dbactivate                                   - Aktivációs infó megtekintése
!g <kérdés>                                   - ChatGPT-4 válasz (mindenkinek engedélyezett szerveren)
!dbhelp                                       - Ez a súgó
```"""
    await ctx.send(help_text)

# !dbactivate – tartalom megjelenítése az activateinfo.txt-ből
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

# Új !g parancs – ChatGPT-4 válasz (mindenkinek az engedélyezett szervereken)
@bot.command()
async def g(ctx, *, prompt: str):
    # Kizárólag engedélyezett szervereken működjön
    if not ctx.guild or ctx.guild.id not in allowed_guilds:
        await ctx.send("⚠️ Ez a parancs csak engedélyezett szervereken használható.")
        return

    if not OPENAI_API_KEY:
        await ctx.send("❌ Az OPENAI_API_KEY nincs beállítva a környezetben.")
        return

    await ctx.trigger_typing()

    def call_openai():
        return openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )

    try:
        # Ne blokkoljuk az eseményhurokot: futtatjuk executorban
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, call_openai)

        # Robustabb kinyerés, különböző openai-pakk verziókhoz
        reply = ""
        if response and getattr(response, "choices", None):
            choice = response.choices[0]
            if isinstance(choice, dict):
                reply = choice.get("message", {}).get("content") or choice.get("text") or ""
            else:
                try:
                    reply = choice.message["content"]
                except Exception:
                    reply = getattr(choice, "text", "") or ""
        else:
            reply = ""

        if not reply:
            await ctx.send("⚠️ Nem érkezett érdemi válasz a ChatGPT-től.")
            return

        # Üzenetfelosztás 2000 char felett
        for chunk in [reply[i:i+2000] for i in range(0, len(reply), 2000)]:
            await ctx.send(chunk)

    except Exception as e:
        await ctx.send(f"❌ Hiba történt a ChatGPT hívása közben: {e}")

# Reakciókezelés
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

# Webszerver: gyökér
async def handle(request):
    return web.Response(text="✅ DarkyBot él!", content_type='text/html')

# JSON megtekintő – nyersen, szépen formázva
async def get_json(request):
    if not os.path.exists(REACTION_ROLES_FILE):
        return web.json_response({}, status=200, dumps=lambda x: json.dumps(x, ensure_ascii=False, indent=4))

    with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {}
    return web.json_response(data, status=200, dumps=lambda x: json.dumps(x, ensure_ascii=False, indent=4))

# Webserver setup
app = web.Application()
app.router.add_get("/", handle)
app.router.add_get("/reaction_roles.json", get_json)

async def start_webserver():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# Indítás
async def main():
    print("✅ Bot indítás folyamatban...")
    print("DISCORD_TOKEN:", "✅ beállítva" if DISCORD_TOKEN else "❌ HIÁNYZIK")
    print("OPENAI_API_KEY:", "✅ beállítva" if OPENAI_API_KEY else "❌ HIÁNYZIK")

    await start_webserver()

    try:
        await bot.start(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ Hiba a bot indításakor: {e}")

if __name__ == "__main__":
    asyncio.run(main())
