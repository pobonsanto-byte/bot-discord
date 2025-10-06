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
import re

# === CONFIGURAÇÃO ===
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ARQUIVO_IMUNES = "imunidades.json"
ARQUIVO_CONFIG = "config.json"

# === CONFIG GITHUB ===
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = os.getenv("GITHUB_REPO")
BRANCH = os.getenv("GITHUB_BRANCH", "main")

# === FUNÇÕES ===
def carregar_json(nome_arquivo):
    url = f"https://api.github.com/repos/{REPO}/contents/{nome_arquivo}?ref={BRANCH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        content = base64.b64decode(r.json()["content"]).decode("utf-8")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            print(f"⚠️ Erro ao decodificar {nome_arquivo}")
            return {}
    else:
        print(f"⚠️ Não foi possível carregar {nome_arquivo}: {r.status_code}")
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
    r = requests.put(url, headers=headers, json=data)
    if r.status_code in [200, 201]:
        print(f"✅ {nome_arquivo} atualizado no GitHub.")
    else:
        print(f"❌ Erro ao salvar {nome_arquivo}: {r.status_code} - {r.text}")

# === BOT ===
class ImuneBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        try:
            synced = await self.tree.sync()
            print(f"✅ {len(synced)} comandos sincronizados globalmente")
        except Exception as e:
            print(f"❌ Erro ao sincronizar comandos: {e}")
        verificar_imunidades.start()

bot = ImuneBot()

# === AUXILIARES ===
def canal_imunidade():
    async def predicate(interaction: discord.Interaction) -> bool:
        guild_id = str(interaction.guild.id)
        config = carregar_json(ARQUIVO_CONFIG)
        canal_id = config.get(guild_id)
        if not canal_id:
            await interaction.response.send_message(
                "⚙️ O canal de imunidade ainda não foi configurado.", ephemeral=True
            )
            return False
        if interaction.channel.id == canal_id:
            return True
        await interaction.response.send_message(
            "❌ Esse comando só pode ser usado no canal configurado.", ephemeral=True
        )
        return False
    return app_commands.check(predicate)

def limpar_nome(nome):
    nome = re.sub(r"<:.+?:\d+>", "", nome)
    nome = re.sub(r"[^\w\s]", "", nome)
    return nome.lower().strip()

