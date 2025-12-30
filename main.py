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

# --- VALIDATION STRICTE SECTEUR ---
def est_secteur_valide(s):
    s = s.upper().strip()
    if s in ["2A", "2B"]: return s
    if s.isdigit():
        val = int(s)
        if 1 <= val <= 98: return str(val).zfill(2)
    return None

# --- SÉCURITÉ ADMIN ---
class SecureView(discord.ui.View):
    def __init__(self, ctx, timeout=60):
        super().__init__(timeout=timeout)
        self.ctx = ctx
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Seuls les Administrateurs peuvent utiliser ce panel.", ephemeral=True)
            return False
        return True

# --- RECHERCHE ET TRI ---
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

# --- STATUT DYNAMIQUE ---
@tasks.loop(seconds=20)
async def dynamic_status():
    await bot.wait_until_ready()
    db_sect = load_db(DB_FILE)
    count_sect = len([k for k, v in db_sect.items() if v])
    status_list = [
        discord.Activity(type=discord.ActivityType.watching, name="👑 Créateur : louis_lmd"),
        discord.Activity(type=discord.ActivityType.competing, name=f"📍 {count_sect} secteurs"),
        discord.Activity(type=discord.ActivityType.playing, name="⚡ !panel | !renforts")
    ]
    await bot.change_presence(status=discord.Status.online, activity=random.choice(status_list))

# --- QUESTIONNAIRE ---
class ValidationSecteurView(discord.ui.View):
    def __init__(self, member_id, secteur):
        super().__init__(timeout=None)
        self.member_id, self.secteur = member_id, secteur

    @discord.ui.button(label="Valider le secteur", style=discord.ButtonStyle.success, emoji="✅")
    async def validate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Seuls les Administrateurs peuvent valider un secteur.", ephemeral=True)
        
        db = load_db(DB_FILE)
        db.setdefault(self.secteur, [])
        if self.member_id not in db[self.secteur]:
            db[self.secteur].append(self.member_id)
            save_db(DB_FILE, db)
        
        button.disabled = True
        button.label = "Secteur Validé"
        await interaction.response.edit_message(view=self)

        log_channel = bot.get_channel(ID_SALON_LOGS)
        if log_channel:
            member = interaction.guild.get_member(self.member_id)
            member_name = member.display_name if member else f"ID: {self.member_id}"
            
            emb_log = discord.Embed(title="📍 Secteur Validé", color=discord.Color.green())
            emb_log.add_field(name="Administrateur", value=interaction.user.mention, inline=True)
            emb_log.add_field(name="Membre validé", value=f"{member_name}", inline=True)
            emb_log.add_field(name="Secteur attribué", value=f"**{self.secteur}**", inline=True)
            emb_log.set_footer(text=f"Date : {datetime.datetime.now().strftime('%d/%m/%Y à %H:%M')}")
            
            await log_channel.send(embed=emb_log)

async def lancer_questionnaire(member):
    try:
        await member.send(f"Salut {member.name} ! Bienvenue 🎉")
        questions = ["Pseudo AS ?", "Secteur (ex: 75) ?", "Motivation ?", "Autres jeux ?"]
        reponses = []
        for q in questions:
            await member.send(q)
            msg = await bot.wait_for("message", check=lambda m: m.author == member and isinstance(m.channel, discord.DMChannel), timeout=600.0)
            reponses.append(msg.content)
        
        s_raw = reponses[1]
        secteur = est_secteur_valide(s_raw)
        if not secteur: secteur = "INVALIDE"

        salon = bot.get_channel(ID_SALON_REPONSES)
        if salon:
            emb = discord.Embed(title=f"🆕 Fiche de {member.name}", color=discord.Color.blue())
            emb.add_field(name="👤 Pseudo AS", value=reponses[0], inline=True)
            emb.add_field(name="📍 Secteur proposé", value=secteur, inline=True)
            emb.add_field(name="📝 Motivation", value=reponses[2], inline=False)
            emb.add_field(name="🎮 Autres jeux", value=reponses[3], inline=False)
            view = ValidationSecteurView(member.id, secteur) if secteur != "INVALIDE" else None
            await salon.send(embed=emb, view=view)
        return True
    except: return False

