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
intents.members = True          # Pour détecter les nouveaux membres
intents.message_content = True  # Pour lire les commandes
bot = commands.Bot(command_prefix="!", intents=intents)

# --- FONCTIONS DE LA BASE DE DONNÉES ---
def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Erreur lecture JSON: {e}")
        return {}

def save_db(data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Erreur écriture JSON: {e}")

# --- ÉVÉNEMENT : LANCE LE BOT ---
@bot.event
async def on_ready():
    print(f"✅ Bot opérationnel : {bot.user}")

# --- SYSTÈME DE BIENVENUE & ENREGISTREMENT AUTO ---
@bot.event
async def on_member_join(member):
    try:
        await member.send(f"Salut {member.name} ! Bienvenue sur **{member.guild.name}** 🎉\n"
                          "Réponds à ces questions pour ton enregistrement :")
        
        questions = [
            "Quel est ton pseudo AS ?",
            "Ton secteur de jeux ? (Donne uniquement le numéro de département, ex: 75, 13, 2A) 🌍",
            "Qu'est-ce qui t'a motivé à nous rejoindre ? 🤔",
            "Joues-tu à d'autres jeux ? 🎮"
        ]
        
        reponses = []
        for q in questions:
            await member.send(q)
            def check(m):
                return m.author == member and isinstance(m.channel, discord.DMChannel)
            
            try:
                msg = await bot.wait_for("message", check=check, timeout=600.0)
                reponses.append(msg.content)
            except asyncio.TimeoutError:
                return await member.send("⏱️ Temps écoulé. Rejoint le serveur pour recommencer.")

        # Validation du secteur (réponse à la 2ème question)
        secteur = reponses[1].strip().upper()
        
        if secteur not in DEPARTEMENTS_VALIDES:
            await member.send(f"❌ '{secteur}' n'est pas un département valide. Ton inscription automatique a échoué.")
        else:
            db = load_db()
            if secteur not in db: db[secteur] = []
            if member.id not in db[secteur]:
                db[secteur].append(member.id)
                save_db(db)
            await member.send(f"✅ Tu as été enregistré dans le secteur **{secteur}**.")

        # Envoi du récapitulatif au staff
        salon = bot.get_channel(ID_SALON_REPONSES)
        if salon:
            embed = discord.Embed(title=f"🆕 Nouveau membre : {member.name}", color=discord.Color.green())
            for i, q in enumerate(questions):
                embed.add_field(name=q, value=reponses[i], inline=False)
            await salon.send(embed=embed)

    except Exception as e:
        print(f"Erreur on_member_join pour {member.name}: {e}")

# --- COMMANDE : RENFORTS ---
@bot.command()
async def renforts(ctx):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        await ctx.send("🚨 **Demande de renfort**\nQuel est le **Numéro d'intervention** ?")
        n_inter = (await bot.wait_for("message", check=check, timeout=60.0)).content
        
        await ctx.send("Quels **véhicules** sont demandés ?")
        vehicules = (await bot.wait_for("message", check=check, timeout=60.0)).content
        
        await ctx.send("📍 Quel **Département** ? (ex: 75, 13, 2B)")
        secteur = (await bot.wait_for("message", check=check, timeout=60.0)).content.strip().upper()

        if secteur not in DEPARTEMENTS_VALIDES:
            return await ctx.send(f"❌ Secteur `{secteur}` invalide. Utilise un numéro de département officiel.")

        db = load_db()
        membres_ids = db.get(secteur, [])
        mentions = " ".join([f"<@{uid}>" for uid in membres_ids])

        embed = discord.Embed(title="🚨 ALERTE RENFORTS 🚨", color=discord.Color.red())
        embed.add_field(name="Secteur", value=f"📍 {secteur}", inline=True)
        embed.add_field(name="N° Inter", value=n_inter, inline=True)
        embed.add_field(name="Véhicules", value=vehicules, inline=False)
        embed.set_footer(text=f"Demandé par {ctx.author.display_name}")

        await ctx.send(content=f"📢 {mentions if mentions else 'Aucun personnel enregistré'}", embed=embed)

    except asyncio.TimeoutError:
        await ctx.send("❌ Commande annulée pour inactivité.")

# --- COMMANDES DE GESTION (ADMIN) ---
@bot.command()
@commands.has_permissions(administrator=True)
async def ajouter_secteur(ctx, membre: discord.Member, secteur: str):
    secteur = secteur.strip().upper()
    if secteur not in DEPARTEMENTS_VALIDES:
        return await ctx.send("❌ Département invalide (01-95, 2A, 2B).")

    db = load_db()
    if secteur not in db: db[secteur] = []
    if membre.id not in db[secteur]:
        db[secteur].append(member.id)
        save_db(db)
        await ctx.send(f"✅ {membre.display_name} ajouté au **{secteur}**.")
    else:
        await ctx.send("Déjà présent.")

@bot.command()
@commands.has_permissions(administrator=True)
async def retirer_secteur(ctx, membre: discord.Member, secteur: str):
    secteur = secteur.strip().upper()
    db = load_db()
    if secteur in db and membre.id in db[secteur]:
        db[secteur].remove(membre.id)
        save_db(db)
        await ctx.send(f"🗑️ {membre.display_name} retiré du secteur **{secteur}**.")
    else:
        await ctx.send("Membre introuvable dans ce secteur.")

@bot.command()
async def voir_base(ctx):
    db = load_db()
    if not db: return await ctx.send("La base est vide.")
    
    embed = discord.Embed(title="📋 Répertoire des Secteurs", color=discord.Color.blue())
    for s in sorted(db.keys()):
        mentions = ", ".join([f"<@{uid}>" for uid in db[s]])
        if mentions:
            embed.add_field(name=f"📍 Secteur {s}", value=mentions, inline=False)
    
    await ctx.send(embed=embed)

# --- LANCEMENT ---
keep_alive() # Maintient le bot en ligne via ton script keep_alive.py
bot.run(TOKEN)
