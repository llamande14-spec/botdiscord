import discord
from discord.ext import commands, tasks
import os
import asyncio
import json
from keep_alive import keep_alive

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
ID_SALON_REPONSES = 1433793778111484035 
ID_TON_COMPTE = 697919761312383057 
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
    """Gère le questionnaire complet et l'enregistrement automatique"""
    try:
        await member.send(f"Salut {member.name} ! Bienvenue sur **{member.guild.name}** 🎉")
        questions = [
            "Quel est ton pseudo AS ?",
            "Ton secteur (Département, ex: 75, 13, 2A) ?",
            "Ta motivation ? 🤔",
            "Joues-tu à d'autres jeux ? 🎮"
        ]
        reponses = []
        for q in questions:
            await member.send(q)
            def check(m): return m.author == member and isinstance(m.channel, discord.DMChannel)
            try:
                msg = await bot.wait_for("message", check=check, timeout=600.0)
                reponses.append(msg.content)
            except asyncio.TimeoutError: return False

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

        salon = bot.get_channel(ID_SALON_REPONSES)
        if salon:
            embed = discord.Embed(title=f"🆕 Fiche de {member.name}", color=discord.Color.blue())
            embed.add_field(name="Pseudo AS", value=reponses[0], inline=True)
            embed.add_field(name="Secteur", value=reponses[1], inline=True)
            embed.add_field(name="Motivation", value=reponses[2], inline=False)
            embed.add_field(name="Statut Base", value=status_enregistrement, inline=False)
            await salon.send(embed=embed)
        
        await member.send(f"Merci ! {status_enregistrement}")
        return True
    except: return False

# --- TÂCHES AUTOMATIQUES ---
@tasks.loop(hours=24)
async def backup_automatique():
    await bot.wait_until_ready()
    user = await bot.fetch_user(ID_TON_COMPTE)
    if user and os.path.exists(DB_FILE):
        try:
            await user.send("📦 **Backup Quotidien**", file=discord.File(DB_FILE))
        except: pass

@bot.event
async def on_ready():
    print(f"✅ Bot opérationnel : {bot.user}")
    if not backup_automatique.is_running():
        backup_automatique.start()

@bot.event
async def on_member_join(member):
    await lancer_questionnaire(member)

# --- COMMANDES ADMIN ---
@bot.command()
@commands.has_permissions(everyone=True)
async def ajouter_secteur(ctx, membre: discord.Member, secteur: str):
    secteur = secteur.strip().upper()
    if secteur.isdigit() and len(secteur) == 1: secteur = "0" + secteur
    if secteur not in DEPARTEMENTS_VALIDES:
        return await ctx.send(f"❌ `{secteur}` n'est pas un département valide.")
    db = load_db()
    if secteur not in db: db[secteur] = []
    if membre.id not in db[secteur]:
        db[secteur].append(membre.id)
        save_db(db)
        await ctx.send(f"✅ {membre.display_name} ajouté au secteur {secteur}.")

@bot.command()
@commands.has_permissions(administrator=True)
async def retirer_secteur(ctx, membre: discord.Member, secteur: str):
    secteur = secteur.strip().upper()
    if secteur.isdigit() and len(secteur) == 1: secteur = "0" + secteur
    db = load_db()
    if secteur in db and membre.id in db[secteur]:
        db[secteur].remove(membre.id)
        save_db(db)
        await ctx.send(f"🗑️ {membre.display_name} retiré du secteur {secteur}.")

# --- COMMANDE RENFORTS (AVEC VÉHICULES ET COOLDOWN) ---
@bot.command()
@commands.cooldown(1, 30, commands.BucketType.user)
async def renforts(ctx):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    try:
        await ctx.send("🚨 **Demande de renfort**\nN° Intervention ?")
        n_inter = (await bot.wait_for("message", check=check, timeout=60)).content
        
        await ctx.send("🚒 Quels **véhicules** sont demandés ?")
        vehicules = (await bot.wait_for("message", check=check, timeout=60)).content

        await ctx.send("📍 Quel **Département** ? (ex: 75, 2B)")
        secteur = (await bot.wait_for("message", check=check, timeout=60)).content.strip().upper()
        if secteur.isdigit() and len(secteur) == 1: secteur = "0" + secteur

        if secteur not in DEPARTEMENTS_VALIDES:
            return await ctx.send("❌ Secteur invalide.")

        db = load_db()
        mentions = " ".join([f"<@{uid}>" for uid in db.get(secteur, [])])
        
        embed = discord.Embed(title="🚨 ALERTE RENFORTS 🚨", color=discord.Color.red())
        embed.add_field(name="Secteur", value=f"📍 {secteur}", inline=True)
        embed.add_field(name="N° Inter", value=n_inter, inline=True)
        embed.add_field(name="Véhicules requis", value=vehicules, inline=False)
        embed.set_footer(text=f"Demandé par {ctx.author.display_name}")
        
        await ctx.send(content=f"📢 {mentions if mentions else 'Aucun personnel enregistré'}", embed=embed)
    except asyncio.TimeoutError:
        await ctx.send("❌ Temps écoulé, commande annulée.")

# --- GESTION BACKUP / VOIR ---
@bot.command()
@commands.has_permissions(administrator=True)
async def backup(ctx):
    if os.path.exists(DB_FILE):
        await ctx.author.send("📦 Sauvegarde manuelle :", file=discord.File(DB_FILE))
        await ctx.send("✅ Envoyé en MP.")

@bot.command()
@commands.has_permissions(administrator=True)
async def restore(ctx):
    if ctx.message.attachments:
        await ctx.message.attachments[0].save(DB_FILE)
        await ctx.send("✅ Base restaurée.")

@bot.command()
@commands.has_permissions(administrator=True)
async def msgmp(ctx, membre: discord.Member):
    await ctx.send(f"⏳ Envoi du questionnaire à {membre.mention}...")
    if await lancer_questionnaire(membre):
        await ctx.send(f"✅ Terminé pour {membre.display_name}.")
    else:
        await ctx.send("❌ Échec (MP fermés).")

@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user)
async def voir_base(ctx):
    db = load_db()
    if not db: return await ctx.send("La base est vide.")
    embed = discord.Embed(title="📋 Répertoire Secteurs", color=discord.Color.gold())
    for s in sorted(db.keys()):
        m = ", ".join([f"<@{uid}>" for uid in db[s]])
        if m: embed.add_field(name=f"📍 {s}", value=m, inline=False)
    await ctx.send(embed=embed)

# --- GESTION DES ERREURS ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Calme-toi ! Réessaie dans {error.retry_after:.1f}s.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Tu n'as pas la permission d'utiliser cette commande.")

keep_alive()
bot.run(TOKEN)
