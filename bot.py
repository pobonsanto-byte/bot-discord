import discord
from discord import app_commands
from discord.ext import tasks
from datetime import datetime, timedelta
import os
from flask import Flask
from threading import Thread
import requests
import time

# === CONFIGURAÇÃO ===
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
JSONBIN_API_KEY = os.getenv("JSONBIN_API_KEY")
CONFIG_BIN_ID = os.getenv("CONFIG_BIN_ID")
IMUNES_BIN_ID = os.getenv("IMUNES_BIN_ID")

ARQUIVO_IMUNES = "imunidades.json"
ARQUIVO_CONFIG = "config.json"

HEADERS = {
    "Content-Type": "application/json",
    "X-Master-Key": JSONBIN_API_KEY
}

# === FUNÇÕES PARA JSONBIN.IO ===
def carregar_bin(bin_id):
    try:
        url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
        resp = requests.get(url, headers=HEADERS)
        print(f"📡 JSONBin Response ({bin_id}):", resp.text)  # Debug
        if resp.status_code == 200:
            return resp.json()["record"]
        print(f"⚠️ Erro ao carregar bin: {resp.text}")
    except Exception as e:
        print(f"❌ Erro carregar_bin: {e}")
    return {}

def salvar_bin(bin_id, dados):
    try:
        url = f"https://api.jsonbin.io/v3/b/{bin_id}"
        resp = requests.put(url, json=dados, headers=HEADERS)
        if resp.status_code != 200:
            print(f"⚠️ Erro ao salvar bin: {resp.text}")
    except Exception as e:
        print(f"❌ Erro salvar_bin: {e}")

def carregar_json(arquivo):
    if arquivo == ARQUIVO_CONFIG:
        return carregar_bin(CONFIG_BIN_ID)
    elif arquivo == ARQUIVO_IMUNES:
        return carregar_bin(IMUNES_BIN_ID)
    return {}

def salvar_json(arquivo, dados):
    if arquivo == ARQUIVO_CONFIG:
        salvar_bin(CONFIG_BIN_ID, dados)
    elif arquivo == ARQUIVO_IMUNES:
        salvar_bin(IMUNES_BIN_ID, dados)

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

# === FUNÇÃO DE CHECAGEM DE CANAL COM AUTO-CONFIGURAÇÃO ===
def canal_imunidade():
    async def predicate(interaction: discord.Interaction) -> bool:
        guild_id = str(interaction.guild.id)
        print(f"🔍 Checando canal de imunidade para servidor: {guild_id}")

        config = carregar_json(ARQUIVO_CONFIG)
        print(f"📂 Config atual: {config}")

        canal_id = config.get(guild_id)
        print(f"🎯 Canal configurado: {canal_id}")
        print(f"🛠 Canal onde comando foi usado: {interaction.channel.id}")

        if not canal_id:
            # Auto-configurar o canal
            config[guild_id] = interaction.channel.id
            salvar_json(ARQUIVO_CONFIG, config)
            await interaction.response.send_message(
                f"⚙️ Canal de imunidade não estava configurado. Agora configurado automaticamente para {interaction.channel.mention}.",
                ephemeral=True
            )
            print(f"✅ Canal auto-configurado: {interaction.channel.id}")
            return True

        if interaction.channel.id == canal_id:
            print("✅ Canal correto.")
            return True

        await interaction.response.send_message(
            "❌ Esse comando só pode ser usado no canal configurado para imunidades.",
            ephemeral=True
        )
        print("❌ Canal incorreto.")
        return False

    return app_commands.check(predicate)

# === COMANDOS ADMINISTRATIVOS ===
@bot.tree.command(name="set_canal_imune", description="Define o canal onde os comandos de imunidade funcionarão.")
@app_commands.checks.has_permissions(administrator=True)
async def set_canal_imune(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    config = carregar_json(ARQUIVO_CONFIG)
    config[guild_id] = interaction.channel.id
    salvar_json(ARQUIVO_CONFIG, config)
    await interaction.response.send_message(
        f"✅ Canal de imunidade configurado para: {interaction.channel.mention}",
        ephemeral=False
    )
    print(f"📌 Canal configurado manualmente: {interaction.channel.id} para servidor {guild_id}")

@set_canal_imune.error
async def set_canal_imune_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ Apenas administradores podem usar este comando.", ephemeral=True)

@bot.tree.command(name="ver_canal_imune", description="Mostra o canal configurado para imunidades.")
@app_commands.checks.has_permissions(administrator=True)
async def ver_canal_imune(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    config = carregar_json(ARQUIVO_CONFIG)
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
    config = carregar_json(ARQUIVO_CONFIG)

    if guild_id not in config:
        await interaction.response.send_message("⚠️ Nenhum canal de imunidade está configurado neste servidor.", ephemeral=True)
        return

    canal_removido = config[guild_id]
    del config[guild_id]
    salvar_json(ARQUIVO_CONFIG, config)
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
    imunes = carregar_json(ARQUIVO_IMUNES)
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
    salvar_json(ARQUIVO_IMUNES, imunes)
    await interaction.response.send_message(
        f"🛡️ {interaction.user.mention} definiu **{nome_personagem} ({jogo_anime})** como imune!",
        ephemeral=False
    )

@bot.tree.command(name="imune_lista", description="Mostra a lista atual de personagens imunes.")
@canal_imunidade()
async def imune_lista(interaction: discord.Interaction):
    imunes = carregar_json(ARQUIVO_IMUNES)
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
        salvar_json(ARQUIVO_IMUNES, imunes)

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
    if not JSONBIN_API_KEY or not CONFIG_BIN_ID or not IMUNES_BIN_ID:
        print("❌ ERRO: Variáveis JSONBIN não configuradas!")
        exit(1)
    print(f"🔑 Token configurado (primeiros 10 caracteres): {TOKEN[:10]}...")
    print("🚀 Tentando conectar ao Discord...")
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("❌ ERRO DE AUTENTICAÇÃO! Token inválido ou expirado.")
        exit(1)
