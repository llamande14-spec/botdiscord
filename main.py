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

# --- MODALS DE BIENVENUE ---
class WelcomeModal(discord.ui.Modal, title="Questionnaire de Bienvenue"):
    pseudo = discord.ui.TextInput(label="Ton pseudo AS", placeholder="Ex: Matthieu-bo4")
    secteur = discord.ui.TextInput(label="Quel est ton secteurs ?", placeholder="Ex: 29, 2A", min_length=1, max_length=2)
    motivations = discord.ui.TextInput(label="T'es motivations ?", style=discord.TextStyle.paragraph)
    autres_jeux = discord.ui.TextInput(label="Joue tu à d'autres jeux ?", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        sec = self.secteur.value.upper().zfill(2) if self.secteur.value.isdigit() else self.secteur.value.upper()
        if not is_valid_secteur(sec):
            return await interaction.response.send_message("Secteur invalide. Recommencez via !msgmp", ephemeral=True)
        
        embed = discord.Embed(title="📝 Nouvelle Fiche de Bienvenue", color=discord.Color.blue())
        embed.add_field(name="Utilisateur", value=interaction.user.mention)
        embed.add_field(name="Pseudo AS", value=self.pseudo.value)
        embed.add_field(name="Secteur souhaité", value=sec)
        embed.add_field(name="Motivations", value=self.motivations.value, inline=False)
        embed.add_field(name="Autres jeux", value=self.autres_jeux.value or "Aucun")

        class AcceptView(discord.ui.View):
            @discord.ui.button(label="Accepter le secteurs", style=discord.ButtonStyle.success)
            async def accept(self, inter, btn):
                db = load_db("secteurs")
                if sec not in db: db[sec] = []
                if interaction.user.id not in db[sec]: db[sec].append(interaction.user.id)
                save_db("secteurs", db)
                
                log_chan = bot.get_channel(CHAN_LOGS)
                if log_chan:
                    await log_chan.send(f"✅ **Secteur validé** : {interaction.user.mention} assigné au **{sec}** par {inter.user.mention}")
                await inter.response.send_message(f"Secteur {sec} enregistré !", ephemeral=True)
                self.stop()

        recap_chan = bot.get_channel(CHAN_FICHE_RECAP)
        if recap_chan:
            await recap_chan.send(embed=embed, view=AcceptView())
        await interaction.response.send_message("Merci ! Ta fiche a été envoyée au staff.", ephemeral=True)

# --- SYSTÈME DE RÉPERTOIRE À PAGES ---
class RepertoirePaginator(discord.ui.View):
    def __init__(self, pages):
        super().__init__(timeout=None)
        self.pages = pages
        self.current_page = 0

    async def update_view(self, interaction):
        embed = discord.Embed(title="📖 RÉPERTOIRE DES SECTEURS", description=self.pages[self.current_page], color=discord.Color.blue())
        embed.set_footer(text=f"Page {self.current_page + 1}/{len(self.pages)}")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⬅️ Précédent", style=discord.ButtonStyle.grey)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page - 1) % len(self.pages)
        await self.update_view(interaction)

    @discord.ui.button(label="➡️ Suivant", style=discord.ButtonStyle.grey)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page + 1) % len(self.pages)
        await self.update_view(interaction)

    @discord.ui.button(label="Rendre Public", style=discord.ButtonStyle.danger)
    async def public(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.send(f"📖 **Répertoire Public (Page {self.current_page + 1})** :\n{self.pages[self.current_page]}")
        await interaction.response.defer()

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="📂 **Secteurs**", embed=None, view=SecteurPanel())

