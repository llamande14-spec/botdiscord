import discord
from discord.ext import commands, tasks
import os
import json
import datetime
import asyncio
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

# --- RECHERCHE UNIVERSELLE (PSEUDO / MENTION / ID) ---
def trouver_membre(guild, texte):
    texte = texte.replace("<@", "").replace(">", "").replace("!", "").strip()
    # 1. Par ID
    if texte.isdigit():
        return guild.get_member(int(texte))
    # 2. Par Pseudo exact ou Nom d'affichage
    member = discord.utils.get(guild.members, display_name=texte)
    if not member:
        member = discord.utils.get(guild.members, name=texte)
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

# --- VALIDATION AUTOMATIQUE (BOUTON SUR FICHE) ---
class ValidationSecteurView(discord.ui.View):
    def __init__(self, member_id, secteur):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.secteur = secteur

    @discord.ui.button(label="Valider le secteur", style=discord.ButtonStyle.success, emoji="✅")
    async def validate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Admin uniquement.", ephemeral=True)
        
        db = load_db(DB_FILE)
        db.setdefault(self.secteur, [])
        if self.member_id not in db[self.secteur]:
            db[self.secteur].append(self.member_id)
            save_db(DB_FILE, db)
            
        button.disabled = True
        button.label = "Secteur Validé"
        await interaction.response.edit_message(view=self)

# --- QUESTIONNAIRE ---
async def lancer_questionnaire(member):
    try:
        await member.send(f"Salut {member.name} ! Bienvenue 🎉")
        questions = ["Pseudo AS ?", "Secteur (ex: 75) ?", "Motivation ?", "Autres jeux ?"]
        reponses = []
        for q in questions:
            await member.send(q)
            def check(m): return m.author == member and isinstance(m.channel, discord.DMChannel)
            msg = await bot.wait_for("message", check=check, timeout=600.0)
            reponses.append(msg.content)
            
        sect = reponses[1].strip().upper()
        secteur = sect.zfill(2) if sect.isdigit() and len(sect) == 1 else sect
        
        salon = bot.get_channel(ID_SALON_REPONSES)
        if salon:
            emb = discord.Embed(title=f"🆕 Fiche de {member.name}", color=discord.Color.blue())
            emb.add_field(name="👤 Pseudo AS", value=reponses[0], inline=True)
            emb.add_field(name="📍 Secteur", value=secteur, inline=True)
            emb.add_field(name="📝 Motivation", value=reponses[2], inline=False)
            emb.add_field(name="🎮 Autres jeux", value=reponses[3], inline=False)
            await salon.send(embed=emb, view=ValidationSecteurView(member.id, secteur))
        return True
    except: return False

# --- LOGS ---
async def log_sanction(member, type_s, raison, admin):
    salon = bot.get_channel(ID_SALON_LOGS)
    if salon:
        emb = discord.Embed(title="📝 Sanction", color=0x2f3136, timestamp=discord.utils.utcnow())
        emb.add_field(name="Membre", value=f"{member.mention}", inline=True)
        emb.add_field(name="Type", value=type_s, inline=True)
        emb.add_field(name="Admin", value=admin.mention, inline=True)
        emb.add_field(name="Raison", value=raison, inline=False)
        await salon.send(embed=emb)

# --- MODAL SANCTION ---
class SanctionGlobalModal(discord.ui.Modal):
    def __init__(self, type_s, admin):
        super().__init__(title=f"Action : {type_s}")
        self.type_s, self.admin = type_s, admin
        self.user_in = discord.ui.TextInput(label="Pseudo ou Mention", placeholder="Ex: Louis", required=True)
        self.raison = discord.ui.TextInput(label="Raison", style=discord.TextStyle.paragraph, required=True)
        self.add_item(self.user_in); self.add_item(self.raison)

    async def on_submit(self, interaction: discord.Interaction):
        member = trouver_membre(interaction.guild, self.user_in.value)
        if not member: return await interaction.response.send_message("❌ Membre introuvable.", ephemeral=True)
        
        db = load_db(SANCTIONS_FILE); db.setdefault(str(member.id), [])
        db[str(member.id)].append({"type": self.type_s, "raison": self.raison.value, "date": datetime.datetime.now().strftime("%d/%m/%Y"), "par": self.admin.display_name})
        save_db(SANCTIONS_FILE, db)
        await log_sanction(member, self.type_s, self.raison.value, self.admin)
        
        try:
            if self.type_s == "KICK": await member.kick()
            elif self.type_s == "BAN": await member.ban()
            elif "MUTE" in self.type_s or "EXCLU" in self.type_s:
                m = 10 if "10m" in self.type_s else (60 if "1h" in self.type_s else 1440)
                await member.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=m))
        except: pass
        await interaction.response.send_message(f"✅ Sanction {self.type_s} appliquée à {member.display_name}", ephemeral=True)

