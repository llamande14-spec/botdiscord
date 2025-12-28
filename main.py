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
ID_SALON_LOGS = 1439697621156495543
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

# --- LOGIQUE DE TRI ---
def trier_secteurs(db):
    """Trie les secteurs : Chiffres d'abord (01, 02), puis 2A, 2B, puis le reste."""
    def key_sort(item):
        k = item[0]
        if k == "2A": return (0, 2.1)
        if k == "2B": return (0, 2.2)
        if k.isdigit(): return (0, int(k))
        return (1, k)
    return sorted(db.items(), key=key_sort)

# --- VALIDATION SECTEUR (BOUTON FICHE) ---
class ValidationSecteurView(discord.ui.View):
    def __init__(self, member_id, secteur):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.secteur = secteur

    @discord.ui.button(label="Valider le secteur", style=discord.ButtonStyle.success, emoji="✅")
    async def validate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Seul un admin peut valider.", ephemeral=True)
        
        db = load_db(DB_FILE)
        db.setdefault(self.secteur, [])
        if self.member_id not in db[self.secteur]:
            db[self.secteur].append(self.member_id)
            save_db(DB_FILE, db)
            
        button.disabled = True
        button.label = "Secteur Validé"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"✅ Membre ajouté au secteur {self.secteur}.", ephemeral=True)

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
        
        salon = bot.get_channel(ID_SALON_REPONSES)
        if salon:
            emb = discord.Embed(title=f"🆕 Fiche de {member.name}", color=discord.Color.blue())
            emb.add_field(name="Pseudo AS", value=reponses[0], inline=True)
            emb.add_field(name="Secteur proposé", value=secteur, inline=True)
            emb.set_footer(text="Validation admin requise")
            await salon.send(embed=emb, view=ValidationSecteurView(member.id, secteur))
        await member.send("Merci ! Ta fiche est en attente de validation.")
    except: pass

# --- SYSTÈME DE LOGS ---
async def log_sanction(member, type_s, raison, admin):
    salon_logs = bot.get_channel(ID_SALON_LOGS) or await bot.fetch_channel(ID_SALON_LOGS)
    if salon_logs:
        emb = discord.Embed(title="📝 Journal des Sanctions", color=0x2f3136)
        emb.add_field(name="👤 Membre", value=f"{member.mention}", inline=False)
        emb.add_field(name="⚖️ Type", value=f"**{type_s}**", inline=True)
        emb.add_field(name="🛡️ Admin", value=f"{admin.mention}", inline=True)
        emb.add_field(name="💬 Raison", value=raison, inline=False)
        emb.set_timestamp()
        await salon_logs.send(embed=emb)

async def notifier_sanction(member, type_s, raison):
    try:
        emb = discord.Embed(title="⚠️ Notification de Sanction", color=discord.Color.red())
        emb.add_field(name="Type", value=type_s, inline=True)
        emb.add_field(name="Raison", value=raison, inline=False)
        await member.send(embed=emb)
    except: pass

# --- MODALS SANCTIONS ---
class SanctionGlobalModal(discord.ui.Modal):
    def __init__(self, type_s, admin):
        super().__init__(title=f"Action : {type_s}")
        self.type_s, self.admin = type_s, admin
        self.user_input = discord.ui.TextInput(label="ID ou Mention", required=True)
        self.raison = discord.ui.TextInput(label="Raison", style=discord.TextStyle.paragraph, required=True)
        self.add_item(self.user_input); self.add_item(self.raison)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        uid_str = self.user_input.value.replace("<@", "").replace(">", "").replace("!", "")
        member = interaction.guild.get_member(int(uid_str))
        if not member: return await interaction.followup.send("❌ Inconnu.", ephemeral=True)
        db = load_db(SANCTIONS_FILE); db.setdefault(str(member.id), [])
        db[str(member.id)].append({"type": self.type_s, "raison": self.raison.value, "date": datetime.datetime.now().strftime("%d/%m/%Y"), "par": self.admin.display_name})
        save_db(SANCTIONS_FILE, db)
        await log_sanction(member, self.type_s, self.raison.value, self.admin)
        await notifier_sanction(member, self.type_s, self.raison.value)
        try:
            if self.type_s == "KICK": await member.kick(reason=self.raison.value)
            elif self.type_s == "BAN": await member.ban(reason=self.raison.value)
            elif any(x in self.type_s for x in ["MUTE", "EXCLU"]):
                m = 10 if "10m" in self.type_s else (60 if "1h" in self.type_s.lower() else 1440)
                await member.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=m), reason=self.raison.value)
        except: pass
        await interaction.followup.send(f"✅ Fait.", ephemeral=True)

