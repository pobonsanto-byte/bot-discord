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
ARQUIVO_IMUNES = "imunidades.json"
ARQUIVO_CONFIG = "config.json"
ARQUIVO_LOGS = "logs_config.json"

# === CONFIG GITHUB ===
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = os.getenv("GITHUB_REPO")
BRANCH = os.getenv("GITHUB_BRANCH", "main")

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

    data = {
        "message": f"Atualizando {nome_arquivo}",
        "content": base64_content,
        "branch": BRANCH,
    }
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
def canal_configurado(guild_id):
    config = carregar_json(ARQUIVO_CONFIG)
    return config.get(str(guild_id))

def canal_log_configurado(guild_id):
    logs = carregar_json(ARQUIVO_LOGS)
    return logs.get(str(guild_id))

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

# === COMANDOS ADMINISTRATIVOS: CANAL IMUNE ===
@bot.tree.command(name="set_canal_imune", description="Define o canal onde os comandos de imunidade funcionarão.")
@app_commands.checks.has_permissions(administrator=True)
async def set_canal_imune(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    config = carregar_json(ARQUIVO_CONFIG)
    config[guild_id] = interaction.channel.id
    salvar_json(ARQUIVO_CONFIG, config)
    await interaction.response.send_message(f"✅ Canal de imunidade configurado para: {interaction.channel.mention}")

@bot.tree.command(name="ver_canal_imune", description="Mostra o canal configurado para imunidades.")
@app_commands.checks.has_permissions(administrator=True)
async def ver_canal_imune(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    config = carregar_json(ARQUIVO_CONFIG)
    canal_id = config.get(guild_id)

    if not canal_id:
        await interaction.response.send_message("⚙️ Nenhum canal configurado ainda.")
        return

    canal = interaction.guild.get_channel(canal_id)
    if canal:
        await interaction.response.send_message(f"📍 Canal configurado: {canal.mention}")
    else:
        await interaction.response.send_message(f"⚠️ Canal não encontrado (ID: `{canal_id}`)")

@bot.tree.command(name="remover_canal_imune", description="Remove o canal configurado para imunidades.")
@app_commands.checks.has_permissions(administrator=True)
async def remover_canal_imune(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    config = carregar_json(ARQUIVO_CONFIG)
    if guild_id not in config:
        await interaction.response.send_message("⚠️ Nenhum canal de imunidade configurado.")
        return
    del config[guild_id]
    salvar_json(ARQUIVO_CONFIG, config)
    await interaction.response.send_message("🗑️ Canal de imunidade removido com sucesso!")

# === COMANDOS ADMINISTRATIVOS: CANAL DE LOG ===
@bot.tree.command(name="set_canal_log", description="Define o canal onde os logs de imunidade e Mudae serão enviados.")
@app_commands.checks.has_permissions(administrator=True)
async def set_canal_log(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    logs = carregar_json(ARQUIVO_LOGS)
    logs[guild_id] = interaction.channel.id
    salvar_json(ARQUIVO_LOGS, logs)
    await interaction.response.send_message(f"✅ Canal de logs configurado para: {interaction.channel.mention}")

@bot.tree.command(name="ver_canal_log", description="Mostra o canal configurado para logs.")
@app_commands.checks.has_permissions(administrator=True)
async def ver_canal_log(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    logs = carregar_json(ARQUIVO_LOGS)
    canal_id = logs.get(guild_id)
    if not canal_id:
        await interaction.response.send_message("⚙️ Nenhum canal de logs configurado.")
        return
    canal = interaction.guild.get_channel(canal_id)
    if canal:
        await interaction.response.send_message(f"📜 Canal de logs configurado: {canal.mention}")
    else:
        await interaction.response.send_message(f"⚠️ Canal não encontrado (ID: `{canal_id}`)")

@bot.tree.command(name="remover_canal_log", description="Remove o canal configurado para logs.")
@app_commands.checks.has_permissions(administrator=True)
async def remover_canal_log(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    logs = carregar_json(ARQUIVO_LOGS)
    if guild_id not in logs:
        await interaction.response.send_message("⚠️ Nenhum canal de logs configurado.")
        return
    del logs[guild_id]
    salvar_json(ARQUIVO_LOGS, logs)
    await interaction.response.send_message("🗑️ Canal de logs removido com sucesso!")

# === COMANDOS DE IMUNIDADE ===
@bot.tree.command(name="imune_add", description="Adiciona um personagem imune (1 por jogador).")
@canal_imunidade()
@app_commands.describe(nome_personagem="Nome do personagem", jogo_anime="Origem do personagem")
async def imune_add(interaction: discord.Interaction, nome_personagem: str, jogo_anime: str):
    imunes = carregar_json(ARQUIVO_IMUNES)
    guild_id = str(interaction.guild.id)
    if guild_id not in imunes:
        imunes[guild_id] = {}
    user_id = str(interaction.user.id)
    if user_id in imunes[guild_id]:
        await interaction.response.send_message("⚠️ Você já possui um personagem imune!")
        return
    imunes[guild_id][user_id] = {
        "usuario": interaction.user.name,
        "personagem": nome_personagem,
        "origem": jogo_anime,
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    salvar_json(ARQUIVO_IMUNES, imunes)
    await interaction.response.send_message(f"🛡️ {interaction.user.mention} definiu **{nome_personagem} ({jogo_anime})** como imune!")

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
        data_criacao = datetime.strptime(dados["data"], "%Y-%m-%d %H:%M:%S")
        horas_restantes = max(0, 48 - int((datetime.now() - data_criacao).total_seconds() // 3600))
        embed.add_field(
            name=f"{dados['personagem']} ({dados['origem']})",
            value=f"Dono: **{dados['usuario']}**\n⏳ Expira em: {horas_restantes}h",
            inline=False
        )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="imune_reset", description="Remove TODAS as imunidades do servidor atual (somente administradores).")
@app_commands.checks.has_permissions(administrator=True)
async def imune_reset(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    imunes = carregar_json(ARQUIVO_IMUNES)
    if guild_id not in imunes or not imunes[guild_id]:
        await interaction.response.send_message("📭 Não há imunidades para remover neste servidor.")
        return
    qtd = len(imunes[guild_id])
    imunes[guild_id] = {}
    salvar_json(ARQUIVO_IMUNES, imunes)
    await interaction.response.send_message(f"🧹 Todas as **{qtd} imunidades** foram removidas com sucesso!")

# === VERIFICADOR DE EXPIRAÇÃO ===
@tasks.loop(hours=1)
async def verificar_imunidades():
    imunes = carregar_json(ARQUIVO_IMUNES)
    configs = carregar_json(ARQUIVO_CONFIG)
    agora = datetime.now()
    alterado = False
    for guild_id, usuarios in list(imunes.items()):
        guild = bot.get_guild(int(guild_id))
        canal = guild.get_channel(configs[guild_id]) if guild and guild_id in configs else None
        if not canal:
            continue
        for user_id, dados in list(usuarios.items()):
            data_inicial = datetime.strptime(dados["data"], "%Y-%m-%d %H:%M:%S")
            if agora - data_inicial >= timedelta(days=2):
                await canal.send(f"🕒 A imunidade de **{dados['personagem']} ({dados['origem']})** do jogador **{dados['usuario']}** expirou!")
                del usuarios[user_id]
                alterado = True
    if alterado:
        salvar_json(ARQUIVO_IMUNES, imunes)

# === MONITORAMENTO MUDAE + LOGS ===
@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    mensagem = reaction.message
    if not mensagem.author or not mensagem.author.bot or "mudae" not in mensagem.author.name.lower():
        return
    if not mensagem.embeds or not mensagem.embeds[0].title:
        return
    nome_personagem = mensagem.embeds[0].title.strip()
    guild_id = str(mensagem.guild.id)
    imunes = carregar_json(ARQUIVO_IMUNES)
    if guild_id not in imunes:
        return
    for user_id, dados in imunes[guild_id].items():
        if nome_personagem.lower() == dados["personagem"].strip().lower():
            dono_id = int(user_id)
            dono_nome = dados["usuario"]
            origem = dados.get("origem", "Desconhecida")
            if user.id == dono_id:
                aviso = f"✅ {user.mention} reagiu ao próprio imune **{nome_personagem}** (*{origem}*)."
                emoji = "✅"
                acao = "REAGIU AO PRÓPRIO IMUNE"
            else:
                aviso = f"⚠️ {user.mention} reagiu ao personagem **{nome_personagem}** (*{origem}*), mas o dono é **{dono_nome}**!"
                emoji = "⚠️"
                acao = "TENTOU PEGAR IMUNE"
            try:
                await mensagem.add_reaction(emoji)
                await mensagem.channel.send(aviso)
                await registrar_log_mudae(mensagem.guild, user, dono_nome, nome_personagem, origem, acao)
            except Exception as e:
                print(f"⚠️ Erro ao enviar aviso/log: {e}")
            break

async def registrar_log_mudae(guild, usuario, dono_nome, personagem, origem, acao):
    logs = carregar_json(ARQUIVO_LOGS)
    canal_id = logs.get(str(guild.id))
    canal_log = guild.get_channel(canal_id) if canal_id else None
    if not canal_log:
        canal_nome = "logs-imunes"
        canal_log = discord.utils.get(guild.text_channels, name=canal_nome)
        if not canal_log:
            try:
                canal_log = await guild.create_text_channel(canal_nome)
                await canal_log.send("📜 Canal de logs de imunidade criado automaticamente.")
            except Exception as e:
                print(f"❌ Erro ao criar canal de log: {e}")
                return
    log_msg = (
        f"🕓 **{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}**\n"
        f"👤 **Usuário:** {usuario.mention} (`{usuario.id}`)\n"
        f"🎭 **Personagem:** {personagem} (*{origem}*)\n"
        f"👑 **Dono:** {dono_nome}\n"
        f"📝 **Ação:** {acao}"
    )
    await canal_log.send(log_msg)

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
                print(f"🔄 Auto-ping enviado para {url}")
        except Exception as e:
            print(f"❌ Erro no auto-ping: {e}")
        time.sleep(300)

Thread(target=auto_ping, daemon=True).start()

# === INICIAR BOT ===
if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERRO: DISCORD_BOT_TOKEN não encontrado!")
        exit(1)
    bot.run(TOKEN)
