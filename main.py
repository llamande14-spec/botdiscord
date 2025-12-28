import discord
from discord.ext import commands, tasks
import os
import json
import datetime
import asyncio
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

# --- NOTIFICATION MP AUTOMATIQUE ---
async def notifier_sanction(member, type_s, raison):
    """Envoie un MP détaillé au membre lors d'une sanction"""
    embed = discord.Embed(title="⚠️ Notification de Sanction", color=discord.Color.red())
    embed.add_field(name="Serveur", value=member.guild.name, inline=True)
    embed.add_field(name="Type de Sanction", value=type_s, inline=True)
    embed.add_field(name="Motif / Raison", value=raison, inline=False)
    embed.set_footer(text=f"Date : {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}")
    try:
        await member.send(embed=embed)
    except:
        pass # Si les MP sont fermés, on ignore l'erreur

# --- STATUT DYNAMIQUE ---
@tasks.loop(seconds=15)
async def dynamic_status():
    await bot.wait_until_ready()
    db_sect = load_db(DB_FILE)
    count_sect = len([k for k, v in db_sect.items() if v])
    total_members = sum(g.member_count for g in bot.guilds)
    
    status_list = [
        discord.Activity(type=discord.ActivityType.watching, name="👑 Créateur : louis_lmd"),
        discord.Activity(type=discord.ActivityType.watching, name=f"👥 {total_members} membres"),
        discord.Activity(type=discord.ActivityType.competing, name=f"📍 {count_sect} secteurs"),
        discord.Activity(type=discord.ActivityType.listening, name="🛡️ Sécurité Active"),
        discord.Activity(type=discord.ActivityType.playing, name="⚡ !panel | !sanction")
    ]
    await bot.change_presence(status=discord.Status.online, activity=random.choice(status_list))

# --- TÂCHE AUTOMATIQUE (SAUVEGARDE 24H) ---
@tasks.loop(hours=24)
async def auto_backup():
    try:
        u = await bot.fetch_user(ID_TON_COMPTE)
        files = [discord.File(f) for f in [DB_FILE, SANCTIONS_FILE] if os.path.exists(f)]
        if files: await u.send("🔄 **Sauvegarde Automatique (24h)**", files=files)
    except: pass

# --- QUESTIONNAIRE DE BIENVENUE ---
async def lancer_questionnaire(member):
    try:
        await member.send(f"Salut {member.name} ! Bienvenue sur **{member.guild.name}** 🎉")
        questions = ["Pseudo AS ?", "Secteur (Département, ex: 75) ?", "Motivation ?", "Autres jeux ?"]
        reponses = []
        for q in questions:
            await member.send(q)
            def check(m): return m.author == member and isinstance(m.channel, discord.DMChannel)
            msg = await bot.wait_for("message", check=check, timeout=600.0)
            reponses.append(msg.content)

        secteur = reponses[1].strip().upper().zfill(2) if reponses[1].strip().isdigit() and len(reponses[1].strip()) == 1 else reponses[1].strip().upper()
        status = "❌ Secteur invalide"
        if secteur in DEPARTEMENTS_VALIDES:
            db = load_db(DB_FILE)
            db.setdefault(secteur, [])
            if member.id not in db[secteur]:
                db[secteur].append(member.id)
                save_db(DB_FILE, db)
                status = f"✅ Enregistré au secteur {secteur}"

        salon = bot.get_channel(ID_SALON_REPONSES)
        if salon:
            emb = discord.Embed(title=f"🆕 Fiche de {member.name}", color=discord.Color.blue())
            emb.add_field(name="Pseudo AS", value=reponses[0], inline=True)
            emb.add_field(name="Secteur", value=reponses[1], inline=True)
            emb.add_field(name="Statut Base", value=status, inline=False)
            await salon.send(embed=emb)
        await member.send(f"Merci ! {status}")
        return True
    except: return False

# --- MODALS (FENÊTRES) ---