# --- PANEL VIEWS ---
class MainMenuView(SecureView):
    @discord.ui.button(label="Secteurs", emoji="📍", style=discord.ButtonStyle.primary)
    async def b1(self, i, b): await i.response.edit_message(view=SecteurMenuView(self.ctx))
    @discord.ui.button(label="Sanctions", emoji="⚖️", style=discord.ButtonStyle.danger)
    async def b2(self, i, b): await i.response.edit_message(view=SanctionGlobalView(self.ctx))
    @discord.ui.button(label="Sauvegarde", emoji="📦", style=discord.ButtonStyle.success)
    async def b3(self, i, b):
        f = [discord.File(fi) for fi in [DB_FILE, SANCTIONS_FILE] if os.path.exists(fi)]
        if f: await i.user.send("📦 Sauvegarde manuelle :", files=f)
        await i.response.send_message("✅ Backup envoyé en MP.", ephemeral=True)

class SecteurMenuView(SecureView):
    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.success)
    async def add(self, i, b):
        modal = discord.ui.Modal(title="Ajouter au Secteur")
        u_in = discord.ui.TextInput(label="Pseudo/ID"); modal.add_item(u_in)
        s_in = discord.ui.TextInput(label="Secteur (1-98, 2A, 2B)"); modal.add_item(s_in)
        async def on_sub(inter):
            m = trouver_membre(inter.guild, u_in.value)
            s = est_secteur_valide(s_in.value)
            if not m: return await inter.response.send_message("❌ Membre inconnu.", ephemeral=True)
            if not s: return await inter.response.send_message("❌ Secteur invalide.", ephemeral=True)
            db = load_db(DB_FILE); db.setdefault(s, [])
            if m.id not in db[s]: db[s].append(m.id); save_db(DB_FILE, db)
            await inter.response.send_message(f"✅ Ajouté au secteur {s}.", ephemeral=True)
        modal.on_submit = on_sub; await i.response.send_modal(modal)

    @discord.ui.button(label="Retirer", style=discord.ButtonStyle.danger)
    async def rem(self, i, b):
        modal = discord.ui.Modal(title="Retirer"); u_in = discord.ui.TextInput(label="Pseudo/ID"); modal.add_item(u_in)
        s_in = discord.ui.TextInput(label="Secteur"); modal.add_item(s_in)
        async def on_sub(inter):
            m = trouver_membre(inter.guild, u_in.value); db = load_db(DB_FILE); s = s_in.value.upper().strip()
            if s in db and m and m.id in db[s]: db[s].remove(m.id); save_db(DB_FILE, db)
            await inter.response.send_message("✅ Retiré.", ephemeral=True)
        modal.on_submit = on_sub; await i.response.send_modal(modal)

    @discord.ui.button(label="Voir Répertoire", style=discord.ButtonStyle.secondary)
    async def view(self, i, b):
        db = load_db(DB_FILE); tries = trier_secteurs(db); lines = []
        for k, v in tries:
            if v:
                pseudos = [i.guild.get_member(uid).display_name if i.guild.get_member(uid) else f"Inconnu({uid})" for uid in v]
                lines.append(f"**{k}** : {', '.join(pseudos)}")
        v_public = discord.ui.View(timeout=60)
        btn_pub = discord.ui.Button(label="Rendre Public", style=discord.ButtonStyle.primary, emoji="📢")
        async def make_pub(inter):
            public_lines = []
            for k, v in tries:
                if v:
                    pseudos_pub = [inter.guild.get_member(uid).display_name if inter.guild.get_member(uid) else f"Inconnu({uid})" for uid in v]
                    public_lines.append(f"**{k}** : {', '.join(pseudos_pub)}")
            await inter.channel.send(f"📢 **RÉPERTOIRE DES SECTEURS**\n" + "\n".join(public_lines))
            await inter.response.send_message("✅ Répertoire posté.", ephemeral=True)
        btn_pub.callback = make_pub; v_public.add_item(btn_pub)
        await i.response.send_message("📍 **Répertoire Privé :**\n" + ("\n".join(lines) if lines else "Vide"), view=v_public, ephemeral=True)

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
    @discord.ui.button(label="Exclure 24h", row=1)
    async def s6(self, i, b): await i.response.send_modal(SanctionGlobalModal("EXCLU 24h", i.user))
    @discord.ui.button(label="KICK", style=discord.ButtonStyle.danger, row=2)
    async def s7(self, i, b): await i.response.send_modal(SanctionGlobalModal("KICK", i.user))
    @discord.ui.button(label="BAN", style=discord.ButtonStyle.danger, row=2)
    async def s8(self, i, b): await i.response.send_modal(SanctionGlobalModal("BAN", i.user))
    @discord.ui.button(label="Voir Casier", emoji="📂", style=discord.ButtonStyle.success, row=3)
    async def v_cas(self, i, b):
        modal = discord.ui.Modal(title="Casier"); u_in = discord.ui.TextInput(label="Pseudo/ID"); modal.add_item(u_in)
        async def on_sub(inter):
            m = trouver_membre(inter.guild, u_in.value); uid = str(m.id) if m else u_in.value.strip()
            db = load_db(SANCTIONS_FILE); emb = discord.Embed(title=f"Casier de {m.display_name if m else uid}", color=0xe74c3c)
            if uid in db:
                for idx, s in enumerate(db[uid], 1): emb.add_field(name=f"#{idx} {s['type']}", value=f"📝 {s['raison']}\n📅 {s['date']}", inline=False)
            else: emb.description = "Vierge."
            await inter.response.send_message(embed=emb, ephemeral=True)
        modal.on_submit = on_sub; await i.response.send_modal(modal)
    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.gray, row=4)
    async def back(self, i, b): await i.response.edit_message(view=MainMenuView(self.ctx))