# --- MODALS SANCTION (CORRIGÉ) ---
class GenericSanctionModal(discord.ui.Modal):
    def __init__(self, action):
        super().__init__(title=f"Sanction : {action}")
        self.action = action
        self.user_id = discord.ui.TextInput(label="ID du Membre", min_length=15, max_length=20)
        self.reason = discord.ui.TextInput(label="Motif", style=discord.TextStyle.paragraph)
        
        # --- CORRECTION CRITIQUE : AJOUT DES ITEMS A LA VUE ---
        self.add_item(self.user_id)
        self.add_item(self.reason)

    async def on_submit(self, i: discord.Interaction):
        try:
            target_id = int(self.user_id.value)
            member = i.guild.get_member(target_id)
            
            # Action réelle (Mute/Kick/Ban)
            if member:
                try:
                    if "MUTE" in self.action or "EXCLURE" in self.action:
                        mins = 10 if "10M" in self.action else (60 if "1H" in self.action else 1440)
                        await member.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=mins), reason=self.reason.value)
                    elif self.action == "KICK": await member.kick(reason=self.reason.value)
                    elif self.action == "BAN": await member.ban(reason=self.reason.value)
                    
                    # Message MP à l'utilisateur
                    embed_mp = discord.Embed(title=f"⚠️ Sanction reçue : {self.action}", color=discord.Color.red())
                    embed_mp.add_field(name="Motif", value=self.reason.value)
                    await member.send(embed=embed_mp)
                except Exception as e:
                    print(f"Erreur modération : {e}")

            # Logs JSON
            db = load_db("sanctions")
            uid = str(target_id)
            if uid not in db: db[uid] = []
            db[uid].append({
                "type": self.action, 
                "reason": self.reason.value, 
                "staff": str(i.user), 
                "date": datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
            })
            save_db("sanctions", db)

            # Logs Salon
            log_chan = bot.get_channel(CHAN_LOGS)
            if log_chan:
                embed_log = discord.Embed(title="🔨 Sanction Appliquée", color=discord.Color.dark_red())
                embed_log.add_field(name="Type", value=self.action)
                embed_log.add_field(name="Cible", value=f"<@{target_id}>")
                embed_log.add_field(name="Staff", value=i.user.mention)
                embed_log.add_field(name="Raison", value=self.reason.value)
                await log_chan.send(embed=embed_log)

            await i.response.send_message(f"✅ Sanction {self.action} enregistrée.", ephemeral=True)
        except Exception as e: await i.response.send_message(f"Erreur : {e}", ephemeral=True)

# --- PANELS ---
class MainPanel(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Secteurs", style=discord.ButtonStyle.primary, row=0)
    async def sec(self, i, b): await i.response.edit_message(content="📂 **Gestion des Secteurs**", view=SecteurPanel())
    @discord.ui.button(label="Sanctions", style=discord.ButtonStyle.danger, row=0)
    async def sanc(self, i, b): await i.response.edit_message(content="⚖️ **Gestion des Sanctions**", view=SanctionPanel())
    @discord.ui.button(label="Sauvegarde", style=discord.ButtonStyle.success, row=1)
    async def save_all(self, i, b):
        files = [discord.File(f) for f in ["secteurs.json", "sanctions.json"] if os.path.exists(f)]
        await i.user.send("📂 Sauvegarde :", files=files)
        await i.response.send_message("Envoyé en MP !", ephemeral=True)

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
                u_id = int(self.u.value)
                if u_id not in db[sec]: db[sec].append(u_id)
                self.add_item(self.u); self.add_item(self.s) # Correction
                save_db("secteurs", db)
                await it.response.send_message("Ajouté !", ephemeral=True)
        
        modal = AddM()
        modal.add_item(modal.u); modal.add_item(modal.s)
        await i.response.send_modal(modal)

    @discord.ui.button(label="Retirer", style=discord.ButtonStyle.danger)
    async def rem(self, i, b):
        class RemM(discord.ui.Modal, title="Retirer"):
            u = discord.ui.TextInput(label="ID Member")
            s = discord.ui.TextInput(label="Secteur")
            async def on_submit(self, it):
                db = load_db("secteurs")
                sec = self.s.value.upper()
                if sec in db and int(self.u.value) in db[sec]:
                    db[sec].remove(int(self.u.value))
                    if not db[sec]: del db[sec]
                    save_db("secteurs", db)
                    await it.response.send_message("Retiré !", ephemeral=True)
                else: await it.response.send_message("Pas trouvé.", ephemeral=True)
        
        modal = RemM()
        modal.add_item(modal.u); modal.add_item(modal.s)
        await i.response.send_modal(modal)

    @discord.ui.button(label="Voir Répertoire", style=discord.ButtonStyle.secondary)
    async def view_rep(self, i, b):
        db = load_db("secteurs")
        if not db: return await i.response.send_message("Vide.", ephemeral=True)
        sorted_keys = sorted(db.keys(), key=sort_secteurs)
        pages, current_page_txt = [], ""
        for s in sorted_keys:
            line = f"**Secteur {s}** : {', '.join([f'<@{uid}>' for uid in db[s]])}\n"
            if len(current_page_txt) + len(line) > 1000:
                pages.append(current_page_txt); current_page_txt = line
            else: current_page_txt += line
        pages.append(current_page_txt)
        embed = discord.Embed(title="📖 RÉPERTOIRE", description=pages[0], color=discord.Color.blue())
        embed.set_footer(text=f"Page 1/{len(pages)}")
        await i.response.edit_message(content=None, embed=embed, view=RepertoirePaginator(pages))

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey)
    async def back(self, i, b): await i.response.edit_message(content="🛠 Admin", embed=None, view=MainPanel())

