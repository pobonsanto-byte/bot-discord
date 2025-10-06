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
ARQUIVO_IMUNES = "imunidades.json"

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
def carregar_imunes():
    if not os.path.exists(ARQUIVO_IMUNES):
        return {}
    try:
        with open(ARQUIVO_IMUNES, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError) as e:
        print(f"⚠️ Erro ao carregar {ARQUIVO_IMUNES}: {e}")
        return {}

def salvar_imunes(imunes):
    try:
        with open(ARQUIVO_IMUNES, "w", encoding="utf-8") as f:
            json.dump(imunes, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"❌ Erro ao salvar {ARQUIVO_IMUNES}: {e}")

def canal_imunidade():
    async def predicate(interaction: discord.Interaction) -> bool:
        if isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            if "imunidade" in interaction.channel.name.lower():
                return True
        await interaction.response.send_message(
            "❌ Esse comando só pode ser usado em canais com 'imunidade' no nome.",
            ephemeral=True
        )
        return False
    return app_commands.check(predicate)

# === COMANDOS ===
@bot.tree.command(name="imune_add", description="Adiciona um personagem imune (1 por jogador).")
@canal_imunidade()
@app_commands.describe(nome_personagem="Nome do personagem", jogo_anime="Nome do jogo/anime")
async def imune_add(interaction: discord.Interaction, nome_personagem: str, jogo_anime: str):
    if not interaction.guild:
        await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)
        return
    imunes = carregar_imunes()
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
    salvar_imunes(imunes)
    await interaction.response.send_message(
        f"🛡️ {interaction.user.mention} definiu **{nome_personagem} ({jogo_anime})** como imune!",
        ephemeral=False
    )

@bot.tree.command(name="imune_lista", description="Mostra a lista atual de personagens imunes.")
@canal_imunidade()
async def imune_lista(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)
        return
    imunes = carregar_imunes()
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
        except (KeyError, ValueError) as e:
            print(f"⚠️ Erro ao processar dados de imunidade: {e}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="imune_remover", description="Remove sua imunidade manualmente.")
@canal_imunidade()
async def imune_remover(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)
        return
    imunes = carregar_imunes()
    guild_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)
    if guild_id not in imunes or user_id not in imunes[guild_id]:
        await interaction.response.send_message("❌ Você não possui imunidade ativa.", ephemeral=True)
        return
    del imunes[guild_id][user_id]
    salvar_imunes(imunes)
    await interaction.response.send_message(f"✅ {interaction.user.mention}, sua imunidade foi removida.", ephemeral=False)

@tasks.loop(hours=1)
async def verificar_imunidades():
    imunes = carregar_imunes()
    agora = datetime.now()
    alterado = False
    for guild_id, usuarios in list(imunes.items()):
        canal = None
        guild = bot.get_guild(int(guild_id))
        if guild:
            for c in guild.text_channels:
                if "imunidade" in c.name.lower():
                    canal = c
                    break
        if not canal:
            print(f"⚠️ Nenhum canal de imunidade encontrado no servidor {guild.name if guild else guild_id}.")
            continue
        for user_id, dados in list(usuarios.items()):
            try:
                data_inicial = datetime.strptime(dados["data"], "%Y-%m-%d %H:%M:%S")
                if agora - data_inicial >= timedelta(days=2):
                    try:
                        await canal.send(f"🕒 A imunidade de **{dados['personagem']} ({dados['origem']})** do jogador **{dados['usuario']}** expirou!")
                    except discord.errors.HTTPException as e:
                        print(f"❌ Erro ao enviar mensagem de expiração: {e}")
                    del usuarios[user_id]
                    alterado = True
                    print(f"🔁 Imunidade expirada: {dados['usuario']} ({dados['personagem']})")
            except (KeyError, ValueError) as e:
                print(f"⚠️ Dados inválidos para user_id {user_id}: {e}")
    if alterado:
        salvar_imunes(imunes)

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    await bot.change_presence(activity=discord.Game(name="/imune_add | /imune_lista"))

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
            url = os.environ.get("REPLIT_URL")  # Coloque seu link do Replit aqui
            if url:
                requests.get(url)
                print(f"🔄 Auto-ping enviado para {url}")
            else:
                print("⚠️ REPLIT_URL não definido.")
        except Exception as e:
            print(f"❌ Erro no auto-ping: {e}")
        time.sleep(300)  # ping a cada 5 minutos

ping_thread = Thread(target=auto_ping)
ping_thread.daemon = True
ping_thread.start()

# === INICIAR BOT ===
if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERRO: DISCORD_BOT_TOKEN não encontrado nas variáveis de ambiente!")
        exit(1)
    print(f"🔑 Token configurado (primeiros 10 caracteres): {TOKEN[:10]}...")
    print("🚀 Tentando conectar ao Discord...")
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("❌ ERRO DE AUTENTICAÇÃO! Token inválido ou expirado.")
        exit(1)
