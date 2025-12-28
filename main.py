import discord
from discord.ext import commands, tasks
import os
import asyncio
import json
from keep_alive import keep_alive

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
ID_SALON_REPONSES = 1433793778111484035
ID_TON_COMPTE = 123456789012345678 # ⚠️ REMPLACE PAR TON ID DISCORD (Clic droit sur ton nom > Copier l'identifiant)
DB_FILE = "secteurs.json"

DEPARTEMENTS_VALIDES = [str(i).zfill(2) for i in range(1, 96)] + ["2A", "2B"]

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- GESTION JSON ---
def load_db():
    if not os.path.exists(DB_FILE): return {}
    try:
        with open(DB_FILE, "r") as f: return json.load(f)
    except: return {}

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- BACKUP AUTOMATIQUE (Toutes les 24h) ---
@tasks.loop(hours=24)
async def backup_automatique():
    await bot.wait_until_ready()
    user = await bot.fetch_user(ID_TON_COMPTE)
    if user and os.path.exists(DB_FILE):
        try:
            await user.send("📦 **Backup Automatique Journalière**", file=discord.File(DB_FILE))
            print("✅ Backup envoyé automatiquement.")
        except Exception as e:
            print(f"❌ Erreur envoi backup auto: {e}")

# --- ÉVÉNEMENTS ---
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    if not backup_automatique.is_running():
        backup_automatique.start()

# --- COMMANDE RESTAURER ---
@bot.command()
@commands.has_permissions(administrator=True)
async def restore(ctx):
    if not ctx.message.attachments:
        return await ctx.send("❌ Joins le fichier `secteurs.json` à ton message.")
    
    file = ctx.message.attachments[0]
    try:
        await file.save(DB_FILE)
        await ctx.send("✅ Base de données restaurée et mise à jour !")
    except Exception as e:
        await ctx.send(f"❌ Erreur: {e}")

# --- COMMANDE RENFORTS ---
@bot.command()
@commands.cooldown(1, 30, commands.BucketType.user)
async def renforts(ctx):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    try:
        await ctx.send("🚨 N° Intervention ?")
        n_inter = (await bot.wait_for("message", check=check, timeout=60)).content
        await ctx.send("📍 Département ? (ex: 75, 2B)")
        secteur = (await bot.wait_for("message", check=check, timeout=60)).content.strip().upper()
        
        if secteur.isdigit() and len(secteur) == 1: secteur = "0" + secteur
        if secteur not in DEPARTEMENTS_VALIDES: return await ctx.send("❌ Invalide.")

        db = load_db()
        mentions = " ".join([f"<@{uid}>" for uid in db.get(secteur, [])])
        
        embed = discord.Embed(title="🚨 ALERTE RENFORTS 🚨", color=discord.Color.red())
        embed.add_field(name="Secteur", value=f"📍 {secteur}", inline=True)
        embed.add_field(name="Inter", value=n_inter, inline=True)
        await ctx.send(content=f"📢 {mentions if mentions else 'Aucun personnel'}", embed=embed)
    except asyncio.TimeoutError:
        await ctx.send("❌ Trop lent.")

# --- BIENVENUE & AUTO-ENREGISTREMENT ---
@bot.event
async def on_member_join(member):
    try:
        await member.send(f"Bienvenue {member.name} ! Ton département (ex: 75, 2A) ?")
        def check(m): return m.author == member and isinstance(m.channel, discord.DMChannel)
        msg = await bot.wait_for("message", check=check, timeout=600.0)
        secteur = msg.content.strip().upper()
        if secteur.isdigit() and len(secteur) == 1: secteur = "0" + secteur

        if secteur in DEPARTEMENTS_VALIDES:
            db = load_db()
            if secteur not in db: db[secteur] = []
            if member.id not in db[secteur]:
                db[secteur].append(member.id)
                save_db(db)
            await member.send(f"✅ Enregistré au secteur {secteur}.")
    except: pass

# --- GESTION ERREURS ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Réessaie dans {error.retry_after:.1f}s.")

keep_alive()
bot.run(TOKEN)
