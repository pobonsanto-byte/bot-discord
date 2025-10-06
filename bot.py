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

# === CONFIGURAÇÃO ===
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GIST_IMUNIDADES_ID = os.getenv("GIST_IMUNIDADES_ID")
GIST_CONFIG_ID = os.getenv("GIST_CONFIG_ID")
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}

# === FUNÇÕES DE GIST ===
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
        payload = {
            "files": {
                "data.json": {"content": conteudo}
            }
        }
        resp = requests.patch(url, headers=HEADERS, json=payload)
        if resp.status_code == 200:
            print(f"✅ Dados salvos com sucesso no Gist {gist_id}")
        else:
            print(f"❌ Erro ao salvar Gist {gist_id}: {resp.status_code}")
    except Exception as e:
        print(f"⚠️ Falha ao salvar no Gist: {e}")

def carregar_json(arquivo):
    if "imunidades" in arquivo:
        return carregar_gist(GIST_IMUNIDADES_ID)
    elif "config" in arquivo:
        return carregar_gist(GIST_CONFIG_ID)
    return {}

def salvar_json(arquivo, dados):
    if "imunidades" in arquivo:
        salvar_gist(GIST_IMUNIDADES_ID, dados)
    elif "config" in arquivo:
        salvar_gist(GIST_CONFIG_ID, dados)

# === CLASSE DO BOT ===
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

class ImuneBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ Comandos sincronizados com sucesso")
        verificar_imunidades.start()

bot = ImuneBot()

# === FUNÇÃO DE CHECAGEM DE CANAL ===
def canal_imunidade():
    async def predicate(interaction: discord.Interaction) -> bool:
        guild_id = str(interaction.guild.id)
        config = carregar_json("config.json")
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
    config = carregar_json("config.json")
    config[guild_id] = interaction.channel.id
    salvar_json("config.json", config)
    await interaction.response.send_message(
        f"✅ Canal configurado: {interaction.channel.mention}"
    )

@bot.tree.command(name="ver_canal_imune", description="Mostra o canal configurado para imunidades.")
@app_commands.checks.has_permissions(administrator=True)
async def ver_canal_imune(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    config = carregar_json("config.json")
    canal_id = config.get(guild_id)
    if not canal_id:
        await interaction.response.send_message("⚙️ Nenhum canal configurado ainda.", ephemeral=True)
        return
    canal = interaction.guild.get_channel(canal_id)
    if canal:
        await interaction.response.send_message(f"📍 Canal configurado: {canal.mention}")
    else:
        await interaction.response.send_message(f"⚠️ Canal configurado não encontrado.", ephemeral=True)

@bot.tree.command(name="remover_canal_imune", description="Remove o canal configurado para imunidades.")
@app_commands.checks.has_permissions(administrator=True)
async def remover_canal_imune(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    config = carregar_json("config.json")
    if guild_id not in config:
        await interaction.response.send_message("⚠️ Nenhum canal configurado neste servidor.", ephemeral=True)
        return
    del config[guild_id]
    salvar_json("config.json", config)
    await interaction.response.send_message("🗑️ Canal de imunidade removido com sucesso.")

# === COMANDOS DE IMUNIDADE ===
@bot.tree.command(name="imune_add", description="Adiciona um personagem imune.")
@canal_imunidade()
@app_commands.describe(nome_personagem="Nome do personagem", jogo_anime="Nome do jogo/anime")
async def imune_add(interaction: discord.Interaction, nome_personagem: str, jogo_anime: str):
    imunes = carregar_json("imunidades.json")
    guild_id = str(interaction.guild.id)
    if guild_id not in imunes:
        imunes[guild_id] = {}
    user_id = str(interaction.user.id)
    if user_id in imunes[guild_id]:
        await interaction.response.send_message("⚠️ Você já possui um personagem imune.", ephemeral=True)
        return
    imunes[guild_id][user_id] = {
        "usuario": interaction.user.name,
        "personagem": nome_personagem,
        "origem": jogo_anime,
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    salvar_json("imunidades.json", imunes)
    await interaction.response.send_message(f"🛡️ {interaction.user.mention} definiu **{nome_personagem} ({jogo_anime})** como imune!")

@bot.tree.command(name="imune_lista", description="Mostra a lista atual de personagens imunes.")
@canal_imunidade()
async def imune_lista(interaction: discord.Interaction):
    try:
        imunes = carregar_json("imunidades.json")
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
                embed.add_field(name="⚠️ Erro ao processar imunidade", value=str(e))
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao listar imunidades: {e}")

@bot.tree.command(name="imune_remover", description="Remove sua imunidade manualmente.")
@canal_imunidade()
async def imune_remover(interaction: discord.Interaction):
    imunes = carregar_json("imunidades.json")
    guild_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)
    if guild_id not in imunes or user_id not in imunes[guild_id]:
        await interaction.response.send_message("❌ Você não possui imunidade ativa.", ephemeral=True)
        return
    del imunes[guild_id][user_id]
    salvar_json("imunidades.json", imunes)
    await interaction.response.send_message(f"✅ {interaction.user.mention}, sua imunidade foi removida.")

# === LOOP DE VERIFICAÇÃO ===
@tasks.loop(hours=1)
async def verificar_imunidades():
    imunes = carregar_json("imunidades.json")
    configs = carregar_json("config.json")
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
            try:
                data_inicial = datetime.strptime(dados["data"], "%Y-%m-%d %H:%M:%S")
                if agora - data_inicial >= timedelta(days=2):
                    await canal.send(f"🕒 A imunidade de **{dados['personagem']} ({dados['origem']})** do jogador **{dados['usuario']}** expirou!")
                    del usuarios[user_id]
                    alterado = True
            except Exception as e:
                print(f"⚠️ Erro ao verificar expiração: {e}")
    if alterado:
        salvar_json("imunidades.json", imunes)

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

# === AUTO-PING ===
def auto_ping():
    while True:
        try:
            url = os.environ.get("REPLIT_URL")
            if url:
                requests.get(url)
            time.sleep(300)
        except Exception as e:
            print(f"❌ Erro no auto-ping: {e}")

ping_thread = Thread(target=auto_ping)
ping_thread.daemon = True
ping_thread.start()

# === INICIAR BOT ===
if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_BOT_TOKEN não encontrado!")
        exit(1)
    if not GITHUB_TOKEN or not GIST_IMUNIDADES_ID or not GIST_CONFIG_ID:
        print("❌ Variáveis do Gist não configuradas!")
        exit(1)
    bot.run(TOKEN)