class ViewCasierModal(discord.ui.Modal, title="Consulter un Casier"):
    user_input = discord.ui.TextInput(label="ID ou Mention du membre", placeholder="Qui ?", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        uid = self.user_input.value.replace("<@", "").replace(">", "").replace("!", "")
        db = load_db(SANCTIONS_FILE)
        emb = discord.Embed(title=f"📂 Casier de {uid}", color=0xe74c3c)
        if uid in db and db[uid]:
            for idx, s in enumerate(db[uid], 1):
                emb.add_field(name=f"#{idx} {s['type']}", value=f"📝 {s['raison']}\n📅 {s['date']}\n👤 Par: {s['par']}", inline=False)
        else: emb.description = "Casier vierge."
        await interaction.response.send_message(embed=emb, ephemeral=True)

class DeleteSanctionModal(discord.ui.Modal, title="Supprimer une Sanction"):
    def __init__(self, target_id=None):
        super().__init__()
        self.target_id = target_id
        if not target_id:
            self.user_input = discord.ui.TextInput(label="ID ou Mention du membre", placeholder="Qui ?", required=True)
            self.add_item(self.user_input)
        self.index = discord.ui.TextInput(label="Numéro de la sanction", placeholder="Ex: 1", required=True)
        self.add_item(self.index)

    async def on_submit(self, interaction: discord.Interaction):
        uid = self.user_input.value.replace("<@", "").replace(">", "").replace("!", "") if not self.target_id else str(self.target_id)
        db = load_db(SANCTIONS_FILE)
        if uid in db and db[uid]:
            try:
                idx = int(self.index.value) - 1
                suppr = db[uid].pop(idx)
                save_db(SANCTIONS_FILE, db)
                await interaction.response.send_message(f"🗑️ Sanction #{self.index.value} supprimée.", ephemeral=True)
            except: await interaction.response.send_message("❌ Numéro invalide.", ephemeral=True)
        else: await interaction.response.send_message("❌ Aucun casier.", ephemeral=True)

class SecteurActionModal(discord.ui.Modal):
    def __init__(self, action_type):
        super().__init__(title=f"{action_type} un Membre")
        self.action_type = action_type
        self.user_id = discord.ui.TextInput(label="ID ou Mention du membre", required=True)
        self.secteur = discord.ui.TextInput(label="Secteur (Département)", min_length=1, max_length=3, required=True)
        self.add_item(self.user_id)
        self.add_item(self.secteur)

    async def on_submit(self, interaction: discord.Interaction):
        db = load_db(DB_FILE)
        s = self.secteur.value.upper().zfill(2) if self.secteur.value.isdigit() and len(self.secteur.value) == 1 else self.secteur.value.upper()
        uid = int(self.user_id.value.replace("<@", "").replace(">", "").replace("!", ""))
        if self.action_type == "Ajouter":
            db.setdefault(s, [])
            if uid not in db[s]: db[s].append(uid)
            msg = f"✅ Ajouté en {s}."
        else:
            if s in db and uid in db[s]: db[s].remove(uid)
            msg = f"🗑️ Retiré de {s}."
        save_db(DB_FILE, db)
        await interaction.response.send_message(msg, ephemeral=True)

class SanctionGlobalModal(discord.ui.Modal):
    def __init__(self, type_s, admin, target_member=None):
        super().__init__(title=f"Action : {type_s}")
        self.type_s, self.admin, self.target_member = type_s, admin, target_member
        if not target_member:
            self.user_input = discord.ui.TextInput(label="ID ou Mention du membre", required=True)
            self.add_item(self.user_input)
        self.raison = discord.ui.TextInput(label="Raison", style=discord.TextStyle.paragraph, required=True)
        self.add_item(self.raison)

    async def on_submit(self, interaction: discord.Interaction):
        uid_str = self.user_input.value.replace("<@", "").replace(">", "").replace("!", "") if not self.target_member else str(self.target_member.id)
        member = self.target_member or interaction.guild.get_member(int(uid_str))
        if not member: return await interaction.response.send_message("❌ Membre introuvable.", ephemeral=True)
        
        # Enregistrement DB
        db = load_db(SANCTIONS_FILE)
        db.setdefault(str(member.id), [])
        db[str(member.id)].append({"type": self.type_s, "raison": self.raison.value, "date": discord.utils.utcnow().strftime("%d/%m/%Y %H:%M"), "par": self.admin.display_name})
        save_db(SANCTIONS_FILE, db)
        
        # Notification MP
        await notifier_sanction(member, self.type_s, self.raison.value)

        # Action Discord
        try:
            if self.type_s == "KICK": await member.kick(reason=self.raison.value)
            elif self.type_s == "BAN": await member.ban(reason=self.raison.value)
            elif "MUTE" in self.type_s or "EXCLU" in self.type_s:
                m = 10 if "10m" in self.type_s else (60 if "1h" in self.type_s else 1440)
                await member.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=m), reason=self.raison.value)
        except: pass
        await interaction.response.send_message(f"✅ Appliqué à {member.display_name}.", ephemeral=True)

