import discord
from discord.ext import commands
import os
import sys
from keep_alive import keep_alive

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("❌ ERREUR: La variable d'environnement DISCORD_TOKEN n'est pas définie!")
    print("Veuillez configurer votre token Discord dans les Secrets Replit.")
    sys.exit(1)

ID_SALON_REPONSES = 1433793778111484035

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

questions = [
    "Salut et bienvenue ! 😊 Quel est ton pseudo AS ?",
    "Ton secteur de jeux ? 🌍",
    "Qu'est-ce qui t'a motivé à rejoindre le groupement ? 🤔",
    "Joues-tu à d'autres jeux? 🎮"
]

@bot.event
async def on_member_join(member):
    try:
        await member.send(f"Salut {member.name} ! Bienvenue sur **{member.guild.name}** 🎉\n"
                          "J'ai quelques petites questions pour toi !")
        
        responses = []
        for q in questions:
            await member.send(q)
            
            def check(m):
                return m.author == member and isinstance(m.channel, discord.DMChannel)
            
            msg = await bot.wait_for("message", check=check)
            responses.append(msg.content)
        
        salon = bot.get_channel(ID_SALON_REPONSES)
        if salon and isinstance(salon, discord.TextChannel):
            formatted = "\n".join([f"**{questions[i]}**\n➡️ {responses[i]}" for i in range(len(questions))])
            await salon.send(f"🆕 **Nouveau membre : {member.mention} ({member.name})**\n\n{formatted}")
        
        await member.send("Merci pour tes réponses ! 💬 Elles ont été envoyées à l'équipe du serveur 👌")

    except Exception as e:
        print(f"Erreur avec {member.name}: {e}")

@bot.event
async def on_ready():
    if bot.user:
        print(f"✅ Bot connecté en tant que {bot.user}")
        print(f"ID: {bot.user.id}")
        print(f"Serveurs: {len(bot.guilds)}")
        print("Le bot est prêt à accueillir de nouveaux membres !")

keep_alive()
bot.run(TOKEN)
