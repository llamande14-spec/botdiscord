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
MY_ID = 697919761312383057 
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

# --- MODALS DE GESTION (SANS COMMANDES) ---

class AddSecteurModal(discord.ui.Modal, title="Ajouter un Secteur"):
    user_id = discord.ui.TextInput(label="ID du Membre", placeholder="Copiez l'ID du membre...")
    secteur = discord.ui.TextInput(label="Secteur", placeholder="Ex: 2A, 45, 2B...")
    async def on_submit(self, i: discord.Interaction):
        sec = self.secteur.value.upper()
        if not is_valid_secteur(sec): return await i.response.send_message("Secteur invalide.", ephemeral=True)
        db = load_db("secteurs")
        db[str(self.user_id.value)] = sec
        save_db("secteurs", db)
        await i.response.send_message(f"✅ Secteur {sec} attribué à l'ID {self.user_id.value}", ephemeral=True)

class RemSecteurModal(discord.ui.Modal, title="Retirer un Secteur"):
    user_id = discord.ui.TextInput(label="ID du Membre")
    async def on_submit(self, i: discord.Interaction):
        db = load_db("secteurs")
        if str(self.user_id.value) in db:
            del db[str(self.user_id.value)]
            save_db("secteurs", db)
            await i.response.send_message("❌ Secteur retiré.", ephemeral=True)
        else: await i.response.send_message("Membre non trouvé.", ephemeral=True)

class GenericSanctionModal(discord.ui.Modal):
    def __init__(self, action):
        super().__init__(title=f"Sanction : {action}")
        self.action = action
        self.user_id = discord.ui.TextInput(label="ID du Membre à sanctionner")
        self.reason = discord.ui.TextInput(label="Raison", style=discord.TextStyle.paragraph)

    async def on_submit(self, i: discord.Interaction):
        guild = i.guild
        member = guild.get_member(int(self.user_id.value))
        if not member: return await i.response.send_message("Membre introuvable sur le serveur.", ephemeral=True)

        try:
            if self.action == "KICK": await member.kick(reason=self.reason.value)
            elif self.action == "BAN": await member.ban(reason=self.reason.value)
            elif "MUTE" in self.action:
                time = 10 if "10M" in self.action else 60
                await member.timeout(datetime.timedelta(minutes=time), reason=self.reason.value)
            
            # Log JSON
            db = load_db("sanctions")
            uid = str(member.id)
            if uid not in db: db[uid] = []
            db[uid].append({"type": self.action, "raison": self.reason.value, "staff": str(i.user), "date": str(datetime.datetime.now())})
            save_db("sanctions", db)

            await bot.get_channel(CHAN_LOGS).send(f"🔨 **{self.action}** | {member.mention} par {i.user.mention}\nRaison: {self.reason.value}")
            await i.response.send_message(f"✅ Sanction {self.action} appliquée.", ephemeral=True)
        except Exception as e:
            await i.response.send_message(f"Erreur : {e}", ephemeral=True)

# --- PANELS ---

class MainPanel(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Secteurs", style=discord.ButtonStyle.primary, emoji="📂")
    async def sec(self, i, b): await i.response.edit_message(content="📂 **Gestion des Secteurs**", view=SecteurPanel())
    @discord.ui.button(label="Sanctions", style=discord.ButtonStyle.danger, emoji="⚖️")
    async def sanc(self, i, b): await i.response.edit_message(content="⚖️ **Gestion des Sanctions**", view=SanctionPanel())
    @discord.ui.button(label="Backup MP", style=discord.ButtonStyle.success, emoji="📥")
    async def backup(self, i, b):
        files = [discord.File("secteurs.json"), discord.File("sanctions.json")]
        await i.user.send("📂 Sauvegarde manuelle :", files=files)
        await i.response.send_message("Vérifie tes MPs !", ephemeral=True)

class SecteurPanel(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.success)
    async def add(self, i, b): await i.response.send_modal(AddSecteurModal())
    @discord.ui.button(label="Retirer", style=discord.ButtonStyle.danger)
    async def rem(self, i, b): await i.response.send_modal(RemSecteurModal())
    @discord.ui.button(label="Voir Répertoire", style=discord.ButtonStyle.secondary)
    async def view(self, i, b):
        db = load_db("secteurs")
        if not db: return await i.response.send_message("Le répertoire est vide.", ephemeral=True)
        
        rep = {}
        for uid, sec in db.items():
            if sec not in rep: rep[sec] = []
            rep[sec].append(f"<@{uid}>")
        
        sorted_keys = sorted(rep.keys(), key=sort_secteurs)
        content = "**📖 RÉPERTOIRE DES SECTEURS**\n\n"
        for s in sorted_keys:
            content += f"**Secteur {s}** : {', '.join(rep[s])}\n"

        await i.response.send_message(content, ephemeral=True)

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey)
    async def back(self, i, b): await i.response.edit_message(content="🛠 **Panel Administration**", view=MainPanel())

class SanctionPanel(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Mute 10m", style=discord.ButtonStyle.secondary)
    async def m10(self, i, b): await i.response.send_modal(GenericSanctionModal("MUTE 10M"))
    @discord.ui.button(label="Mute 1h", style=discord.ButtonStyle.secondary)
    async def m1h(self, i, b): await i.response.send_modal(GenericSanctionModal("MUTE 1H"))
    @discord.ui.button(label="KICK", style=discord.ButtonStyle.primary)
    async def kick(self, i, b): await i.response.send_modal(GenericSanctionModal("KICK"))
    @discord.ui.button(label="BAN", style=discord.ButtonStyle.danger)
    async def ban(self, i, b): await i.response.send_modal(GenericSanctionModal("BAN"))
    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey)
    async def back(self, i, b): await i.response.edit_message(content="🛠 **Panel Administration**", view=MainPanel())

# --- AUTO BACKUP ---
@tasks.loop(hours=24)
async def auto_backup_task():
    await bot.wait_until_ready()
    user = await bot.fetch_user(MY_ID)
    if user:
        files = [discord.File(f) for f in ["secteurs.json", "sanctions.json"] if os.path.exists(f)]
        await user.send(f"📦 **SAUVEGARDE 24H** - {datetime.datetime.now().strftime('%d/%m/%Y')}", files=files)

@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    if not auto_backup_task.is_running(): auto_backup_task.start()
    user = await bot.fetch_user(MY_ID)
    if user:
        files = [discord.File(f) for f in ["secteurs.json", "sanctions.json"] if os.path.exists(f)]
        await user.send("🚀 **Bot Redémarré** : Sauvegarde auto effectuée.", files=files)

@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx):
    await ctx.send("🛠 **Panel Administration**\nTout est centralisé ici.", view=MainPanel())

@bot.command()
@commands.has_permissions(administrator=True)
async def restore(ctx):
    if not ctx.message.attachments: return await ctx.send("Joint un fichier .json")
    att = ctx.message.attachments[0]
    await att.save(att.filename)
    await ctx.send(f"✅ `{att.filename}` restauré avec succès !")

keep_alive()
bot.run(TOKEN)
