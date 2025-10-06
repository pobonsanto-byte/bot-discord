import discord
from discord import app_commands
from discord.ext import tasks
from datetime import datetime, timedelta
import json
import os
from flask import Flask
from threading import Thread
import requests
import time
import base64

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ARQUIVO_IMUNES = "imunidades.json"
ARQUIVO_CONFIG = "config.json"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = os.getenv("GITHUB_REPO")
BRANCH = os.getenv("GITHUB_BRANCH", "main")

def carregar_json(nome_arquivo):
    url = f"https://api.github.com/repos/{REPO}/contents/{nome_arquivo}?ref={BRANCH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        content = base64.b64decode(r.json()["content"]).decode("utf-8")
        try:
            return json.loads(content)
        except:
            return {}
    return {}

def salvar_json(nome_arquivo, dados):
    url = f"https://api.github.com/repos/{REPO}/contents/{nome_arquivo}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    conteudo = json.dumps(dados, indent=4, ensure_ascii=False)
    base64_content = base64.b64encode(conteudo.encode()).decode()
    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None
    data = {"message": f"Atualizando {nome_arquivo}", "content": base64_content, "branch": BRANCH}
    if sha:
        data["sha"] = sha
    requests.put(url, headers=headers, json=data)

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.reactions = True

class ImuneBot(discord.Client):
    def __init__(self, intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
    async def setup_hook(self):
        await self.tree.sync()
        verificar_imunidades.start()

bot = ImuneBot(intents=intents)

def canal_configurado(guild_id):
    config = carregar_json(ARQUIVO_CONFIG)
    return config.get(str(guild_id))

def canal_imunidade():
    async def predicate(interaction: discord.Interaction) -> bool:
        config = carregar_json(ARQUIVO_CONFIG)
        canal_id = config.get(str(interaction.guild.id))
        if not canal_id:
            await interaction.response.send_message("⚙️ Canal não configurado.", ephemeral=True)
            return False
        if interaction.channel.id == canal_id:
            return True
        await interaction.response.send_message("❌ Esse comando só pode ser usado no canal configurado.", ephemeral=True)
        return False
    return app_commands.check(predicate)

@bot.tree.command(name="imune_add")
@canal_imunidade()
async def imune_add(interaction: discord.Interaction, nome_personagem: str, jogo_anime: str):
    imunes = carregar_json(ARQUIVO_IMUNES)
    guild_id = str(interaction.guild.id)
    if guild_id not in imunes:
        imunes[guild_id] = {}
    for dados in imunes[guild_id].values():
        if dados["personagem"].lower() == nome_personagem.lower():
            await interaction.response.send_message("⚠️ Personagem já imune!", ephemeral=True)
            return
    imunes[guild_id][str(interaction.user.id)] = {"usuario": interaction.user.name,"personagem": nome_personagem,"origem": jogo_anime,"data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    salvar_json(ARQUIVO_IMUNES, imunes)
    await interaction.response.send_message(f"🛡️ {interaction.user.mention} definiu **{nome_personagem} ({jogo_anime})** como imune!")

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    imunes = carregar_json(ARQUIVO_IMUNES)
    for guild_id, usuarios in imunes.items():
        guild = bot.get_guild(int(guild_id))
        if not guild:
            continue
        for user_id, dados in usuarios.items():
            if dados["personagem"].lower() in reaction.message.content.lower():
                dono = guild.get_member(int(user_id))
                if user.id != int(user_id):
                    await reaction.message.channel.send(f"⚠️ {user.mention} pegou **{dados['personagem']} ({dados['origem']})** que está imune, dono: {dono.mention if dono else 'Desconhecido'}.")

@tasks.loop(hours=1)
async def verificar_imunidades():
    imunes = carregar_json(ARQUIVO_IMUNES)
    configs = carregar_json(ARQUIVO_CONFIG)
    agora = datetime.now()
    alterado = False
    for guild_id, usuarios in list(imunes.items()):
        guild = bot.get_guild(int(guild_id))
        canal = None
        if guild and guild_id in configs:
            canal = guild.get_channel(configs[guild_id])
        if not canal:
            continue
        for user_id, dados in list(usuarios.items()):
            data_inicial = datetime.strptime(dados["data"], "%Y-%m-%d %H:%M:%S")
            if agora - data_inicial >= timedelta(days=2):
                await canal.send(f"🕒 Imunidade de **{dados['personagem']}** expirou!")
                del usuarios[user_id]
                alterado = True
    if alterado:
        salvar_json(ARQUIVO_IMUNES, imunes)

app = Flask('')
@app.route('/')
def home():
    return "🤖 Bot rodando!"
def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
def keep_alive():
    t = Thread(target=run)
    t.start()
keep_alive()

def auto_ping():
    while True:
        url = os.environ.get("REPLIT_URL")
        if url:
            requests.get(url)
        time.sleep(300)
ping_thread = Thread(target=auto_ping)
ping_thread.daemon = True
ping_thread.start()

if __name__ == "__main__":
    if not TOKEN:
        exit(1)
    bot.run(TOKEN)
