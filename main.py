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

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Enregistre la vue des renforts pour qu'elle soit immortelle
        self.add_view(PersistentRenfortView())

bot = MyBot()

# --- GESTION DES FICHIERS ---
def load_db(file):
    if not os.path.exists(file): return {}
    try:
        with open(file, "r", encoding='utf-8') as f: return json.load(f)
    except: return {}

def save_db(file, data):
    with open(file, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- VALIDATION ET RECHERCHE ---
def est_secteur_valide(s):
    s = s.upper().strip()
    if s in ["2A", "2B"]: return s
    if s.isdigit():
        val = int(s)
        if 1 <= val <= 98: return str(val).zfill(2)
    return None

def trouver_membre(guild, texte):
    texte = texte.replace("<@", "").replace(">", "").replace("!", "").strip()
    if texte.isdigit(): return guild.get_member(int(texte))
    member = discord.utils.get(guild.members, display_name=texte)
    if not member: member = discord.utils.get(guild.members, name=texte)
    return member

def trier_secteurs(db):
    def key_sort(item):
        k = item[0]
        if k == "2A": return (0, 2.1)
        if k == "2B": return (0, 2.2)
        if k.isdigit(): return (0, int(k))
        return (1, k)
    return sorted(db.items(), key=key_sort)

# --- VIEWS PERSISTANTES (RENFORTS) ---

class PersistentRenfortView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Je prends le renfort", emoji="🚑", style=discord.ButtonStyle.success, custom_id="persistent_take_renfort")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = interaction.message.embeds[0]
        current_intervenants = ""
        field_index = -1
        for idx, field in enumerate(embed.fields):
            if field.name == "👥 En route":
                field_index = idx
                current_intervenants = field.value
                break
        
        if interaction.user.mention in current_intervenants:
            return await interaction.response.send_message("Tu es déjà noté !", ephemeral=True)

        new_val = f"{current_intervenants}, {interaction.user.mention}" if current_intervenants else interaction.user.mention
        
        if field_index != -1:
            embed.set_field_at(field_index, name="👥 En route", value=new_val, inline=False)
        else:
            embed.add_field(name="👥 En route", value=new_val, inline=False)
            
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Fin de besoin", emoji="🛑", style=discord.ButtonStyle.danger, custom_id="persistent_end_renfort")
    async def end_need(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_author = False
        if interaction.message.embeds[0].footer.text:
            if interaction.user.display_name in interaction.message.embeds[0].footer.text:
                is_author = True

        if not interaction.user.guild_permissions.administrator and not is_author:
            return await interaction.response.send_message("❌ Seul l'auteur ou un Admin peut finir cela.", ephemeral=True)
        
        for item in self.children: item.disabled = True
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.greyple()
        embed.title = "🛑 RENFORTS TERMINÉS"
        await interaction.response.edit_message(embed=embed, view=self)

# --- PANELS ADMIN & MODÉRATION ---

class SecureView(discord.ui.View):
    def __init__(self, ctx, timeout=60):
        super().__init__(timeout=timeout)
        self.ctx = ctx
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Seuls les Administrateurs peuvent utiliser ce panel.", ephemeral=True)
            return False
        return True

class MainMenuView(SecureView):
    @discord.ui.button(label="Secteurs", emoji="📍", style=discord.ButtonStyle.primary)
    async def b1(self, i, b): await i.response.edit_message(view=SecteurMenuView(self.ctx))
    @discord.ui.button(label="Sanctions", emoji="⚖️", style=discord.ButtonStyle.danger)
    async def b2(self, i, b): await i.response.edit_message(view=SanctionGlobalView(self.ctx))
    @discord.ui.button(label="Sauvegarde", emoji="📦", style=discord.ButtonStyle.success)
    async def b3(self, i, b):
        f = [discord.File(fi) for fi in [DB_FILE, SANCTIONS_FILE] if os.path.exists(fi)]
        if f: await i.user.send("📦 Backup manuelle :", files=f)
        await i.response.send_message("✅ Backup envoyé en MP.", ephemeral=True)

class SecteurMenuView(SecureView):
    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.success)
    async def add(self, i, b):
        modal = discord.ui.Modal(title="Ajouter"); u_in = discord.ui.TextInput(label="Pseudo/ID"); s_in = discord.ui.TextInput(label="Secteur")
        modal.add_item(u_in); modal.add_item(s_in)
        async def on_sub(inter):
            m, s = trouver_membre(inter.guild, u_in.value), est_secteur_valide(s_in.value)
            if not m or not s: return await inter.response.send_message("❌ Erreur.", ephemeral=True)
            db = load_db(DB_FILE); db.setdefault(s, []); db[s].append(m.id); save_db(DB_FILE, db)
            await inter.response.send_message(f"✅ Ajouté au {s}.", ephemeral=True)
        modal.on_submit = on_sub; await i.response.send_modal(modal)

    @discord.ui.button(label="Retirer", style=discord.ButtonStyle.danger)
    async def remove(self, i, b):
        modal = discord.ui.Modal(title="Retirer"); u_in = discord.ui.TextInput(label="Pseudo/ID"); s_in = discord.ui.TextInput(label="Secteur")
        modal.add_item(u_in); modal.add_item(s_in)
        async def on_sub(inter):
            m, s = trouver_membre(inter.guild, u_in.value), est_secteur_valide(s_in.value)
            db = load_db(DB_FILE)
            if s in db and m.id in db[s]:
                db[s].remove(m.id); save_db(DB_FILE, db)
                await inter.response.send_message(f"✅ Retiré du {s}.", ephemeral=True)
            else: await inter.response.send_message("❌ Non trouvé.", ephemeral=True)
        modal.on_submit = on_sub; await i.response.send_modal(modal)

    @discord.ui.button(label="Voir Répertoire", style=discord.ButtonStyle.secondary)
    async def view(self, i, b):
        db = load_db(DB_FILE); tries = trier_secteurs(db); lines = []
        for k, v in tries:
            if v:
                ps = [i.guild.get_member(uid).display_name if i.guild.get_member(uid) else f"ID:{uid}" for uid in v]
                lines.append(f"**{k}** : {', '.join(ps)}")
        await i.response.send_message("📍 **Répertoire :**\n" + ("\n".join(lines) if lines else "Vide"), ephemeral=True)

    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray)
    async def back(self, i, b): await i.response.edit_message(view=MainMenuView(self.ctx))

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
    @discord.ui.button(label="Exclure 24h", row=1, style=discord.ButtonStyle.danger)
    async def s6(self, i, b): await i.response.send_modal(SanctionGlobalModal("EXCLUSION 24h", i.user))
    @discord.ui.button(label="Voir Casier", row=2, style=discord.ButtonStyle.secondary)
    async def view_casier(self, i, b):
        modal = discord.ui.Modal(title="Voir Casier"); u_in = discord.ui.TextInput(label="Pseudo/ID")
        modal.add_item(u_in)
        async def on_sub(inter):
            m = trouver_membre(inter.guild, u_in.value)
            if not m: return await inter.response.send_message("❌ Inconnu.", ephemeral=True)
            db = load_db(SANCTIONS_FILE); uid = str(m.id)
            if uid not in db or not db[uid]: return await inter.response.send_message("✅ Casier vierge.", ephemeral=True)
            hist = "\n".join([f"[{s['date'][:10]}] {s['type']} - {s['raison']} (par {s['par']})" for s in db[uid]])
            await inter.response.send_message(f"📂 **Casier de {m.display_name} :**\n{hist}", ephemeral=True)
        modal.on_submit = on_sub; await i.response.send_modal(modal)
    @discord.ui.button(label="KICK", style=discord.ButtonStyle.danger, row=3)
    async def s7(self, i, b): await i.response.send_modal(SanctionGlobalModal("KICK", i.user))
    @discord.ui.button(label="BAN", style=discord.ButtonStyle.danger, row=3)
    async def s8(self, i, b): await i.response.send_modal(SanctionGlobalModal("BAN", i.user))
    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray, row=4)
    async def back(self, i, b): await i.response.edit_message(view=MainMenuView(self.ctx))