class SanctionGlobalModal(discord.ui.Modal):
    def __init__(self, type_s, admin):
        super().__init__(title=f"Action : {type_s}")
        self.type_s, self.admin = type_s, admin
        self.u_in = discord.ui.TextInput(label="Pseudo, Mention ou ID")
        self.add_item(self.u_in)
        self.r_in = discord.ui.TextInput(label="Raison", style=discord.TextStyle.paragraph)
        self.add_item(self.r_in)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        m = trouver_membre(interaction.guild, self.u_in.value)
        if not m: return await interaction.followup.send("❌ Membre introuvable.", ephemeral=True)
        
        date_now = datetime.datetime.now().strftime("%d/%m/%Y à %H:%M")
        db = load_db(SANCTIONS_FILE)
        uid = str(m.id)
        db.setdefault(uid, [])
        db[uid].append({"type": self.type_s, "raison": self.r_in.value, "date": date_now, "par": self.admin.display_name})
        save_db(SANCTIONS_FILE, db)

        mp_status = "✅ MP Envoyé"
        try:
            emb_mp = discord.Embed(title="⚠️ Notification de Sanction", description=f"Sanction sur **{interaction.guild.name}**.", color=0xe74c3c)
            emb_mp.add_field(name="Type", value=self.type_s, inline=True)
            emb_mp.add_field(name="Raison", value=self.r_in.value, inline=False)
            await m.send(embed=emb_mp)
        except: mp_status = "❌ MP Fermés"

        log_channel = bot.get_channel(ID_SALON_LOGS)
        if log_channel:
            emb_log = discord.Embed(title="⚖️ Nouvelle Sanction", color=0xe74c3c)
            emb_log.add_field(name="Utilisateur", value=m.mention, inline=True)
            emb_log.add_field(name="Modérateur", value=self.admin.mention, inline=True)
            emb_log.add_field(name="Type", value=self.type_s, inline=True)
            emb_log.add_field(name="Raison", value=self.r_in.value, inline=True)
            emb_log.set_footer(text=f"Statut MP: {mp_status} | Date: {date_now}")
            await log_channel.send(embed=emb_log)
        await interaction.followup.send(f"✅ Sanction appliquée.", ephemeral=True)

import discord
from discord.ext import commands

# Configuration du bot
intents = discord.Intents.default()
intents.message_content = True  # Obligatoire pour lire le !renforts
bot = commands.Bot(command_command_prefix="!", intents=intents)

