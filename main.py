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
    with open(f"{name}.json", 'r') as f:
        try: return json.load(f)
        except: return {}

def save_db(name, data):
    with open(f"{name}.json", 'w') as f: json.dump(data, f, indent=4)

def is_valid_secteur(s):
    s = str(s).upper().zfill(2) if str(s).isdigit() else str(s).upper()
    valid_list = ["2A", "2B"] + [str(i).zfill(2) for i in range(1, 99)]
    return s in valid_list

def sort_secteurs(secteur_key):
    s = str(secteur_key).upper()
    if s == "2A": return -2
    if s == "2B": return -1
    return int(s) if s.isdigit() else 999

# --- MODALS BIENVENUE & SANCTIONS ---

class WelcomeModal(discord.ui.Modal, title="Questionnaire de Bienvenue"):
    pseudo = discord.ui.TextInput(label="Pseudo AS")
    secteur = discord.ui.TextInput(label="Secteur (Ex: 01, 2A)")
    motivations = discord.ui.TextInput(label="Motivations", style=discord.TextStyle.paragraph)
    
    async def on_submit(self, i):
        sec = self.secteur.value.upper().zfill(2) if self.secteur.value.isdigit() else self.secteur.value.upper()
        if not is_valid_secteur(sec): return await i.response.send_message("Secteur invalide.", ephemeral=True)
        
        embed = discord.Embed(title="📝 Nouvelle Fiche", color=discord.Color.blue())
        embed.add_field(name="Joueur", value=i.user.mention)
        embed.add_field(name="Secteur", value=sec)

        class Accept(discord.ui.View):
            @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success)
            async def ok(self, inter, btn):
                db = load_db("secteurs")
                if sec not in db: db[sec] = []
                if i.user.id not in db[sec]: db[sec].append(i.user.id)
                save_db("secteurs", db)
                await inter.response.send_message("Validé !", ephemeral=True)

        await bot.get_channel(CHAN_FICHE_RECAP).send(embed=embed, view=Accept())
        await i.response.send_message("Envoyé !", ephemeral=True)

class GenericSanctionModal(discord.ui.Modal):
    def __init__(self, action):
        super().__init__(title=f"Sanction : {action}")
        self.action = action
        self.user_id = discord.ui.TextInput(label="ID du Membre")
        self.reason = discord.ui.TextInput(label="Motif", style=discord.TextStyle.paragraph)

    async def on_submit(self, i: discord.Interaction):
        try:
            uid = str(self.user_id.value)
            db = load_db("sanctions")
            if uid not in db: db[uid] = []
            db[uid].append({
                "type": self.action, "reason": self.reason.value,
                "staff": str(i.user), "date": datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
            })
            save_db("sanctions", db)
            await i.response.send_message(f"✅ Sanction enregistrée pour <@{uid}>.", ephemeral=True)
        except Exception as e: await i.response.send_message(f"Erreur : {e}", ephemeral=True)

# --- PANELS ---

class MainPanel(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Secteurs", style=discord.ButtonStyle.primary)
    async def sec(self, i, b): await i.response.edit_message(content="📂 **Secteurs**", view=SecteurPanel())
    @discord.ui.button(label="Sanctions", style=discord.ButtonStyle.danger)
    async def sanc(self, i, b): await i.response.edit_message(content="⚖️ **Sanctions**", view=SanctionPanel())

class SecteurPanel(discord.ui.View):
    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.success)
    async def add(self, i, b):
        class AddM(discord.ui.Modal, title="Ajouter"):
            u = discord.ui.TextInput(label="ID Member")
            s = discord.ui.TextInput(label="Secteur")
            async def on_submit(self, it):
                db = load_db("secteurs")
                sec = self.s.value.upper().zfill(2) if self.s.value.isdigit() else self.s.value.upper()
                if sec not in db: db[sec] = []
                db[sec].append(int(self.u.value)); save_db("secteurs", db)
                await it.response.send_message("Ajouté !", ephemeral=True)
        await i.response.send_modal(AddM())

    @discord.ui.button(label="Voir Répertoire", style=discord.ButtonStyle.secondary)
    async def view(self, i, b):
        db = load_db("secteurs")
        if not db: return await i.response.send_message("Vide.", ephemeral=True)
        sorted_keys = sorted(db.keys(), key=sort_secteurs)
        
        # --- GESTION RÉPERTOIRE LONG ---
        messages, current_msg = [], "**📖 RÉPERTOIRE**\n"
        for s in sorted_keys:
            mentions = [f"<@{uid}>" for uid in db[s]]
            line = f"**Secteur {s}** : {', '.join(mentions)}\n"
            if len(current_msg) + len(line) > 1900:
                messages.append(current_msg); current_msg = line
            else: current_msg += line
        messages.append(current_msg)

        await i.response.send_message(messages[0], ephemeral=True)
        if len(messages) > 1:
            for extra in messages[1:]: await i.followup.send(extra, ephemeral=True)

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey)
    async def back(self, i, b): await i.response.edit_message(content="🛠 Admin", view=MainPanel())

