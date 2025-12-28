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

# --- GESTION DES FICHIERS ---

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

# --- NOTIFICATION MP ---

async def notifier_membre(membre, type_s, raison):
    """Envoie un message privé au membre pour l'informer de sa sanction"""
    embed = discord.Embed(
        title="⚠️ Information de Sanction",
        description=f"Bonjour {membre.name}, une action a été prise sur ton compte sur le serveur **{membre.guild.name}**.",
        color=discord.Color.red()
    )
    embed.add_field(name="Type de sanction", value=type_s, inline=True)
    embed.add_field(name="Raison", value=raison, inline=False)
    embed.set_footer(text="Ceci est un message automatique.")
    
    try:
        await membre.send(embed=embed)
        return True
    except:
        return False

# --- SYSTÈME DE SANCTIONS (MODALS & VIEWS) ---

class ReasonModal(discord.ui.Modal, title="Détails de la sanction"):
    raison = discord.ui.TextInput(
        label="Raison du motif",
        style=discord.TextStyle.paragraph,
        placeholder="Expliquez pourquoi...",
        required=True,
        min_length=5
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

        # 1. Tentative d'envoi du MP avant le kick/ban
        mp_status = await notifier_membre(self.target, self.type_sanction, self.raison.value)

        # 2. Exécution des actions réelles
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
            return await interaction.response.send_message(f"⚠️ Erreur action Discord : {e}", ephemeral=True)

        msg_confirm = f"✅ **{self.type_sanction}** enregistrée."
        if not mp_status: msg_confirm += " *(Le membre n'a pas pu être prévenu en MP)*"
        
        await interaction.response.send_message(msg_confirm, ephemeral=False)

class SanctionView(discord.ui.View):
    def __init__(self, target: discord.Member, admin: discord.Member):
        super().__init__(timeout=60)
        self.target = target
        self.admin = admin

    async def open_modal(self, interaction, type_sanction):
        if interaction.user != self.admin:
            return await interaction.response.send_message("Tu n'es pas l'auteur.", ephemeral=True)
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

# --- QUESTIONNAIRE ---

async def lancer_questionnaire(member):
    try:
        await member.send(f"Salut {member.name} ! Bienvenue sur **{member.guild.name}** 🎉")
        questions = ["Pseudo AS ?", "Département (ex: 75) ?", "Motivation ?", "Autres jeux ?"]
        reponses = []
        for q in questions:
            await member.send(q)
            def check(m): return m.author == member and isinstance(m.channel, discord.DMChannel)
            msg = await bot.wait_for("message", check=check, timeout=600.0)
            reponses.append(msg.content)
        
        secteur = reponses[1].strip().upper()
        if secteur.isdigit() and len(secteur) == 1: secteur = "0" + secteur
        st = "❌ Invalide"
        if secteur in DEPARTEMENTS_VALIDES:
            db = load_db(DB_FILE)
            if secteur not in db: db[secteur] = []
            if member.id not in db[secteur]:
                db[secteur].append(member.id)
                save_db(DB_FILE, db)
                st = f"✅ Enregistré ({secteur})"
        
        salon = bot.get_channel(ID_SALON_REPONSES)
        if salon:
            emb = discord.Embed(title=f"🆕 Fiche de {member.name}", color=discord.Color.blue())
            emb.add_field(name="Pseudo", value=reponses[0])
            emb.add_field(name="Secteur", value=reponses[1])
            emb.add_field(name="Motivation", value=reponses[2], inline=False)
            emb.add_field(name="Statut", value=st)
            await salon.send(embed=emb)
        await member.send(f"Merci ! {st}")
    except: pass

# --- ÉVÉNEMENTS & TÂCHES ---

@tasks.loop(hours=24)
async def backup_automatique():
    await bot.wait_until_ready()
    user = await bot.fetch_user(ID_TON_COMPTE)
    files = [discord.File(f) for f in [DB_FILE, SANCTIONS_FILE] if os.path.exists(f)]
    if user and files:
        try: await user.send("📦 **Backup Quotidien**", files=files)
        except: pass

@bot.event
async def on_ready():
    print(f"✅ Bot prêt : {bot.user}")
    if not backup_automatique.is_running(): backup_automatique.start()

@bot.event
async def on_member_join(member):
    await lancer_questionnaire(member)

# --- COMMANDES ---

@bot.command()
@commands.has_permissions(administrator=True)
async def sanction(ctx, membre: discord.Member):
    emb = discord.Embed(title=f"⚖️ Sanctionner {membre.display_name}", color=0xffa500)
    await ctx.send(embed=emb, view=SanctionView(membre, ctx.author))

@bot.command()
@commands.has_permissions(administrator=True)
async def casier(ctx, membre: discord.Member):
    db = load_db(SANCTIONS_FILE)
    uid = str(membre.id)
    if uid not in db or not db[uid]: return await ctx.send("✅ Casier vierge.")
    emb = discord.Embed(title=f"📁 Casier : {membre.display_name}", color=discord.Color.red())
    for i, s in enumerate(db[uid], 1):
        emb.add_field(name=f"#{i} {s['type']}", value=f"📝 {s['raison']}\n📅 {s['date']}\n👮 par {s['par']}", inline=False)
    await ctx.send(embed=emb)

@bot.command()
@commands.has_permissions(administrator=True)
async def ajouter_secteur(ctx, membre: discord.Member, secteur: str):
    secteur = secteur.strip().upper()
    if secteur.isdigit() and len(secteur) == 1: secteur = "0" + secteur
    if secteur not in DEPARTEMENTS_VALIDES: return await ctx.send("❌ Département invalide.")
    db = load_db(DB_FILE)
    if secteur not in db: db[secteur] = []
    if membre.id not in db[secteur]:
        db[secteur].append(membre.id)
        save_db(DB_FILE, db)
        await ctx.send(f"✅ {membre.display_name} ajouté en {secteur}.")

@bot.command()
@commands.has_permissions(administrator=True)
async def voir_base(ctx, s_demande: str = None):
    db = load_db(DB_FILE)
    if not db: return await ctx.send("Base vide.")
    if s_demande:
        s_demande = s_demande.strip().upper()
        if s_demande in db:
            mentions = ", ".join([f"<@{uid}>" for uid in db[s_demande]])
            return await ctx.send(embed=discord.Embed(title=f"📍 Secteur {s_demande}", description=mentions))
        return await ctx.send("Personne ici.")
    # Liste complète
    msg = "**📋 Répertoire :**\n"
    for s in sorted(db.keys()):
        m = ", ".join([f"<@{u}>" for u in db[s]])
        if m: msg += f"**{s}** : {m}\n"
    await ctx.send(msg[:2000])

@bot.command()
@commands.has_permissions(administrator=True)
async def renforts(ctx):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    try:
        await ctx.send("🚨 N° Inter ?")
        n = (await bot.wait_for("message", check=check, timeout=60)).content
        await ctx.send("🚒 Véhicules ?")
        v = (await bot.wait_for("message", check=check, timeout=60)).content
        await ctx.send("📍 Département ?")
        s = (await bot.wait_for("message", check=check, timeout=60)).content.strip().upper()
        db = load_db(DB_FILE)
        mentions = " ".join([f"<@{uid}>" for uid in db.get(s, [])])
        emb = discord.Embed(title="🚨 ALERTE RENFORTS", color=discord.Color.red())
        emb.add_field(name="Secteur", value=s)
        emb.add_field(name="N°", value=n)
        emb.add_field(name="Demande", value=v)
        await ctx.send(content=f"📢 {mentions}", embed=emb)
    except: pass

@bot.command()
@commands.has_permissions(administrator=True)
async def backup(ctx):
    files = [discord.File(f) for f in [DB_FILE, SANCTIONS_FILE] if os.path.exists(f)]
    if files:
        await ctx.author.send("📦 Backup :", files=files)
        await ctx.send("✅ Envoyé en MP.")

@bot.command()
@commands.has_permissions(administrator=True)
async def restore(ctx):
    if ctx.message.attachments:
        att = ctx.message.attachments[0]
        if att.filename in [DB_FILE, SANCTIONS_FILE]:
            await att.save(att.filename)
            await ctx.send(f"✅ `{att.filename}` restauré.")

keep_alive()
bot.run(TOKEN)
