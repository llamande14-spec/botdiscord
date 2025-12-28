import discord
from discord.ext import commands, tasks
import os
import asyncio
import json
from keep_alive import keep_alive

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
ID_SALON_REPONSES = 1433793778111484035  # Salon pour les fiches staff
ID_TON_COMPTE = 697919761312383057       # ⚠️ REMPLACE PAR TON ID (Clic droit sur ton nom)
DB_FILE = "secteurs.json"

# Liste des départements valides (01-95, 2A, 2B)
DEPARTEMENTS_VALIDES = [str(i).zfill(2) for i in range(1, 96)] + ["2A", "2B"]

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- FONCTIONS DE GESTION ---
def load_db():
    if not os.path.exists(DB_FILE): return {}
    try:
        with open(DB_FILE, "r") as f: return json.load(f)
    except: return {}

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

async def lancer_questionnaire(member):
    """Gère le questionnaire, l'enregistrement et la fiche staff"""
    try:
        await member.send(f"Salut {member.name} ! Bienvenue sur **{member.guild.name}** 🎉\nRéponds à ces questions pour ton enregistrement :")
        
        questions = [
            "Quel est ton pseudo AS ?",
            "Ton secteur (Département, ex: 75, 13, 2A) ?",
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
            except asyncio.TimeoutError:
                return await member.send("⏱️ Temps écoulé. Le questionnaire est annulé.")

        # Traitement du secteur (ex: '5' -> '05')
        secteur = reponses[1].strip().upper()
        if secteur.isdigit() and len(secteur) == 1: secteur = "0" + secteur

        status_enregistrement = "❌ Non enregistré (Secteur invalide)"
        if secteur in DEPARTEMENTS_VALIDES:
            db = load_db()
            if secteur not in db: db[secteur] = []
            if member.id not in db[secteur]:
                db[secteur].append(member.id)
                save_db(db)
            status_enregistrement = f"✅ Enregistré au secteur {secteur}"

        # Envoi de la fiche staff
        salon = bot.get_channel(ID_SALON_REPONSES)
        if salon:
            embed = discord.Embed(title=f"🆕 Fiche Membre : {member.name}", color=discord.Color.blue())
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="Pseudo AS", value=reponses[0], inline=True)
            embed.add_field(name="Secteur choisi", value=reponses[1], inline=True)
            embed.add_field(name="Motivation", value=reponses[2], inline=False)
            embed.add_field(name="Autres jeux", value=reponses[3], inline=False)
            embed.add_field(name="Statut Base", value=status_enregistrement, inline=False)
            await salon.send(embed=embed)
        
        await member.send(f"Merci ! Tes infos ont été transmises. {status_enregistrement}")
        return True
    except discord.Forbidden:
        return False
    except Exception as e:
        print(f"Erreur questionnaire: {e}")
        return False

# --- TÂCHE DE BACKUP AUTO ---
@tasks.loop(hours=24)
async def backup_automatique():
    await bot.wait_until_ready()
    user = await bot.fetch_user(ID_TON_COMPTE)
    if user and os.path.exists(DB_FILE):
        try:
            await user.send("📦 **Backup Journalière** : Voici ton fichier `secteurs.json` actuel.", file=discord.File(DB_FILE))
        except: pass

@bot.event
async def on_ready():
    print(f"✅ Bot opérationnel : {bot.user}")
    if not backup_automatique.is_running():
        backup_automatique.start()

# --- ÉVÉNEMENTS & COMMANDES ---
@bot.event
async def on_member_join(member):
    await lancer_questionnaire(member)

@bot.command()
@commands.has_permissions(administrator=True)
async def msgmp(ctx, membre: discord.Member):
    """Relance manuellement le questionnaire"""
    await ctx.send(f"⏳ Tentative d'envoi du questionnaire à {membre.mention}...")
    success = await lancer_questionnaire(membre)
    if success:
        await ctx.send(f"✅ Questionnaire terminé pour {membre.display_name}.")
    else:
        await ctx.send(f"❌ Impossible d'envoyer le MP (messages fermés ou bot bloqué).")

@bot.command()
@commands.cooldown(1, 30, commands.BucketType.user)
async def renforts(ctx):
    """Commande de demande de renforts avec mentions auto"""
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    try:
        await ctx.send("🚨 **Demande de renfort**\nQuel est le **Numéro d'intervention** ?")
        n_inter = (await bot.wait_for("message", check=check, timeout=60)).content
        await ctx.send("📍 Quel **Département** ? (ex: 75, 13, 2B)")
        secteur = (await bot.wait_for("message", check=check, timeout=60)).content.strip().upper()
        
        if secteur.isdigit() and len(secteur) == 1: secteur = "0" + secteur

        db = load_db()
        mentions = " ".join([f"<@{uid}>" for uid in db.get(secteur, [])])
        
        embed = discord.Embed(title="🚨 ALERTE RENFORTS 🚨", color=discord.Color.red())
        embed.add_field(name="Secteur", value=f"📍 {secteur}", inline=True)
        embed.add_field(name="N° Inter", value=n_inter, inline=True)
        await ctx.send(content=f"📢 {mentions if mentions else 'Aucun personnel enregistré'}", embed=embed)
    except: pass

@bot.command()
@commands.has_permissions(administrator=True)
async def restore(ctx):
    """Restaure la base depuis un fichier joint"""
    if ctx.message.attachments:
        await ctx.message.attachments[0].save(DB_FILE)
        await ctx.send("✅ Base de données restaurée avec succès.")

@bot.command()
async def voir_base(ctx):
    """Affiche les membres par secteur"""
    db = load_db()
    if not db: return await ctx.send("La base est vide.")
    embed = discord.Embed(title="📋 Répertoire des Secteurs", color=discord.Color.gold())
    for s in sorted(db.keys()):
        m = ", ".join([f"<@{uid}>" for uid in db[s]])
        if m: embed.add_field(name=f"📍 Secteur {s}", value=m, inline=False)
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Calme-toi ! Réessaie dans **{error.retry_after:.1f}** secondes.")

keep_alive()
bot.run(TOKEN)
