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
import pytz
from discord.ui import View, Button

# === CONFIGURAÇÃO ===
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ARQUIVO_IMUNES = "imunidades.json"
ARQUIVO_CONFIG = "config.json"
ARQUIVO_COOLDOWN = "cooldowns.json"

# === CONFIG GITHUB ===
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = os.getenv("GITHUB_REPO")
BRANCH = os.getenv("GITHUB_BRANCH", "main")

# === FUSO HORÁRIO BRASIL ===
fuso_brasil = pytz.timezone("America/Sao_Paulo")

def agora_brasil():
    """Retorna a data/hora atual no fuso de Brasília"""
    return datetime.now(fuso_brasil)

# === FUNÇÕES GITHUB ===
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
    if r.status_code not in [200, 201]:
        print(f"❌ Erro ao salvar {nome_arquivo}: {r.status_code} - {r.text}")

# === FUNÇÕES COOLDOWN ===
def esta_em_cooldown(user_id):
    cooldowns = carregar_json(ARQUIVO_COOLDOWN)
    agora = agora_brasil()
    expira_em_str = cooldowns.get(str(user_id))
    if not expira_em_str:
        return False
    expira_em = datetime.strptime(expira_em_str, "%Y-%m-%d %H:%M:%S")
    if agora >= expira_em:
        del cooldowns[str(user_id)]
        salvar_json(ARQUIVO_COOLDOWN, cooldowns)
        return False
    return True

def definir_cooldown(user_id, dias=3):
    cooldowns = carregar_json(ARQUIVO_COOLDOWN)
    expira_em = agora_brasil() + timedelta(days=dias)
    cooldowns[str(user_id)] = expira_em.strftime("%Y-%m-%d %H:%M:%S")
    salvar_json(ARQUIVO_COOLDOWN, cooldowns)

# === BOT ===
class ImuneBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.guilds = True
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
    async def setup_hook(self):
        await self.tree.sync()
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

# === PAGINAÇÃO ===
class ListaImunesView(View):
    def __init__(self, grupos, timeout=120):
        super().__init__(timeout=timeout)
        self.grupos = list(grupos.items())
        self.page = 0
        self.total_pages = (len(self.grupos) - 1) // 3 + 1
        self.message = None
        if self.total_pages > 1:
            b1 = Button(label="⬅️", style=discord.ButtonStyle.gray)
            b1.callback = self.anterior_callback
            b2 = Button(label="➡️", style=discord.ButtonStyle.gray)
            b2.callback = self.proximo_callback
            self.add_item(b1)
            self.add_item(b2)
    def gerar_embed(self):
        embed = discord.Embed(title="🧾 Lista de Personagens Imunes", color=0x5865F2)
        start, end = self.page * 3, self.page * 3 + 3
        for origem, lista in self.grupos[start:end]:
            texto = "\n".join(f"• **{d['personagem']}** — {d['usuario']}" for d in lista)
            embed.add_field(name=f"🎮 {origem}", value=texto, inline=False)
        embed.set_footer(text=f"Página {self.page+1}/{self.total_pages}")
        return embed
    async def anterior_callback(self, i):
        if self.page > 0:
            self.page -= 1
            await i.response.edit_message(embed=self.gerar_embed(), view=self)
    async def proximo_callback(self, i):
        if self.page < self.total_pages - 1:
            self.page += 1
            await i.response.edit_message(embed=self.gerar_embed(), view=self)

# === COMANDOS ADMIN ===
@bot.tree.command(name="set_canal_imune", description="Define o canal onde os comandos de imunidade funcionarão.")
@app_commands.checks.has_permissions(administrator=True)
async def set_canal_imune(interaction: discord.Interaction):
    config = carregar_json(ARQUIVO_CONFIG)
    config[str(interaction.guild.id)] = interaction.channel.id
    salvar_json(ARQUIVO_CONFIG, config)
    await interaction.response.send_message(f"✅ Canal de imunidade definido: {interaction.channel.mention}")

