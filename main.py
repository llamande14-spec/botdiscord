import discord
from discord.ext import commands
import os
import sys
import asyncio
import json
from keep_alive import keep_alive

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
ID_SALON_REPONSES = 1433793778111484035
DB_FILE = "secteurs.json"

# Liste des départements (on s'assure qu'ils sont au format '01', '02'...)
DEPARTEMENTS_VALIDES = [str(i).zfill(2) for i in range(1, 96)] + ["2A", "2B"]

intents = discord.Intents.default()
intents.members = True          
intents.message_content = True  
bot = commands.Bot(command_prefix="!", intents=intents)

# --- GESTION JSON (LES DEUX FONCTIONS SONT ICI) ---
def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)
        print("✅ Données sauvegardées dans secteurs.json")

@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")

# --- BIENVENUE & ENREGISTREMENT ---
@bot.event
async def on_member_join(member):
    try:
        await member.send(f"Salut {member.name} ! Bienvenue sur **{member.guild.name}** 🎉")
        questions = [
            "Quel est ton pseudo AS ?",
            "Ton secteur (Département, ex: 75, 13, 2A) ?",
            "Ta motivation ?",
            "Autres jeux ?"
        ]
        reponses = []
        for q in questions:
            await member.send(q)
            def check(m): return m.author == member and isinstance(m.channel, discord.DMChannel)
            try:
                msg = await bot.wait_for("message", check=check, timeout=600.0)
                reponses.append(msg.content)
            except asyncio.TimeoutError: return

        # Correction : on rajoute un '0' si l'utilisateur tape '5' au lieu de '05'
        secteur = reponses[1].strip().upper()
        if secteur.isdigit() and len(secteur) == 1:
            secteur = "0" + secteur

        if secteur in DEPARTEMENTS_VALIDES:
            db = load_db()
            if secteur not in db: db[secteur] = []
            if member.id not in db[secteur]:
                db[secteur].append(member.id)
                save_db(db)
            await member.send(f"✅ Enregistré dans le secteur **{secteur}**.")
    except Exception as e: print(f"Erreur join: {e}")

# --- COMMANDES ---
@bot.command()
@commands.has_permissions(administrator=False)
async def ajouter_secteur(ctx, membre: discord.Member, secteur: str):
    secteur = secteur.strip().upper()
    # Correction automatique du format (5 -> 05)
    if secteur.isdigit() and len(secteur) == 1:
        secteur = "0" + secteur

    if secteur not in DEPARTEMENTS_VALIDES:
        return await ctx.send(f"❌ `{secteur}` n'est pas un département valide.")

    db = load_db()
    if secteur not in db: db[secteur] = []
    if membre.id not in db[secteur]:
        db[secteur].append(membre.id)
        save_db(db)
        await ctx.send(f"✅ {membre.display_name} ajouté au **{secteur}**.")
    else:
        await ctx.send("Déjà dans la base.")

@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user)
async def voir_base(ctx):
    db = load_db()
    if not db:
        return await ctx.send("Base vide.")
    
    embed = discord.Embed(title="📋 Répertoire", color=discord.Color.blue())
    for s in sorted(db.keys()):
        mentions = ", ".join([f"<@{uid}>" for uid in db[s]])
        if mentions:
            embed.add_field(name=f"📍 {s}", value=mentions, inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def renforts(ctx):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    try:
        await ctx.send("🚨 N° Inter ?")
        n_inter = (await bot.wait_for("message", check=check, timeout=60)).content
        await ctx.send("📍 Département ?")
        secteur = (await bot.wait_for("message", check=check, timeout=60)).content.strip().upper()
        
        if secteur.isdigit() and len(secteur) == 1: secteur = "0" + secteur

        db = load_db()
        mentions = " ".join([f"<@{uid}>" for uid in db.get(secteur, [])])
        await ctx.send(f"🚨 **RENFORTS {secteur}** (Inter {n_inter})\n📢 {mentions if mentions else 'Aucun personnel'}")
    except: pass

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Attends {error.retry_after:.1f}s.")

keep_alive()
bot.run(TOKEN)