class ViewCasierModal(discord.ui.Modal, title="Consulter un Casier"):
    user_input = discord.ui.TextInput(label="ID ou Mention", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        uid = self.user_input.value.replace("<@", "").replace(">", "").replace("!", "")
        db = load_db(SANCTIONS_FILE)
        emb = discord.Embed(title=f"📂 Casier de {uid}", color=0xe74c3c)
        if uid in db and db[uid]:
            for idx, s in enumerate(db[uid], 1):
                emb.add_field(name=f"#{idx} {s['type']}", value=f"📝 {s['raison']}\n📅 {s['date']}", inline=False)
        else: emb.description = "Vierge."
        await interaction.response.send_message(embed=emb, ephemeral=True)

class DeleteSanctionModal(discord.ui.Modal, title="Supprimer une Sanction"):
    user_input = discord.ui.TextInput(label="ID ou Mention", required=True)
    index = discord.ui.TextInput(label="Numéro", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        uid = self.user_input.value.replace("<@", "").replace(">", "").replace("!", "")
        db = load_db(SANCTIONS_FILE)
        if uid in db and db[uid]:
            try:
                idx = int(self.index.value) - 1
                db[uid].pop(idx); save_db(SANCTIONS_FILE, db)
                await interaction.response.send_message("🗑️ Supprimé.", ephemeral=True)
            except: await interaction.response.send_message("❌ Index invalide.", ephemeral=True)

# --- VIEWS ---
class SecureView(discord.ui.View):
    def __init__(self, ctx): super().__init__(timeout=60); self.ctx = ctx
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Privé.", ephemeral=True)
            return False
        return True

class MainMenuView(SecureView):
    @discord.ui.button(label="Secteurs", emoji="📍", style=discord.ButtonStyle.primary)
    async def b1(self, i, b): await i.response.edit_message(embed=discord.Embed(title="📍 Secteurs"), view=SecteurMenuView(self.ctx))
    @discord.ui.button(label="Sanctions", emoji="⚖️", style=discord.ButtonStyle.danger)
    async def b2(self, i, b): await i.response.edit_message(embed=discord.Embed(title="⚖️ Sanctions"), view=SanctionGlobalView(self.ctx))
    @discord.ui.button(label="Sauvegarde", emoji="📦", style=discord.ButtonStyle.success)
    async def b3(self, i, b): await i.response.edit_message(embed=discord.Embed(title="📦 Sauvegarde"), view=BackupMenuView(self.ctx))

class SecteurMenuView(SecureView):
    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.success)
    async def add(self, i, b): await i.response.send_modal(SecteurActionModal("Ajouter"))
    @discord.ui.button(label="Retirer", style=discord.ButtonStyle.danger)
    async def rem(self, i, b): await i.response.send_modal(SecteurActionModal("Retirer"))
    @discord.ui.button(label="Voir Répertoire", style=discord.ButtonStyle.secondary)
    async def view(self, i, b):
        db = load_db(DB_FILE)
        secteurs_tries = trier_secteurs(db)
        lines = [f"**{k}** : " + ", ".join([f"<@{u}>" for u in v]) for k, v in secteurs_tries if v]
        msg = "**📍 Répertoire :**\n" + ("\n".join(lines) if lines else "Vide")
        
        view = discord.ui.View(timeout=30)
        btn_public = discord.ui.Button(label="Rendre Public", style=discord.ButtonStyle.primary, emoji="📢")
        async def make_public(inter):
            await inter.channel.send(f"📢 **RÉPERTOIRE DES SECTEURS**\n" + "\n".join(lines))
            await inter.response.send_message("✅ Posté.", ephemeral=True)
        btn_public.callback = make_public; view.add_item(btn_public)
        await i.response.send_message(msg, view=view, ephemeral=True)
    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray)
    async def back(self, i, b): await i.response.edit_message(embed=discord.Embed(title="🛡️ Menu Admin"), view=MainMenuView(self.ctx))

class SanctionGlobalView(SecureView):
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
    @discord.ui.button(label="Suppr Sanction", emoji="🗑️", style=discord.ButtonStyle.secondary, row=3)
    async def s_del(self, i, b): await i.response.send_modal(DeleteSanctionModal())
    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray, row=4)
    async def back(self, i, b): await i.response.edit_message(embed=discord.Embed(title="🛡️ Menu Admin"), view=MainMenuView(self.ctx))