# --- VIEWS DU !PANEL ---

class MainMenuView(discord.ui.View):
    def __init__(self, ctx): super().__init__(timeout=60); self.ctx = ctx
    @discord.ui.button(label="Secteurs", emoji="📍", style=discord.ButtonStyle.primary)
    async def b1(self, i, b): await i.response.edit_message(embed=discord.Embed(title="📍 Menu Secteurs", color=0x3498db), view=SecteurMenuView(self.ctx))
    @discord.ui.button(label="Sanctions", emoji="⚖️", style=discord.ButtonStyle.danger)
    async def b2(self, i, b): await i.response.edit_message(embed=discord.Embed(title="⚖️ Menu Sanctions", color=0xe74c3c), view=SanctionGlobalView(self.ctx))
    @discord.ui.button(label="Sauvegarde", emoji="📦", style=discord.ButtonStyle.success)
    async def b3(self, i, b): await i.response.edit_message(embed=discord.Embed(title="📦 Menu Sauvegarde", color=0x2ecc71), view=BackupMenuView(self.ctx))

class SecteurMenuView(discord.ui.View):
    def __init__(self, ctx): super().__init__(timeout=60); self.ctx = ctx
    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.success)
    async def add(self, i, b): await i.response.send_modal(SecteurActionModal("Ajouter"))
    @discord.ui.button(label="Retirer", style=discord.ButtonStyle.danger)
    async def rem(self, i, b): await i.response.send_modal(SecteurActionModal("Retirer"))
    @discord.ui.button(label="Voir Répertoire", style=discord.ButtonStyle.secondary)
    async def view(self, i, b):
        db = load_db(DB_FILE)
        msg = "**📍 Répertoire :**\n" + "\n".join([f"**{k}** : {', '.join([f'<@{u}>' for u in v])}" for k, v in db.items() if v])
        await i.response.send_message(msg if len(msg)>15 else "Vide", ephemeral=True)
    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray)
    async def back(self, i, b): await i.response.edit_message(embed=discord.Embed(title="🛡️ Menu Admin"), view=MainMenuView(self.ctx))

class SanctionGlobalView(discord.ui.View):
    def __init__(self, ctx): super().__init__(timeout=60); self.ctx = ctx
    @discord.ui.button(label="Sommation", row=0)
    async def s1(self, i, b): await i.response.send_modal(SanctionGlobalModal("SOMMATION", i.user))
    @discord.ui.button(label="Rappel", row=0)
    async def s2(self, i, b): await i.response.send_modal(SanctionGlobalModal("RAPPEL", i.user))
    @discord.ui.button(label="Avertissement", row=0)
    async def s3(self, i, b): await i.response.send_modal(SanctionGlobalModal("AVERTISSEMENT", i.user))
    @discord.ui.button(label="Mute 10m", row=1)
    async def s4(self, i, b): await i.response.send_modal(SanctionGlobalModal("MUTE 10m", i.user))
    @discord.ui.button(label="Mute 1h", row=1)
    async def s5(self, i, b): await i.response.send_modal(SanctionGlobalModal("MUTE 1h", i.user))
    @discord.ui.button(label="Exclure 24h", row=1)
    async def s6(self, i, b): await i.response.send_modal(SanctionGlobalModal("EXCLU 24h", i.user))
    @discord.ui.button(label="KICK", style=discord.ButtonStyle.danger, row=2)
    async def s7(self, i, b): await i.response.send_modal(SanctionGlobalModal("KICK", i.user))
    @discord.ui.button(label="BAN", style=discord.ButtonStyle.danger, row=2)
    async def s8(self, i, b): await i.response.send_modal(SanctionGlobalModal("BAN", i.user))
    @discord.ui.button(label="Voir Casier", emoji="📂", style=discord.ButtonStyle.success, row=3)
    async def v_cas(self, i, b): await i.response.send_modal(ViewCasierModal())
    @discord.ui.button(label="Suppr Sanction", emoji="🗑️", style=discord.ButtonStyle.gray, row=3)
    async def s_del(self, i, b): await i.response.send_modal(DeleteSanctionModal())
    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray, row=4)
    async def back(self, i, b): await i.response.edit_message(embed=discord.Embed(title="🛡️ Menu Admin"), view=MainMenuView(self.ctx))

