import discord
from discord import app_commands
from discord.ext import tasks
from datetime import datetime, timedelta
import os
from flask import Flask
from threading import Thread
import requests
import time
import json

# === CONFIGURAÇÃO ===
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}

# Arquivos virtuais
ARQUIVO_IMUNES = "imunidades.json"
ARQUIVO_CONFIG = "config.json"

GIST_IMUNES_ID = None
GIST_CONFIG_ID = None

# === FUNÇÕES DE GIST ===
def criar_gist(nome, conteudo="{}"):
    try:
        payload = {
            "description": nome,
            "public": False,
            "files": {
                "data.json": {"content": conteudo}
            }
        }
        resp = requests.post("https://api.github.com/gists", headers=HEADERS, json=payload)
        if resp.status_code == 201:
            return resp.json()["id"]
    except Exception as e:
        print(f"❌ Erro ao criar Gist {nome}: {e}")
    return None

def carregar_gist(gist_id):
    try:
        url = f"https://api.github.com/gists/{gist_id}"
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            files = resp.json().get("files", {})
            for content in files.values():
                return json.loads(content.get("content", "{}"))
    except Exception as e:
        print(f"⚠️ Erro ao carregar Gist {gist_id}: {e}")
    return {}

def salvar_gist(gist_id, dados):
    try:
        url = f"https://api.github.com/gists/{gist_id}"
        conteudo = json.dumps(dados, indent=4, ensure_ascii=False)
        payload = {"files": {"data.json": {"content": conteudo}}}
        resp = requests.patch(url, headers=HEADERS, json=payload)
        if resp.status_code != 200:
            print(f"❌ Erro ao salvar no Gist: {resp.status_code}")
    except Exception as e:
        print(f"⚠️ Falha ao salvar no Gist: {e}")

def carregar_json(arquivo):
    if "imunidades" in arquivo:
        return carregar_gist(GIST_IMUNES_ID)
    elif "config" in arquivo:
        return carregar_gist(GIST_CONFIG_ID)
    return {}

def salvar_json(arquivo, dados):
    if "imunidades" in arquivo:
        salvar_gist(GIST_IMUNES_ID, dados)
    elif "config" in arquivo:
        salvar_gist(GIST_CONFIG_ID, dados)

# === CONFIGURAÇÃO INICIAL DOS GISTS ===
def inicializar_gists():
    global GIST_IMUNES_ID, GIST_CONFIG_ID

    gists_resp = requests.get("https://api.github.com/gists", headers=HEADERS).json()
    for gist in gists_resp:
        desc = gist.get("description", "")
        if desc == "Gist de imunidades do bot":
            GIST_IMUNES_ID = gist["id"]
        elif desc == "Gist de configuração do bot":
            GIST_CONFIG_ID = gist["id"]

    if not GIST_IMUNES_ID:
        GIST_IMUNES_ID = criar_gist("Gist de imunidades do bot")
    if not GIST_CONFIG_ID:
        GIST_CONFIG_ID = criar_gist("Gist de configuração do bot")

# === CLASSE DO BOT ===
class ImuneBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        try:
            synced = await self.tree.sync()
            print(f"✅ {len(synced)} comandos sincronizados globalmente")
        except Exception as e:
            print(f"❌ Erro ao sincronizar comandos: {e}")
        verificar_imunidades.start()

bot = ImuneBot()

# === CHECK DE CANAL ===
def canal_imunidade():
    async def predicate(interaction: discord.Interaction) -> bool:
        guild_id = str(interaction.guild.id)
        config = carregar_json(ARQUIVO_CONFIG)
        canal_id = config.get(guild_id)

        if not canal_id:
            await interaction.response.send_message(
                "⚙️ O canal de imunidade ainda não foi configurado. Use `/set_canal_imune`.",
                ephemeral=True
            )
            return False

        if interaction.channel.id == canal_id:
            return True

        await interaction.response.send_message(
            "❌ Esse comando só pode ser usado no canal configurado.",
            ephemeral=True
        )
        return False
    return app_commands.check(predicate)

