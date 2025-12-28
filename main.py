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

# Liste stricte des secteurs autorisés (01 à 95 + Corse)
DEPARTEMENTS_VALIDES = [str(i).zfill(2) for i in range(1, 96)] + ["2A", "2B"]

intents = discord.Intents.default()
intents.members = True          
intents.message_content = True  
bot = commands.Bot(command_prefix="!", intents=intents)

# --- GESTION JSON ---
def load_db():
    if not os.path.exists(DB_FILE):
        print(f"⚠️ Le fichier {DB_FILE} n'existe pas. Création d'une nouvelle base.")
        return {}
    try:
        with open(DB_FILE, "r") as f:
            data = json.load(f)
            print(f"✅ Base de données chargée : {len(data)} secteurs trouvés.")
            return data
    except json.JSONDecodeError:
        print(f"❌ Erreur critique : Le fichier {DB_FILE} est corrompu ou vide. Backup nécessaire.")
        return {}
    except Exception as e:
        print(f"❌ Erreur inconnue lors du chargement : {e}")
        return {}

# --- BIENVENUE & ENREGISTREMENT ---
@bot.event
async def on_member_join(member):
    try:
        await member.send(f"Salut {member.name} ! Bienvenue sur **{member.guild.name}** 🎉")
        
        questions = [
            "Quel est ton pseudo AS ?",
            "Ton secteur de jeux ? (Donne uniquement le numéro de département, ex: 75, 13, 2A) 🌍",
            "Qu'est-ce qui t'a motivé à nous rejoindre ? 🤔",
            "Joues-tu à d'autres jeux ? 🎮"
        ]
        
        reponses = []
        for q in questions:
            await member.send(q)
            def check(m): return m.author == member and isinstance(m.channel, discord.DMChannel)
            try:
                msg = await bot.wait_for("message", check=check, timeout=600.0)
                reponses.append(msg.content)
            except asyncio.TimeoutError: return

        secteur = reponses[1].strip().upper()
        if secteur in DEPARTEMENTS_VALIDES:
            db = load_db()
            if secteur not in db: db[secteur] = []
            if member.id not in db[secteur]:
                db[secteur].append(member.id)
                save_db(db)
            await member.send(f"✅ Enregistré dans le secteur **{secteur}**.")

        salon = bot.get_channel(ID_SALON_REPONSES)
        if salon:
            embed = discord.Embed(title=f"🆕 Nouveau membre : {member.name}", color=discord.Color.green())
            for i, q in enumerate(questions): embed.add_field(name=q, value=reponses[i], inline=False)
            await salon.send(embed=embed)
    except Exception as e: print(f"Erreur join: {e}")

# --- COMMANDE : RENFORTS (COOLDOWN : 1 fois toutes les 30 secondes par utilisateur) ---
@bot.command()
@commands.cooldown(1, 30, commands.BucketType.user)
async def renforts(ctx):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    try:
        await ctx.send("🚨 **Demande de renfort**\nN° Intervention ?")
        n_inter = (await bot.wait_for("message", check=check, timeout=60.0)).content
        await ctx.send("Quels **véhicules** ?")
        vehicules = (await bot.wait_for("message", check=check, timeout=60.0)).content
        await ctx.send("📍 Département ? (ex: 75, 2B)")
        secteur = (await bot.wait_for("message", check=check, timeout=60.0)).content.strip().upper()

        if secteur not in DEPARTEMENTS_VALIDES:
            return await ctx.send(f"❌ Secteur `{secteur}` invalide.")

        db = load_db()
        mentions = " ".join([f"<@{uid}>" for uid in db.get(secteur, [])])
        embed = discord.Embed(title="🚨 ALERTE RENFORTS 🚨", color=discord.Color.red())
        embed.add_field(name="Secteur", value=f"📍 {secteur}", inline=True)
        embed.add_field(name="N° Inter", value=n_inter, inline=True)
        embed.add_field(name="Véhicules", value=vehicules, inline=False)
        await ctx.send(content=f"📢 {mentions if mentions else 'Aucun personnel'}", embed=embed)
    except asyncio.TimeoutError: await ctx.send("❌ Trop lent !")

# --- GESTION ADMIN ---
@bot.command()
@commands.has_permissions(administrator=True)
async def ajouter_secteur(ctx, membre: discord.Member, secteur: str):
    secteur = secteur.strip().upper()
    if secteur not in DEPARTEMENTS_VALIDES: return await ctx.send("❌ Invalide.")
    db = load_db()
    if secteur not in db: db[secteur] = []
    if membre.id not in db[secteur]:
        db[secteur].append(membre.id)
        save_db(db)
        await ctx.send(f"✅ {membre.display_name} ajouté au **{secteur}**.")

@bot.command()
@commands.has_permissions(administrator=True)
async def retirer_secteur(ctx, membre: discord.Member, secteur: str):
    secteur = secteur.strip().upper()
    db = load_db()
    if secteur in db and membre.id in db[secteur]:
        db[secteur].remove(membre.id)
        save_db(db)
        await ctx.send(f"🗑️ {membre.display_name} retiré du secteur **{secteur}**.")

@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user)
async def voir_base(ctx):
    db = load_db()
    if not db: return await ctx.send("Base vide.")
    embed = discord.Embed(title="📋 Répertoire", color=discord.Color.blue())
    for s in sorted(db.keys()):
        mentions = ", ".join([f"<@{uid}>" for uid in db[s]])
        if mentions: embed.add_field(name=f"📍 {s}", value=mentions, inline=False)
    await ctx.send(embed=embed)

# --- GESTION DES ERREURS DE COOLDOWN ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Calme-toi ! Réessaie dans **{error.retry_after:.1f}** secondes.")

keep_alive()
bot.run(TOKEN)