class SanctionPanel(discord.ui.View):
    @discord.ui.button(label="Sommation", row=0)
    async def s1(self, i, b): await i.response.send_modal(GenericSanctionModal("SOMMATION"))
    @discord.ui.button(label="Avertissement", row=0)
    async def s2(self, i, b): await i.response.send_modal(GenericSanctionModal("AVERTISSEMENT"))
    
    @discord.ui.button(label="Casier", style=discord.ButtonStyle.secondary, row=1)
    async def s3(self, i, b):
        class CasierM(discord.ui.Modal, title="Casier"):
            u = discord.ui.TextInput(label="ID Member")
            async def on_submit(self, it):
                d = load_db("sanctions").get(str(self.u.value), [])
                txt = "\n".join([f"**#{idx+1}** {x['type']}: {x.get('reason', x.get('raison',''))}" for idx, x in enumerate(d)]) or "Vide."
                await it.response.send_message(f"Casier <@{self.u.value}> :\n{txt}", ephemeral=True)
        await i.response.send_modal(CasierM())

    @discord.ui.button(label="Suppr. 1 Sanction", style=discord.ButtonStyle.danger, row=1)
    async def s4(self, i, b):
        class DelM(discord.ui.Modal, title="Supprimer"):
            u = discord.ui.TextInput(label="ID Member")
            idx = discord.ui.TextInput(label="Numéro (#)")
            async def on_submit(self, it):
                db = load_db("sanctions")
                uid, index = str(self.u.value), int(self.idx.value)-1
                if uid in db and 0 <= index < len(db[uid]):
                    db[uid].pop(index); save_db("sanctions", db)
                    await it.response.send_message("Supprimé !", ephemeral=True)
        await i.response.send_modal(DelM())

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, row=2)
    async def back(self, i, b): await i.response.edit_message(content="🛠 Admin", view=MainPanel())

# --- EVENTS & TASKS ---

@tasks.loop(hours=24)
async def auto_backup():
    u = await bot.fetch_user(MY_ID)
    if u:
        files = [discord.File(f) for f in ["secteurs.json", "sanctions.json"] if os.path.exists(f)]
        await u.send("📦 Backup auto.", files=files)

@bot.event
async def on_ready():
    if not auto_backup.is_running(): auto_backup.start()
    u = await bot.fetch_user(MY_ID)
    if u:
        files = [discord.File(f) for f in ["secteurs.json", "sanctions.json"] if os.path.exists(f)]
        await u.send("🚀 Démarrage.", files=files)

@bot.event
async def on_member_join(m):
    class Start(discord.ui.View):
        @discord.ui.button(label="Questionnaire", style=discord.ButtonStyle.green)
        async def go(self, i, b): await i.response.send_modal(WelcomeModal())
    try: await m.send("Bienvenue !", view=Start())
    except: pass

@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx): await ctx.send("🛠 Admin", view=MainPanel())

@bot.command()
@commands.has_permissions(administrator=True)
async def restore(ctx):
    if ctx.message.attachments:
        await ctx.message.attachments[0].save(ctx.message.attachments[0].filename)
        await ctx.send("✅ Restauré.")

keep_alive()
bot.run(TOKEN)
