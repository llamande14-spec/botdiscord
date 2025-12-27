import discord
from discord.ext import commands
import os
import sys
import asyncio 
from keep_alive import keep_alive

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("❌ ERREUR: La variable d'environnement DISCORD_TOKEN n'est pas définie!")
    sys.exit(1)

ID_SALON_REPONSES = 1433793778111484035

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

questions = [
    "Salut et bienvenue ! 😊 Quel est ton pseudo AS ?",
    "Ton secteur de jeux ? (numéro de département) 🌍",
    "Qu'est-ce qui t'a motivé à rejoindre le groupement ? 🤔",
    "Joues-tu à d'autres jeux? (si oui les quelles) 🎮"
]

@bot.event
async def on_member_join(member):
    try:
        await member.send(f"Salut {member.name} ! Bienvenue sur **{member.guild.name}** 🎉\n"
                          "J'ai quelques petites questions pour toi !")
        
        responses = []
        # CORRECTION INDENTATION ICI
        for q in questions:
            await member.send(q)
            
            def check(m):
                return m.author == member and isinstance(m.channel, discord.DMChannel)
            
            try:
                msg = await bot.wait_for("message", check=check, timeout=600.0)
                responses.append(msg.content)
            except asyncio.TimeoutError:
                await member.send("⏱️ Temps écoulé. Le questionnaire est annulé.")
                return 

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

@bot.command()
@commands.has_permissions(administrator=True)
async def msgmp(ctx, member: discord.Member):
    await ctx.send(f"⏳ Tentative d'envoi du questionnaire à {member.mention}...")
    
    try:
        await member.send(f"Salut {member.name} ! Bienvenue sur **{member.guild.name}** 🎉\n"
                          "J'ai quelques petites questions pour toi !")
        
        responses = []
        # CORRECTION INDENTATION ICI
        for q in questions:
            await member.send(q)
            
            def check(m):
                return m.author == member and isinstance(m.channel, discord.DMChannel)
            
            try:
                msg = await bot.wait_for("message", check=check, timeout=600.0) 
                responses.append(msg.content)
            except asyncio.TimeoutError:
                await member.send("⏱️ Tu as mis trop de temps à répondre. Le questionnaire est annulé.")
                return 
        
        salon = bot.get_channel(ID_SALON_REPONSES)
        if salon and isinstance(salon, discord.TextChannel):
            formatted = "\n".join([f"**{questions[i]}**\n➡️ {responses[i]}" for i in range(len(questions))])
            await salon.send(f"🆕 **Réponses manuelles de : {member.mention} ({member.name})**\n\n{formatted}")
        
        await member.send("Merci pour tes réponses ! 💬 Elles ont été envoyées à l'équipe du serveur 👌")
        await ctx.send(f"✅ Questionnaire terminé avec succès pour {member.name}.")

    except discord.Forbidden:
        await ctx.send(f"❌ Impossible d'envoyer un MP à {member.mention}. Ses messages privés sont peut-être fermés.")
    except Exception as e:
        await ctx.send(f"⚠️ Une erreur est survenue : {e}")


keep_alive()     
bot.run(TOKEN)