@bot.tree.command(name="ver_canal_imune", description="Mostra qual canal está configurado para imunidade.")
@app_commands.checks.has_permissions(administrator=True)
async def ver_canal_imune(interaction: discord.Interaction):
    config = carregar_json(ARQUIVO_CONFIG)
    canal_id = config.get(str(interaction.guild.id))
    if not canal_id:
        await interaction.response.send_message("⚙️ Nenhum canal de imunidade configurado.")
    else:
        canal = interaction.guild.get_channel(canal_id)
        await interaction.response.send_message(f"🔒 Canal de imunidade configurado: {canal.mention}")

@bot.tree.command(name="remover_canal_imune", description="Remove o canal configurado para imunidade.")
@app_commands.checks.has_permissions(administrator=True)
async def remover_canal_imune(interaction: discord.Interaction):
    config = carregar_json(ARQUIVO_CONFIG)
    if str(interaction.guild.id) in config:
        del config[str(interaction.guild.id)]
        salvar_json(ARQUIVO_CONFIG, config)
        await interaction.response.send_message("🗑️ Canal de imunidade removido com sucesso.")
    else:
        await interaction.response.send_message("⚙️ Nenhum canal de imunidade configurado.")

# === REMOVER IMUNE (sem cooldown) ===
@bot.tree.command(name="imune_remover", description="Remove manualmente o personagem imune de um jogador (apenas admins).")
@app_commands.describe(usuario="Usuário que terá o personagem removido")
@app_commands.checks.has_permissions(administrator=True)
@canal_imunidade()
async def imune_remover(interaction: discord.Interaction, usuario: discord.Member):
    imunes = carregar_json(ARQUIVO_IMUNES)
    guild_id = str(interaction.guild.id)
    if guild_id not in imunes or str(usuario.id) not in imunes[guild_id]:
        await interaction.response.send_message(f"⚠️ {usuario.mention} não possui personagem imune.")
        return
    personagem = imunes[guild_id][str(usuario.id)]["personagem"]
    origem = imunes[guild_id][str(usuario.id)]["origem"]
    del imunes[guild_id][str(usuario.id)]
    salvar_json(ARQUIVO_IMUNES, imunes)
    await interaction.response.send_message(f"🗑️ {interaction.user.mention} removeu a imunidade de **{personagem} ({origem})** de {usuario.mention}.")

# === COMANDOS PADRÃO ===
@bot.tree.command(name="imune_add", description="Adiciona um personagem imune (1 por jogador).")
@canal_imunidade()
@app_commands.describe(nome_personagem="Nome do personagem", jogo_anime="Nome do jogo/anime")
async def imune_add(interaction: discord.Interaction, nome_personagem: str, jogo_anime: str):
    imunes = carregar_json(ARQUIVO_IMUNES)
    guild_id, user_id = str(interaction.guild.id), str(interaction.user.id)
    imunes.setdefault(guild_id, {})
    if esta_em_cooldown(user_id):
        await interaction.response.send_message(f"⏳ {interaction.user.mention}, você está em cooldown. Aguarde 3 dias.", ephemeral=True)
        return
    if user_id in imunes[guild_id]:
        await interaction.response.send_message("⚠️ Você já possui um personagem imune.", ephemeral=True)
        return
    for d in imunes[guild_id].values():
        if d["personagem"].strip().lower() == nome_personagem.strip().lower():
            await interaction.response.send_message("⚠️ Esse personagem já está imune.", ephemeral=True)
            return
    imunes[guild_id][user_id] = {
        "usuario": interaction.user.name,
        "personagem": nome_personagem,
        "origem": jogo_anime,
        "data": agora_brasil().strftime("%Y-%m-%d %H:%M:%S")
    }
    salvar_json(ARQUIVO_IMUNES, imunes)
    await interaction.response.send_message(f"🔒 {interaction.user.mention} definiu **{nome_personagem} ({jogo_anime})** como imune!")

@bot.tree.command(name="imune_lista", description="Mostra a lista de personagens imunes.")
@canal_imunidade()
async def imune_lista(interaction: discord.Interaction):
    imunes = carregar_json(ARQUIVO_IMUNES)
    guild_id = str(interaction.guild.id)
    if guild_id not in imunes or not imunes[guild_id]:
        await interaction.response.send_message("📭 Nenhum personagem imune.")
        return
    grupos = {}
    for d in imunes[guild_id].values():
        grupos.setdefault(d["origem"], []).append(d)
    view = ListaImunesView(grupos)
    await interaction.response.send_message(embed=view.gerar_embed(), view=view if view.total_pages > 1 else None)
    msg = await interaction.original_response()
    view.message = msg

