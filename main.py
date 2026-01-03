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

# --- MODALS DE GESTION ---

class GenericSanctionModal(discord.ui.Modal):
    def __init__(self, action):
        super().__init__(title=f"Sanction : {action}")
        self.action = action
        self.user_id = discord.ui.TextInput(label="ID du Membre")
        self.reason = discord.ui.TextInput(label="Motif", style=discord.TextStyle.paragraph)

    async def on_submit(self, i: discord.Interaction):
        try:
            target_id = int(self.user_id.value)
            member = i.guild.get_member(target_id)
            if member:
                if "MUTE" in self.action or "EXCLURE" in self.action:
                    mins = 10 if "10M" in self.action else (60 if "1H" in self.action else 1440)
                    await member.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=mins), reason=self.reason.value)
                elif self.action == "KICK": await member.kick(reason=self.reason.value)
                elif self.action == "BAN": await member.ban(reason=self.reason.value)
            
            db = load_db("sanctions")
            uid = str(target_id)
            if uid not in db: db[uid] = []
            db[uid].append({"type": self.action, "reason": self.reason.value, "date": str(datetime.datetime.now())})
            save_db("sanctions", db)
            await i.response.send_message(f"✅ Sanction enregistrée pour <@{uid}>.", ephemeral=True)
        except Exception as e: await i.response.send_message(f"Erreur : {e}", ephemeral=True)

class AddSecteurModal(discord.ui.Modal, title="Ajouter au Secteur"):
    user_id = discord.ui.TextInput(label="ID du Membre")
    secteur = discord.ui.TextInput(label="Secteur (Ex: 01, 2A, 56)")
    async def on_submit(self, i: discord.Interaction):
        sec = self.secteur.value.upper().zfill(2) if self.secteur.value.isdigit() else self.secteur.value.upper()
        if not is_valid_secteur(sec): return await i.response.send_message("Secteur invalide.", ephemeral=True)
        
        db = load_db("secteurs")
        if sec not in db: db[sec] = []
        uid = int(self.user_id.value)
        if uid not in db[sec]: db[sec].append(uid)
        
        save_db("secteurs", db)
        await i.response.send_message(f"✅ <@{uid}> ajouté au secteur {sec}.", ephemeral=True)

# --- PANELS ---

class MainPanel(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Secteurs", style=discord.ButtonStyle.primary)
    async def sec(self, i, b): await i.response.edit_message(content="📂 **Gestion des Secteurs**", view=SecteurPanel())
    @discord.ui.button(label="Sanctions", style=discord.ButtonStyle.danger)
    async def sanc(self, i, b): await i.response.edit_message(content="⚖️ **Gestion des Sanctions**", view=SanctionPanel())
    @discord.ui.button(label="Sauvegarde MP", style=discord.ButtonStyle.success)
    async def save(self, i, b):
        files = [discord.File(f) for f in ["secteurs.json", "sanctions.json"] if os.path.exists(f)]
        await i.user.send("📂 Sauvegarde manuelle :", files=files)
        await i.response.send_message("Vérifie tes MPs !", ephemeral=True)

class SecteurPanel(discord.ui.View):
    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.success)
    async def add(self, i, b): await i.response.send_modal(AddSecteurModal())
    @discord.ui.button(label="Retirer", style=discord.ButtonStyle.danger)
    async def rem(self, i, b):
        class RemModal(discord.ui.Modal, title="Retirer d'un Secteur"):
            uid = discord.ui.TextInput(label="ID du Membre")
            sec = discord.ui.TextInput(label="Secteur")
            async def on_submit(self, it):
                db = load_db("secteurs")
                s = self.sec.value.upper()
                if s in db and int(self.uid.value) in db[s]:
                    db[s].remove(int(self.uid.value))
                    if not db[s]: del db[s]
                    save_db("secteurs", db)
                    await it.response.send_message("Retiré avec succès.", ephemeral=True)
                else: await it.response.send_message("Non trouvé dans ce secteur.", ephemeral=True)
        await i.response.send_modal(RemModal())

    @discord.ui.button(label="Voir Répertoire", style=discord.ButtonStyle.secondary)
    async def view(self, i, b):
        db = load_db("secteurs")
        if not db: return await i.response.send_message("Répertoire vide.", ephemeral=True)
        
        sorted_keys = sorted(db.keys(), key=sort_secteurs)
        txt = "**📖 RÉPERTOIRE DES SECTEURS**\n\n"
        for s in sorted_keys:
            mentions = [f"<@{uid}>" for uid in db[s]]
            txt += f"**Secteur {s}** : {', '.join(mentions)}\n"
        
        class Pub(discord.ui.View):
            @discord.ui.button(label="Rendre public", style=discord.ButtonStyle.danger)
            async def p(self, it, bt): await it.channel.send(txt); await it.response.defer()
        await i.response.send_message(txt, view=Pub(), ephemeral=True)

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey)
    async def back(self, i, b): await i.response.edit_message(content="🛠 **Panel Admin**", view=MainPanel())

