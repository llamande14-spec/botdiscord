import discord
from discord.ext import commands
import os
import sys
import asyncio
import json
from keep_alive import keep_alive

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("❌ ERREUR: La variable d'environnement DISCORD_TOKEN n'est pas définie!")
    sys.exit(1)

ID_SALON_REPONSES = 1433793778111484035
DB_FILE = "secteurs.json"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- GESTION JSON ---
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

# --- QUESTIONS BIENVENUE ---
questions_bienvenue = [
    "Salut et bienvenue ! 😊 Quel est ton pseudo AS ?",
    "Ton secteur de jeux ? (numéro de département) 🌍",
    "Qu'est-ce qui t'a motivé à rejoindre le groupement ? 🤔",
    "Joues-tu à d'autres jeux? (si oui les quelles) 🎮"
]

@bot.event
async def on_ready():
    if bot.user:
        print(f"✅ Bot connecté en tant que {bot.user}")

# --- SYSTÈME DE BIENVENUE ---
@bot.event
async def on_member_join(member):
    try:
        await member.send(f"Salut {member.name} ! Bienvenue sur **{member.guild.name}** 🎉\n"
                          "J'ai quelques petites questions pour toi !")
        responses = []
        for q in questions_bienvenue:
            await member.send(q)
            def check(m):
                return m.author == member and isinstance(m.channel, discord.DMChannel)
            try:
                msg = await bot.wait_for("message", check=check, timeout=600.0)
                responses.append(msg.content)
            except asyncio.TimeoutError:
                await member.send("⏱️ Temps écoulé. Le questionnaire est annulé.")
                return 

        salon = bot.get_channel(ID_SALON_REPONSES)
        if salon and isinstance(salon, discord.TextChannel):
            formatted = "\n".join([f"**{questions_bienvenue[i]}**\n➡️ {responses[i]}" for i in range(len(questions_bienvenue))])
            await salon.send(f"🆕 **Nouveau membre : {member.mention} ({member.name})**\n\n{formatted}")
        await member.send("Merci pour tes réponses ! 💬")
    except Exception as e:
        print(f"Erreur avec {member.name}: {e}")

# --- COMMANDE RENFORTS ---
@bot.command()
async def renforts(ctx):
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        await ctx.send("🚨 **Lancement d'une demande de renfort.**\nQuel est le **Numéro d'intervention** ?")
        n_inter = (await bot.wait_for("message", check=check, timeout=60.0)).content
        
        await ctx.send("Quels **véhicules** sont demandés ?")
        vehicules = (await bot.wait_for("message", check=check, timeout=60.0)).content
        
        await ctx.send("Quel est le **Secteur** ? (ex: Paris, Nord, Sud)")
        secteur = (await bot.wait_for("message", check=check, timeout=60.0)).content
        
        await ctx.send("Quel est le **Département** ?")
        dep = (await bot.wait_for("message", check=check, timeout=60.0)).content

        # Récupération des mentions depuis la base de données
        db = load_db()
        secteur_key = secteur.strip().capitalize()
        mentions = ""
        if secteur_key in db:
            mentions = " ".join([f"<@{uid}>" for uid in db[secteur_key]])

        # Création de la fiche
        embed = discord.Embed(title="🚨 DEMANDE DE RENFORTS 🚨", color=discord.Color.red())
        embed.add_field(name="N° Intervention", value=n_inter, inline=True)
        embed.add_field(name="Département", value=dep, inline=True)
        embed.add_field(name="Secteur", value=secteur_key, inline=False)
        embed.add_field(name="Véhicules", value=vehicules, inline=False)
        
        await ctx.send(content=f"📢 {mentions if mentions else 'Aucun personnel enregistré'}", embed=embed)

    except asyncio.TimeoutError:
        await ctx.send("❌ Commande annulée (trop long à répondre).")

# --- GESTION DE LA BASE DE DONNÉES ---
@bot.command()
@commands.has_permissions(administrator=True)
async def ajouter_secteur(ctx, membre: discord.Member, *, secteur: str):
    db = load_db()
    secteur = secteur.strip().capitalize()
    if secteur not in db: db[secteur] = []
    if membre.id not in db[secteur]:
        db[secteur].append(membre.id)
        save_db(db)
        await ctx.send(f"✅ {membre.display_name} ajouté au secteur **{secteur}**.")
    else:
        await ctx.send("Cet utilisateur est déjà dans ce secteur.")

@bot.command()
@commands.has_permissions(administrator=True)
async def retirer_secteur(ctx, membre: discord.Member, *, secteur: str):
    db = load_db()
    secteur = secteur.strip().capitalize()
    if secteur in db and membre.id in db[secteur]:
        db[secteur].remove(membre.id)
        save_db(db)
        await ctx.send(f"🗑️ {membre.display_name} retiré du secteur **{secteur}**.")
    else:
        await ctx.send("Utilisateur introuvable dans ce secteur.")

@bot.command()
async def voir_base(ctx):
    db = load_db()
    if not db: return await ctx.send("La base est vide.")
    embed = discord.Embed(title="📋 Répertoire des Secteurs", color=discord.Color.blue())
    for sect, ids in db.items():
        noms = [f"<@{uid}>" for uid in ids]
        embed.add_field(name=f"📍 {sect}", value=", ".join(noms) if noms else "Vide", inline=False)
    await ctx.send(embed=embed)

# Conserve ta commande msgmp si besoin ou utilise celle de bienvenue
keep_alive()
bot.run(TOKEN)
