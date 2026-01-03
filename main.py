import discord
from discord.ext import commands
import json
import os
import datetime
import asyncio
from discord.ext import tasks
from keep_alive import keep_alive

# --- CONFIGURATION ---
TOKEN = os.environ.get("DISCORD_TOKEN")
MY_ID = 697919761312383057 # Ton ID pour les MPs
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

def sort_secteurs(secteur_key):
    if secteur_key == "2A": return -2
    if secteur_key == "2B": return -1
    return int(secteur_key) if secteur_key.isdigit() else 999

# --- TÂCHE DE SAUVEGARDE AUTOMATIQUE EN MP ---
@tasks.loop(hours=24)
async def auto_backup():
    await bot.wait_until_ready()
    user = await bot.fetch_user(MY_ID)
    if user:
        files = []
        if os.path.exists("secteurs.json"): files.append(discord.File("secteurs.json"))
        if os.path.exists("sanctions.json"): files.append(discord.File("sanctions.json"))
        if files:
            await user.send(f"📦 **SAUVEGARDE AUTOMATIQUE (24H)** - {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}", files=files)

# --- VIEWS DU PANEL ---
class MainPanel(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Secteurs", style=discord.ButtonStyle.primary)
    async def sec_cat(self, i, b): await i.response.edit_message(content="📂 **Gestion des Secteurs**", view=SecteurPanel())
    @discord.ui.button(label="Sanctions", style=discord.ButtonStyle.danger)
    async def sanc_cat(self, i, b): await i.response.edit_message(content="⚖️ **Gestion des Sanctions**", view=SanctionPanel())
    @discord.ui.button(label="Sauvegarde", style=discord.ButtonStyle.success)
    async def save_cat(self, i, b):
        files = [discord.File("secteurs.json"), discord.File("sanctions.json")]
        await i.user.send("Voici vos fichiers :", files=files)
        await i.response.send_message("Envoyé en MP !", ephemeral=True)

class SecteurPanel(discord.ui.View):
    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.green)
    async def add(self, i, b): await i.response.send_message("Tapez `!setsec @membre XX`", ephemeral=True)
    @discord.ui.button(label="Retirer", style=discord.ButtonStyle.red)
    async def rem(self, i, b): await i.response.send_message("Tapez `!remsec @membre`", ephemeral=True)
    @discord.ui.button(label="Voir Répertoire", style=discord.ButtonStyle.grey)
    async def view(self, i, b):
        db = load_db("secteurs")
        rep = {}
        for uid, sec in db.items():
            if sec not in rep: rep[sec] = []
            rep[sec].append(f"<@{uid}> (ID: {uid})")
        sorted_keys = sorted(rep.keys(), key=sort_secteurs)
        txt = "\n".join([f"**Secteur {s}** : {', '.join(rep[s])}" for s in sorted_keys]) or "Vide."
        
        class Pub(discord.ui.View):
            @discord.ui.button(label="Rendre public", style=discord.ButtonStyle.danger)
            async def p(self, it, bt): await it.channel.send(f"📖 **Répertoire :**\n{txt}"); await it.response.defer()
        await i.response.send_message(f"**Répertoire :**\n{txt}", view=Pub(), ephemeral=True)
    @discord.ui.button(label="Retour", style=discord.ButtonStyle.secondary)
    async def back(self, i, b): await i.response.edit_message(content="🛠 **Panel Admin**", view=MainPanel())

class SanctionPanel(discord.ui.View):
    @discord.ui.button(label="Sanctionner", style=discord.ButtonStyle.danger)
    async def pun(self, i, b): await i.response.send_message("Tapez `!punish @membre`", ephemeral=True)
    @discord.ui.button(label="Voir Casier", style=discord.ButtonStyle.secondary)
    async def cas(self, i, b): await i.response.send_message("Tapez `!casier @membre`", ephemeral=True)
    @discord.ui.button(label="Retour", style=discord.ButtonStyle.secondary)
    async def back(self, i, b): await i.response.edit_message(content="🛠 **Panel Admin**", view=MainPanel())

# --- MODALS ---
class WelcomeModal(discord.ui.Modal, title="Questionnaire de Bienvenue"):
    pseudo = discord.ui.TextInput(label="Pseudo AS")
    secteur = discord.ui.TextInput(label="Secteur (1-98, 2A, 2B)", min_length=1, max_length=2)
    motivations = discord.ui.TextInput(label="Motivations", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        sec = self.secteur.value.upper()
        if not is_valid_secteur(sec): return await interaction.response.send_message("Secteur invalide.", ephemeral=True)
        embed = discord.Embed(title="📝 Nouvelle Fiche", color=discord.Color.blue())
        embed.add_field(name="Joueur", value=interaction.user.mention)
        embed.add_field(name="Pseudo", value=self.pseudo.value)
        embed.add_field(name="Secteur", value=sec)
        class Accept(discord.ui.View):
            @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success)
            async def ok(self, inter, btn):
                db = load_db("secteurs"); db[str(interaction.user.id)] = sec; save_db("secteurs", db)
                await bot.get_channel(CHAN_LOGS).send(f"✅ Secteur {sec} validé pour {interaction.user.mention}")
                await inter.response.send_message("Validé !", ephemeral=True)
        await bot.get_channel(CHAN_FICHE_RECAP).send(embed=embed, view=Accept())
        await interaction.response.send_message("Fiche envoyée !", ephemeral=True)