class SanctionPanel(discord.ui.View):
    @discord.ui.button(label="Mute 10m", row=0)
    async def s1(self, i, b): await i.response.send_modal(GenericSanctionModal("MUTE 10M"))
    @discord.ui.button(label="Mute 1h", row=0)
    async def s2(self, i, b): await i.response.send_modal(GenericSanctionModal("MUTE 1H"))
    @discord.ui.button(label="Exclure 24h", row=0)
    async def s3(self, i, b): await i.response.send_modal(GenericSanctionModal("EXCLURE 24H"))
    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger, row=1)
    async def s4(self, i, b): await i.response.send_modal(GenericSanctionModal("KICK"))
    @discord.ui.button(label="Ban", style=discord.ButtonStyle.danger, row=1)
    async def s5(self, i, b): await i.response.send_modal(GenericSanctionModal("BAN"))
    @discord.ui.button(label="Casier", style=discord.ButtonStyle.secondary, row=2)
    async def s6(self, i, b):
        class C(discord.ui.Modal, title="Casier"):
            u = discord.ui.TextInput(label="ID Member")
            async def on_submit(self, it):
                d = load_db("sanctions").get(str(self.u.value), [])
                t = "\n".join([f"[{x['date']}] {x['type']}: {x['reason']}" for x in d]) or "Vide."
                await it.response.send_message(f"Casier de <@{self.u.value}> :\n{t}", ephemeral=True)
        await i.response.send_modal(C())
    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, row=2)
    async def back(self, i, b): await i.response.edit_message(content="🛠 **Panel Admin**", view=MainPanel())

# --- RENFORTS ---

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
    
    sec = ans[2].upper().zfill(2) if ans[2].isdigit() else ans[2].upper()
    db = load_db("secteurs")
    mentions = [f"<@{uid}>" for uid in db.get(sec, [])]
    mentions_str = " ".join(mentions) if mentions else "Aucun membre dans ce secteur."

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
            self.c, self.road = creator, []
        @discord.ui.button(label="Je prend le renfort", style=discord.ButtonStyle.blurple)
        async def take(self, it, b):
            if it.user.mention not in self.road:
                self.road.append(it.user.mention)
                embed.set_field_at(6, name="👥 En route", value=", ".join(self.road))
                await it.response.edit_message(embed=embed)
        @discord.ui.button(label="Fin de besoin", style=discord.ButtonStyle.secondary)
        async def end(self, it, b):
            if it.user == self.c or it.user.guild_permissions.administrator: await it.message.delete()

    await ctx.send(content=mentions_str, embed=embed, view=Action(ctx.author))

# --- GESTION DES BACKUPS ---

@tasks.loop(hours=24)
async def auto_backup():
    u = await bot.fetch_user(MY_ID)
    if u:
        files = [discord.File(f) for f in ["secteurs.json", "sanctions.json"] if os.path.exists(f)]
        await u.send("📦 Sauvegarde automatique 24H.", files=files)

@bot.event
async def on_ready():
    print(f"✅ Connecté : {bot.user}")
    if not auto_backup.is_running(): auto_backup.start()
    u = await bot.fetch_user(MY_ID)
    if u:
        files = [discord.File(f) for f in ["secteurs.json", "sanctions.json"] if os.path.exists(f)]
        await u.send("🚀 Bot Redémarré.", files=files)
    
    sl = ["Créateur : louis_lmd", "Gère les secteurs", "Modération active 🛡️"]
    while True:
        for s in sl:
            await bot.change_presence(activity=discord.Game(name=s)); await asyncio.sleep(10)

@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx): await ctx.send("🛠 **Panel Admin**", view=MainPanel())

@bot.command()
@commands.has_permissions(administrator=True)
async def restore(ctx):
    if ctx.message.attachments:
        a = ctx.message.attachments[0]
        await a.save(a.filename)
        await ctx.send(f"✅ `{a.filename}` restauré.")

keep_alive()
bot.run(TOKEN)
