# Bot Discord - Questionnaire de Bienvenue

Bot Discord automatisé qui accueille les nouveaux membres et leur pose une série de questions pour faciliter leur intégration au serveur.

## 🎯 Fonctionnalités

- Détection automatique des nouveaux membres rejoignant le serveur
- Envoi de messages privés (DM) avec un questionnaire de bienvenue
- Collecte des réponses en messages privés
- Publication des réponses dans un salon dédié du serveur
- Serveur Flask pour maintenir le bot actif (keep-alive)

## 📋 Questions posées aux nouveaux membres

1. "Salut et bienvenue ! 😊 Quel est ton pseudo AS ?"
2. "Ton secteur de jeux ? 🌍"
3. "Qu'est-ce qui t'a motivé à rejoindre le groupement ? 🤔"
4. "Joues-tu à d'autres jeux? 🎮"

## 🔧 Installation et Configuration

### Prérequis
- Python 3.11 ou supérieur
- Un bot Discord créé sur le [Discord Developer Portal](https://discord.com/developers/applications)

### Installation

1. **Cloner le projet**
   ```bash
   git clone <votre-repo>
   cd <nom-du-projet>
   ```

2. **Installer les dépendances**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configurer les variables d'environnement**
   
   Créez un fichier `.env` à la racine du projet :
   ```
   DISCORD_TOKEN=votre_token_discord_ici
   ```
   
   ⚠️ **Important** : Remplacez `votre_token_discord_ici` par votre véritable token Discord Bot

4. **Modifier l'ID du salon de réponses**
   
   Dans `main.py`, changez cette ligne avec l'ID de votre salon Discord :
   ```python
   ID_SALON_REPONSES = 1433793778111484035  # Remplacez par votre ID
   ```

### Lancer le bot localement

```bash
python main.py
```

## 🚀 Déploiement sur Render

### Étapes de déploiement

1. **Créer un compte sur [Render.com](https://render.com)**

2. **Créer un nouveau Web Service**
   - Cliquez sur "New +" → "Web Service"
   - Connectez votre repository Git (GitHub, GitLab, etc.)
   - Ou uploadez le projet manuellement

3. **Configuration Render**
   - **Name** : discord-bot (ou votre nom)
   - **Environment** : Python 3
   - **Build Command** : `pip install -r requirements.txt`
   - **Start Command** : `python main.py`
   - **Instance Type** : Free (gratuit)

4. **Variables d'environnement**
   
   Dans les paramètres Render, ajoutez :
   - **Key** : `DISCORD_TOKEN`
   - **Value** : Votre token Discord Bot

5. **Déployer**
   - Cliquez sur "Create Web Service"
   - Attendez que le déploiement se termine (quelques minutes)

### Keep-Alive sur Render

Le serveur Flask sur le port 5000 maintient votre bot actif. Render pingera automatiquement votre application, donc pas besoin de service externe comme UptimeRobot.

## 🔒 Permissions Discord requises

Votre bot Discord doit avoir ces permissions :
- Lire les messages
- Envoyer des messages
- Gérer les membres (pour détecter les nouveaux arrivants)

Et ces **Intents** dans le Developer Portal :
- ✅ **Presence Intent**
- ✅ **Server Members Intent**
- ✅ **Message Content Intent**

### Comment activer les Intents :
1. Allez sur [Discord Developer Portal](https://discord.com/developers/applications)
2. Sélectionnez votre application
3. Allez dans "Bot" → "Privileged Gateway Intents"
4. Activez les 3 intents mentionnés ci-dessus

## 📁 Structure du projet

```
.
├── main.py              # Code principal du bot Discord
├── keep_alive.py        # Serveur Flask pour keep-alive
├── requirements.txt     # Dépendances Python
├── runtime.txt          # Version de Python (pour Render)
├── README.md           # Documentation
└── .gitignore          # Fichiers à exclure de Git
```

## ⚠️ Important - Messages privés

Pour que le bot fonctionne, les nouveaux membres doivent avoir les **messages privés activés** pour le serveur :

**Sur Discord PC/Mac :**
1. Clic droit sur le nom du serveur
2. "Paramètres de confidentialité"
3. Activer "Autoriser les messages privés venant des membres du serveur"

**Sur Discord Mobile :**
1. Appuyer sur le nom du serveur
2. "Confidentialité"
3. Activer "Messages privés"

## 🛠️ Personnalisation

### Modifier les questions

Dans `main.py`, modifiez la liste `questions` :
```python
questions = [
    "Votre question 1 ?",
    "Votre question 2 ?",
    "Votre question 3 ?",
    # Ajoutez autant de questions que vous voulez
]
```

### Changer l'ID du salon de réponses

Dans `main.py` :
```python
ID_SALON_REPONSES = 1234567890  # Remplacez par votre ID de salon
```

Pour obtenir un ID de salon Discord :
1. Activez le mode développeur dans Discord (Paramètres → Avancés → Mode développeur)
2. Clic droit sur le salon → "Copier l'identifiant"

## 🐛 Dépannage

### Le bot ne répond pas
- Vérifiez que le token Discord est correct
- Vérifiez que les Intents sont activés
- Vérifiez les logs pour voir les erreurs

### "Cannot send messages to this user"
- Le membre a désactivé les messages privés
- Demandez-lui d'activer les DM pour le serveur

### Le bot se déconnecte
- Sur Render (gratuit), le bot peut redémarrer après 15 min d'inactivité
- Le serveur Flask devrait éviter cela en gardant l'application active

## 📝 Licence

Ce projet est libre d'utilisation.

## 💬 Support

Pour toute question ou problème, consultez la [documentation Discord.py](https://discordpy.readthedocs.io/).