@bot.tree.command(name="imune_status", description="Mostra seu status atual de imunidade e cooldown.")
@canal_imunidade()
async def imune_status(interaction: discord.Interaction):
    user_id, guild_id = str(interaction.user.id), str(interaction.guild.id)
    imunes, cooldowns = carregar_json(ARQUIVO_IMUNES), carregar_json(ARQUIVO_COOLDOWN)
    embed = discord.Embed(title=f"📊 Status de {interaction.user.display_name}", color=0x00B0F4)
    if guild_id in imunes and user_id in imunes[guild_id]:
        p = imunes[guild_id][user_id]
        embed.add_field(name="🔒 Personagem Imune", value=f"**{p['personagem']}** — {p['origem']}\n📅 Desde: `{p['data']}`", inline=False)
    else:
        embed.add_field(name="🔒 Personagem Imune", value="Nenhum ativo.", inline=False)
    if user_id in cooldowns:
        expira = datetime.strptime(cooldowns[user_id], "%Y-%m-%d %H:%M:%S")
        if expira > agora_brasil():
            restante = expira - agora_brasil()
            dias, resto = divmod(restante.total_seconds(), 86400)
            horas, resto = divmod(resto, 3600)
            minutos = (resto % 3600) // 60
            embed.add_field(name="⏳ Cooldown", value=f"Em andamento — {int(dias)}d {int(horas)}h {int(minutos)}min restantes.", inline=False)
        else:
            embed.add_field(name="⏳ Cooldown", value="Expirado (você pode adicionar outro).", inline=False)
    else:
        embed.add_field(name="⏳ Cooldown", value="Nenhum cooldown ativo.", inline=False)
    await interaction.response.send_message(embed=embed)

# === EVENTO DE CASAMENTO ===
@bot.event
async def on_message(msg: discord.Message):
    if msg.author == bot.user:
        return
    padrao = r"💖\s*(.*?)\s*e\s*(.*?)\s*agora são casados!\s*💖"
    m = re.search(padrao, msg.content)
    if not m:
        return
    usuario_nome, personagem_nome = m.group(1).strip(), m.group(2).strip()
    imunes = carregar_json(ARQUIVO_IMUNES)
    guild_id = str(msg.guild.id)
    if guild_id not in imunes:
        return
    personagem_encontrado = None
    for uid, d in imunes[guild_id].items():
        if d["personagem"].strip().lower() == personagem_nome.lower():
            personagem_encontrado = (uid, d)
            break
    if not personagem_encontrado:
        return
    user_id, dados_p = personagem_encontrado
    config = carregar_json(ARQUIVO_CONFIG)
    canal_id = config.get(str(msg.guild.id))
    if not canal_id:
        return
    canal = msg.guild.get_channel(canal_id)
    if not canal:
        return
    usuario_imune = msg.guild.get_member(int(user_id))
    texto = f"{usuario_imune.mention}, seu personagem imune **{personagem_nome} ({dados_p['origem']})** foi pego por **{usuario_nome}**!"
    await canal.send(texto)
    del imunes[guild_id][user_id]
    salvar_json(ARQUIVO_IMUNES, imunes)
    definir_cooldown(user_id)
    await bot.process_commands(msg)

# === TAREFA ===
@tasks.loop(hours=1)
async def verificar_imunidades():
    print("⏳ Verificação executada")

# === ON READY ===
@bot.event
async def on_ready():
    print(f"✅ Logado como {bot.user}")

# === KEEP ALIVE (Render) ===
app = Flask('')
@app.route('/')
def home(): return "🤖 Bot rodando!"
def run(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
Thread(target=run).start()
def auto_ping():
    while True:
        try:
            url = os.environ.get("REPLIT_URL")
            if url: requests.get(url)
            time.sleep(300)
        except Exception as e:
            print(f"Erro no ping: {e}")
Thread(target=auto_ping, daemon=True).start()

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERRO: DISCORD_BOT_TOKEN ausente!")
    else:
        bot.run(TOKEN)