class SanctionModal(discord.ui.Modal):
    def __init__(self, target, action):
        super().__init__(title=f"Sanction : {action}")
        self.target, self.action = target, action
        self.reason = discord.ui.TextInput(label="Motif", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        try: await self.target.send(f"⚠️ Tu as reçu : **{self.action}**\nMotif : {self.reason.value}")
        except: pass
        try:
            if "Mute" in self.action:
                mins = 10 if "10m" in self.action else (1440 if "24H" in self.action else 60)
                await self.target.timeout(datetime.timedelta(minutes=mins), reason=self.reason.value)
            elif self.action == "Kick": await self.target.kick(reason=self.reason.value)
            elif self.action == "Ban": await self.target.ban(reason=self.reason.value)
        except: return await interaction.response.send_message("Permission erreur.", ephemeral=True)
        db = load_db("sanctions"); uid = str(self.target.id)
        if uid not in db: db[uid] = []
        db[uid].append({"type": self.action, "raison": self.reason.value, "staff": str(interaction.user), "date": str(datetime.datetime.now())})
        save_db("sanctions", db)
        await bot.get_channel(CHAN_LOGS).send(f"🔨 **{self.action}** sur {self.target.mention} par {interaction.user.mention}")
        await interaction.response.send_message("Appliqué.", ephemeral=True)

# --- EVENTS ---
@bot.event
async def on_ready():
    print(f"✅ Bot prêt : {bot.user}")
    if not auto_backup.is_running(): auto_backup.start()
    
    # Backup immédiat en MP au démarrage
    user = await bot.fetch_user(MY_ID)
    if user:
        files = []
        if os.path.exists("secteurs.json"): files.append(discord.File("secteurs.json"))
        if os.path.exists("sanctions.json"): files.append(discord.File("sanctions.json"))
        await user.send("🚀 **Bot Redémarré** : Sauvegarde effectuée.", files=files)

    status_list = ["Créateur : louis_lmd", f"{len(bot.guilds)} serveurs", "Gère les secteurs", "!renforts pour aide", "Modération active 🛡️"]
    while True:
        for status in status_list:
            await bot.change_presence(activity=discord.Game(name=status))
            await asyncio.sleep(10)

# --- COMMANDES ---
@bot.command()
@commands.has_permissions(administrator=True)
async def restore(ctx):
    if not ctx.message.attachments: return await ctx.send("Joint un fichier .json")
    att = ctx.message.attachments[0]
    await att.save(att.filename)
    await ctx.send(f"✅ `{att.filename}` restauré !")

@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx): await ctx.send("🛠 **Panel Administration**", view=MainPanel())

@bot.command()
@commands.has_permissions(administrator=True)
async def setsec(ctx, member: discord.Member, s: str):
    if is_valid_secteur(s):
        db = load_db("secteurs"); db[str(member.id)] = s.upper(); save_db("secteurs", db)
        await ctx.send(f"Secteur {s.upper()} mis.")

@bot.command()
@commands.has_permissions(administrator=True)
async def remsec(ctx, member: discord.Member):
    db = load_db("secteurs"); uid = str(member.id)
    if uid in db: del db[uid]; save_db("secteurs", db); await ctx.send("Retiré.")

@bot.command()
@commands.has_permissions(administrator=True)
async def punish(ctx, member: discord.Member):
    class S(discord.ui.View):
        @discord.ui.select(options=[discord.SelectOption(label=x, value=x) for x in ["Sommation", "Rappel", "Avertissement", "Mute 10m", "Mute 1H", "Exclure 24H", "Kick", "Ban"]])
        async def c(self, i, s): await i.response.send_modal(SanctionModal(member, s.values[0]))
    await ctx.send(f"Sanction pour {member.display_name}:", view=S())

@bot.command()
@commands.has_permissions(administrator=True)
async def msgmp(ctx, member: discord.Member):
    class Start(discord.ui.View):
        @discord.ui.button(label="Démarrer le questionnaire", style=discord.ButtonStyle.green)
        async def go(self, i, b): await i.response.send_modal(WelcomeModal())
    await member.send("Bienvenue ! Cliquez ici :", view=Start())
    await ctx.send("Envoyé.")

@bot.command()
async def renforts(ctx):
    if ctx.channel.id != CHAN_RENFORTS: return
    qs = ["Motif ?", "Numéro d'inter ?", "Secteur ?", "Adresse ?", "Véhicules ?"]
    ans = []
    for q in qs:
        m = await ctx.send(q)
        try:
            r = await bot.wait_for("message", check=lambda msg: msg.author == ctx.author and msg.channel == ctx.channel, timeout=60)
            ans.append(r.content); await m.delete(); await r.delete()
        except: return
    sec = ans[2].upper()
    if not is_valid_secteur(sec): return await ctx.send("Secteur invalide.")
    db = load_db("secteurs"); mentions = [f"<@{uid}>" for uid, s in db.items() if s == sec]
    mentions_str = " ".join(mentions) if mentions else "Aucun membre."
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
            self.creator, self.on_road = creator, []
        @discord.ui.button(label="Je prend le renfort", style=discord.ButtonStyle.blurple)
        async def take(self, i, b):
            if i.user.mention not in self.on_road:
                self.on_road.append(i.user.mention)
                embed.set_field_at(6, name="👥 En route", value=", ".join(self.on_road))
                await i.response.edit_message(embed=embed)
        @discord.ui.button(label="Fin de besoin", style=discord.ButtonStyle.secondary)
        async def end(self, i, b):
            if i.user == self.creator or i.user.guild_permissions.administrator: await i.message.delete()
    await ctx.send(content=mentions_str, embed=embed, view=Action(ctx.author))

keep_alive()
bot.run(TOKEN)