# === COMANDOS ADMINISTRATIVOS ===
@bot.tree.command(name="set_canal_imune", description="Define o canal de imunidade.")
@app_commands.checks.has_permissions(administrator=True)
async def set_canal_imune(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    config = carregar_json(ARQUIVO_CONFIG)
    config[guild_id] = interaction.channel.id
    salvar_json(ARQUIVO_CONFIG, config)
    await interaction.response.send_message(f"✅ Canal de imunidade definido: {interaction.channel.mention}", ephemeral=False)

@bot.tree.command(name="ver_canal_imune", description="Mostra o canal configurado.")
@app_commands.checks.has_permissions(administrator=True)
async def ver_canal_imune(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    config = carregar_json(ARQUIVO_CONFIG)
    canal_id = config.get(guild_id)
    if not canal_id:
        await interaction.response.send_message("⚙️ Nenhum canal configurado.", ephemeral=True)
        return
    canal = interaction.guild.get_channel(canal_id)
    if canal:
        await interaction.response.send_message(f"📍 Canal configurado: {canal.mention}", ephemeral=False)
    else:
        await interaction.response.send_message(f"⚠️ Canal configurado não encontrado.", ephemeral=True)

@bot.tree.command(name="remover_canal_imune", description="Remove o canal configurado.")
@app_commands.checks.has_permissions(administrator=True)
async def remover_canal_imune(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    config = carregar_json(ARQUIVO_CONFIG)
    if guild_id not in config:
        await interaction.response.send_message("⚠️ Nenhum canal configurado.", ephemeral=True)
        return
    del config[guild_id]
    salvar_json(ARQUIVO_CONFIG, config)
    await interaction.response.send_message(f"🗑️ Canal removido com sucesso.", ephemeral=False)

# === COMANDOS DE IMUNIDADE ===
@bot.tree.command(name="imune_add", description="Adiciona um personagem imune.")
@canal_imunidade()
@app_commands.describe(nome_personagem="Nome do personagem", jogo_anime="Nome do jogo/anime")
async def imune_add(interaction: discord.Interaction, nome_personagem: str, jogo_anime: str):
    imunes = carregar_json(ARQUIVO_IMUNES)
    guild_id = str(interaction.guild.id)
    if guild_id not in imunes:
        imunes[guild_id] = {}
    user_id = str(interaction.user.id)
    if user_id in imunes[guild_id]:
        await interaction.response.send_message(f"⚠️ Você já possui imunidade!", ephemeral=True)
        return
    imunes[guild_id][user_id] = {
        "usuario": interaction.user.name,
        "personagem": nome_personagem,
        "origem": jogo_anime,
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    salvar_json(ARQUIVO_IMUNES, imunes)
    await interaction.response.send_message(f"🛡️ Imunidade adicionada: **{nome_personagem} ({jogo_anime})**", ephemeral=False)

@bot.tree.command(name="imune_lista", description="Lista personagens imunes.")
@canal_imunidade()
async def imune_lista(interaction: discord.Interaction):
    imunes = carregar_json(ARQUIVO_IMUNES)
    guild_id = str(interaction.guild.id)
    if guild_id not in imunes or not imunes[guild_id]:
        await interaction.response.send_message("📭 Nenhum personagem imune no momento.")
        return
    embed = discord.Embed(title="🧾 Lista de Imunidades", color=0x5865F2)
    for dados in imunes[guild_id].values():
        try:
            data_criacao = datetime.strptime(dados["data"], "%Y-%m-%d %H:%M:%S")
            tempo_passado = datetime.now() - data_criacao
            horas_restantes = max(0, 48 - int(tempo_passado.total_seconds() // 3600))
            embed.add_field(
                name=f"{dados['personagem']} ({dados['origem']})",
                value=f"Dono: **{dados['usuario']}**\n⏳ Expira em: {horas_restantes}h",
                inline=False
            )
        except Exception as e:
            print(f"⚠️ Erro ao processar dados: {e}")
    await interaction.response.send_message(embed=embed)

# === VERIFICADOR DE EXPIRAÇÃO ===
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
            print(f"⚠️ Canal não configurado em {guild.name if guild else guild_id}")
            continue
        for user_id, dados in list(usuarios.items()):
            try:
                data_inicial = datetime.strptime(dados["data"], "%Y-%m-%d %H:%M:%S")
                if agora - data_inicial >= timedelta(days=2):
                    await canal.send(f"🕒 A imunidade de **{dados['personagem']} ({dados['origem']})** expirou!")
                    del usuarios[user_id]
                    alterado = True
            except Exception as e:
                print(f"⚠️ Erro ao verificar expiração: {e}")
    if alterado:
        salvar_json(ARQUIVO_IMUNES, imunes)

# === EVENTOS ===
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    await bot.change_presence(activity=discord.Game(name="/set_canal_imune | /imune_add"))

# === KEEP ALIVE ===
app = Flask('')
@app.route('/')
def home(): return "🤖 Bot rodando!"

def run(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
def keep_alive(): Thread(target=run).start()
keep_alive()

# === AUTO-PING INTERNO ===
def auto_ping():
    while True:
        try:
            url = os.environ.get("REPLIT_URL")
            if url: requests.get(url)
        except Exception as e:
            print(f"❌ Erro no auto-ping: {e}")
        time.sleep(300)

Thread(target=auto_ping, daemon=True).start()

# === INICIAR BOT ===
if __name__ == "__main__":
    if not TOKEN or not GITHUB_TOKEN:
        print("❌ DISCORD_BOT_TOKEN ou GITHUB_TOKEN não configurados!")
        exit(1)
    inicializar_gists()
    bot.run(TOKEN)
