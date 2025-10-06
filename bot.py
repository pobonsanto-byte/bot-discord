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

# === CONFIGURAÇÃO ===
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Adicione no Render
REPO = "pobonsanto-byte/bot-discord"  # Alterado para seu repositório
CONFIG_FILE = "config.json"
IMUNIDADES_FILE = "imunidades.json"

CONFIG_URL = f"https://pobonsanto-byte.github.io/bot-discord/{CONFIG_FILE}"
IMUNIDADES_URL = f"https://pobonsanto-byte.github.io/bot-discord/{IMUNIDADES_FILE}"

# === FUNÇÕES GITHUB ===
def carregar_json_url(url):
    try:
        resp = requests.get(url)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"Erro ao carregar JSON da URL: {e}")
    return {}

def salvar_json_url(dados, file_path):
    try:
        url = f"https://api.github.com/repos/{REPO}/contents/{file_path}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}

        resp = requests.get(url, headers=headers)
        sha = resp.json().get("sha", None)

        content = base64.b64encode(json.dumps(dados, indent=4, ensure_ascii=False).encode()).decode()

        payload = {
            "message": f"Atualizando {file_path}",
            "content": content,
        }
        if sha:
            payload["sha"] = sha

        resp = requests.put(url, headers=headers, json=payload)
        if resp.status_code in [200, 201]:
            print(f"✅ {file_path} salvo com sucesso no GitHub")
            return True
        print(f"❌ Erro ao salvar {file_path}: {resp.text}")
    except Exception as e:
        print(f"Erro ao salvar JSON na URL: {e}")
    return False

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

# === FUNÇÕES AUXILIARES ===
def carregar_json(arquivo_url):
    return carregar_json_url(arquivo_url)

def salvar_json(arquivo_url, dados):
    if arquivo_url == CONFIG_URL:
        return salvar_json_url(dados, CONFIG_FILE)
    elif arquivo_url == IMUNIDADES_URL:
        return salvar_json_url(dados, IMUNIDADES_FILE)

def canal_configurado(guild_id):
    config = carregar_json(CONFIG_URL)
    return config.get(str(guild_id))

def canal_imunidade():
    async def predicate(interaction: discord.Interaction) -> bool:
        guild_id = str(interaction.guild.id)
        config = carregar_json(CONFIG_URL)
        canal_id = config.get(guild_id)

        if not canal_id:
            await interaction.response.send_message(
                "⚙️ O canal de imunidade ainda não foi configurado. Peça a um administrador para usar `/set_canal_imune`.",
                ephemeral=True
            )
            return False

        if interaction.channel.id == canal_id:
            return True

        await interaction.response.send_message(
            "❌ Esse comando só pode ser usado no canal configurado para imunidades.",
            ephemeral=True
        )
        return False
    return app_commands.check(predicate)