class SanctionGlobalModal(discord.ui.Modal):
    def __init__(self, type_s, admin):
        super().__init__(title=f"Action : {type_s}")
        self.type_s, self.admin = type_s, admin
        self.u_in = discord.ui.TextInput(label="Pseudo/ID"); self.r_in = discord.ui.TextInput(label="Raison", style=discord.TextStyle.paragraph)
        self.add_item(self.u_in); self.add_item(self.r_in)

    async def on_submit(self, interaction: discord.Interaction):
        m = trouver_membre(interaction.guild, self.u_in.value)
        if not m: return await interaction.response.send_message("❌ Inconnu.", ephemeral=True)
        
        # Sauvegarde en Base de Données
        db = load_db(SANCTIONS_FILE); uid = str(m.id); db.setdefault(uid, [])
        db[uid].append({"type": self.type_s, "raison": self.r_in.value, "date": str(datetime.datetime.now()), "par": self.admin.display_name})
        save_db(SANCTIONS_FILE, db)
        
        # Envoi Log dans le salon spécial
        log_c = bot.get_channel(ID_SALON_LOGS)
        if log_c:
            emb_log = discord.Embed(title="⚖️ Nouvelle Sanction", color=discord.Color.orange())
            emb_log.add_field(name="Cible", value=f"{m.mention} ({m.id})", inline=True)
            emb_log.add_field(name="Admin", value=self.admin.mention, inline=True)
            emb_log.add_field(name="Type", value=f"**{self.type_s}**", inline=True)
            emb_log.add_field(name="Raison", value=self.r_in.value, inline=False)
            emb_log.set_timestamp()
            await log_c.send(embed=emb_log)

        # DM au membre
        try: await m.send(f"⚠️ Sanction sur {interaction.guild.name} : **{self.type_s}**\nRaison : {self.r_in.value}")
        except: pass
        
        await interaction.response.send_message(f"✅ Action {self.type_s} appliquée sur {m.display_name}.", ephemeral=True)