class BackupMenuView(discord.ui.View):
    def __init__(self, ctx): super().__init__(timeout=60); self.ctx = ctx
    @discord.ui.button(label="Backup Manuelle (MP)", style=discord.ButtonStyle.primary)
    async def send_b(self, i, b):
        f = [discord.File(f) for f in [DB_FILE, SANCTIONS_FILE] if os.path.exists(f)]
        u = await bot.fetch_user(ID_TON_COMPTE)
        if f: await u.send("📦 **Backup Manuelle**", files=f)
        await i.response.send_message("Envoyé en MP !", ephemeral=True)
    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray)
    async def back(self, i, b): await i.response.edit_message(embed=discord.Embed(title="🛡️ Menu Admin"), view=MainMenuView(self.ctx))

# --- PANEL !sanction @membre ---
class PanelSanctionView(discord.ui.View):
    def __init__(self, target, admin): super().__init__(timeout=60); self.target, self.admin = target, admin
    @discord.ui.button(label="Sommation", row=0)
    async def b1(self, i, b): await i.response.send_modal(SanctionGlobalModal("SOMMATION", self.admin, self.target))
    @discord.ui.button(label="Rappel", row=0)
    async def b2(self, i, b): await i.response.send_modal(SanctionGlobalModal("RAPPEL", self.admin, self.target))
    @discord.ui.button(label="Mute 10m", row=1)
    async def b4(self, i, b): await i.response.send_modal(SanctionGlobalModal("MUTE 10m", self.admin, self.target))
    @discord.ui.button(label="Voir Casier", emoji="📂", style=discord.ButtonStyle.success, row=2)
    async def b5(self, i, b):
        db = load_db(SANCTIONS_FILE); uid = str(self.target.id)
        emb = discord.Embed(title=f"Casier : {self.target.name}", color=0xe74c3c)
        if uid in db and db[uid]:
            for idx, s in enumerate(db[uid], 1): emb.add_field(name=f"#{idx} {s['type']}", value=f"📝 {s['raison']}\n📅 {s['date']}", inline=False)
        else: emb.description = "Casier vierge."
        await i.response.send_message(embed=emb, ephemeral=True)
    @discord.ui.button(label="Suppr Sanction", emoji="🗑️", style=discord.ButtonStyle.gray, row=2)
    async def b6(self, i, b): await i.response.send_modal(DeleteSanctionModal(self.target.id))

# --- COMMANDES & EVENTS ---

@bot.event
async def on_ready():
    print(f"✅ {bot.user} Connecté")
    if not auto_backup.is_running(): auto_backup.start()
    if not dynamic_status.is_running(): dynamic_status.start()
    u = await bot.fetch_user(ID_TON_COMPTE)
    f = [discord.File(f) for f in [DB_FILE, SANCTIONS_FILE] if os.path.exists(f)]
    if f: await u.send("🚀 **Bot Redémarré**", files=f)

@bot.event
async def on_member_join(member): await lancer_questionnaire(member)

@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx):
    await ctx.send(embed=discord.Embed(title="🛡️ Menu Admin", color=0x2b2d31), view=MainMenuView(ctx))

@bot.command()
@commands.has_permissions(administrator=True)
async def sanction(ctx, membre: discord.Member):
    await ctx.send(embed=discord.Embed(title=f"⚖️ Modération : {membre.display_name}", color=0xffa500), view=PanelSanctionView(membre, ctx.author))

@bot.command()
@commands.has_permissions(administrator=True)
async def msgmp(ctx, membre: discord.Member):
    await lancer_questionnaire(membre)
    await ctx.send(f"✅ Questionnaire envoyé.")

@bot.command()
@commands.has_permissions(administrator=True)
async def restore(ctx):
    if ctx.message.attachments:
        att = ctx.message.attachments[0]
        if att.filename in [DB_FILE, SANCTIONS_FILE]:
            await att.save(att.filename)
            await ctx.send(f"✅ `{att.filename}` restauré.")

@bot.command()
@commands.has_permissions(administrator=True)
async def backup(ctx):
    files = [discord.File(f) for f in [DB_FILE, SANCTIONS_FILE] if os.path.exists(f)]
    if files: await ctx.author.send("📦 Backup demandée", files=files)
    await ctx.send("✅ Backup envoyée en MP.")

keep_alive()
bot.run(TOKEN)
