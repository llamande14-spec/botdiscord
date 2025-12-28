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

# --- NOTIFICATION MP ---
async def notifier_membre(membre, type_s, raison):
    embed = discord.Embed(title="⚠️ Information de Sanction", color=discord.Color.red())
    embed.add_field(name="Type", value=type_s, inline=True)
    embed.add_field(name="Raison", value=raison, inline=False)
    try: await membre.send(embed=embed); return True
    except: return False

# --- MODALS (FENÊTRES) ---
class ReasonModal(discord.ui.Modal, title="Détails de la sanction"):
    raison = discord.ui.TextInput(label="Raison du motif", style=discord.TextStyle.paragraph, required=True, min_length=5)
    def __init__(self, target, admin, type_sanction):
        super().__init__(); self.target, self.admin, self.type_sanction = target, admin, type_sanction
    async def on_submit(self, interaction: discord.Interaction):
        db = load_db(SANCTIONS_FILE); uid = str(self.target.id)
        if uid not in db: db[uid] = []
        db[uid].append({"type": self.type_sanction, "raison": self.raison.value, "date": discord.utils.utcnow().strftime("%d/%m/%Y %H:%M"), "par": self.admin.display_name})
        save_db(SANCTIONS_FILE, db)
        await notifier_membre(self.target, self.type_sanction, self.raison.value)
        try:
            if self.type_sanction == "KICK": await self.target.kick(reason=self.raison.value)
            elif self.type_sanction == "BAN": await self.target.ban(reason=self.raison.value)
            elif "MUTE" in self.type_sanction or "EXCLUSION" in self.type_sanction:
                temps = 10 if "10m" in self.type_sanction else (60 if "1h" in self.type_sanction else 1440)
                await self.target.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=temps), reason=self.raison.value)
        except: pass
        await interaction.response.send_message(f"✅ **{self.type_sanction}** enregistrée.", ephemeral=False)

class DeleteSanctionModal(discord.ui.Modal, title="Supprimer une sanction"):
    index = discord.ui.TextInput(label="Numéro de la sanction", placeholder="Ex: 1")
    def __init__(self, target): super().__init__(); self.target = target
    async def on_submit(self, interaction: discord.Interaction):
        db = load_db(SANCTIONS_FILE); uid = str(self.target.id)
        try:
            idx = int(self.index.value) - 1
            db[uid].pop(idx); save_db(SANCTIONS_FILE, db)
            await interaction.response.send_message(f"🗑️ Sanction #{self.index.value} supprimée.", ephemeral=False)
        except: await interaction.response.send_message("❌ Numéro invalide.", ephemeral=True)

# --- PANEL DE SANCTION ---
class SanctionView(discord.ui.View):
    def __init__(self, target, admin): super().__init__(timeout=60); self.target, self.admin = target, admin
    async def open_modal(self, i, t): await i.response.send_modal(ReasonModal(self.target, self.admin, t))

    @discord.ui.button(label="Sommation", style=discord.ButtonStyle.secondary, row=0)
    async def b1(self, i, b): await self.open_modal(i, "SOMMATION")
    @discord.ui.button(label="Rappel", style=discord.ButtonStyle.primary, row=0)
    async def b2(self, i, b): await self.open_modal(i, "RAPPEL")
    @discord.ui.button(label="Avertissement", style=discord.ButtonStyle.danger, row=0)
    async def b3(self, i, b): await self.open_modal(i, "AVERTISSEMENT")
    @discord.ui.button(label="Mute 10m", style=discord.ButtonStyle.gray, row=1)
    async def b4(self, i, b): await self.open_modal(i, "MUTE (10m)")
    @discord.ui.button(label="Mute 1h", style=discord.ButtonStyle.gray, row=1)
    async def b5(self, i, b): await self.open_modal(i, "MUTE (1h)")
    @discord.ui.button(label="Exclure 24h", style=discord.ButtonStyle.gray, row=1)
    async def b6(self, i, b): await self.open_modal(i, "EXCLUSION (24h)")
    @discord.ui.button(label="KICK", style=discord.ButtonStyle.danger, row=2)
    async def b7(self, i, b): await self.open_modal(i, "KICK")
    @discord.ui.button(label="BAN", style=discord.ButtonStyle.danger, row=2)
    async def b8(self, i, b): await self.open_modal(i, "BAN")
    
    @discord.ui.button(label="Voir Sanctions", emoji="📂", style=discord.ButtonStyle.success, row=3)
    async def b_view(self, i, b):
        db = load_db(SANCTIONS_FILE); uid = str(self.target.id)
        if uid not in db or not db[uid]: return await i.response.send_message("Vierge.", ephemeral=True)
        emb = discord.Embed(title=f"Casier de {self.target.name}", color=discord.Color.red())
        for idx, s in enumerate(db[uid], 1): emb.add_field(name=f"#{idx} {s['type']}", value=f"📝 {s['raison']}\n📅 {s['date']}", inline=False)
        await i.response.send_message(embed=emb, ephemeral=True)

    @discord.ui.button(label="Supprimer", emoji="🗑️", style=discord.ButtonStyle.gray, row=3)
    async def b_del(self, i, b): await i.response.send_modal(DeleteSanctionModal(self.target))