# --- VIEWS DU PANEL ---
class MainMenuView(discord.ui.View):
    def __init__(self, ctx): super().__init__(timeout=60); self.ctx = ctx
    @discord.ui.button(label="Secteurs", emoji="📍", style=discord.ButtonStyle.primary)
    async def b1(self, i, b): await i.response.edit_message(view=SecteurMenuView(self.ctx))
    @discord.ui.button(label="Sanctions", emoji="⚖️", style=discord.ButtonStyle.danger)
    async def b2(self, i, b): await i.response.edit_message(view=SanctionGlobalView(self.ctx))

class SecteurMenuView(discord.ui.View):
    def __init__(self, ctx): super().__init__(timeout=60); self.ctx = ctx
    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.success)
    async def add(self, i, b):
        modal = discord.ui.Modal(title="Ajouter un membre")
        u_in = discord.ui.TextInput(label="Pseudo ou Mention"); modal.add_item(u_in)
        s_in = discord.ui.TextInput(label="Secteur (ex: 2A)"); modal.add_item(s_in)
        async def on_sub(inter):
            member = trouver_membre(inter.guild, u_in.value)
            if not member: return await inter.response.send_message("❌ Inconnu.", ephemeral=True)
            db = load_db(DB_FILE); s = s_in.value.upper().zfill(2)
            db.setdefault(s, []); db[s].append(member.id) if member.id not in db[s] else None
            save_db(DB_FILE, db); await inter.response.send_message("✅ Ajouté.", ephemeral=True)
        modal.on_submit = on_sub; await i.response.send_modal(modal)

    @discord.ui.button(label="Retirer", style=discord.ButtonStyle.danger)
    async def rem(self, i, b):
        modal = discord.ui.Modal(title="Retirer un membre")
        u_in = discord.ui.TextInput(label="Pseudo ou Mention"); modal.add_item(u_in)
        s_in = discord.ui.TextInput(label="Secteur"); modal.add_item(s_in)
        async def on_sub(inter):
            member = trouver_membre(inter.guild, u_in.value)
            db = load_db(DB_FILE); s = s_in.value.upper().zfill(2)
            if s in db and member and member.id in db[s]:
                db[s].remove(member.id); save_db(DB_FILE, db)
            await inter.response.send_message("✅ Retiré.", ephemeral=True)
        modal.on_submit = on_sub; await i.response.send_modal(modal)

    @discord.ui.button(label="Voir Répertoire", style=discord.ButtonStyle.secondary)
    async def view_rep(self, i, b):
        db = load_db(DB_FILE); tries = trier_secteurs(db)
        lines = [f"**{k}** : " + ", ".join([f"<@{u}>" for u in v]) for k, v in tries if v]
        msg = "📍 **Répertoire :**\n" + ("\n".join(lines) if lines else "Vide")
        await i.response.send_message(msg, ephemeral=True)

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
        u_in = discord.ui.TextInput(label="Pseudo ou Mention"); modal.add_item(u_in)
        async def on_sub(inter):
            m = trouver_membre(inter.guild, u_in.value)
            uid = str(m.id) if m else u_in.value
            db = load_db(SANCTIONS_FILE)
            emb = discord.Embed(title=f"Casier de {uid}", color=0xe74c3c)
            if uid in db:
                for idx, s in enumerate(db[uid], 1):
                    emb.add_field(name=f"#{idx} {s['type']}", value=f"📝 {s['raison']}\n📅 {s['date']}", inline=False)
            else: emb.description = "Vierge."
            await inter.response.send_message(embed=emb, ephemeral=True)
        modal.on_submit = on_sub; await i.response.send_modal(modal)

# --- COMMANDES ---
@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx):
    await ctx.send(embed=discord.Embed(title="🛡️ Menu Administration", color=0x2b2d31), view=MainMenuView(ctx))

@bot.command()
@commands.has_permissions(administrator=True)
async def msgmp(ctx, membre: discord.Member):
    if await lancer_questionnaire(membre): await ctx.send(f"✅ Questionnaire envoyé à {membre.mention}")
    else: await ctx.send("❌ Impossible (MP fermés)")

@bot.event
async def on_member_join(member): await lancer_questionnaire(member)

@bot.event
async def on_ready(): print(f"✅ Connecté : {bot.user}")

keep_alive()
bot.run(TOKEN)
