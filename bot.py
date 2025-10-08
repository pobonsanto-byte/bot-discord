import discord
from discord import app_commands
from discord.ext import tasks
from datetime import datetime
import json
import os
from flask import Flask
from threading import Thread
import requests
import time
import base64

# === NOVO IMPORT PARA MONITORAMENTO ===
from monitoramento import monitorar_casamentos

# === CONFIGURAÇÃO ===
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ARQUIVO_IMUNES = "imunidades.json"
ARQUIVO_CONFIG = "config.json"

# === CONFIG GITHUB ===
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = os.getenv("GITHUB_REPO")
BRANCH = os.getenv("GITHUB_BRANCH", "main")

# === INFO DO REPOSITÓRIO (PARA MONITORAMENTO) ===
repo_info = {
    "GITHUB_TOKEN": GITHUB_TOKEN,
    "REPO": REPO,
    "BRANCH": BRANCH
}

# === FUNÇÕES DE ARMAZENAMENTO ONLINE ===
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

# === AUXILIARES ===
def canal_configurado(guild_id):
    config = carregar_json(ARQUIVO_CONFIG)
    return config.get(str(guild_id))

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
    config = carregar_json(ARQUIVO_CONFIG)
    config[guild_id] = interaction.channel.id
    salvar_json(ARQUIVO_CONFIG, config)
    await interaction.response.send_message(f"✅ Canal de imunidade configurado para: {interaction.channel.mention}")

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
        await interaction.response.send_message(f"📍 Canal configurado: {canal.mention}")
    else:
        await interaction.response.send_message(f"⚠️ O canal configurado (ID: `{canal_id}`) não foi encontrado.", ephemeral=True)

@ver_canal_imune.error
async def ver_canal_imune_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ Apenas administradores podem usar este comando.", ephemeral=True)

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
    await interaction.response.send_message(f"🗑️ Canal de imunidade removido com sucesso (ID: `{canal_removido}`).")

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

    nome_personagem_clean = nome_personagem.strip().lower()

    for dados in imunes[guild_id].values():
        if dados["personagem"].strip().lower() == nome_personagem_clean:
            await interaction.response.send_message(
                f"⚠️ Esse personagem já está imune para outra pessoa: **{dados['personagem']} ({dados['origem']})**.",
                ephemeral=True
            )
            return

    user_id = str(interaction.user.id)
    if user_id in imunes[guild_id]:
        await interaction.response.send_message(f"⚠️ {interaction.user.mention}, você já possui um personagem imune!", ephemeral=True)
        return

    imunes[guild_id][user_id] = {
        "usuario": interaction.user.name,
        "personagem": nome_personagem.strip(),
        "origem": jogo_anime.strip(),
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    salvar_json(ARQUIVO_IMUNES, imunes)
    await interaction.response.send_message(f"🔒 {interaction.user.mention} definiu **{nome_personagem} ({jogo_anime})** como imune!")

@bot.tree.command(name="imune_lista", description="Mostra a lista atual de personagens imunes, agrupados por origem.")
@canal_imunidade()
async def imune_lista(interaction: discord.Interaction):
    imunes = carregar_json(ARQUIVO_IMUNES)
    guild_id = str(interaction.guild.id)
    if guild_id not in imunes or not imunes[guild_id]:
        await interaction.response.send_message("📭 Nenhum personagem imune no momento.", ephemeral=True)
        return

    embed = discord.Embed(title="🧾 Lista de Personagens Imunes", color=0x5865F2)
    grupos = {}
    for dados in imunes[guild_id].values():
        origem = dados["origem"].strip()
        if origem not in grupos:
            grupos[origem] = []
        grupos[origem].append(dados)

    for origem, lista_personagens in grupos.items():
        texto = ""
        for dados in lista_personagens:
            texto += f"• **{dados['personagem']}** — {dados['usuario']}\n"
        embed.add_field(name=f"🎮 {origem}", value=texto, inline=False)

    await interaction.response.send_message(embed=embed)

# === COMANDO PARA REMOVER IMUNIDADE ===
@bot.tree.command(name="imune_remover", description="Remove um personagem imune de um usuário (Admin somente).")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(usuario="Usuário alvo", personagem="Nome do personagem")
async def imune_remover(interaction: discord.Interaction, usuario: discord.Member, personagem: str):
    imunes = carregar_json(ARQUIVO_IMUNES)
    guild_id = str(interaction.guild.id)

    if guild_id not in imunes or not imunes[guild_id]:
        await interaction.response.send_message("⚠️ Não há imunidades configuradas neste servidor.", ephemeral=True)
        return

    personagem_clean = personagem.strip().lower()
    usuario_id = str(usuario.id)
    encontrado = False

    for user_id, dados in list(imunes[guild_id].items()):
        if dados["personagem"].strip().lower() == personagem_clean and user_id == usuario_id:
            del imunes[guild_id][user_id]
            salvar_json(ARQUIVO_IMUNES, imunes)
            encontrado = True
            await interaction.response.send_message(f"🗑️ Imunidade de **{personagem}** removida para {usuario.mention}.")
            break

    if not encontrado:
        await interaction.response.send_message(f"⚠️ Nenhuma imunidade encontrada para {usuario.mention} com o personagem **{personagem}**.", ephemeral=True)

@imune_remover.error
async def imune_remover_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ Apenas administradores podem usar este comando.", ephemeral=True)

# === VERIFICADOR DE IMUNIDADES (DESATIVADO) ===
@tasks.loop(hours=1)
async def verificar_imunidades():
    print("⏳ Verificação de imunidades executada (sem expiração).")

# === EVENTOS ===
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    await bot.change_presence(activity=None)  # 🔕 Remove qualquer status de "Jogando"

# === NOVO EVENTO PARA MONITORAR CASAMENTOS ===
@bot.event
async def on_message(message):
    await monitorar_casamentos(bot, message, repo_info, ARQUIVO_IMUNES)
    await bot.process_commands(message)

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
            time.sleep(300)
        except Exception as e:
            print(f"❌ Erro no auto-ping: {e}")
ping_thread = Thread(target=auto_ping)
ping_thread.daemon = True
ping_thread.start()

# === INICIAR BOT ===
if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERRO: DISCORD_BOT_TOKEN não encontrado!")
        exit(1)
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("❌ ERRO DE AUTENTICAÇÃO! Token inválido ou expirado.")
        exit(1)