# === COMANDOS ===
@bot.tree.command(name="set_canal_imune", description="Define o canal onde os comandos de imunidade funcionarão.")
@app_commands.checks.has_permissions(administrator=True)
async def set_canal_imune(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    config = carregar_json(ARQUIVO_CONFIG)
    config[guild_id] = interaction.channel.id
    salvar_json(ARQUIVO_CONFIG, config)
    await interaction.response.send_message(f"✅ Canal de imunidade configurado para: {interaction.channel.mention}", ephemeral=False)

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
    await interaction.response.send_message(f"🗑️ Canal de imunidade removido com sucesso (ID: `{canal_removido}`).", ephemeral=False)

@bot.tree.command(name="imune_add", description="Adiciona um personagem imune (1 por jogador).")
@canal_imunidade()
@app_commands.describe(nome_personagem="Nome do personagem", jogo_anime="Nome do jogo/anime")
async def imune_add(interaction: discord.Interaction, nome_personagem: str, jogo_anime: str):
    if not nome_personagem or not jogo_anime:
        await interaction.response.send_message("❌ Por favor, informe o nome do personagem e a origem.", ephemeral=True)
        return
    imunes = carregar_json(ARQUIVO_IMUNES)
    guild_id = str(interaction.guild.id)
    if guild_id not in imunes:
        imunes[guild_id] = {}
    user_id = str(interaction.user.id)
    if user_id in imunes[guild_id]:
        dados_existentes = imunes[guild_id][user_id]
        if "personagem" in dados_existentes:
            await interaction.response.send_message(f"⚠️ {interaction.user.mention}, você já possui um personagem imune!", ephemeral=True)
            return
        else:
            del imunes[guild_id][user_id]
    imunes[guild_id][user_id] = {
        "usuario": interaction.user.name,
        "personagem": nome_personagem,
        "origem": jogo_anime,
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    salvar_json(ARQUIVO_IMUNES, imunes)
    await interaction.response.send_message(f"🛡️ {interaction.user.mention} definiu **{nome_personagem} ({jogo_anime})** como imune!", ephemeral=False)

@bot.tree.command(name="imune_lista", description="Mostra a lista atual de personagens imunes.")
@canal_imunidade()
async def imune_lista(interaction: discord.Interaction):
    imunes = carregar_json(ARQUIVO_IMUNES)
    guild_id = str(interaction.guild.id)
    if guild_id not in imunes or not imunes[guild_id]:
        await interaction.response.send_message("📭 Nenhum personagem imune no momento.", ephemeral=True)
        return
    embed = discord.Embed(title="🧾 Lista de Personagens Imunes", color=0x5865F2)
    for dados in imunes[guild_id].values():
        try:
            if "personagem" not in dados or "origem" not in dados or "usuario" not in dados:
                continue
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
    await interaction.response.send_message(embed=embed, ephemeral=False)

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
            continue
        for user_id, dados in list(usuarios.items()):
            try:
                if "personagem" not in dados:
                    continue
                data_inicial = datetime.strptime(dados["data"], "%Y-%m-%d %H:%M:%S")
                if agora - data_inicial >= timedelta(days=2):
                    await canal.send(f"🕒 A imunidade de **{dados['personagem']} ({dados['origem']})** do jogador **{dados['usuario']}** expirou!")
                    del usuarios[user_id]
                    alterado = True
            except Exception as e:
                print(f"⚠️ Erro ao verificar expiração: {e}")
    if alterado:
        salvar_json(ARQUIVO_IMUNES, imunes)

# === EVENTO DE REAÇÃO ===
avisos_enviados = {}
@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    mensagem = reaction.message
    guild = mensagem.guild
    if not guild:
        return
    guild_id = str(guild.id)
    imunes = carregar_json(ARQUIVO_IMUNES)
    config = carregar_json(ARQUIVO_CONFIG)
    canal_id = config.get(guild_id)
    if not canal_id or canal_id != mensagem.channel.id:
        return
    if not mensagem.author.bot or "Mudae" not in mensagem.author.name:
        return
    personagem_nome = ""
    if mensagem.embeds:
        embed = mensagem.embeds[0]
        if embed.title:
            personagem_nome = embed.title
        elif embed.description:
            personagem_nome = embed.description
    if not personagem_nome and mensagem.content:
        personagem_nome = mensagem.content
    personagem_nome = limpar_nome(personagem_nome)
    encontrou = False
    for user_id, dados in imunes.get(guild_id, {}).items():
        if not isinstance(dados, dict):
            continue
        if "personagem" not in dados or "origem" not in dados or "usuario" not in dados:
            continue
        if limpar_nome(dados["personagem"]) in personagem_nome:
            dono = dados["usuario"]
            chave = f"{mensagem.id}-{dados['personagem']}"
            if chave in avisos_enviados:
                return
            await mensagem.channel.send(
                f"⚠️ {user.mention} reagiu à mensagem do Mudae com o personagem **{dados['personagem']} ({dados['origem']})** usando {reaction.emoji}!\n"
                f"💠 Imunidade definida por: {dono}\n"
                f"{'✅ Você é o dono da imunidade!' if user.name == dono else '❌ Você não é o dono da imunidade!'}"
            )
            avisos_enviados[chave] = True
            encontrou = True
            break

# === READY EVENT ===
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
        except:
            pass
        time.sleep(300)
ping_thread = Thread(target=auto_ping)
ping_thread.daemon = True
ping_thread.start()

# === INICIAR BOT ===
if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERRO: DISCORD_BOT_TOKEN não encontrado!")
        exit(1)
    bot.run(TOKEN)
