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

# --- RECHERCHE UNIVERSELLE ---
def trouver_membre(guild, texte):
    texte = texte.replace("<@", "").replace(">", "").replace("!", "").strip()
    if texte.isdigit(): return guild.get_member(int(texte))
    member = discord.utils.get(guild.members, display_name=texte)
    if not member: member = discord.utils.get(guild.members, name=texte)
    return member

# --- LOGIQUE DE TRI ---
def trier_secteurs(db):
    def key_sort(item):
        k = item[0]
        if k == "2A": return (0, 2.1)
        if k == "2B": return (0, 2.2)
        if k.isdigit(): return (0, int(k))
        return (1, k)
    return sorted(db.items(), key=key_sort)

# --- SYSTÈME DE LOGS ---
async def log_sanction(member, type_s, raison, admin):
    try:
        salon = bot.get_channel(ID_SALON_LOGS) or await bot.fetch_channel(ID_SALON_LOGS)
        if salon:
            emb = discord.Embed(title="📝 Journal des Sanctions", color=0x2f3136, timestamp=discord.utils.utcnow())
            emb.add_field(name="👤 Membre", value=f"{member.mention}", inline=False)
            emb.add_field(name="⚖️ Type", value=f"**{type_s}**", inline=True)
            emb.add_field(name="🛡️ Admin", value=f"{admin.mention}", inline=True)
            emb.add_field(name="💬 Raison", value=raison, inline=False)
            await salon.send(embed=emb)
    except: pass

# --- VIEWS DU PANEL ---
class MainMenuView(discord.ui.View):
    def __init__(self, ctx): super().__init__(timeout=60); self.ctx = ctx
    @discord.ui.button(label="Secteurs", emoji="📍", style=discord.ButtonStyle.primary)
    async def b1(self, i, b): await i.response.edit_message(view=SecteurMenuView(self.ctx))
    @discord.ui.button(label="Sanctions", emoji="⚖️", style=discord.ButtonStyle.danger)
    async def b2(self, i, b): await i.response.edit_message(view=SanctionGlobalView(self.ctx))
    @discord.ui.button(label="Sauvegarde", emoji="📦", style=discord.ButtonStyle.success)
    async def b3(self, i, b):
        f = [discord.File(fi) for fi in [DB_FILE, SANCTIONS_FILE] if os.path.exists(fi)]
        if f: await i.user.send("📦 Sauvegarde manuelle :", files=f)
        await i.response.send_message("✅ Backup envoyé en MP.", ephemeral=True)

class SecteurMenuView(discord.ui.View):
    def __init__(self, ctx): super().__init__(timeout=60); self.ctx = ctx
    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.success)
    async def add(self, i, b):
        modal = discord.ui.Modal(title="Ajouter au Secteur")
        u_in = discord.ui.TextInput(label="Pseudo ou Mention"); modal.add_item(u_in)
        s_in = discord.ui.TextInput(label="Secteur (ex: 2A)"); modal.add_item(s_in)
        async def on_sub(inter):
            m = trouver_membre(inter.guild, u_in.value)
            if not m: return await inter.response.send_message("❌ Inconnu.", ephemeral=True)
            db = load_db(DB_FILE); s = s_in.value.upper().zfill(2)
            db.setdefault(s, []); db[s].append(m.id) if m.id not in db[s] else None
            save_db(DB_FILE, db); await inter.response.send_message(f"✅ {m.display_name} ajouté en {s}.", ephemeral=True)
        modal.on_submit = on_sub; await i.response.send_modal(modal)

    @discord.ui.button(label="Retirer", style=discord.ButtonStyle.danger)
    async def rem(self, i, b):
        modal = discord.ui.Modal(title="Retirer du Secteur")
        u_in = discord.ui.TextInput(label="Pseudo ou Mention"); modal.add_item(u_in)
        s_in = discord.ui.TextInput(label="Secteur"); modal.add_item(s_in)
        async def on_sub(inter):
            m = trouver_membre(inter.guild, u_in.value)
            db = load_db(DB_FILE); s = s_in.value.upper().zfill(2)
            if s in db and m and m.id in db[s]:
                db[s].remove(m.id); save_db(DB_FILE, db)
                await inter.response.send_message(f"🗑️ {m.display_name} retiré du secteur {s}.", ephemeral=True)
            else: await inter.response.send_message("❌ Membre ou secteur non trouvé.", ephemeral=True)
        modal.on_submit = on_sub; await i.response.send_modal(modal)

    @discord.ui.button(label="Voir Répertoire", style=discord.ButtonStyle.secondary)
    async def view_rep(self, i, b):
        db = load_db(DB_FILE); tries = trier_secteurs(db)
        lines = []
        for k, v in tries:
            if v:
                pseudos = [i.guild.get_member(uid).display_name if i.guild.get_member(uid) else f"Inconnu({uid})" for uid in v]
                lines.append(f"**{k}** : {', '.join(pseudos)}")
        msg = "📍 **Répertoire Privé :**\n" + ("\n".join(lines) if lines else "Vide")
        await i.response.send_message(msg, ephemeral=True)
    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray)
    async def back(self, i, b): await i.response.edit_message(view=MainMenuView(self.ctx))

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
    async def v_cas(self, i, b):
        modal = discord.ui.Modal(title="Casier")
        u_in = discord.ui.TextInput(label="Pseudo ou ID"); modal.add_item(u_in)
        async def on_sub(inter):
            m = trouver_membre(inter.guild, u_in.value); uid = str(m.id) if m else u_in.value.strip()
            db = load_db(SANCTIONS_FILE); emb = discord.Embed(title=f"Casier de {uid}", color=0xe74c3c)
            if uid in db:
                for idx, s in enumerate(db[uid], 1):
                    emb.add_field(name=f"#{idx} {s['type']}", value=f"📝 {s['raison']}\n📅 {s['date']}", inline=False)
            else: emb.description = "Vierge."
            await inter.response.send_message(embed=emb, ephemeral=True)
        modal.on_submit = on_sub; await i.response.send_modal(modal)
    @discord.ui.button(label="Supprimer Sanction", emoji="🗑️", style=discord.ButtonStyle.secondary, row=3)
    async def s_del(self, i, b):
        modal = discord.ui.Modal(title="Supprimer Sanction")
        u_in = discord.ui.TextInput(label="Pseudo ou ID"); modal.add_item(u_in)
        idx_in = discord.ui.TextInput(label="Numéro de la sanction"); modal.add_item(idx_in)
        async def on_sub(inter):
            m = trouver_membre(inter.guild, u_in.value); uid = str(m.id) if m else u_in.value.strip(); db = load_db(SANCTIONS_FILE)
            try:
                db[uid].pop(int(idx_in.value)-1); save_db(SANCTIONS_FILE, db)
                await inter.response.send_message("🗑️ Sanction supprimée.", ephemeral=True)
            except: await inter.response.send_message("❌ Numéro invalide.", ephemeral=True)
        modal.on_submit = on_sub; await i.response.send_modal(modal)
    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray, row=4)
    async def back(self, i, b): await i.response.edit_message(view=MainMenuView(self.ctx))

