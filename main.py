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

# --- SYSTÈME DE NAVIGATION !COM ---

class MainMenuView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=60)
        self.ctx = ctx

    @discord.ui.button(label="Secteurs", emoji="📍", style=discord.ButtonStyle.primary)
    async def sect_menu(self, interaction, button):
        embed = discord.Embed(title="📍 Gestion des Secteurs", color=discord.Color.blue())
        await interaction.response.edit_message(embed=embed, view=SecteurMenuView(self.ctx))

    @discord.ui.button(label="Sanctions", emoji="⚖️", style=discord.ButtonStyle.primary)
    async def sanc_menu(self, interaction, button):
        embed = discord.Embed(title="⚖️ Gestion des Sanctions", color=discord.Color.red())
        await interaction.response.edit_message(embed=embed, view=SanctionMenuView(self.ctx))

    @discord.ui.button(label="Sauvegardes", emoji="📦", style=discord.ButtonStyle.success)
    async def backup_menu(self, interaction, button):
        embed = discord.Embed(title="📦 Gestion des Sauvegardes", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=BackupMenuView(self.ctx))

class SecteurMenuView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=60)
        self.ctx = ctx

    @discord.ui.button(label="Voir Répertoire", style=discord.ButtonStyle.secondary)
    async def view_base(self, interaction, button):
        db = load_db(DB_FILE)
        msg = "**📍 Répertoire :**\n" + "\n".join([f"**{k}** : {', '.join([f'<@{u}>' for u in v])}" for k, v in sorted(db.items()) if v])
        await interaction.response.send_message(msg if len(msg) > 15 else "Base vide.", ephemeral=True)

    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray)
    async def back(self, interaction, button):
        await interaction.response.edit_message(embed=discord.Embed(title="🛡️ Menu Principal"), view=MainMenuView(self.ctx))

class SanctionMenuView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=60)
        self.ctx = ctx

    @discord.ui.button(label="Dernières Sanctions", style=discord.ButtonStyle.secondary)
    async def last_sanc(self, interaction, button):
        db = load_db(SANCTIONS_FILE)
        all_s = []
        for uid, s_list in db.items():
            for s in s_list: all_s.append(f"<@{uid}> : {s['type']} ({s['date']})")
        msg = "**10 Dernières :**\n" + "\n".join(all_s[-10:])
        await interaction.response.send_message(msg if all_s else "Aucune sanction.", ephemeral=True)

    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray)
    async def back(self, interaction, button):
        await interaction.response.edit_message(embed=discord.Embed(title="🛡️ Menu Principal"), view=MainMenuView(self.ctx))

class BackupMenuView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=60)
        self.ctx = ctx

    @discord.ui.button(label="Recevoir Backup MP", style=discord.ButtonStyle.primary)
    async def send_back(self, interaction, button):
        files = [discord.File(f) for f in [DB_FILE, SANCTIONS_FILE] if os.path.exists(f)]
        if files:
            user = await bot.fetch_user(ID_TON_COMPTE)
            await user.send("📦 Backup manuel demandé :", files=files)
            await interaction.response.send_message("✅ Envoyé !", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Fichiers introuvables.", ephemeral=True)

    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray)
    async def back(self, interaction, button):
        await interaction.response.edit_message(embed=discord.Embed(title="🛡️ Menu Principal"), view=MainMenuView(self.ctx))

# --- PANEL !sanction @membre ---

class ReasonModal(discord.ui.Modal, title="Détails de la sanction"):
    raison = discord.ui.TextInput(label="Raison", style=discord.TextStyle.paragraph, required=True)
    def __init__(self, target, admin, type_s):
        super().__init__(); self.target, self.admin, self.type_s = target, admin, type_s
    async def on_submit(self, interaction: discord.Interaction):
        db = load_db(SANCTIONS_FILE); uid = str(self.target.id)
        if uid not in db: db[uid] = []
        db[uid].append({"type": self.type_s, "raison": self.raison.value, "date": discord.utils.utcnow().strftime("%d/%m/%Y %H:%M"), "par": self.admin.display_name})
        save_db(SANCTIONS_FILE, db)
        await interaction.response.send_message(f"✅ Sanctionnée enregistrée.", ephemeral=True)

class SanctionView(discord.ui.View):
    def __init__(self, target, admin): super().__init__(timeout=60); self.target, self.admin = target, admin
    
    @discord.ui.button(label="Sanctionner", emoji="⚖️", style=discord.ButtonStyle.danger)
    async def do_s(self, i, b): await i.response.send_modal(ReasonModal(self.target, self.admin, "SANCTION"))

# --- TÂCHES ET STATUT ---

@tasks.loop(hours=24)
async def backup_loop():
    user = await bot.fetch_user(ID_TON_COMPTE)
    files = [discord.File(f) for f in [DB_FILE, SANCTIONS_FILE] if os.path.exists(f)]
    if user and files:
        try: await user.send("📦 **Backup Automatique (24h)**", files=files)
        except: pass

@tasks.loop(seconds=30)
async def status_loop():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"la sécurité | !com"))

@bot.event
async def on_ready():
    print(f"✅ {bot.user} est en ligne !")
    
    # 1. Envoi du backup IMMEDIAT au lancement
    user = await bot.fetch_user(ID_TON_COMPTE)
    files = [discord.File(f) for f in [DB_FILE, SANCTIONS_FILE] if os.path.exists(f)]
    if user and files:
        try: await user.send("🚀 **Bot Redémarré : Voici ta sauvegarde actuelle**", files=files)
        except: pass

    # 2. Lancement des boucles
    if not backup_loop.is_running(): backup_loop.start()
    if not status_loop.is_running(): status_loop.start()

# --- COMMANDES ---

@bot.command()
@commands.has_permissions(administrator=True)
async def com(ctx):
    embed = discord.Embed(title="🛡️ Centre de Contrôle Admin", description="Naviguez avec les boutons.", color=0x2b2d31)
    await ctx.send(embed=embed, view=MainMenuView(ctx))

@bot.command()
@commands.has_permissions(administrator=True)
async def sanction(ctx, membre: discord.Member):
    await ctx.send(embed=discord.Embed(title=f"⚖️ Modération : {membre.display_name}", color=0xffa500), view=SanctionView(membre, ctx.author))

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
