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

# --- MODALS ---

class GenericSanctionModal(discord.ui.Modal):
    def __init__(self, action):
        super().__init__(title=f"Sanction : {action}")
        self.action = action
        self.user_id = discord.ui.TextInput(label="ID du Membre", placeholder="ID Discord ici...")
        self.reason = discord.ui.TextInput(label="Motif", style=discord.TextStyle.paragraph)

    async def on_submit(self, i: discord.Interaction):
        try:
            target_id = int(self.user_id.value)
            member = i.guild.get_member(target_id)
            
            # Action réelle pour Mute/Kick/Ban
            if member:
                if "MUTE" in self.action or "EXCLURE" in self.action:
                    mins = 10 if "10M" in self.action else (60 if "1H" in self.action else 1440)
                    await member.timeout(datetime.timedelta(minutes=mins), reason=self.reason.value)
                elif self.action == "KICK": await member.kick(reason=self.reason.value)
                elif self.action == "BAN": await member.ban(reason=self.reason.value)
                
                try: await member.send(f"⚠️ Sanction : **{self.action}**\nRaison : {self.reason.value}")
                except: pass

            # Log JSON
            db = load_db("sanctions")
            uid = str(target_id)
            if uid not in db: db[uid] = []
            db[uid].append({"type": self.action, "raison": self.reason.value, "staff": str(i.user), "date": str(datetime.datetime.now())})
            save_db("sanctions", db)

            await bot.get_channel(CHAN_LOGS).send(f"🔨 **{self.action}** | <@{target_id}> par {i.user.mention}\nRaison: {self.reason.value}")
            await i.response.send_message(f"✅ Sanction {self.action} enregistrée.", ephemeral=True)
        except Exception as e:
            await i.response.send_message(f"Erreur : {e}", ephemeral=True)

class AddSecteurModal(discord.ui.Modal, title="Ajouter un Secteur"):
    user_id = discord.ui.TextInput(label="ID du Membre")
    secteur = discord.ui.TextInput(label="Secteur (1-98, 2A, 2B)")
    async def on_submit(self, i: discord.Interaction):
        sec = self.secteur.value.upper()
        if not is_valid_secteur(sec): return await i.response.send_message("Secteur invalide.", ephemeral=True)
        db = load_db("secteurs")
        db[str(self.user_id.value)] = sec
        save_db("secteurs", db)
        await bot.get_channel(CHAN_LOGS).send(f"✅ **Secteur Ajouté** : ID {self.user_id.value} -> {sec} par {i.user.mention}")
        await i.response.send_message(f"✅ Enregistré.", ephemeral=True)

# --- PANELS ---

class MainPanel(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Secteurs", style=discord.ButtonStyle.primary, row=0)
    async def sec(self, i, b): await i.response.edit_message(content="📂 **Gestion des Secteurs**", view=SecteurPanel())
    @discord.ui.button(label="Sanctions", style=discord.ButtonStyle.danger, row=0)
    async def sanc(self, i, b): await i.response.edit_message(content="⚖️ **Gestion des Sanctions**", view=SanctionPanel())
    @discord.ui.button(label="Sauvegarde", style=discord.ButtonStyle.success, row=1)
    async def save(self, i, b):
        files = [discord.File(f) for f in ["secteurs.json", "sanctions.json"] if os.path.exists(f)]
        await i.user.send("Sauvegarde manuelle :", files=files)
        await i.response.send_message("Envoyé en MP.", ephemeral=True)

class SecteurPanel(discord.ui.View):
    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.success)
    async def add(self, i, b): await i.response.send_modal(AddSecteurModal())
    @discord.ui.button(label="Retirer", style=discord.ButtonStyle.danger)
    async def rem(self, i, b):
        class RemModal(discord.ui.Modal, title="Retirer"):
            uid = discord.ui.TextInput(label="ID du Membre")
            async def on_submit(self, it: discord.Interaction):
                db = load_db("secteurs")
                if str(self.uid.value) in db:
                    del db[str(self.uid.value)]; save_db("secteurs", db)
                    await it.response.send_message("Retiré.", ephemeral=True)
                else: await it.response.send_message("ID non trouvé.", ephemeral=True)
        await i.response.send_modal(RemModal())

    @discord.ui.button(label="Voir Répertoire", style=discord.ButtonStyle.secondary)
    async def view(self, i, b):
        db = load_db("secteurs")
        rep = {}
        for uid, sec in db.items():
            if sec not in rep: rep[sec] = []
            rep[sec].append(f"<@{uid}>")
        sorted_keys = sorted(rep.keys(), key=sort_secteurs)
        txt = "**📖 RÉPERTOIRE DES SECTEURS**\n\n" + "\n".join([f"**Secteur {s}** : {', '.join(rep[s])}" for s in sorted_keys])
        
        class Pub(discord.ui.View):
            @discord.ui.button(label="Rendre public", style=discord.ButtonStyle.danger)
            async def p(self, it, bt): await it.channel.send(txt); await it.response.defer()
        await i.response.send_message(txt or "Répertoire vide.", view=Pub(), ephemeral=True)

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey)
    async def back(self, i, b): await i.response.edit_message(content="🛠 **Panel Admin**", view=MainPanel())

