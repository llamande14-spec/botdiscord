import discord
from discord.ext import commands, tasks
import os
import asyncio
import json
import datetime
from keep_alive import keep_alive

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
ID_SALON_REPONSES = 1433793778111484035
ID_TON_COMPTE = 697919761312383057
DB_FILE = "secteurs.json"
SANCTIONS_FILE = "sanctions.json"

# Liste des départements valides (01-95, 2A, 2B)
DEPARTEMENTS_VALIDES = [str(i).zfill(2) for i in range(1, 96)] + ["2A", "2B"]

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- GESTION DES FICHIERS (BASE DE DONNÉES) ---

def load_db(file):
    if not os.path.exists(file): return {}
    try:
        with open(file, "r", encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_db(file, data):
    with open(file, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- SYSTÈME DE SANCTIONS (MODALS & VIEWS) ---

class ReasonModal(discord.ui.Modal, title="Détails de la sanction"):
    raison = discord.ui.TextInput(
        label="Raison du motif",
        style=discord.TextStyle.paragraph,
        placeholder="Expliquez le motif de la sanction ici...",
        required=True,
        min_length=5,
        max_length=300
    )

    def __init__(self, target, admin, type_sanction):
        super().__init__()
        self.target = target
        self.admin = admin
        self.type_sanction = type_sanction

    async def on_submit(self, interaction: discord.Interaction):
        db = load_db(SANCTIONS_FILE)
        uid = str(self.target.id)
        
        if uid not in db: db[uid] = []
        
        entry = {
            "type": self.type_sanction,
            "raison": self.raison.value,
            "date": discord.utils.utcnow().strftime("%d/%m/%Y %H:%M"),
            "par": self.admin.display_name
        }
        
        db[uid].append(entry)
        save_db(SANCTIONS_FILE, db)

        # Exécution des actions réelles sur Discord
        try:
            if self.type_sanction == "KICK":
                await self.target.kick(reason=self.raison.value)
            elif self.type_sanction == "BAN":
                await self.target.ban(reason=self.raison.value)
            elif self.type_sanction == "MUTE (1h)":
                await self.target.timeout(discord.utils.utcnow() + datetime.timedelta(hours=1), reason=self.raison.value)
            elif self.type_sanction == "EXCLUSION (24h)":
                await self.target.timeout(discord.utils.utcnow() + datetime.timedelta(days=1), reason=self.raison.value)
        except Exception as e:
            return await interaction.response.send_message(f"⚠️ Action Discord impossible : {e}", ephemeral=True)

        embed = discord.Embed(title=f"✅ {self.type_sanction} Appliquée", color=discord.Color.red())
        embed.add_field(name="Membre", value=self.target.mention)
        embed.add_field(name="Raison", value=self.raison.value, inline=False)
        await interaction.response.send_message(embed=embed)

class SanctionView(discord.ui.View):
    def __init__(self, target: discord.Member, admin: discord.Member):
        super().__init__(timeout=60)
        self.target = target
        self.admin = admin

    async def open_modal(self, interaction, type_sanction):
        if interaction.user != self.admin:
            return await interaction.response.send_message("Seul l'auteur de la commande peut faire ça.", ephemeral=True)
        await interaction.response.send_modal(ReasonModal(self.target, self.admin, type_sanction))

    @discord.ui.button(label="Sommation", style=discord.ButtonStyle.secondary, row=0)
    async def b1(self, i, b): await self.open_modal(i, "SOMMATION")
    
    @discord.ui.button(label="Rappel", style=discord.ButtonStyle.primary, row=0)
    async def b2(self, i, b): await self.open_modal(i, "RAPPEL")
    
    @discord.ui.button(label="Avertissement", style=discord.ButtonStyle.danger, row=0)
    async def b3(self, i, b): await self.open_modal(i, "AVERTISSEMENT")
    
    @discord.ui.button(label="Mute (1h)", style=discord.ButtonStyle.secondary, row=1)
    async def b4(self, i, b): await self.open_modal(i, "MUTE (1h)")
    
    @discord.ui.button(label="Exclure (24h)", style=discord.ButtonStyle.secondary, row=1)
    async def b5(self, i, b): await self.open_modal(i, "EXCLUSION (24h)")
    
    @discord.ui.button(label="KICK", style=discord.ButtonStyle.danger, row=2)
    async def b6(self, i, b): await self.open_modal(i, "KICK")
    
    @discord.ui.button(label="BAN", style=discord.ButtonStyle.danger, row=2)
    async def b7(self, i, b): await self.open_modal(i, "BAN")

# --- FONCTION QUESTIONNAIRE ---

async def lancer_questionnaire(member):
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
            db = load_db(DB_FILE)
            if secteur not in db: db[secteur] = []
            if member.id not in db[secteur]:
                db[secteur].append(member.id)
                save_db(DB_FILE, db)
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
    if user:
        files = []
        if os.path.exists(DB_FILE): files.append(discord.File(DB_FILE))
        if os.path.exists(SANCTIONS_FILE): files.append(discord.File(SANCTIONS_FILE))
        if files:
            try: await user.send("📦 **Backup Quotidien (Secteurs & Sanctions)**", files=files)
            except: pass

@bot.event
async def on_ready():
    print(f"✅ Bot opérationnel : {bot.user}")
    if not backup_automatique.is_running():
        backup_automatique.start()

@bot.event
async def on_member_join(member):
    await lancer_questionnaire(member)

# --- COMMANDES DE MODÉRATION & CASIER ---

@bot.command()
@commands.has_permissions(administrator=True)
async def sanction(ctx, membre: discord.Member):
    """Ouvre le panel de sanction interactif"""
    embed = discord.Embed(
        title=f"⚖️ Gestion des sanctions : {membre.display_name}",
        description="Cliquez sur le bouton pour appliquer une action et saisir un motif.",
        color=discord.Color.orange()
    )
    view = SanctionView(membre, ctx.author)
    await ctx.send(embed=embed, view=view)

@bot.command()
@commands.has_permissions(administrator=True)
async def casier(ctx, membre: discord.Member):
    """Affiche l'historique des sanctions d'un membre"""
    db = load_db(SANCTIONS_FILE)
    uid = str(membre.id)
    if uid not in db or not db[uid]:
        return await ctx.send(f"✅ Le casier de **{membre.display_name}** est vierge.")
    
    embed = discord.Embed(title=f"📁 Casier de {membre.display_name}", color=discord.Color.red())
    for i, s in enumerate(db[uid], 1):
        embed.add_field(
            name=f"#{i} - {s['type']}", 
            value=f"📝 **Motif:** {s['raison']}\n📅 **Date:** {s['date']}\n👮 **Par:** {s['par']}", 
            inline=False
        )
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def clear_casier(ctx, membre: discord.Member):
    """Efface tout le casier d'un membre"""
    db = load_db(SANCTIONS_FILE)
    if str(membre.id) in db:
        del db[str(membre.id)]
        save_db(SANCTIONS_FILE, db)
        await ctx.send(f"🗑️ Casier de {membre.display_name} réinitialisé.")

# --- COMMANDES SECTEURS ---

@bot.command()
@commands.has_permissions(administrator=True)
async def ajouter_secteur(ctx, membre: discord.Member, secteur: str):
    secteur = secteur.strip().upper()
    if secteur.isdigit() and len(secteur) == 1: secteur = "0" + secteur
    if secteur not in DEPARTEMENTS_VALIDES:
        return await ctx.send(f"❌ `{secteur}` n'est pas un département valide.")
    db = load_db(DB_FILE)
    if secteur not in db: db[secteur] = []
    if membre.id not in db[secteur]:
        db[secteur].append(membre.id)
        save_db(DB_FILE, db)
        await ctx.send(f"✅ {membre.display_name} ajouté au secteur {secteur}.")

@bot.command()
@commands.has_permissions(administrator=True)
async def retirer_secteur(ctx, membre: discord.Member, secteur: str):
    secteur = secteur.strip().upper()
    if secteur.isdigit() and len(secteur) == 1: secteur = "0" + secteur
    db = load_db(DB_FILE)
    if secteur in db and membre.id in db[secteur]:
        db[secteur].remove(membre.id)
        save_db(DB_FILE, db)
        await ctx.send(f"🗑️ {membre.display_name} retiré du secteur {secteur}.")

@bot.command()
@commands.has_permissions(administrator=True)
async def voir_base(ctx, secteur_demande: str = None):
    db = load_db(DB_FILE)
    if not db: return await ctx.send("La base est vide.")
    if secteur_demande:
        secteur_demande = secteur_demande.strip().upper()
        if secteur_demande.isdigit() and len(secteur_demande) == 1: secteur_demande = "0" + secteur_demande
        if secteur_demande in db:
            mentions = ", ".join([f"<@{uid}>" for uid in db[secteur_demande]])
            embed = discord.Embed(title=f"📍 Secteur {secteur_demande}", description=mentions, color=discord.Color.gold())
            await ctx.send(embed=embed)
        else: await ctx.send(f"Aucun personnel en `{secteur_demande}`.")
        return
    msg = "**📋 Répertoire Complet :**\n\n"
    for s in sorted(db.keys()):
        mentions = ", ".join([f"<@{uid}>" for uid in db[s]])
        if mentions:
            ligne = f"**{s}** : {mentions}\n"
            if len(msg) + len(ligne) > 1900:
                await ctx.send(msg)
                msg = ""
            msg += ligne
    if msg: await ctx.send(msg)

# --- SYSTÈME RENFORTS ---

@bot.command()
@commands.has_permissions(administrator=True)
@commands.cooldown(1, 10, commands.BucketType.user)
async def renforts(ctx):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    try:
        await ctx.send("🚨 **Intervention N° ?**")
        n_inter = (await bot.wait_for("message", check=check, timeout=60)).content
        await ctx.send("🚒 **Quels véhicules ?**")
        vehicules = (await bot.wait_for("message", check=check, timeout=60)).content
        await ctx.send("📍 **Quel Département ?**")
        secteur = (await bot.wait_for("message", check=check, timeout=60)).content.strip().upper()
        if secteur.isdigit() and len(secteur) == 1: secteur = "0" + secteur
        if secteur not in DEPARTEMENTS_VALIDES: return await ctx.send("❌ Secteur invalide.")
        db = load_db(DB_FILE)
        mentions = " ".join([f"<@{uid}>" for uid in db.get(secteur, [])])
        embed = discord.Embed(title="🚨 ALERTE RENFORTS 🚨", color=discord.Color.red())
        embed.add_field(name="Secteur", value=f"📍 {secteur}", inline=True)
        embed.add_field(name="N° Inter", value=n_inter, inline=True)
        embed.add_field(name="Véhicules requis", value=vehicules, inline=False)
        await ctx.send(content=f"📢 {mentions if mentions else 'Aucun personnel'}", embed=embed)
    except asyncio.TimeoutError: await ctx.send("❌ Temps écoulé.")

# --- BACKUP & RESTORE ---

@bot.command()
@commands.has_permissions(administrator=True)
async def backup(ctx):
    files = []
    if os.path.exists(DB_FILE): files.append(discord.File(DB_FILE))
    if os.path.exists(SANCTIONS_FILE): files.append(discord.File(SANCTIONS_FILE))
    if files:
        await ctx.author.send("📦 Sauvegarde actuelle :", files=files)
        await ctx.send("✅ Sauvegardes envoyées en MP.")

@bot.command()
@commands.has_permissions(administrator=True)
async def restore(ctx):
    if ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        if attachment.filename in [DB_FILE, SANCTIONS_FILE]:
            await attachment.save(attachment.filename)
            await ctx.send(f"✅ Fichier `{attachment.filename}` restauré avec succès.")
        else: await ctx.send("❌ Nom de fichier invalide.")

@bot.command()
@commands.has_permissions(administrator=True)
async def msgmp(ctx, membre: discord.Member):
    await ctx.send(f"⏳ Envoi du questionnaire à {membre.mention}...")
    if await lancer_questionnaire(membre): await ctx.send(f"✅ Fini pour {membre.display_name}.")
    else: await ctx.send("❌ Échec.")

# --- GESTION ERREURS ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Réessaie dans {error.retry_after:.1f}s.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Permission insuffisante.")

keep_alive()
bot.run(TOKEN)
