import discord
from discord import app_commands
from discord.ext import tasks
from datetime import datetime, timedelta
import os
from flask import Flask
from threading import Thread
import requests
import time
from pymongo import MongoClient

# === CONFIGURAÇÃO ===
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# === CONEXÃO COM MONGO ===
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["bot_imunidade"]
config_collection = db["config"]
imunes_collection = db["imunes"]

# === FUNÇÕES AUXILIARES MONGO ===
def salvar_config(guild_id, canal_id):
    config_collection.update_one(
        {"guild_id": guild_id},
        {"$set": {"canal_id": canal_id}},
        upsert=True
    )

def carregar_config(guild_id):
    doc = config_collection.find_one({"guild_id": guild_id})
    return doc["canal_id"] if doc else None

def adicionar_imune(guild_id, user_id, usuario, personagem, origem):
    imunes_collection.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": {
            "usuario": usuario,
            "personagem": personagem,
            "origem": origem,
            "data": datetime.now()
        }},
        upsert=True
    )

def listar_imunes(guild_id):
    return list(imunes_collection.find({"guild_id": guild_id}))

def remover_imune(guild_id, user_id):
    imunes_collection.delete_one({"guild_id": guild_id, "user_id": user_id})

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
        canal_id = carregar_config(str(interaction.guild.id))
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
    salvar_config(guild_id, interaction.channel.id)
    await interaction.response.send_message(
        f"✅ Canal de imunidade configurado para: {interaction.channel.mention}",
        ephemeral=False
    )

@bot.tree.command(name="ver_canal_imune", description="Mostra o canal configurado para imunidades.")
@app_commands.checks.has_permissions(administrator=True)
async def ver_canal_imune(interaction: discord.Interaction):
    canal_id = carregar_config(str(interaction.guild.id))
    if not canal_id:
        await interaction.response.send_message("⚙️ Nenhum canal configurado ainda.", ephemeral=True)
        return
    canal = interaction.guild.get_channel(canal_id)
    if canal:
        await interaction.response.send_message(f"📍 Canal configurado: {canal.mention}", ephemeral=False)
    else:
        await interaction.response.send_message(f"⚠️ Canal configurado não encontrado.", ephemeral=True)

@bot.tree.command(name="remover_canal_imune", description="Remove o canal configurado para imunidades.")
@app_commands.checks.has_permissions(administrator=True)
async def remover_canal_imune(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    canal_id = carregar_config(guild_id)
    if not canal_id:
        await interaction.response.send_message("⚠️ Nenhum canal de imunidade está configurado.", ephemeral=True)
        return
    config_collection.delete_one({"guild_id": guild_id})
    await interaction.response.send_message(f"🗑️ Canal de imunidade removido com sucesso (ID: `{canal_id}`).", ephemeral=False)

# === COMANDOS DE IMUNIDADE ===
@bot.tree.command(name="imune_add", description="Adiciona um personagem imune (1 por jogador).")
@canal_imunidade()
@app_commands.describe(nome_personagem="Nome do personagem", jogo_anime="Nome do jogo/anime")
async def imune_add(interaction: discord.Interaction, nome_personagem: str, jogo_anime: str):
    guild_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)
    if imunes_collection.find_one({"guild_id": guild_id, "user_id": user_id}):
        await interaction.response.send_message(f"⚠️ {interaction.user.mention}, você já possui um personagem imune!", ephemeral=True)
        return
    adicionar_imune(guild_id, user_id, interaction.user.name, nome_personagem, jogo_anime)
    await interaction.response.send_message(f"🛡️ {interaction.user.mention} definiu **{nome_personagem} ({jogo_anime})** como imune!", ephemeral=False)

@bot.tree.command(name="imune_lista", description="Mostra a lista atual de personagens imunes.")
@canal_imunidade()
async def imune_lista(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    imunes = listar_imunes(guild_id)
    if not imunes:
        await interaction.response.send_message("📭 Nenhum personagem imune no momento.")
        return
    embed = discord.Embed(title="🧾 Lista de Personagens Imunes", color=0x5865F2)
    for dados in imunes:
        try:
            data_criacao = dados["data"]
            if isinstance(data_criacao, str):
                data_criacao = datetime.strptime(data_criacao, "%Y-%m-%d %H:%M:%S.%f")
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
    agora = datetime.now()
    for doc in imunes_collection.find({}):
        try:
            data_inicial = doc["data"]
            if isinstance(data_inicial, str):
                data_inicial = datetime.strptime(data_inicial, "%Y-%m-%d %H:%M:%S.%f")
            if agora - data_inicial >= timedelta(days=2):
                guild = bot.get_guild(int(doc["guild_id"]))
                canal_id = carregar_config(doc["guild_id"])
                canal = guild.get_channel(canal_id) if guild and canal_id else None
                if canal:
                    await canal.send(f"🕒 A imunidade de **{doc['personagem']} ({doc['origem']})** do jogador **{doc['usuario']}** expirou!")
                remover_imune(doc["guild_id"], doc["user_id"])
        except Exception as e:
            print(f"⚠️ Erro ao verificar expiração: {e}")

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
    if not TOKEN or not MONGO_URI:
        print("❌ ERRO: DISCORD_BOT_TOKEN ou MONGO_URI não encontrados!")
        exit(1)
    print(f"🔑 Token configurado (primeiros 10 caracteres): {TOKEN[:10]}...")
    print("🚀 Tentando conectar ao Discord...")
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("❌ ERRO DE AUTENTICAÇÃO! Token inválido ou expirado.")
        exit(1)