# === COMANDOS ADMINISTRATIVOS ===
@bot.tree.command(name="set_canal_imune", description="Define o canal onde os comandos de imunidade funcionarão.")
@app_commands.checks.has_permissions(administrator=True)
async def set_canal_imune(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    config = carregar_json(CONFIG_URL)
    config[guild_id] = interaction.channel.id
    salvar_json(CONFIG_URL, config)
    await interaction.response.send_message(
        f"✅ Canal de imunidade configurado para: {interaction.channel.mention}",
        ephemeral=False
    )

@set_canal_imune.error
async def set_canal_imune_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ Apenas administradores podem usar este comando.", ephemeral=True)

@bot.tree.command(name="ver_canal_imune", description="Mostra o canal configurado para imunidades.")
@app_commands.checks.has_permissions(administrator=True)
async def ver_canal_imune(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    config = carregar_json(CONFIG_URL)
    canal_id = config.get(guild_id)

    if not canal_id:
        await interaction.response.send_message("⚙️ Nenhum canal configurado ainda.", ephemeral=True)
        return

    canal = interaction.guild.get_channel(canal_id)
    if canal:
        await interaction.response.send_message(f"📍 Canal configurado: {canal.mention}", ephemeral=False)
    else:
        await interaction.response.send_message(f"⚠️ O canal configurado (ID: `{canal_id}`) não foi encontrado.", ephemeral=True)

@bot.tree.command(name="remover_canal_imune", description="Remove o canal configurado para imunidades.")
@app_commands.checks.has_permissions(administrator=True)
async def remover_canal_imune(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    config = carregar_json(CONFIG_URL)

    if guild_id not in config:
        await interaction.response.send_message("⚠️ Nenhum canal de imunidade está configurado neste servidor.", ephemeral=True)
        return

    canal_removido = config[guild_id]
    del config[guild_id]
    salvar_json(CONFIG_URL, config)
    await interaction.response.send_message(
        f"🗑️ Canal de imunidade removido com sucesso (ID: `{canal_removido}`).",
        ephemeral=False
    )

@remover_canal_imune.error
async def remover_canal_imune_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ Apenas administradores podem usar este comando.", ephemeral=True)

# === COMANDOS DE IMUNIDADE ===
@bot.tree.command(name="imune_add", description="Adiciona um personagem imune (1 por jogador).")
@canal_imunidade()
@app_commands.describe(nome_personagem="Nome do personagem", jogo_anime="Nome do jogo/anime")
async def imune_add(interaction: discord.Interaction, nome_personagem: str, jogo_anime: str):
    imunes = carregar_json(IMUNIDADES_URL)
    guild_id = str(interaction.guild.id)
    if guild_id not in imunes:
        imunes[guild_id] = {}
    user_id = str(interaction.user.id)
    if user_id in imunes[guild_id]:
        await interaction.response.send_message(f"⚠️ {interaction.user.mention}, você já possui um personagem imune!", ephemeral=True)
        return
    imunes[guild_id][user_id] = {
        "usuario": interaction.user.name,
        "personagem": nome_personagem,
        "origem": jogo_anime,
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    salvar_json(IMUNIDADES_URL, imunes)
    await interaction.response.send_message(
        f"🛡️ {interaction.user.mention} definiu **{nome_personagem} ({jogo_anime})** como imune!",
        ephemeral=False
    )

@bot.tree.command(name="imune_lista", description="Mostra a lista atual de personagens imunes.")
@canal_imunidade()
async def imune_lista(interaction: discord.Interaction):
    imunes = carregar_json(IMUNIDADES_URL)
    guild_id = str(interaction.guild.id)
    if guild_id not in imunes or not imunes[guild_id]:
        await interaction.response.send_message("📭 Nenhum personagem imune no momento.")
        return
    embed = discord.Embed(title="🧾 Lista de Personagens Imunes", color=0x5865F2)
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
    imunes = carregar_json(IMUNIDADES_URL)
    configs = carregar_json(CONFIG_URL)
    agora = datetime.now()
    alterado = False

    for guild_id, usuarios in list(imunes.items()):
        guild = bot.get_guild(int(guild_id))
        canal = None

        if guild and guild_id in configs:
            canal = guild.get_channel(configs[guild_id])

        if not canal:
            print(f"⚠️ Canal de imunidade não configurado em {guild.name if guild else guild_id}")
            continue

        for user_id, dados in list(usuarios.items()):
            try:
                data_inicial = datetime.strptime(dados["data"], "%Y-%m-%d %H:%M:%S")
                if agora - data_inicial >= timedelta(days=2):
                    await canal.send(f"🕒 A imunidade de **{dados['personagem']} ({dados['origem']})** do jogador **{dados['usuario']}** expirou!")
                    del usuarios[user_id]
                    alterado = True
            except Exception as e:
                print(f"⚠️ Erro ao verificar expiração: {e}")

    if alterado:
        salvar_json(IMUNIDADES_URL, imunes)

# === EVENTOS ===
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    await bot.change_presence(activity=discord.Game(name="/set_canal_imune | /imune_add"))

# === KEEP ALIVE ===
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

# === AUTO-PING INTERNO ===
def auto_ping():
    while True:
        try:
            url = os.environ.get("REPLIT_URL")
            if url:
                requests.get(url)
                print(f"🔄 Auto-ping enviado para {url}")
            else:
                print("⚠️ REPLIT_URL não definido.")
        except Exception as e:
            print(f"❌ Erro no auto-ping: {e}")
        time.sleep(300)

ping_thread = Thread(target=auto_ping)
ping_thread.daemon = True
ping_thread.start()

# === INICIAR BOT ===
if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERRO: DISCORD_BOT_TOKEN não encontrado!")
        exit(1)
    print(f"🔑 Token configurado (primeiros 10 caracteres): {TOKEN[:10]}...")
    print("🚀 Tentando conectar ao Discord...")
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("❌ ERRO DE AUTENTICAÇÃO! Token inválido ou expirado.")
        exit(1)