class ValidationSecteurView(discord.ui.View):
    def __init__(self, member_id, secteur):
        super().__init__(timeout=None)
        self.member_id, self.secteur = member_id, secteur
        self.is_public = False

    @discord.ui.button(label="Valider le secteur", style=discord.ButtonStyle.success, emoji="✅")
    async def validate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Admin requis.", ephemeral=True)
        db = load_db(DB_FILE)
        db.setdefault(self.secteur, [])
        if self.member_id not in db[self.secteur]:
            db[self.secteur].append(self.member_id)
            save_db(DB_FILE, db)
        button.disabled, button.label = True, "Secteur Validé"
        await interaction.response.edit_message(view=self)
        
        log_c = bot.get_channel(ID_SALON_LOGS)
        if log_c:
            m = interaction.guild.get_member(self.member_id)
            emb = discord.Embed(title="📍 Secteur Validé", color=discord.Color.green())
            emb.add_field(name="Admin", value=interaction.user.mention)
            emb.add_field(name="Membre", value=m.display_name if m else self.member_id)
            emb.add_field(name="Secteur", value=self.secteur)
            await log_c.send(embed=emb)

    @discord.ui.button(label="Rendre Public", style=discord.ButtonStyle.primary, emoji="🌍")
    async def toggle_public(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Admin requis.", ephemeral=True)
        self.is_public = not self.is_public
        button.label = "Rendre Privé" if self.is_public else "Rendre Public"
        button.style = discord.ButtonStyle.secondary if self.is_public else discord.ButtonStyle.primary
        await interaction.response.edit_message(view=self)

# --- COMMANDES ---

@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx):
    await ctx.send(embed=discord.Embed(title="🛡️ Menu Admin", color=0x2b2d31), view=MainMenuView(ctx))

@bot.command()
async def renforts(ctx):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    try:
        q_list = ["🚨 N° Inter ?", "☎️ Motif ?", "🚒 Véhicules ?", "🏠 Adresse ?", "📍 Département ?"]
        reps = []
        for q in q_list:
            t = await ctx.send(q)
            msg = await bot.wait_for("message", check=check, timeout=60)
            reps.append(msg.content)
            await t.delete(); await msg.delete()
        
        s = est_secteur_valide(reps[4])
        if not s: return await ctx.send("❌ Secteur invalide.")
        
        db = load_db(DB_FILE)
        mentions = " ".join([f"<@{uid}>" for uid in db.get(s, [])])
        
        emb = discord.Embed(title="🚨 ALERTE RENFORTS", color=discord.Color.red())
        emb.add_field(name="👤 Demandeur", value=ctx.author.mention, inline=True)
        emb.add_field(name="📍 Secteur", value=s, inline=True)
        emb.add_field(name="🔢 Inter", value=reps[0], inline=True)
        emb.add_field(name="☎️ Motif", value=reps[1], inline=False)
        emb.add_field(name="🏠 Adresse", value=reps[3], inline=False)
        emb.add_field(name="🚒 Besoin", value=reps[2], inline=False)
        emb.set_footer(text=f"Demande de {ctx.author.display_name}")

        await ctx.send(content=f"📢 {mentions}" if mentions else "@everyone", embed=emb, view=PersistentRenfortView())
        await ctx.message.delete()
    except Exception as e: 
        print(f"Erreur : {e}")
        pass

# --- TASKS & EVENTS ---

@tasks.loop(hours=24)
async def auto_backup():
    u = await bot.fetch_user(ID_TON_COMPTE)
    f = [discord.File(fi) for fi in [DB_FILE, SANCTIONS_FILE] if os.path.exists(fi)]
    if u and f: await u.send("📦 **Backup Automatique**", files=f)

@tasks.loop(seconds=20)
async def dynamic_status():
    await bot.wait_until_ready()
    st = [discord.Activity(type=discord.ActivityType.watching, name="👑 Créateur : louis_lmd"),
          discord.Activity(type=discord.ActivityType.playing, name="⚡ !panel | !renforts")]
    await bot.change_presence(activity=random.choice(st))

@bot.event
async def on_ready():
    print(f"✅ {bot.user} Prêt - Logs de sanctions activés.")
    if not auto_backup.is_running(): auto_backup.start()
    if not dynamic_status.is_running(): dynamic_status.start()

keep_alive()
bot.run(TOKEN)
