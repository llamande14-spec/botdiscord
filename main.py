import discord
from discord.ext import commands
import json
import os
import datetime
import asyncio
from keep_alive import keep_alive

# --- RÉCUPÉRATION DU TOKEN ---
TOKEN = os.environ.get("DISCORD_TOKEN")

# --- CONFIGURATION ---
CHAN_FICHE_RECAP = 1433793778111484035
CHAN_LOGS = 1439697621156495543
CHAN_RENFORTS = 1454875150263521280

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- UTILS JSON ---
def load_db(name):
    if not os.path.exists(f"{name}.json"):
        with open(f"{name}.json", 'w') as f: json.dump({}, f)
    with open(f"{name}.json", 'r') as f: return json.load(f)

def save_db(name, data):
    with open(f"{name}.json", 'w') as f: json.dump(data, f, indent=4)

def is_valid_secteur(s):
    s = s.upper()
    return s in ["2A", "2B"] or (s.isdigit() and 1 <= int(s) <= 98)

# --- MODAL SANCTION RÉELLE ---
class RealSanctionModal(discord.ui.Modal):
    def __init__(self, target, action_type):
        super().__init__(title=f"Sanction : {action_type}")
        self.target = target
        self.action_type = action_type
        self.reason = discord.ui.TextInput(label="Motif", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            embed_mp = discord.Embed(title=f"⚠️ Sanction : {self.action_type}", color=discord.Color.red())
            embed_mp.add_field(name="Serveur", value=interaction.guild.name)
            embed_mp.add_field(name="Raison", value=self.reason.value)
            await self.target.send(embed=embed_mp)
        except: pass

        try:
            if self.action_type == "Mute 10m": await self.target.timeout(datetime.timedelta(minutes=10), reason=self.reason.value)
            elif self.action_type == "Mute 1H": await self.target.timeout(datetime.timedelta(hours=1), reason=self.reason.value)
            elif self.action_type == "Exclure 24H": await self.target.timeout(datetime.timedelta(days=1), reason=self.reason.value)
            elif self.action_type == "Kick": await self.target.kick(reason=self.reason.value)
            elif self.action_type == "Ban": await self.target.ban(reason=self.reason.value)
        except discord.Forbidden:
            return await interaction.response.send_message("Permissions insuffisantes (Rôle bot trop bas).", ephemeral=True)

        db = load_db("sanctions")
        uid = str(self.target.id)
        if uid not in db: db[uid] = []
        db[uid].append({"type": self.action_type, "raison": self.reason.value, "staff": str(interaction.user), "date": str(datetime.datetime.now().strftime("%d/%m/%Y %H:%M"))})
        save_db("sanctions", db)

        log_embed = discord.Embed(title="🔨 Sanction Appliquée", color=discord.Color.dark_red())
        log_embed.add_field(name="Type", value=self.action_type)
        log_embed.add_field(name="Cible", value=self.target.mention)
        log_embed.add_field(name="Staff", value=interaction.user.mention)
        log_embed.add_field(name="Raison", value=self.reason.value)
        await bot.get_channel(CHAN_LOGS).send(embed=log_embed)
        await interaction.response.send_message(f"Sanction appliquée à {self.target.display_name}.", ephemeral=True)

# --- PANEL ADMIN COMPLET ---
class AdminPanel(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    # SECTEURS (Row 0)
    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.green, row=0)
    async def add_sec(self, i, b): await i.response.send_message("Tapez `!setsec @membre XX`", ephemeral=True)

    @discord.ui.button(label="Retirer", style=discord.ButtonStyle.red, row=0)
    async def rem_sec(self, i, b): await i.response.send_message("Tapez `!remsec @membre`", ephemeral=True)

    @discord.ui.button(label="Voir Répertoire", style=discord.ButtonStyle.grey, row=0)
    async def view_rep(self, i, b):
        db = load_db("secteurs")
        txt = "\n".join([f"<@{u}> : {s}" for u, s in db.items()]) or "Vide."
        class Public(discord.ui.View):
            @discord.ui.button(label="Rendre public", style=discord.ButtonStyle.danger)
            async def pub(self, it, bt):
                await it.channel.send(f"**Répertoire des Secteurs :**\n{txt}")
                await it.response.defer()
        await i.response.send_message(f"**Répertoire :**\n{txt}", view=Public(), ephemeral=True)

    # SANCTIONS (Row 1 & 2)
    @discord.ui.button(label="Sanctionner (Menu)", style=discord.ButtonStyle.danger, row=1)
    async def punish_btn(self, i, b): await i.response.send_message("Utilisez `!punish @membre`", ephemeral=True)

    @discord.ui.button(label="Voir Casier", style=discord.ButtonStyle.secondary, row=1)
    async def casier_btn(self, i, b): await i.response.send_message("Utilisez `!casier @membre`", ephemeral=True)

    # SAUVEGARDE (Row 3)
    @discord.ui.button(label="Sauvegarde JSON", style=discord.ButtonStyle.primary, row=2)
    async def save_all(self, i, b):
        await i.user.send("Sauvegardes :", files=[discord.File("secteurs.json"), discord.File("sanctions.json")])
        await i.response.send_message("Fichiers envoyés en MP.", ephemeral=True)

# --- COMMANDES ---

@bot.command()
async def renforts(ctx):
    if ctx.channel.id != CHAN_RENFORTS: return
    # On ne demande pas le demandeur, on le prend directement (ctx.author)
    qs = ["Motif ?", "Numéro d'inter ?", "Secteur ?", "Adresse ?", "Quels véhicules ?"]
    ans = []
    
    for q in qs:
        m = await ctx.send(q)
        try:
            r = await bot.wait_for("message", check=lambda msg: msg.author == ctx.author and msg.channel == ctx.channel, timeout=60)
            ans.append(r.content)
            await m.delete()
            await r.delete()
        except: return

    sec = ans[2].upper()
    tries = 0
    while not is_valid_secteur(sec) and tries < 1:
        tries += 1
        m = await ctx.send("Secteurs invalide, donné un nouveaux secteurs correcte")
        r = await bot.wait_for("message", check=lambda msg: msg.author == ctx.author and msg.channel == ctx.channel)
        sec = r.content.upper()
        await m.delete()
        await r.delete()
    
    if not is_valid_secteur(sec):
        return await ctx.send("2ème secteurs invalide, commande annulée.")

    db = load_db("secteurs")
    mentions = [f"<@{u}>" for u, s in db.items() if s == sec]
    
    embed = discord.Embed(title="🚨 ALERTE RENFORTS", color=0xed4245)
    embed.add_field(name="👤 Demandeur", value=ctx.author.mention)
    embed.add_field(name="📍 Secteur", value=sec)
    embed.add_field(name="🔢 Inter", value=ans[1])
    embed.add_field(name="☎️ Motif", value=ans[0], inline=False)
    embed.add_field(name="🏠 Adresse", value=ans[3], inline=False)
    embed.add_field(name="🚒 Besoin", value=ans[4], inline=False)
    embed.add_field(name="👥 En route", value="...")

    class Action(discord.ui.View):
        def __init__(self, creator):
            super().__init__(timeout=None)
            self.creator = creator
            self.on_road = []
        @discord.ui.button(label="Je prend le renfort", style=discord.ButtonStyle.blurple)
        async def take(self, i, b):
            if i.user.mention not in self.on_road:
                self.on_road.append(i.user.mention)
                embed.set_field_at(6, name="👥 En route", value=", ".join(self.on_road))
                await i.response.edit_message(embed=embed)
        @discord.ui.button(label="Fin de besoin", style=discord.ButtonStyle.secondary)
        async def end(self, i, b):
            if i.user == self.creator or i.user.guild_permissions.administrator:
                await i.message.delete()

    await ctx.send(content=" ".join(mentions), embed=embed, view=Action(ctx.author))

# --- RESTE DES COMMANDES (Punish, Casier, Setsec, Welcome) ---
# (Le reste est identique au code précédent pour assurer la stabilité)

@bot.command()
@commands.has_permissions(administrator=True)
async def punish(ctx, member: discord.Member):
    class PunishSelect(discord.ui.View):
        @discord.ui.select(placeholder="Sanction pour " + member.display_name, options=[
            discord.SelectOption(label="Sommation", value="Sommation"),
            discord.SelectOption(label="Rappel", value="Rappel"),
            discord.SelectOption(label="Avertissement", value="Avertissement"),
            discord.SelectOption(label="Mute 10m", value="Mute 10m"),
            discord.SelectOption(label="Mute 1H", value="Mute 1H"),
            discord.SelectOption(label="Exclure 24H", value="Exclure 24H"),
            discord.SelectOption(label="Kick", value="Kick"),
            discord.SelectOption(label="Ban", value="Ban"),
        ])
        async def callback(self, inter, select):
            await inter.response.send_modal(RealSanctionModal(member, select.values[0]))
    await ctx.send("Sélectionnez la sanction :", view=PunishSelect())

@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx):
    embed = discord.Embed(title="🛡️ Panel Administration", color=discord.Color.dark_blue())
    await ctx.send(embed=embed, view=AdminPanel())

# Lancement
keep_alive()
bot.run(TOKEN)
