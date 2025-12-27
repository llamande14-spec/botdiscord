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

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- GESTION DE LA BASE DE DONNÉES ---
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
    "Ton secteur de jeux ? (Donne juste le nom ou le numéro, ex: 75 ou Paris) 🌍",
    "Qu'est-ce qui t'a motivé à rejoindre le groupement ? 🤔",
    "Joues-tu à d'autres jeux? (si oui les quelles) 🎮"
]

@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user}")

# --- SYSTÈME DE BIENVENUE AUTOMATIQUE ---
@bot.event
async def on_member_join(member):
    try:
        await member.send(f"Salut {member.name} ! Bienvenue sur **{member.guild.name}** 🎉\nRéponds à ces questions pour t'enregistrer :")
        
        responses = []
        for q in questions_bienvenue:
            await member.send(q)
            def check(m):
                return m.author == member and isinstance(m.channel, discord.DMChannel)
            try:
                msg = await bot.wait_for("message", check=check, timeout=600.0)
                responses.append(msg.content)
            except asyncio.TimeoutError:
                await member.send("⏱️ Temps écoulé.")
                return 

        # --- LOGIQUE D'ENREGISTREMENT AUTOMATIQUE ---
        # La réponse à la question 2 (index 1) est le secteur
        secteur_repondu = responses[1].strip().capitalize()
        
        db = load_db()
        if secteur_repondu not in db:
            db[secteur_repondu] = []
        
        if member.id not in db[secteur_repondu]:
            db[secteur_repondu].append(member.id)
            save_db(db)

        # Envoi dans le salon de log
        salon = bot.get_channel(ID_SALON_REPONSES)
        if salon:
            formatted = "\n".join([f"**{questions_bienvenue[i]}**\n➡️ {responses[i]}" for i in range(len(questions_bienvenue))])
            await salon.send(f"🆕 **Nouveau membre enregistré : {member.mention}**\n📍 Secteur auto-assigné : **{secteur_repondu}**\n\n{formatted}")
        
        await member.send(f"Merci ! Tu as été ajouté à la base de données du secteur **{secteur_repondu}**. 👌")

    except Exception as e:
        print(f"Erreur bienvenue {member.name}: {e}")

# --- COMMANDE RENFORTS (Avec Mentions) ---
@bot.command()
async def renforts(ctx):
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    try:
        await ctx.send("🚨 **Demande de renfort**\nN° Intervention ?")
        n_inter = (await bot.wait_for("message", check=check, timeout=60.0)).content
        await ctx.send("Véhicules ?")
        vehicules = (await bot.wait_for("message", check=check, timeout=60.0)).content
        await ctx.send("Secteur ? (Ex: 75 ou Paris)")
        secteur = (await bot.wait_for("message", check=check, timeout=60.0)).content
        
        db = load_db()
        secteur_key = secteur.strip().capitalize()
        mentions = ""
        if secteur_key in db:
            mentions = " ".join([f"<@{uid}>" for uid in db[secteur_key]])

        embed = discord.Embed(title="🚨 ALERTE RENFORTS 🚨", color=discord.Color.red())
        embed.add_field(name="Secteur", value=secteur_key, inline=True)
        embed.add_field(name="Intervention", value=n_inter, inline=True)
        embed.add_field(name="Véhicules", value=vehicules, inline=False)
        
        await ctx.send(content=f"📢 {mentions if mentions else 'Personne dans ce secteur'}", embed=embed)
    except Exception as e:
        await ctx.send(f"Erreur : {e}")

# --- COMMANDES DE MAINTENANCE ---
@bot.command()
@commands.has_permissions(administrator=True)
async def voir_base(ctx):
    db = load_db()
    if not db: return await ctx.send("Base vide.")
    text = "**Répertoire des secteurs :**\n"
    for s, ids in db.items():
        text += f"📍 **{s}** : {len(ids)} personne(s)\n"
    await ctx.send(text)

@bot.command()
@commands.has_permissions(administrator=True)
async def retirer_secteur(ctx, membre: discord.Member, *, secteur: str):
    db = load_db()
    s = secteur.strip().capitalize() # On nettoie le nom du secteur
    
    if s in db and membre.id in db[s]:
        db[s].remove(membre.id)
        
        # Si le secteur est vide après suppression, on peut le supprimer de la base
        if not db[s]:
            del db[s]
            
        save_db(db)
        await ctx.send(f"🗑️ **{membre.display_name}** a été retiré du secteur **{s}**.")
    else:
        await ctx.send(f"⚠️ Impossible de trouver **{membre.display_name}** dans le secteur **{s}**.")

@retirer_secteur.error
async def retirer_secteur_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Tu n'as pas la permission (Administrateur) pour retirer quelqu'un.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Membre introuvable. Mentionne bien la personne (ex: !retirer_secteur @Pseudo Paris).")

@bot.command()
@commands.has_permissions(administrator=False)
async def ajouter_secteur(ctx, membre: discord.Member, *, secteur: str):
    db = load_db()
    s = secteur.strip().capitalize()
    if s not in db: db[s] = []
    if membre.id not in db[s]:
        db[s].append(membre.id)
        save_db(db)
        await ctx.send(f"✅ Ajouté à {s}")

keep_alive()
bot.run(TOKEN)