class SanctionGlobalModal(discord.ui.Modal):
    def __init__(self, type_s, admin):
        super().__init__(title=f"Action : {type_s}"); self.type_s, self.admin = type_s, admin
        self.u_in = discord.ui.TextInput(label="Pseudo ou ID"); self.add_item(self.u_in)
        self.r_in = discord.ui.TextInput(label="Raison", style=discord.TextStyle.paragraph); self.add_item(self.r_in)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        m = trouver_membre(interaction.guild, self.u_in.value)
        if not m: return await interaction.followup.send("❌ Membre introuvable.", ephemeral=True)
        db = load_db(SANCTIONS_FILE); uid = str(m.id); db.setdefault(uid, [])
        db[uid].append({"type": self.type_s, "raison": self.r_in.value, "date": datetime.datetime.now().strftime("%d/%m/%Y"), "par": self.admin.display_name})
        save_db(SANCTIONS_FILE, db); await log_sanction(m, self.type_s, self.r_in.value, self.admin)
        try:
            if self.type_s == "KICK": await m.kick(reason=self.r_in.value)
            elif self.type_s == "BAN": await m.ban(reason=self.r_in.value)
            elif "MUTE" in self.type_s or "EXCLU" in self.type_s:
                m_time = 10 if "10m" in self.type_s else (60 if "1h" in self.type_s else 1440)
                await m.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=m_time))
        except: pass
        await interaction.followup.send(f"✅ Action {self.type_s} appliquée.", ephemeral=True)

# --- SAUVEGARDES AUTOMATIQUES ---
@tasks.loop(hours=24)
async def auto_backup():
    await bot.wait_until_ready()
    u = await bot.fetch_user(ID_TON_COMPTE)
    f = [discord.File(fi) for fi in [DB_FILE, SANCTIONS_FILE] if os.path.exists(fi)]
    if u and f: await u.send("📦 **Backup Automatique (24h)**", files=f)

@bot.event
async def on_ready():
    print(f"✅ Connecté : {bot.user}")
    auto_backup.start()
    u = await bot.fetch_user(ID_TON_COMPTE)
    f = [discord.File(fi) for fi in [DB_FILE, SANCTIONS_FILE] if os.path.exists(fi)]
    if u and f: await u.send("🚀 **Redémarrage effectué - Fichiers de données envoyés**", files=f)

@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx):
    await ctx.send(embed=discord.Embed(title="🛡️ Menu Administration", color=0x2b2d31), view=MainMenuView(ctx))

keep_alive()
bot.run(TOKEN)