class SanctionPanel(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="Sommation", row=0)
    async def b1(self, i, b): await i.response.send_modal(GenericSanctionModal("SOMMATION"))
    
    @discord.ui.button(label="Rappel", row=0)
    async def b2(self, i, b): await i.response.send_modal(GenericSanctionModal("RAPPEL"))
    
    @discord.ui.button(label="Avertissement", row=0)
    async def b3(self, i, b): await i.response.send_modal(GenericSanctionModal("AVERTISSEMENT"))
    
    @discord.ui.button(label="Mute 10m", row=1)
    async def b4(self, i, b): await i.response.send_modal(GenericSanctionModal("MUTE 10M"))
    
    @discord.ui.button(label="Mute 1h", row=1)
    async def b5(self, i, b): await i.response.send_modal(GenericSanctionModal("MUTE 1H"))
    
    @discord.ui.button(label="Exclure 24h", row=1)
    async def b6(self, i, b): await i.response.send_modal(GenericSanctionModal("EXCLURE 24H"))
    
    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger, row=2)
    async def b7(self, i, b): await i.response.send_modal(GenericSanctionModal("KICK"))
    
    @discord.ui.button(label="Ban", style=discord.ButtonStyle.danger, row=2)
    async def b8(self, i, b): await i.response.send_modal(GenericSanctionModal("BAN"))
    
    @discord.ui.button(label="Casier", row=3)
    async def b9(self, i, b):
        class CM(discord.ui.Modal, title="Casier"):
            u = discord.ui.TextInput(label="ID")
            async def on_submit(self, it):
                d = load_db("sanctions").get(str(self.u.value), [])
                t = "\n".join([f"**#{idx+1}** {x['type']}: {x.get('reason', x.get('raison',''))}" for idx, x in enumerate(d)]) or "Vide."
                await it.response.send_message(f"Casier <@{self.u.value}> :\n{t}", ephemeral=True)
        
        modal = CM(); modal.add_item(modal.u) # Correction ajout item
        await i.response.send_modal(modal)

    @discord.ui.button(label="Suppr Sanction", style=discord.ButtonStyle.danger, row=3)
    async def b10(self, i, b):
        class DM(discord.ui.Modal, title="Suppr"):
            u, idx = discord.ui.TextInput(label="ID"), discord.ui.TextInput(label="Numéro #")
            async def on_submit(self, it):
                db = load_db("sanctions")
                uid, index = str(self.u.value), int(self.idx.value)-1
                if uid in db and 0 <= index < len(db[uid]):
                    db[uid].pop(index); save_db("sanctions", db); await it.response.send_message("Fait !", ephemeral=True)
        
        modal = DM(); modal.add_item(modal.u); modal.add_item(modal.idx) # Correction ajout item
        await i.response.send_modal(modal)
    
    @discord.ui.button(label="Retour", style=discord.ButtonStyle.grey, row=4)
    async def back(self, i, b): await i.response.edit_message(content="🛠 Admin", view=MainPanel())

# --- COMMANDES & EVENTS ---
@bot.event
async def on_ready():
    if not auto_backup.is_running(): auto_backup.start()
    u = await bot.fetch_user(MY_ID)
    if u: await u.send("🚀 Démarrage bot.", files=[discord.File(f) for f in ["secteurs.json", "sanctions.json"] if os.path.exists(f)])
    sl = ["Créateur : louis_lmd", "Gère les secteurs"]
    while True:
        for s in sl: await bot.change_presence(activity=discord.Game(name=s)); await asyncio.sleep(10)

@tasks.loop(hours=24)
async def auto_backup():
    u = await bot.fetch_user(MY_ID)
    if u: await u.send("📦 Backup 24h.", files=[discord.File(f) for f in ["secteurs.json", "sanctions.json"] if os.path.exists(f)])