class RenfortView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=None)
        self.author_id = author_id
        self.intervenants = []

    @discord.ui.button(label="Je prends le renfort", emoji="🚑", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.mention not in self.intervenants:
            self.intervenants.append(interaction.user.mention)
            embed = interaction.message.embeds[0]
            val = ", ".join(self.intervenants)
            
            if len(embed.fields) > 4: 
                embed.set_field_at(4, name="👥 En route", value=val, inline=False)
            else: 
                embed.add_field(name="👥 En route", value=val, inline=False)
            
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Tu es déjà noté comme intervenant !", ephemeral=True)

    @discord.ui.button(label="Fin de besoin", emoji="🛑", style=discord.ButtonStyle.danger)
    async def end_need(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Vérification des permissions (Admin ou l'auteur de la demande)
        if not interaction.user.guild_permissions.administrator and interaction.user.id != self.author_id:
            return await interaction.response.send_message("❌ Seul l'auteur de la demande ou un admin peut clore ceci.", ephemeral=True)
        
        for item in self.children: 
            item.disabled = True
        
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.greyple()
        embed.title = "🛑 RENFORTS TERMINÉS"
        
        await interaction.response.edit_message(embed=embed, view=self)

@bot.command()
async def renforts(ctx):
    # 1. Création de l'Embed
    embed = discord.Embed(
        title="🚑 DEMANDE DE RENFORTS",
        description=f"Une unité demande de l'aide immédiatement !",
        color=discord.Color.red()
    )
    embed.add_field(name="Demandé par", value=ctx.author.mention, inline=True)
    embed.add_field(name="Salon", value=ctx.channel.mention, inline=True)
    embed.set_footer(text="Cliquez sur le bouton pour répondre à l'appel.")

    # 2. Envoi du message avec la View
    view = RenfortView(author_id=ctx.author.id)
    await ctx.send(content="@everyone", embed=embed, view=view)

    # 3. SUPPRESSION DU MESSAGE !renforts (Ce que tu as demandé)
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        print("Erreur : Le bot n'a pas la permission 'Gérer les messages'.")
    except Exception as e:
        print(f"Erreur lors de la suppression : {e}")

# Lancer le bot
# bot.run("TON_TOKEN_ICI")

@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx):
    view = MainMenuView(ctx)
    await ctx.send(embed=discord.Embed(title="🛡️ Menu Admin", color=0x2b2d31), view=view)

@bot.command()
@commands.has_permissions(administrator=True)
async def msgmp(ctx, membre: discord.Member):
    if await lancer_questionnaire(membre): await ctx.send(f"✅ Envoyé.")
    else: await ctx.send("❌ MP fermés.")

@bot.command()
async def renforts(ctx):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    try:
        q1 = await ctx.send("🚨 N° Inter ?")
        r1 = await bot.wait_for("message", check=check, timeout=60)
        q2 = await ctx.send("☎️ Motif ?")
        r2 = await bot.wait_for("message", check=check, timeout=60)
        q3 = await ctx.send("🚒 Véhicules ?")
        r3 = await bot.wait_for("message", check=check, timeout=60)
        q4 = await ctx.send("🏠 Adresse ?")
        r4 = await bot.wait_for("message", check=check, timeout=60)
        q5 = await ctx.send("📍 Département ?")
        r5 = await bot.wait_for("message", check=check, timeout=60)
        
        s = est_secteur_valide(r5.content)
        if not s: return await ctx.send("❌ Secteur invalide.")
        db = load_db(DB_FILE)
        mentions = " ".join([f"<@{uid}>" for uid in db.get(s, [])])
        emb = discord.Embed(title="🚨 ALERTE RENFORTS", color=discord.Color.red())
        emb.add_field(name="📍 Secteur", value=s, inline=True)
        emb.add_field(name="☎️ Motif", value=r2.content, inline=True)
        emb.add_field(name="🔢 Inter", value=r1.content, inline=True)
        emb.add_field(name="🏠 Adresse", value=r4.content, inline=False)
        emb.add_field(name="🚒 Besoin", value=r3.content, inline=False)
        await ctx.send(content=f"📢 {mentions}", embed=emb, view=RenfortView(ctx.author.id))
    except: pass

@bot.command()
@commands.has_permissions(administrator=True)
async def restore(ctx):
    if ctx.message.attachments:
        for att in ctx.message.attachments:
            if att.filename in [DB_FILE, SANCTIONS_FILE]:
                await att.save(att.filename)
                await ctx.send(f"✅ {att.filename} restauré.")

@tasks.loop(hours=24)
async def auto_backup():
    u = await bot.fetch_user(ID_TON_COMPTE)
    f = [discord.File(fi) for fi in [DB_FILE, SANCTIONS_FILE] if os.path.exists(fi)]
    if u and f: await u.send("📦 **Backup Automatique**", files=f)

@bot.event
async def on_member_join(member): await lancer_questionnaire(member)

@bot.event
async def on_ready():
    print(f"✅ {bot.user} OK")
    if not auto_backup.is_running(): auto_backup.start()
    if not dynamic_status.is_running(): dynamic_status.start()
    u = await bot.fetch_user(ID_TON_COMPTE)
    f = [discord.File(fi) for fi in [DB_FILE, SANCTIONS_FILE] if os.path.exists(fi)]
    if u and f: await u.send("🚀 **Redémarrage**", files=f)

keep_alive()
bot.run(TOKEN)
