import discord
from discord.ext import commands, tasks
import os
import asyncio
import json
import datetime
import random
from keep_alive import keep_alive

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
ID_SALON_REPONSES = 1433793778111484035
ID_TON_COMPTE = 697919761312383057
DB_FILE = "secteurs.json"
SANCTIONS_FILE = "sanctions.json"

DEPARTEMENTS_VALIDES = [str(i).zfill(2) for i in range(1, 96)] + ["2A", "2B"]

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- GESTION DES FICHIERS ---
def load_db(file):
    if not os.path.exists(file): return {}
    try:
        with open(file, "r", encoding='utf-8') as f: return json.load(f)
    except: return {}

def save_db(file, data):
    with open(file, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- VIEWS DU MENU !COM (SYSTÈME DE NAVIGATION) ---

class MainMenuView(discord.ui.View):
    """Menu Principal de !com"""
    def __init__(self, ctx):
        super().__init__(timeout=60)
        self.ctx = ctx

    @discord.ui.button(label="Secteurs", emoji="📍", style=discord.ButtonStyle.primary)
    async def sect_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="📍 Gestion des Secteurs", description="Choisissez une action :", color=discord.Color.blue())
        await interaction.response.edit_message(embed=embed, view=SecteurMenuView(self.ctx))

    @discord.ui.button(label="Sauvegardes", emoji="📦", style=discord.ButtonStyle.success)
    async def backup_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="📦 Gestion des Sauvegardes", description="Choisissez une action :", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=BackupMenuView(self.ctx))

class SecteurMenuView(discord.ui.View):
    """Sous-menu Secteurs"""
    def __init__(self, ctx):
        super().__init__(timeout=60)
        self.ctx = ctx

    @discord.ui.button(label="Voir Répertoire", style=discord.ButtonStyle.secondary)
    async def view_base(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_db(DB_FILE)
        msg = "**📍 Répertoire des secteurs :**\n"
        found = False
        for k, v in sorted(db.items()):
            if v:
                found = True
                msg += f"**{k}** : {', '.join([f'<@{u}>' for u in v])}\n"
        await interaction.response.send_message(msg if found else "La base est vide.", ephemeral=True)

    @discord.ui.button(label="Lancer Renforts", style=discord.ButtonStyle.danger)
    async def trigger_renforts(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Tapez `!renforts` dans le salon pour lancer la procédure manuelle.", ephemeral=True)

    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🛡️ Centre de Contrôle Admin", description="Menu Principal", color=0x2b2d31)
        await interaction.response.edit_message(embed=embed, view=MainMenuView(self.ctx))

class BackupMenuView(discord.ui.View):
    """Sous-menu Sauvegardes"""
    def __init__(self, ctx):
        super().__init__(timeout=60)
        self.ctx = ctx

    @discord.ui.button(label="Envoyer Backup MP", style=discord.ButtonStyle.primary)
    async def send_backup(self, interaction: discord.Interaction, button: discord.ui.Button):
        files = [discord.File(f) for f in [DB_FILE, SANCTIONS_FILE] if os.path.exists(f)]
        if files:
            user = await bot.fetch_user(ID_TON_COMPTE)
            await user.send("📦 Backup Manuel :", files=files)
            await interaction.response.send_message("✅ Fichiers envoyés en MP.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Aucun fichier trouvé.", ephemeral=True)

    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🛡️ Centre de Contrôle Admin", description="Menu Principal", color=0x2b2d31)
        await interaction.response.edit_message(embed=embed, view=MainMenuView(self.ctx))

# --- PANEL DE SANCTION (POUR !sanction @membre) ---

class ReasonModal(discord.ui.Modal, title="Détails de la sanction"):
    raison = discord.ui.TextInput(label="Raison du motif", style=discord.TextStyle.paragraph, required=True, min_length=5)
    def __init__(self, target, admin, type_sanction):
        super().__init__(); self.target, self.admin, self.type_sanction = target, admin, type_sanction
    
    async def on_submit(self, interaction: discord.Interaction):
        db = load_db(SANCTIONS_FILE); uid = str(self.target.id)
        if uid not in db: db[uid] = []
        db[uid].append({"type": self.type_sanction, "raison": self.raison.value, "date": discord.utils.utcnow().strftime("%d/%m/%Y %H:%M"), "par": self.admin.display_name})
        save_db(SANCTIONS_FILE, db)
        
        # Action réelle
        try:
            if self.type_sanction == "KICK": await self.target.kick(reason=self.raison.value)
            elif self.type_sanction == "BAN": await self.target.ban(reason=self.raison.value)
            elif "MUTE" in self.type_sanction or "EXCLUSION" in self.type_sanction:
                m = 10 if "10m" in self.type_sanction else (60 if "1h" in self.type_sanction else 1440)
                await self.target.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=m), reason=self.raison.value)
        except: pass
        await interaction.response.send_message(f"✅ Sanction appliquée.", ephemeral=True)