class SanctionPanel(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Sommation", style=discord.ButtonStyle.secondary, row=0)
    async def b1(self, i, b): await i.response.send_modal(GenericSanctionModal("SOMMATION"))
    @discord.ui.button(label="Rappel", style=discord.ButtonStyle.secondary, row=0)
    async def b2(self, i, b): await i.response.send_modal(GenericSanctionModal("RAPPEL"))
    @discord.ui.button(label="Avertissement", style=discord.ButtonStyle.secondary, row=0)
    async def b3(self, i, b): await i.response.send_modal(GenericSanctionModal("AVERTISSEMENT"))
    @discord.ui.button(label="Mute 10m", style=discord.ButtonStyle.primary, row=1)
    async def b4(self, i, b): await i.response.send_modal(GenericSanctionModal("MUTE 10M"))
    @discord.ui.button(label="Mute 1h", style=discord.ButtonStyle.primary, row=1)
    async def b5(self, i, b): await i.response.send_modal(GenericSanctionModal("MUTE 1H"))
    @discord.ui.button(label="Exclure 24h", style=discord.ButtonStyle.primary, row=1)
    async def b6(self, i, b): await i.response.send_modal(GenericSanctionModal("EXCLURE 24H"))
    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger, row=2)
    async def b7(self, i, b): await i.response.send_modal(GenericSanctionModal("KICK"))
    @discord.ui.button(label="Ban", style=discord.ButtonStyle.danger, row=2)
    async def b8(self, i, b): await i.response.send_modal(GenericSanctionModal("BAN"))
    @discord.ui.button(label="Voir Casier", style=discord.ButtonStyle.grey, row=3)
    async def b9(self, i, b):
        class CasierModal(discord.ui.Modal, title="Casier Judiciaire"):
            uid = discord.ui.TextInput(label="ID Discord")
            async def on_submit(self, it: discord.Interaction):
                db = load_db("sanctions")
                logs = db.get(str(self.uid.value), [])
                if not logs: return await it.response.send_message("Casier vide.", ephemeral=True)
                txt = "\n".join([f"[{l['date']}] {l['type']} : {l['raison']}" for l in logs])
                await it.response.send_message(f"📂 **Casier de <@{self.uid.value}>** :\n{txt}", ephemeral=True)
        await i.response.send_modal(CasierModal())
    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, row=3)
    async def back(self, i, b): await i.response.edit_message(content="🛠 **Panel Admin**", view=MainPanel())

# --- AUTO BACKUP MP ---
@tasks.loop(hours=24)
async def auto_backup_task():
    await bot.wait_until_ready()
    user = await bot.fetch_user(MY_ID)
    if user:
        files = [discord.File(f) for f in ["secteurs.json", "sanctions.json"] if os.path.exists(f)]
        if files: await user.send(f"📦 **Sauvegarde 24h**", files=files)

@bot.event
async def on_ready():
    print(f"✅ Bot prêt : {bot.user}")
    if not auto_backup_task.is_running(): auto_backup_task.start()
    user = await bot.fetch_user(MY_ID)
    if user:
        files = [discord.File(f) for f in ["secteurs.json", "sanctions.json"] if os.path.exists(f)]
        if files: await user.send("🚀 **Redémarrage**", files=files)
    
    status_list = ["Créateur : louis_lmd", "Gère les secteurs", "Modération active 🛡️"]
    while True:
        for s in status_list:
            await bot.change_presence(activity=discord.Game(name=s)); await asyncio.sleep(10)

@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx): await ctx.send("🛠 **Panel Administration**", view=MainPanel())

@bot.command()
@commands.has_permissions(administrator=True)
async def restore(ctx):
    if ctx.message.attachments:
        att = ctx.message.attachments[0]
        await att.save(att.filename)
        await ctx.send(f"✅ `{att.filename}` restauré.")

keep_alive()
bot.run(TOKEN)