class BackupMenuView(SecureView):
    @discord.ui.button(label="Backup MP", style=discord.ButtonStyle.primary)
    async def send_b(self, i, b):
        f = [discord.File(fil) for fil in [DB_FILE, SANCTIONS_FILE] if os.path.exists(fil)]
        u = await bot.fetch_user(ID_TON_COMPTE)
        if f: await u.send("📦 Backup", files=f)
        await i.response.send_message("✅", ephemeral=True)
    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray)
    async def back(self, i, b): await i.response.edit_message(embed=discord.Embed(title="🛡️ Menu Admin"), view=MainMenuView(self.ctx))

class SecteurActionModal(discord.ui.Modal):
    def __init__(self, action_type):
        super().__init__(title=f"{action_type}")
        self.action_type = action_type
        self.user_id = discord.ui.TextInput(label="ID/Mention", required=True)
        self.secteur = discord.ui.TextInput(label="Secteur", min_length=1, max_length=3, required=True)
        self.add_item(self.user_id); self.add_item(self.secteur)
    async def on_submit(self, interaction: discord.Interaction):
        db = load_db(DB_FILE)
        s = self.secteur.value.upper().zfill(2) if self.secteur.value.isdigit() and len(self.secteur.value) == 1 else self.secteur.value.upper()
        uid = int(self.user_id.value.replace("<@", "").replace(">", "").replace("!", ""))
        if self.action_type == "Ajouter":
            db.setdefault(s, []); db[s].append(uid) if uid not in db[s] else None
        else:
            if s in db and uid in db[s]: db[s].remove(uid)
        save_db(DB_FILE, db); await interaction.response.send_message("✅", ephemeral=True)

class RenfortView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.intervenants = []
    @discord.ui.button(label="Je prends le renfort", emoji="🚑", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.mention not in self.intervenants:
            self.intervenants.append(interaction.user.mention)
            embed = interaction.message.embeds[0]
            val = ", ".join(self.intervenants)
            if len(embed.fields) > 4: embed.set_field_at(4, name="👥 En route", value=val, inline=False)
            else: embed.add_field(name="👥 En route", value=val, inline=False)
            await interaction.response.edit_message(embed=embed, view=self)

@tasks.loop(hours=24)
async def auto_backup():
    await bot.wait_until_ready()
    u = await bot.fetch_user(ID_TON_COMPTE)
    f = [discord.File(fil) for fil in [DB_FILE, SANCTIONS_FILE] if os.path.exists(fil)]
    if f: await u.send("📦 Sauvegarde Auto", files=f)

@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx):
    view = MainMenuView(ctx)
    msg = await ctx.send(embed=discord.Embed(title="🛡️ Menu Admin", color=0x2b2d31), view=view)
    await view.wait()
    try: await msg.delete()
    except: pass

@bot.command()
async def renforts(ctx):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    msgs = [ctx.message]
    try:
        q1 = await ctx.send("🚨 N° Inter ?"); msgs.append(q1)
        r1 = await bot.wait_for("message", check=check, timeout=60); msgs.append(r1)
        q2 = await ctx.send("🚒 Véhicules ?"); msgs.append(q2)
        r2 = await bot.wait_for("message", check=check, timeout=60); msgs.append(r2)
        q3 = await ctx.send("🏠 Adresse ?"); msgs.append(q3)
        r3 = await bot.wait_for("message", check=check, timeout=60); msgs.append(r3)
        q4 = await ctx.send("📍 Département ?"); msgs.append(q4)
        r4 = await bot.wait_for("message", check=check, timeout=60); msgs.append(r4)
        s = r4.content.strip().upper().zfill(2); db = load_db(DB_FILE)
        mentions = " ".join([f"<@{uid}>" for uid in db.get(s, [])])
        emb = discord.Embed(title="🚨 ALERTE RENFORTS", color=discord.Color.red())
        emb.add_field(name="📍 Secteur", value=s, inline=True)
        emb.add_field(name="🔢 Inter", value=r1.content, inline=True)
        emb.add_field(name="🏠 Adresse", value=r3.content, inline=False)
        emb.add_field(name="🚒 Besoin", value=r2.content, inline=False)
        try: await ctx.channel.delete_messages(msgs)
        except: pass
        await ctx.send(content=f"📢 {mentions}", embed=emb, view=RenfortView())
    except: pass

@bot.event
async def on_member_join(member): await lancer_questionnaire(member)

@bot.event
async def on_ready():
    print(f"✅ {bot.user} OK")
    if not auto_backup.is_running(): auto_backup.start()
    u = await bot.fetch_user(ID_TON_COMPTE)
    f = [discord.File(fi) for fi in [DB_FILE, SANCTIONS_FILE] if os.path.exists(fi)]
    if f: await u.send("🚀 Redémarrage", files=f)

keep_alive()
bot.run(TOKEN)