class SanctionView(discord.ui.View):
    def __init__(self, target, admin): super().__init__(timeout=60); self.target, self.admin = target, admin
    
    @discord.ui.button(label="Sanctionner", emoji="⚖️", style=discord.ButtonStyle.danger)
    async def open_sanc(self, i, b): await i.response.send_modal(ReasonModal(self.target, self.admin, "SANCTION"))

    @discord.ui.button(label="Voir Dossier", emoji="📂", style=discord.ButtonStyle.secondary)
    async def view_s(self, i, b):
        db = load_db(SANCTIONS_FILE); uid = str(self.target.id)
        if uid not in db or not db[uid]: return await i.response.send_message("Casier vide.", ephemeral=True)
        emb = discord.Embed(title=f"Casier : {self.target.name}", color=discord.Color.red())
        for idx, s in enumerate(db[uid], 1): emb.add_field(name=f"#{idx} {s['type']}", value=f"📝 {s['raison']}\n📅 {s['date']}", inline=False)
        await i.response.send_message(embed=emb, ephemeral=True)

# --- STATUT & BOT EVENTS ---

@tasks.loop(seconds=30)
async def change_status():
    await bot.wait_until_ready()
    status_list = [
        discord.Activity(type=discord.ActivityType.watching, name="le personnel"),
        discord.Activity(type=discord.ActivityType.listening, name="!com"),
        discord.Game(name="🚨 Sécurité Active")
    ]
    await bot.change_presence(activity=random.choice(status_list))

@bot.event
async def on_ready():
    print(f"✅ Connecté : {bot.user}")
    if not change_status.is_running(): change_status.start()

# --- COMMANDES ---

@bot.command()
@commands.has_permissions(administrator=True)
async def com(ctx):
    """Affiche le menu de navigation"""
    embed = discord.Embed(title="🛡️ Centre de Contrôle Admin", description="Cliquez sur une catégorie pour voir les commandes.", color=0x2b2d31)
    await ctx.send(embed=embed, view=MainMenuView(ctx))

@bot.command()
@commands.has_permissions(administrator=True)
async def sanction(ctx, membre: discord.Member):
    await ctx.send(embed=discord.Embed(title=f"⚖️ Modération : {membre.display_name}", color=0xffa500), view=SanctionView(membre, ctx.author))

@bot.command()
@commands.has_permissions(administrator=True)
async def renforts(ctx):
    # Logique de renforts identique à avant
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
        emb.add_field(name="Secteur", value=s); emb.add_field(name="N°", value=n); emb.add_field(name="Demande", value=v)
        await ctx.send(content=f"📢 {mentions}", embed=emb)
    except: pass

@bot.command()
@commands.has_permissions(administrator=True)
async def restore(ctx):
    if ctx.message.attachments:
        att = ctx.message.attachments[0]
        if att.filename in [DB_FILE, SANCTIONS_FILE]: await att.save(att.filename); await ctx.send("✅ Restauré.")

keep_alive()
bot.run(TOKEN)