@bot.event
async def on_member_join(member):
    class Start(discord.ui.View):
        @discord.ui.button(label="Démarrer le questionnaire", style=discord.ButtonStyle.green)
        async def go(self, i, b): await i.response.send_modal(WelcomeModal())
    try:
        await member.send(f"Bienvenue sur {member.guild.name} ! Merci de remplir le questionnaire :", view=Start())
    except:
        pass

@bot.command()
@commands.has_permissions(administrator=True)
async def msgmp(ctx, member: discord.Member):
    class Start(discord.ui.View):
        @discord.ui.button(label="Démarrer le questionnaire", style=discord.ButtonStyle.green)
        async def go(self, i, b): await i.response.send_modal(WelcomeModal())
    await member.send("Lancement manuel du questionnaire de bienvenue :", view=Start())
    await ctx.send(f"Questionnaire envoyé à {member.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx): await ctx.send("🛠 **Panel Administration**", view=MainPanel())

@bot.command()
async def renforts(ctx):
    if ctx.channel.id != CHAN_RENFORTS: return
    qs = ["☎️ Le motif de l'appel ?", "🔢 Numéro d'interventoin ?", "📍 Qu'elle Secteur ?", "🏠 L'adresse ?", "🚒 Qu'elle véhicules avez vous besoin ?"]
    ans = []
    
    # Check fonction pour le message
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    for i, q in enumerate(qs):
        msg = await ctx.send(q)
        try:
            resp = await bot.wait_for("message", check=check, timeout=60)
            
            # --- VERIFICATION SPECIFIQUE SECTEUR (Index 2) ---
            if i == 2:
                s_val = resp.content.upper().zfill(2) if resp.content.isdigit() else resp.content.upper()
                if not is_valid_secteur(s_val):
                    await msg.delete(); await resp.delete()
                    # 2ème Chance
                    retry_msg = await ctx.send("Secteur invalide, donnez un nouveaux secteurs correcte (C'est les départements).")
                    try:
                        resp_retry = await bot.wait_for("message", check=check, timeout=60)
                        s_val_retry = resp_retry.content.upper().zfill(2) if resp_retry.content.isdigit() else resp_retry.content.upper()
                        
                        if not is_valid_secteur(s_val_retry):
                            await retry_msg.delete(); await resp_retry.delete()
                            await ctx.send("2ème secteurs invalide, commande annulée.", delete_after=5)
                            return # Annulation
                        else:
                            ans.append(resp_retry.content)
                            await retry_msg.delete(); await resp_retry.delete()
                    except: return
                else:
                    ans.append(resp.content)
                    await msg.delete(); await resp.delete()
            else:
                ans.append(resp.content)
                await msg.delete(); await resp.delete()
        except: return

    sec = ans[2].upper().zfill(2) if ans[2].isdigit() else ans[2].upper()
    db = load_db("secteurs")
    mentions = [f"<@{uid}>" for uid in db.get(sec, [])]
    
    embed = discord.Embed(title="🚨 ALERTE RENFORTS", color=0xed4245)
    embed.add_field(name="👤 Demandeur", value=ctx.author.mention)
    embed.add_field(name="📍 Secteur", value=sec)
    embed.add_field(name="🔢 Inter", value=ans[1])
    embed.add_field(name="☎️ Motif", value=ans[0], inline=False)
    embed.add_field(name="🏠 Adresse", value=ans[3], inline=False)
    embed.add_field(name="🚒 Besoin", value=ans[4], inline=False)
    embed.add_field(name="👥 En route", value="...")
    
    class Act(discord.ui.View):
        def __init__(self, c):
            super().__init__(timeout=None)
            self.c, self.r = c, []
        @discord.ui.button(label="🚑 Je prend le renfort", style=discord.ButtonStyle.blurple)
        async def take(self, it, b):
            if it.user.mention not in self.r:
                self.r.append(it.user.mention)
                embed.set_field_at(6, name="👥 En route", value=", ".join(self.r))
                await it.response.edit_message(embed=embed)
        @discord.ui.button(label="🚫 Fin de besoin", style=discord.ButtonStyle.secondary)
        async def end(self, it, b):
            if it.user == self.c or it.user.guild_permissions.administrator: await it.message.delete()
    
    await ctx.send(content=" ".join(mentions) if mentions else "Aucun membre.", embed=embed, view=Act(ctx.author))

keep_alive()
bot.run(TOKEN)