# --- COMMANDE !COM (MENU D'AIDE) ---
class HelpView(discord.ui.View):
    def __init__(self, ctx): super().__init__(timeout=60); self.ctx = ctx
    
    @discord.ui.button(label="Secteurs", emoji="📍", style=discord.ButtonStyle.primary)
    async def btn_sect(self, i, b):
        db = load_db(DB_FILE); msg = "**Secteurs :**\n" + "\n".join([f"**{k}** : {len(v)} pers." for k, v in db.items()])
        await i.response.send_message(msg or "Vide.", ephemeral=True)

    @discord.ui.button(label="Sauvegarde", emoji="📦", style=discord.ButtonStyle.secondary)
    async def btn_back(self, i, b):
        files = [discord.File(f) for f in [DB_FILE, SANCTIONS_FILE] if os.path.exists(f)]
        if files: await self.ctx.author.send("📦 Backup :", files=files)
        await i.response.send_message("✅ Backup envoyé en MP.", ephemeral=True)

# --- BOT CORE ---
@bot.event
async def on_ready():
    print(f"✅ Bot prêt : {bot.user}")
    if not backup_automatique.is_running(): backup_automatique.start()

@tasks.loop(hours=24)
async def backup_automatique():
    user = await bot.fetch_user(ID_TON_COMPTE)
    files = [discord.File(f) for f in [DB_FILE, SANCTIONS_FILE] if os.path.exists(f)]
    if user and files: await user.send("📦 **Backup Automatique**", files=files)

@bot.command()
@commands.has_permissions(administrator=True)
async def com(ctx):
    emb = discord.Embed(title="🎮 Menu de Commandes Rapides", description="Clique sur les boutons pour agir discrètement.", color=discord.Color.blue())
    await ctx.send(embed=emb, view=HelpView(ctx))

@bot.command()
@commands.has_permissions(administrator=True)
async def sanction(ctx, membre: discord.Member):
    await ctx.send(embed=discord.Embed(title=f"⚖️ Panel : {membre.display_name}", color=0xffa500), view=SanctionView(membre, ctx.author))

@bot.command()
@commands.has_permissions(administrator=True)
async def casier(ctx, membre: discord.Member):
    db = load_db(SANCTIONS_FILE); uid = str(membre.id)
    if uid not in db or not db[uid]: return await ctx.send("✅ Vide.")
    emb = discord.Embed(title=f"📁 Casier : {membre.display_name}", color=discord.Color.red())
    for i, s in enumerate(db[uid], 1): emb.add_field(name=f"#{i} {s['type']}", value=f"📝 {s['raison']}\n📅 {s['date']}", inline=False)
    await ctx.send(embed=emb)

@bot.command()
@commands.has_permissions(administrator=True)
async def ajouter_secteur(ctx, membre: discord.Member, secteur: str):
    secteur = secteur.upper().zfill(2) if secteur.isdigit() and len(secteur) == 1 else secteur.upper()
    db = load_db(DB_FILE); db.setdefault(secteur, [])
    if membre.id not in db[secteur]: db[secteur].append(membre.id); save_db(DB_FILE, db)
    await ctx.send(f"✅ {membre.display_name} -> {secteur}")

@bot.command()
@commands.has_permissions(administrator=True)
async def voir_base(ctx):
    db = load_db(DB_FILE); msg = "**Répertoire :**\n" + "\n".join([f"**{k}** : {', '.join([f'<@{u}>' for u in v])}" for k, v in db.items() if v])
    await ctx.send(msg[:2000] if msg else "Vide.")

@bot.command()
@commands.has_permissions(administrator=True)
async def restore(ctx):
    if ctx.message.attachments:
        att = ctx.message.attachments[0]
        if att.filename in [DB_FILE, SANCTIONS_FILE]: await att.save(att.filename); await ctx.send(f"✅ {att.filename} restauré.")

keep_alive()
bot.run(TOKEN)
