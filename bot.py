import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import json
import os
from flask import Flask
import threading
from threading import Thread
import requests
import time
import base64
import re
import asyncio
from discord.ui import View, Button
import xml.etree.ElementTree as ET
import unicodedata
import math
from wsgiref.simple_server import make_server

# === CONFIGURAÇÃO ===
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ARQUIVO_IMUNES = "imunidades.json"
ARQUIVO_CONFIG = "config.json"
ARQUIVO_COOLDOWN = "cooldowns.json"
ARQUIVO_YOUTUBE = "youtube.json"
ARQUIVO_ATIVIDADE = "atividade.json"
DIAS_INATIVIDADE = 3  # 🕒 define quantos dias sem roletar remove imunidade
ARQUIVO_LOG_ATIVIDADE = "log_atividade.json"
ARQUIVO_ATIVIDADE_6DIAS = "atividade_6dias.json"
ARQUIVO_SERIES = "series.json"
ARQUIVO_ISENCAO = "isencao_inatividade.json"

# =============================
# ARQUIVOS SEASON 2
# =============================
ARQ_S2_CONFIG = "season2_config.json"
ARQ_S2_PLAYERS = "season2_players.json"
ARQ_S2_PERSONAGENS = "season2_personagens.json"
ARQ_S2_VENDAS = "season2_vendas.json"
ARQ_S2_SALAS = "season2_salas.json"

# =============================
# CONFIGURAÇÕES SEASON 2
# =============================
S2_TEMPO_SALA = 10 * 60  # 10 minutos
MUDAE_BOT_ID = 432610292342587392
S2_CATEGORIA_SALAS_ID = None  # Será configurado

S2_ROLL_PREFIXES = ("$w", "$wa", "$wg", "$h", "$ha", "$hg")
S2_ROLL_FREE = ("$vote", "$daily")

S2_SALAS_ATIVAS = {}  # Controle de salas ativas

# === CONFIG GITHUB ===
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = os.getenv("GITHUB_REPO")
BRANCH = os.getenv("GITHUB_BRANCH", "main")

def normalizar_texto(txt: str) -> str:
    """Remove acentuação e converte para minúsculas."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', txt)
        if unicodedata.category(c) != 'Mn'
    ).lower().strip()

# === FUNÇÃO de DM ===
async def enviar_dm(usuario: discord.Member, embed: discord.Embed):
    try:
        await usuario.send(embed=embed)
    except discord.Forbidden:
        print(f"⚠️ DM bloqueada por {usuario.display_name}")
    except Exception as e:
        print(f"❌ Erro ao enviar DM para {usuario.display_name}: {e}")

# === HORA LOCAL (BRASÍLIA, UTC-3) ===
def agora_brasil():
    return datetime.utcnow() - timedelta(hours=3)

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

# 🆕 NOVO BLOCO – funções e loop de verificação de inatividade
def carregar_atividade():
    """Carrega o arquivo de atividade do GitHub."""
    dados = carregar_json(ARQUIVO_ATIVIDADE)
    return dados if dados else {}

def salvar_atividade(dados):
    """Salva o arquivo de atividade no GitHub."""
    salvar_json(ARQUIVO_ATIVIDADE, dados)

def carregar_atividade_6dias():
    return carregar_json(ARQUIVO_ATIVIDADE_6DIAS)

def salvar_atividade_6dias(dados):
    salvar_json(ARQUIVO_ATIVIDADE_6DIAS, dados)

# === FUNÇÕES AUXILIARES DE SÉRIES ===
def carregar_series():
    """Carrega o arquivo de séries do GitHub."""
    dados = carregar_json(ARQUIVO_SERIES)
    return dados if dados else {}

def salvar_series(series):
    """Salva o arquivo de séries no GitHub."""
    salvar_json(ARQUIVO_SERIES, series)

def carregar_isencao():
    """Carrega o arquivo de isenção de inatividade."""
    dados = carregar_json(ARQUIVO_ISENCAO)
    return dados if dados else {}

def salvar_isencao(dados):
    """Salva o arquivo de isenção no GitHub."""
    salvar_json(ARQUIVO_ISENCAO, dados)

def usuario_tem_isencao(user_id):
    """Verifica se um usuário tem isenção de inatividade."""
    isencao = carregar_isencao()
    return str(user_id) in isencao

def toggle_isencao(user_id, usuario_nome):
    """Adiciona ou remove isenção de inatividade de um usuário."""
    isencao = carregar_isencao()
    user_id_str = str(user_id)
    
    if user_id_str in isencao:
        # Remove isenção
        del isencao[user_id_str]
        salvar_isencao(isencao)
        return False  # Isenção removida
    else:
        # Adiciona isenção
        isencao[user_id_str] = {
            "usuario": usuario_nome,
            "data_concessao": agora_brasil().strftime("%Y-%m-%d %H:%M:%S"),
            "concedido_por": "Sistema"  # Será atualizado no comando
        }
        salvar_isencao(isencao)
        return True  # Isenção concedida

# =============================
# FUNÇÕES SEASON 2
# =============================
def s2_load_salas():
    return carregar_json(ARQ_S2_SALAS) or {}

def s2_save_salas(dados):
    salvar_json(ARQ_S2_SALAS, dados)

def s2_load(arq):
    return carregar_json(arq) or {}

def s2_save(arq, dados):
    salvar_json(arq, dados)

def s2_extrair_personagem_do_embed(embed: discord.Embed):
    return embed.title.strip() if embed.title else None

def s2_definir_tipo_personagem(embed: discord.Embed):
    desc = (embed.description or "").lower()
    return "wish_outro" if "wish" in desc else "livre"

def s2_registro_automatico(uid, personagem, tipo):
    chars = s2_load(ARQ_S2_PERSONAGENS)
    chars.setdefault(uid, []).append({
        "personagem": personagem,
        "tipo": tipo,
        "origem": "sala_privada",
        "data": agora_brasil().strftime("%Y-%m-%d %H:%M")
    })
    s2_save(ARQ_S2_PERSONAGENS, chars)

# Função para fechar sala automaticamente (removendo acesso)
async def fechar_sala_automaticamente(uid: str, guild: discord.Guild):
    salas = s2_load_salas()
    players = s2_load(ARQ_S2_PLAYERS)

    sala = salas.get(uid)
    if not sala:
        return

    membro = guild.get_member(int(uid))
    cargo = guild.get_role(sala["cargo_id"])
    canal = guild.get_channel(sala["canal_id"])

    # === DM ===
    if membro:
        embed_dm = discord.Embed(
            title="⏰ Sala Privada Encerrada",
            description="Seu acesso à sala privada foi removido.",
            color=discord.Color.orange()
        )
        embed_dm.add_field(name="Motivo", value="Tempo limite de 10 minutos", inline=False)
        await enviar_dm(membro, embed_dm)

    if membro and cargo:
        await membro.remove_roles(cargo)

    if canal:
        await canal.delete()

    if cargo:
        await cargo.delete()

    if uid in players:
        players[uid]["sala_ativa"] = False
        s2_save(ARQ_S2_PLAYERS, players)

    del salas[uid]
    s2_save_salas(salas)



# === BOT ===
# Mudando para usar commands.Bot em vez de discord.Client
class ImuneBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.guilds = True
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="$", intents=intents)

    async def setup_hook(self):
        # Sincroniza comandos slash
        await self.tree.sync()
        
        # Inicia as tasks
        verificar_imunidades.start()
        verificar_youtube.start()
        verificar_cooldowns.start()
        verificar_inatividade.start()
        checar_atividade.before_loop(self.wait_until_ready)
        checar_atividade.start()
        s2_reset.start()
        verificar_salas_expiradas.start()

        # ✅ Executa o loop uma vez manualmente na inicialização
        await checar_atividade()

        print("✅ Bot totalmente inicializado e checagem feita uma vez.")

bot = ImuneBot()

# === CANAL DE IMUNIDADE ===
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

# === LOOP DE VERIFICAÇÃO DE INATIVIDADE ===
@tasks.loop(hours=1)
async def verificar_inatividade():
    agora = agora_brasil()
    imunes = carregar_json(ARQUIVO_IMUNES)
    atividade = carregar_atividade()
    config = carregar_json(ARQUIVO_CONFIG)

    for guild in bot.guilds:
        guild_id = str(guild.id)
        if guild_id not in imunes:
            continue

        canal_id = config.get(guild_id)
        canal = guild.get_channel(canal_id) if canal_id else None
        remover_lista = []

        for user_id, dados in imunes[guild_id].items():
            # 🔒 VERIFICA SE O USUÁRIO TEM ISENÇÃO
            if usuario_tem_isencao(user_id):
                print(f"🛡️ Usuário {user_id} tem isenção - ignorando verificação de inatividade")
                continue

            # Verifica se existe registro de atividade para este usuário
            user_activity = atividade.get(user_id)
            if not user_activity:
                print(f"⚠️ Usuário {user_id} não tem registro de atividade")
                continue

            # Extrai a string da data (suporta ambos os formatos)
            ultima_str = None
            if isinstance(user_activity, dict):
                ultima_str = user_activity.get("data")
            else:
                ultima_str = user_activity

            if not ultima_str:
                print(f"⚠️ Usuário {user_id} tem atividade mas sem data")
                continue

            try:
                ultima_data = datetime.strptime(ultima_str, "%Y-%m-%d %H:%M:%S")
            except Exception as e:
                print(f"⚠️ Erro ao ler data de {user_id}: {e} - Data: {ultima_str}")
                continue

            # Verifica se passou o limite de inatividade
            dias_inativos = (agora - ultima_data).days
            print(f"👤 Usuário {user_id} - Última atividade: {ultima_str} - Dias inativos: {dias_inativos}")

            if dias_inativos >= DIAS_INATIVIDADE:
                print(f"🔴 Usuário {user_id} inativo há {dias_inativos} dias - REMOVENDO")
                remover_lista.append(user_id)

        # Processa remoções
        for user_id in remover_lista:
            usuario = guild.get_member(int(user_id))
            if not usuario:
                usuario_mention = "Usuário desconhecido"
            else:
                usuario_mention = usuario.mention

            # Pega personagem e origem antes de remover
            personagem = imunes[guild_id][user_id]["personagem"]
            origem = imunes[guild_id][user_id]["origem"]

            # Remove imunidade
            del imunes[guild_id][user_id]
            salvar_json(ARQUIVO_IMUNES, imunes)

            # Aplica cooldown de 7 dias por inatividade
            definir_cooldown(user_id, dias=7)

            # Envia aviso no canal configurado
            if canal:
                await canal.send(
                    f"⚠️ {usuario_mention} perdeu a imunidade de **{personagem} ({origem})** "
                    f"por inatividade (sem roletar há {DIAS_INATIVIDADE}+ dias). "
                    f"Você não poderá adicionar outro personagem imune por 7 dias."
                )
                print(f"✅ Imunidade removida de {usuario_mention}")


# === LOOP DE CHECAGEM DE ATIVIDADE MELHORADO ===
@tasks.loop(hours=3)
async def checar_atividade():
    print("🔄 Executando checar_atividade()...")
    """Analisa o histórico dos últimos 6 dias + última atividade para detectar inatividade real e padrão suspeito."""
    try:
        logs = carregar_json(ARQUIVO_LOG_ATIVIDADE)
        atividades = carregar_atividade()
        historico = carregar_json(ARQUIVO_ATIVIDADE_6DIAS)
        agora = agora_brasil()

        for guild in bot.guilds:
            guild_id = str(guild.id)
            if guild_id not in logs:
                continue

            canal_id = logs[guild_id]
            canal = guild.get_channel(canal_id)
            if not canal:
                continue

            ativos = []
            irregulares = []
            inativos = []

            for user_id, valor in atividades.items():
                if isinstance(valor, dict):
                    ultima_str = valor.get("data")
                else:
                    ultima_str = valor

                if not ultima_str:
                    continue

                try:
                    ultima_atividade = datetime.strptime(ultima_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

                delta = agora - ultima_atividade
                membro = guild.get_member(int(user_id))
                nome = membro.mention if membro else f"Usuário ({user_id})"

                # === Análise com base no histórico ===
                dias_ativos = []
                for dia, registros in historico.items():
                    if isinstance(registros, dict) and user_id in registros:
                        dias_ativos.append(dia)

                dias_ativos = sorted(dias_ativos)
                dias_ativos_count = len(dias_ativos)

                # Calcula espaçamento médio entre dias ativos
                espacamentos = []
                for i in range(1, len(dias_ativos)):
                    d1 = datetime.strptime(dias_ativos[i - 1], "%Y-%m-%d")
                    d2 = datetime.strptime(dias_ativos[i], "%Y-%m-%d")
                    espacamentos.append((d2 - d1).days)

                espacamento_medio = sum(espacamentos) / len(espacamentos) if espacamentos else 0

                # === Classificação ===
                if dias_ativos_count >= 3 and delta.days < 3 and espacamento_medio <= 1.2:
                    ativos.append(f"🟢 {nome} — ativo {dias_ativos_count}/6 dias")
                elif dias_ativos_count >= 3 and espacamento_medio > 1.2:
                    irregulares.append(f"🟡 {nome} — ativo {dias_ativos_count}/6 dias (padrão 1 dia sim, 1 dia não)")
                elif 1 < dias_ativos_count <= 2 and delta.days < 3:
                    ativos.append(f"🟠 {nome} — ativo {dias_ativos_count}/6 dias (baixa frequência)")
                elif delta.days >= 3:
                    inativos.append(f"🔴 {nome} — {delta.days} dias sem roletar")

            # === Se nada pra reportar, pula ===
            if not (ativos or irregulares or inativos):
                continue

            embed = discord.Embed(
                title="📊 Relatório de Atividade da Mudae (Últimos 6 dias)",
                color=discord.Color.blurple(),
            )

            if ativos:
                embed.add_field(
                    name="✅ Jogadores Ativos:",
                    value="\n".join(ativos[:30]) + ("..." if len(ativos) > 30 else ""),
                    inline=False
                )

            if irregulares:
                embed.add_field(
                    name="⚠️ Jogadores com Atividade Irregular:",
                    value="\n".join(irregulares),
                    inline=False
                )

            if inativos:
                embed.add_field(
                    name="❌ Jogadores Inativos (3+ dias):",
                    value="\n".join(inativos),
                    inline=False
                )

            await canal.send(embed=embed)
            print(f"📤 Relatório enviado para {canal.name} em {guild.name}")

    except Exception as e:
        print(f"[ERRO] checar_atividade: {e}")

# === COOLDOWN ===
def esta_em_cooldown(user_id):
    cooldowns = carregar_json(ARQUIVO_COOLDOWN)
    agora = agora_brasil()
    cooldown_data = cooldowns.get(str(user_id))
    
    if not cooldown_data:
        return False
    
    # Verifica se é formato antigo (string) ou novo (dicionário)
    if isinstance(cooldown_data, dict):
        expira_str = cooldown_data.get("expira")
    else:
        expira_str = cooldown_data
    
    if not expira_str:
        # Dado inválido, remove
        del cooldowns[str(user_id)]
        salvar_json(ARQUIVO_COOLDOWN, cooldowns)
        return False
    
    try:
        expira_em = datetime.strptime(expira_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        # Formato inválido, remove
        del cooldowns[str(user_id)]
        salvar_json(ARQUIVO_COOLDOWN, cooldowns)
        return False
    
    if agora >= expira_em:
        # Remove cooldown expirado
        del cooldowns[str(user_id)]
        salvar_json(ARQUIVO_COOLDOWN, cooldowns)
        return False
    
    return True

def definir_cooldown(user_id, dias=3):
    """Define um cooldown para um usuário no formato dicionário."""
    cooldowns = carregar_json(ARQUIVO_COOLDOWN)
    expira_em = agora_brasil() + timedelta(days=dias)
    
    # Formato dicionário com campo de aviso
    cooldowns[str(user_id)] = {
        "expira": expira_em.strftime("%Y-%m-%d %H:%M:%S"),
        "avisado": False
    }
    
    salvar_json(ARQUIVO_COOLDOWN, cooldowns)

# === YOUTUBE ===
CANAL_YOUTUBE = "UCcMSONDJxb18PW5B8cxYdzQ"  # ID do canal
ARQUIVO_YOUTUBE = "youtube.json"  # arquivo para salvar vídeos já notificados

def carregar_youtube():
    if not os.path.exists(ARQUIVO_YOUTUBE):
        return []
    with open(ARQUIVO_YOUTUBE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return []

def salvar_youtube(dados):
    with open(ARQUIVO_YOUTUBE, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

def verificar_novos_videos():
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CANAL_YOUTUBE}"
    r = requests.get(url)
    if r.status_code != 200:
        return []

    tree = ET.fromstring(r.content)
    entries = tree.findall("{http://www.w3.org/2005/Atom}entry")

    antigos = carregar_youtube()
    novos = []

    for e in entries:
        video_id = e.find("{http://www.youtube.com/xml/schemas/2015}videoId").text
        title = e.find("{http://www.w3.org/2005/Atom}title").text
        link = f"https://www.youtube.com/watch?v={video_id}"

        # 🧠 Ignora lives (títulos com "LIVE", "LIVE ON", "AO VIVO", etc)
        if any(palavra in title.lower() for palavra in ["live", "ao vivo", "live on"]):
            continue

        tipo = "Vídeo"
        emoji = "🎬"

        # 📹 Detecta Shorts
        if "shorts" in link or "short" in title.lower():
            tipo = "Short"
            emoji = "📹"

        # 🔒 Ignora vídeos já notificados
        if video_id in antigos:
            continue

        novos.append({
            "id": video_id,
            "title": title,
            "link": link,
            "tipo": tipo,
            "emoji": emoji
        })
        antigos.append(video_id)

    salvar_youtube(antigos[-50:])  # Mantém histórico recente
    return novos

# === COMANDOS ADMIN ===
@bot.tree.command(name="isencao_inatividade", description="Concede ou remove isenção de penalidade por inatividade de um usuário.")
@app_commands.describe(usuario="Usuário que terá a isenção concedida/removida")
@app_commands.checks.has_permissions(administrator=True)
async def isencao_inatividade(interaction: discord.Interaction, usuario: discord.Member):
    """Comando para conceder ou remover isenção de penalidade por inatividade."""
    
    # Atualiza os dados da isenção com quem concediu
    isencao = carregar_isencao()
    user_id_str = str(usuario.id)
    
    if user_id_str in isencao:
        # Remove isenção
        del isencao[user_id_str]
        salvar_isencao(isencao)
        
        embed = discord.Embed(
            title="🛡️ Isenção Removida",
            description=f"A isenção de penalidade por inatividade foi **removida** de {usuario.mention}.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Usuário", value=f"{usuario.display_name} (`{usuario.id}`)", inline=True)
        embed.add_field(name="Ação", value="Removida por " + interaction.user.mention, inline=True)
        embed.set_footer(text="O usuário agora está sujeito à verificação de inatividade normal.")
        
    else:
        # Adiciona isenção
        isencao[user_id_str] = {
            "usuario": usuario.name,
            "display_name": usuario.display_name,
            "data_concessao": agora_brasil().strftime("%Y-%m-%d %H:%M:%S"),
            "concedido_por": interaction.user.name,
            "concedido_por_id": interaction.user.id
        }
        salvar_isencao(isencao)
        
        embed = discord.Embed(
            title="🛡️ Isenção Concedida",
            description=f"A isenção de penalidade por inatividade foi **concedida** a {usuario.mention}.",
            color=discord.Color.green()
        )
        embed.add_field(name="Usuário", value=f"{usuario.display_name} (`{usuario.id}`)", inline=True)
        embed.add_field(name="Concedido por", value=interaction.user.mention, inline=True)
        embed.add_field(name="Data", value=agora_brasil().strftime("%d/%m/%Y %H:%M"), inline=True)
        embed.set_footer(text="O usuário não perderá imunidade por inatividade.")
    
    # 🔒 MENSAGEM PRIVADA (somente o administrador vê)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="lista_isencao", description="Lista todos os usuários com isenção de inatividade.")
@app_commands.checks.has_permissions(administrator=True)
async def lista_isencao(interaction: discord.Interaction):
    """Lista todos os usuários que possuem isenção de penalidade por inatividade."""
    
    isencao = carregar_isencao()
    
    if not isencao:
        embed = discord.Embed(
            title="🛡️ Lista de Isenções",
            description="Nenhum usuário possui isenção de inatividade no momento.",
            color=discord.Color.blue()
        )
        # 🔒 MENSAGEM PRIVADA
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🛡️ Lista de Isenções de Inatividade",
        color=discord.Color.gold()
    )
    
    for user_id, dados in isencao.items():
        usuario = interaction.guild.get_member(int(user_id))
        if usuario:
            mention = usuario.mention
            nome = usuario.display_name
        else:
            mention = f"`{user_id}`"
            nome = dados.get('usuario', 'Usuário não encontrado')
        
        concedido_por = dados.get('concedido_por', 'Sistema')
        data_concessao = dados.get('data_concessao', 'Data desconhecida')
        
        embed.add_field(
            name=f"👤 {nome}",
            value=f"**ID:** {user_id}\n**Usuário:** {mention}\n**Concedido por:** {concedido_por}\n**Data:** {data_concessao}",
            inline=False
        )
    
    embed.set_footer(text=f"Total de {len(isencao)} usuário(s) com isenção")
    # 🔒 MENSAGEM PRIVADA
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="zerar_series", description="Zera todos os dados do series.json (apenas administradores autorizados).")
async def zerar_series(interaction: discord.Interaction):
    # IDs autorizados
    IDS_AUTORIZADOS = [289801244653125634, 292756862020091906]

    # Verifica se o usuário pode usar
    if interaction.user.id not in IDS_AUTORIZADOS:
        await interaction.response.send_message("❌ Você não tem permissão para usar este comando.", ephemeral=True)
        return

    try:
        # Zera o conteúdo
        series_vazio = {}
        salvar_json("series.json", series_vazio)
        await interaction.response.send_message("🧹 O arquivo **series.json** foi zerado com sucesso!", ephemeral=True)
        print(f"✅ {interaction.user.name} ({interaction.user.id}) zerou o series.json.")

    except Exception as e:
        await interaction.response.send_message(f"⚠️ Erro ao zerar o arquivo: `{e}`", ephemeral=True)
        print(f"[ERRO] ao zerar series.json: {e}")

@bot.tree.command(name="add_serie", description="Adiciona uma nova série à lista de séries.")
async def add_serie(interaction: discord.Interaction, nome_serie: str):
    ADMIN_ID = 289801244653125634  # ID autorizado extra

    # Verifica permissão (admin ou ID específico)
    if not interaction.user.guild_permissions.administrator and interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("🚫 Você não tem permissão para usar este comando.", ephemeral=True)
        return

    nome_serie = nome_serie.lower().strip()
    series = carregar_json("series.json")

    if nome_serie in series:
        await interaction.response.send_message(
            f" A série **{nome_serie.title()}** já existe na lista.", ephemeral=True
        )
        return

    series[nome_serie] = {}
    salvar_json("series.json", series)
    await interaction.response.send_message(
        f" Série **{nome_serie.title()}** adicionada com sucesso!", ephemeral=True
    )

@bot.tree.command(name="set_log", description="Define o canal de log de atividade (apenas administradores).")
@app_commands.checks.has_permissions(administrator=True)
async def set_log(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    canal = interaction.channel  # ✅ define o canal atual onde o comando foi usado
    logs = carregar_json(ARQUIVO_LOG_ATIVIDADE)
    logs[guild_id] = canal.id
    salvar_json(ARQUIVO_LOG_ATIVIDADE, logs)
    await interaction.response.send_message(f"✅ Canal de log definido para {canal.mention}.", ephemeral=True)

@bot.tree.command(name="set_canal_imune", description="Define o canal onde os comandos de imunidade funcionarão.")
@app_commands.checks.has_permissions(administrator=True)
async def set_canal_imune(interaction: discord.Interaction):
    config = carregar_json(ARQUIVO_CONFIG)
    config[str(interaction.guild.id)] = interaction.channel.id
    salvar_json(ARQUIVO_CONFIG, config)
    await interaction.response.send_message(f"✅ Canal de imunidade definido: {interaction.channel.mention}")

@bot.tree.command(name="set_canal_youtube", description="Define o canal onde serão enviadas notificações do YouTube.")
@app_commands.checks.has_permissions(administrator=True)
async def set_canal_youtube(interaction: discord.Interaction):
    config = carregar_json(ARQUIVO_CONFIG)
    guild_id = str(interaction.guild.id)

    # Cria a chave "youtube" se não existir
    if "youtube" not in config:
        config["youtube"] = {}
    config["youtube"][guild_id] = interaction.channel.id
    salvar_json(ARQUIVO_CONFIG, config)

    await interaction.response.send_message(
        f"✅ Canal do YouTube definido: {interaction.channel.mention}"
    )

@bot.tree.command(name="set_canal_apply", description="Define o canal onde serão enviadas notificações de aplicações para Sala Privada.")
@app_commands.checks.has_permissions(administrator=True)
async def set_canal_apply(interaction: discord.Interaction):
    """Define o canal para notificações de aplicações de Sala Privada."""
    config = s2_load(ARQ_S2_CONFIG)
    guild_id = str(interaction.guild.id)
    
    if "apply_channel" not in config:
        config["apply_channel"] = {}
    
    config["apply_channel"][guild_id] = interaction.channel.id
    s2_save(ARQ_S2_CONFIG, config)
    
    await interaction.response.send_message(
        f"✅ Canal de notificações de aplicações definido: {interaction.channel.mention}"
    )

@bot.tree.command(name="set_categoria_salas", description="Define a categoria onde serão criadas as salas privadas.")
@app_commands.checks.has_permissions(administrator=True)
async def set_categoria_salas(interaction: discord.Interaction, categoria: discord.CategoryChannel):
    """Define a categoria para criação de salas privadas."""
    global S2_CATEGORIA_SALAS_ID
    S2_CATEGORIA_SALAS_ID = categoria.id
    
    config = s2_load(ARQ_S2_CONFIG)
    guild_id = str(interaction.guild.id)
    
    if "categoria_salas" not in config:
        config["categoria_salas"] = {}
    
    config["categoria_salas"][guild_id] = categoria.id
    s2_save(ARQ_S2_CONFIG, config)
    
    await interaction.response.send_message(
        f"✅ Categoria para salas privadas definida: {categoria.mention}"
    )

@bot.tree.command(name="remover_canal_youtube", description="Remove o canal configurado para notificações do YouTube.")
@app_commands.checks.has_permissions(administrator=True)
async def remover_canal_youtube(interaction: discord.Interaction):
    config = carregar_json(ARQUIVO_CONFIG)
    guild_id = str(interaction.guild.id)

    if "youtube" in config and guild_id in config["youtube"]:
        del config["youtube"][guild_id]
        # Se o objeto youtube ficar vazio, podemos remover a chave para manter o JSON limpo
        if not config["youtube"]:
            del config["youtube"]
        salvar_json(ARQUIVO_CONFIG, config)
        await interaction.response.send_message("🗑️ Canal de notificações do YouTube removido com sucesso.")
    else:
        await interaction.response.send_message("⚙️ Nenhum canal do YouTube configurado para este servidor.")

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

@bot.tree.command(name="imune_remover", description="Remove manualmente o personagem imune de um jogador (sem cooldown).")
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

@bot.tree.command(name="resetar_cooldown", description="Zera o cooldown de um usuário específico.")
@app_commands.describe(usuario="Usuário que terá o cooldown resetado")
@app_commands.checks.has_permissions(administrator=True)
async def resetar_cooldown(interaction: discord.Interaction, usuario: discord.Member):
    cooldowns = carregar_json(ARQUIVO_COOLDOWN)
    user_id = str(usuario.id)

    if user_id not in cooldowns:
        await interaction.response.send_message(
            f"⚙️ {usuario.mention} não possui cooldown ativo.",
            ephemeral=True
        )
        return

    # Remove cooldown
    del cooldowns[user_id]
    salvar_json(ARQUIVO_COOLDOWN, cooldowns)

    await interaction.response.send_message(
        f"✅ Cooldown de {usuario.mention} foi resetado com sucesso!"
    )

# === COMANDOS PADRÃO ===
# === /rank_serie ===
@bot.tree.command(name="rank_serie", description="Mostra o ranking de quem tem mais personagens de uma série/jogo.")
@app_commands.describe(nome="Nome da série ou jogo que deseja ver o ranking")
async def rank_serie(interaction: discord.Interaction, nome: str):
    await interaction.response.defer(thinking=True)

    series = carregar_json("series.json")
    nome = nome.lower().strip()

    if nome not in series:
        await interaction.followup.send(
            f"❌ A série **{nome.title()}** não está cadastrada. Use `/add_serie {nome.title()}` primeiro.",
            ephemeral=True
        )
        return

    dados = series[nome]
    if not dados:
        await interaction.followup.send(
            f"⚠️ Nenhum personagem registrado ainda para **{nome.title()}**.",
            ephemeral=True
        )
        return

    # === Monta ranking com base no número de personagens ===
    ranking = sorted(dados.items(), key=lambda x: len(x[1]), reverse=True)

    linhas = []
    for i, (usuario, personagens) in enumerate(ranking[:10], 1):
        linhas.append(f"**#{i}** — {usuario}: {len(personagens)} personagem(ns)")

    embed = discord.Embed(
        title=f"🏆 Ranking — {nome.title()}",
        description="\n".join(linhas),
        color=discord.Color.gold()
    )

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="atividade_status", description="Exibe o status de atividade dos usuários (somente IDs autorizados).")
async def atividade_status(interaction: discord.Interaction, pagina: int = 1):
    IDS_AUTORIZADOS = [292756862020091906, 289801244653125634]

    # --- Verifica permissão ---
    if interaction.user.id not in IDS_AUTORIZADOS:
        await interaction.response.send_message("🚫 Você não tem permissão para usar este comando.", ephemeral=True)
        return

    # --- Verifica canal configurado ---
    logs = carregar_json(ARQUIVO_LOG_ATIVIDADE)
    canal_log_id = logs.get(str(interaction.guild.id))

    if canal_log_id is None or interaction.channel.id != canal_log_id:
        await interaction.response.send_message("⚠️ Este comando só pode ser usado no canal configurado com `/set_log`.", ephemeral=True)
        return

    # === Função auxiliar para gerar embed ===
    def gerar_embed(pagina_atual: int):
        atividades = carregar_atividade()
        if not atividades:
            return discord.Embed(description="📭 Nenhum registro de atividade encontrado.", color=discord.Color.red())

        agora = agora_brasil()
        ativos, inativos = [], []

        for user_id, info in atividades.items():
            if isinstance(info, dict):
                ultima_str = info.get("data")
                nome_usuario = info.get("usuario", "Desconhecido")
            else:
                ultima_str = info
                nome_usuario = "Desconhecido"

            try:
                ultima_atividade = datetime.strptime(ultima_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            delta = agora - ultima_atividade
            if delta < timedelta(days=3):
                ativos.append(("🟢 Ativo", user_id, nome_usuario, ultima_str))
            else:
                inativos.append(("🔴 Inativo", user_id, nome_usuario, ultima_str))

        todos = ativos + inativos
        total_paginas = max(1, math.ceil(len(todos) / 10))
        pagina_atual = max(1, min(pagina_atual, total_paginas))
        inicio, fim = (pagina_atual - 1) * 10, pagina_atual * 10
        lista_pagina = todos[inicio:fim]

        embed = discord.Embed(
            title=f"📊 Status de Atividade — Página {pagina_atual}/{total_paginas}",
            color=discord.Color.blurple()
        )
        if not lista_pagina:
            embed.description = "Nenhum usuário nesta página."
        else:
            for status, user_id, nome_usuario, tempo in lista_pagina:
                membro = interaction.guild.get_member(int(user_id))
                nome_display = membro.display_name if membro else nome_usuario
                embed.add_field(
                    name=f"{status} — {nome_display}",
                    value=f"Última atividade: `{tempo}`",
                    inline=False
                )
        return embed, total_paginas

    # === VIEW COM BOTÕES ===
    class AtividadeView(View):
        def __init__(self, pagina_atual):
            super().__init__(timeout=120)
            self.pagina = pagina_atual
            self.total_paginas = gerar_embed(self.pagina)[1]

        async def atualizar(self, interaction_btn):
            novo_embed, _ = gerar_embed(self.pagina)
            await interaction_btn.response.edit_message(embed=novo_embed, view=self)

        @discord.ui.button(label="⬅️", style=discord.ButtonStyle.gray)
        async def anterior(self, interaction_btn: discord.Interaction, button: Button):
            if self.pagina > 1:
                self.pagina -= 1
                await self.atualizar(interaction_btn)

        @discord.ui.button(label="➡️", style=discord.ButtonStyle.gray)
        async def proximo(self, interaction_btn: discord.Interaction, button: Button):
            if self.pagina < self.total_paginas:
                self.pagina += 1
                await self.atualizar(interaction_btn)

        @discord.ui.button(label="🔄 Atualizar", style=discord.ButtonStyle.green)
        async def atualizar_lista(self, interaction_btn: discord.Interaction, button: Button):
            # Recarrega tudo do JSON, mas mantém a página
            await self.atualizar(interaction_btn)

    # === Envia a primeira página ===
    embed, total_paginas = gerar_embed(pagina)
    view = AtividadeView(pagina)
    await interaction.response.send_message(embed=embed, view=view)

# === COMANDOS DE COOLDOWN PERSONALIZADO ===
@bot.tree.command(name="remover_cooldown", description="Remove o cooldown de um usuário.")
@app_commands.describe(usuario="Usuário que terá o cooldown removido")
@app_commands.checks.has_permissions(administrator=True)
async def remover_cooldown(interaction: discord.Interaction, usuario: discord.Member):
    """Remove o cooldown de um usuário específico."""
    cooldowns = carregar_json(ARQUIVO_COOLDOWN)
    user_id_str = str(usuario.id)
    
    if user_id_str not in cooldowns:
        await interaction.response.send_message(
            f"⚙️ {usuario.mention} não possui cooldown ativo.",
            ephemeral=True
        )
        return
    
    # Remove o cooldown
    del cooldowns[user_id_str]
    salvar_json(ARQUIVO_COOLDOWN, cooldowns)
    
    embed = discord.Embed(
        title="⏳ Cooldown Removido",
        description=f"O cooldown de {usuario.mention} foi removido com sucesso!",
        color=discord.Color.green()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="aplicar_cooldown", description="Aplica um cooldown personalizado a um usuário.")
@app_commands.describe(
    usuario="Usuário que receberá o cooldown",
    dias="Número de dias de cooldown (padrão: 3)"
)
@app_commands.checks.has_permissions(administrator=True)
async def aplicar_cooldown(interaction: discord.Interaction, usuario: discord.Member, dias: int = 3):
    """Aplica um cooldown personalizado a um usuário."""
    
    # Validação do número de dias
    if dias < 1:
        await interaction.response.send_message(
            "❌ O número de dias deve ser pelo menos 1.",
            ephemeral=True
        )
        return
    
    if dias > 365:  # Limite máximo de 365 dias
        await interaction.response.send_message(
            "❌ O número máximo de dias é 365.",
            ephemeral=True
        )
        return
    
    # ✅ CORREÇÃO: Use str(usuario.id) em vez de user_id
    definir_cooldown(str(usuario.id), dias=dias)
    
    # Calcula a data de expiração
    expira_em = agora_brasil() + timedelta(days=dias)
    
    embed = discord.Embed(
        title="⏳ Cooldown Aplicado",
        description=f"Um cooldown de **{dias} dia(s)** foi aplicado a {usuario.mention}.",
        color=discord.Color.orange()
    )
    embed.add_field(name="Usuário", value=f"{usuario.display_name} (`{usuario.id}`)", inline=True)
    embed.add_field(name="Duração", value=f"{dias} dia(s)", inline=True)
    embed.add_field(name="Expira em", value=expira_em.strftime("%d/%m/%Y %H:%M"), inline=True)
    embed.add_field(name="Aplicado por", value=interaction.user.mention, inline=False)
    
    # 🔒 MENSAGEM PRIVADA AO ADMIN
    await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # 🔔 NOTIFICAÇÃO PÚBLICA (opcional)
    config = carregar_json(ARQUIVO_CONFIG)
    guild_id = str(interaction.guild.id)
    canal_id = config.get(guild_id)
    
    if canal_id:
        canal = interaction.guild.get_channel(canal_id)
        if canal:
            embed_publico = discord.Embed(
                title="⏳ Cooldown Aplicado",
                description=f"{usuario.mention} recebeu um cooldown de **{dias} dia(s)**.",
                color=discord.Color.orange()
            )
            embed_publico.add_field(name="Expira em", value=expira_em.strftime("%d/%m/%Y %H:%M"), inline=True)
            await canal.send(embed=embed_publico)

@bot.tree.command(name="testar_mudae", description="Testa a leitura da última embed enviada pela Mudae no canal.")
async def testar_mudae_embed(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=False)

    # Busca as últimas 10 mensagens do canal
    async for msg in interaction.channel.history(limit=10):
        if msg.author.bot and msg.author.name.lower() == "mudae" and msg.embeds:
            embed = msg.embeds[0]
            titulo = embed.title or "(sem título)"
            descricao = embed.description or "(sem descrição)"
            autor = embed.author.name if embed.author and embed.author.name else "(sem autor)"
            footer = embed.footer.text if embed.footer and embed.footer.text else "(sem footer)"

            await interaction.followup.send(
                f"📦 **Embed da Mudae detectada!**\n"
                f"**Autor:** {autor}\n"
                f"**Título:** {titulo}\n"
                f"**Descrição:** {descricao[:900]}\n"
                f"**Footer:** {footer}",
                ephemeral=False
            )
            return

    await interaction.followup.send("⚠️ Nenhuma embed recente da Mudae encontrada neste canal.", ephemeral=True)

@bot.tree.command(name="imune_add", description="Adiciona um personagem imune (1 por jogador).")
@canal_imunidade()
@app_commands.describe(nome_personagem="Nome do personagem", jogo_anime="Nome do jogo/anime")
async def imune_add(interaction: discord.Interaction, nome_personagem: str, jogo_anime: str):
    imunes = carregar_json(ARQUIVO_IMUNES)
    guild_id, user_id = str(interaction.guild.id), str(interaction.user.id)
    imunes.setdefault(guild_id, {})

    if esta_em_cooldown(user_id):
        await interaction.response.send_message(
            f"⏳ {interaction.user.mention}, você está em cooldown. Aguarde o cooldown acabar.",
            ephemeral=True
        )
        return

    if user_id in imunes[guild_id]:
        await interaction.response.send_message(
            "⚠️ Você já possui um personagem imune.",
            ephemeral=True
        )
        return

    # Normaliza os textos para comparação
    nome_normalizado = normalizar_texto(nome_personagem)
    origem_normalizada = normalizar_texto(jogo_anime)

    # 🔒 Impede nomes iguais com mesma origem (ignorando acentos e maiúsculas)
    for uid, d in imunes[guild_id].items():
        if (normalizar_texto(d["personagem"]) == nome_normalizado and
            normalizar_texto(d["origem"]) == origem_normalizada):
            await interaction.response.send_message(
                f"⚠️ O personagem **{nome_personagem} ({jogo_anime})** já está imune por {d['usuario']}.",
                ephemeral=True
            )
            return

    # ✅ Adiciona o personagem normalmente
    imunes[guild_id][user_id] = {
        "usuario": interaction.user.name,
        "personagem": nome_personagem,
        "origem": jogo_anime,
        "data": agora_brasil().strftime("%Y-%m-%d %H:%M:%S")
    }

    salvar_json(ARQUIVO_IMUNES, imunes)
    await interaction.response.send_message(
        f"🔒 {interaction.user.mention} definiu **{nome_personagem} ({jogo_anime})** como imune!"
    )

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
    
    # Seção de imunidade
    if guild_id in imunes and user_id in imunes[guild_id]:
        p = imunes[guild_id][user_id]
        embed.add_field(name="🔒 Personagem Imune", value=f"**{p['personagem']}** — {p['origem']}\n📅 Desde: `{p['data']}`", inline=False)
    else:
        embed.add_field(name="🔒 Personagem Imune", value="Nenhum ativo.", inline=False)
    
    # Seção de cooldown (corrigida para lidar com ambos os formatos)
    if user_id in cooldowns:
        cooldown_data = cooldowns[user_id]
        
        # 🔹 Verifica se é formato novo (dicionário) ou antigo (string)
        if isinstance(cooldown_data, dict):
            expira_str = cooldown_data.get("expira")
        else:
            expira_str = cooldown_data
        
        if expira_str:
            try:
                expira = datetime.strptime(expira_str, "%Y-%m-%d %H:%M:%S")
                agora = agora_brasil()
                
                if expira > agora:
                    restante = expira - agora
                    dias, resto = divmod(restante.total_seconds(), 86400)
                    horas, resto = divmod(resto, 3600)
                    minutos = (resto % 3600) // 60
                    
                    embed.add_field(name="⏳ Cooldown", 
                                  value=f"Em andamento — {int(dias)}d {int(horas)}h {int(minutos)}min restantes.\n⏰ Expira: {expira.strftime('%d/%m/%Y %H:%M')}", 
                                  inline=False)
                else:
                    embed.add_field(name="⏳ Cooldown", value="Nenhum cooldown ativo.", inline=False)
            except (ValueError, TypeError) as e:
                embed.add_field(name="⏳ Cooldown", value=f"Erro ao ler cooldown: {e}", inline=False)
    else:
        embed.add_field(name="⏳ Cooldown", value="Nenhum cooldown ativo.", inline=False)
    
    await interaction.response.send_message(embed=embed)

# === FUNÇÃO AUXILIAR ===
async def obter_ultima_embed_mudae(channel: discord.TextChannel):
    """Retorna (autor, footer, descricao) da última embed da Mudae no canal."""
    async for msg in channel.history(limit=10):
        if msg.author.bot and msg.author.name.lower() == "mudae" and msg.embeds:
            embed = msg.embeds[0]
            autor = embed.author.name if embed.author and embed.author.name else None
            footer = embed.footer.text if embed.footer and embed.footer.text else None
            descricao = embed.description or ""
            return autor, footer, descricao
    return None, None, None

# =============================
# COMANDOS SEASON 2
# =============================

# ---------- APPLY ----------
@bot.tree.command(name="sala_privada_aplicar", description="Aplique para ter acesso a sala privada.")
async def sala_privada_apply(interaction: discord.Interaction):
    players = s2_load(ARQ_S2_PLAYERS)
    uid = str(interaction.user.id)

    # Verifica se já aplicou
    if uid in players:
        await interaction.response.send_message(
            "⚠️ Você já tem uma aplicação pendente ou já foi aprovado.", ephemeral=True
        )
        return

    players[uid] = {
        "status": "pendente",
        "rodadas": 0,
        "bonus_evento": 0,
        "ultimo_reset": None,
        "sala_ativa": False
    }
    s2_save(ARQ_S2_PLAYERS, players)
    
    # Envia notificação no canal configurado
    config = s2_load(ARQ_S2_CONFIG)
    guild_id = str(interaction.guild.id)
    
    if "apply_channel" in config and guild_id in config["apply_channel"]:
        canal_id = config["apply_channel"][guild_id]
        canal = interaction.guild.get_channel(canal_id)
        if canal:
            embed = discord.Embed(
                title="📨 Nova Aplicação para Sala Privada",
                description=f"**Usuário:** {interaction.user.mention}\n**ID:** {interaction.user.id}\n**Nome:** {interaction.user.display_name}",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Use /sala_privada_aprovar para aprovar")
            await canal.send(embed=embed)
    
    await interaction.response.send_message(
        "📨 Aplicação enviada para a Sala Privada. Aguarde a aprovação dos administradores.", ephemeral=True
    )

# ---------- APROVAR ----------
@bot.tree.command(name="sala_privada_aprovar", description="Aprova aplicação de um usuário.")
@app_commands.checks.has_permissions(administrator=True)
async def sala_privada_aprovar(
    interaction: discord.Interaction,
    usuario: discord.Member
):
    players = s2_load(ARQ_S2_PLAYERS)
    uid = str(usuario.id)

    if uid not in players:
        await interaction.response.send_message("❌ Usuário não aplicou.", ephemeral=True)
        return

    players[uid].update({
        "status": "aprovado",
        "rodadas": 3,
        "ultimo_reset": agora_brasil().strftime("%Y-%m-%d"),
        "sala_ativa": False
    })
    s2_save(ARQ_S2_PLAYERS, players)
    
    # Notifica o usuário
    try:
        embed = discord.Embed(
            title="✅ Aplicação Aprovada",
            description="Sua aplicação para Sala Privada foi aprovada!",
            color=discord.Color.green()
        )
        embed.add_field(name="Rodadas diárias", value="3 rodadas por dia", inline=True)
        embed.add_field(name="Status", value="Aprovado", inline=True)
        embed.add_field(name="Comando para abrir sala", value="`/sala_privada_abrir`", inline=False)
        await usuario.send(embed=embed)
    except:
        pass
    
    await interaction.response.send_message(
        f"✅ {usuario.mention} aprovado na Sala Privada."
    )

# ---------- ABRIR SALA (CRIANDO SALA INDIVIDUAL) ----------
@bot.tree.command(name="sala_privada_abrir", description="Abre sua sala privada por 10 minutos.")
async def sala_privada_abrir(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    guild = interaction.guild
    agora = agora_brasil()

    players = s2_load(ARQ_S2_PLAYERS)
    salas = s2_load_salas()
    config = s2_load(ARQ_S2_CONFIG)

    p = players.get(uid)
    if not p or p["status"] != "aprovado" or p["rodadas"] <= 0:
        await interaction.response.send_message("⛔ Você não pode abrir uma sala agora.", ephemeral=True)
        return

    # Fecha sala antiga (se existir)
    if uid in salas:
        await fechar_sala_automaticamente(uid, guild)

    categoria = guild.get_channel(config["categoria_salas"][str(guild.id)])

    # === CRIA CARGO ===
    cargo = await guild.create_role(
        name=f"sala-{interaction.user.display_name}-{uid[:5]}",
        reason="Sala privada"
    )

    # === CRIA CANAL ===
    canal = await guild.create_text_channel(
        name=f"🔐-privada-{interaction.user.display_name}".lower()[:90],
        category=categoria,
        overwrites={
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            cargo: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True)
        }
    )

    await interaction.user.add_roles(cargo)

    expira_em = agora + timedelta(seconds=S2_TEMPO_SALA)

    # === SALVA NO GITHUB ===
    salas[uid] = {
        "guild_id": str(guild.id),
        "cargo_id": cargo.id,
        "canal_id": canal.id,
        "aberta_em": agora.strftime("%Y-%m-%d %H:%M:%S"),
        "expira_em": expira_em.strftime("%Y-%m-%d %H:%M:%S"),
        "usuario_nome": interaction.user.display_name
    }
    s2_save_salas(salas)

    p["rodadas"] -= 1
    p["sala_ativa"] = True
    s2_save(ARQ_S2_PLAYERS, players)

    # === DM ===
    embed_dm = discord.Embed(
        title="🔓 Sala Privada Aberta",
        color=discord.Color.green()
    )
    embed_dm.add_field(name="Canal", value=canal.mention, inline=False)
    embed_dm.add_field(name="⏳ Duração", value="10 minutos", inline=True)
    embed_dm.add_field(name="⏰ Expira em", value=expira_em.strftime("%H:%M:%S"), inline=True)

    await enviar_dm(interaction.user, embed_dm)

    await interaction.response.send_message(
        f"🔓 Sala aberta! Expira às `{expira_em.strftime('%H:%M:%S')}`",
        ephemeral=True
    )

# ---------- FECHAR SALA MANUALMENTE ----------
@bot.tree.command(name="sala_privada_fechar", description="Fecha sua sala privada manualmente.")
async def sala_privada_fechar(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    
    if uid not in S2_SALAS_ATIVAS:
        await interaction.response.send_message(
            "⚠️ Você não tem uma sala ativa no momento.", ephemeral=True
        )
        return
    
    sala_info = S2_SALAS_ATIVAS[uid]
    cargo = sala_info.get("cargo")
    canal = sala_info.get("canal")
    
    if cargo and cargo in interaction.user.roles:
        await interaction.user.remove_roles(cargo)
        
        # Remove do controle
        del S2_SALAS_ATIVAS[uid]
        
        # Atualiza status
        players = s2_load(ARQ_S2_PLAYERS)
        if uid in players:
            players[uid]["sala_ativa"] = False
            s2_save(ARQ_S2_PLAYERS, players)
        
        embed = discord.Embed(
            title="🔒 Sala Privada Fechada",
            description="Sua sala privada foi fechada manualmente.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Status", value="❌ Acesso removido", inline=True)
        if canal:
            embed.add_field(name="Canal", value=f"{canal.mention}", inline=True)
        embed.set_footer(text=f"Horário Brasil: {agora_brasil().strftime('%H:%M:%S')}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(
            "❌ Não foi possível fechar a sala. Contate um administrador.", ephemeral=True
        )

# ---------- RESET DIÁRIO ----------
@tasks.loop(minutes=1)
async def s2_reset():
    agora = agora_brasil().strftime("%H:%M")
    if agora != "23:45":
        return

    players = s2_load(ARQ_S2_PLAYERS)
    hoje = agora_brasil().strftime("%Y-%m-%d")

    for p in players.values():
        if p["status"] == "aprovado" and p["ultimo_reset"] != hoje:
            p["rodadas"] = 3
            p["ultimo_reset"] = hoje
            p["sala_ativa"] = False

    s2_save(ARQ_S2_PLAYERS, players)

# ---------- VERIFICAR SALAS EXPIRADAS ----------
@tasks.loop(minutes=1)
async def verificar_salas_expiradas():
    agora = agora_brasil()
    salas = s2_load_salas()

    for uid, info in list(salas.items()):
        expira = datetime.strptime(info["expira_em"], "%Y-%m-%d %H:%M:%S")
        if agora >= expira:
            guild = bot.get_guild(int(info["guild_id"]))
            if guild:
                await fechar_sala_automaticamente(uid, guild)


# ---------- STATUS SALA ----------
@bot.tree.command(name="sala_status", description="Mostra seu status atual da Sala Privada.")
async def sala_status(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    players = s2_load(ARQ_S2_PLAYERS)
    agora = agora_brasil()
    
    p = players.get(uid)
    if not p:
        embed = discord.Embed(
            title="📊 Status da Sala Privada",
            description="Você não tem uma aplicação para Sala Privada.",
            color=discord.Color.red()
        )
        embed.add_field(name="Ação necessária", value="Use `/sala_privada_aplicar` para aplicar.", inline=False)
        embed.set_footer(text=f"Horário Brasil: {agora.strftime('%H:%M:%S')}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    embed = discord.Embed(
        title="📊 Status da Sala Privada",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Horário Brasil: {agora.strftime('%H:%M:%S')}")
    
    # Status
    status_emoji = "🟢" if p["status"] == "aprovado" else "🟡" if p["status"] == "pendente" else "🔴"
    embed.add_field(name="Status", value=f"{status_emoji} {p['status'].title()}", inline=True)
    
    # Rodadas
    embed.add_field(name="Rodadas hoje", value=f"{p['rodadas']}/3", inline=True)
    
    # Sala ativa
    sala_ativa = "Sim" if p["sala_ativa"] else "Não"
    embed.add_field(name="Sala ativa", value=sala_ativa, inline=True)
    
    # Último reset
    ultimo_reset = p["ultimo_reset"] if p["ultimo_reset"] else "Nunca"
    embed.add_field(name="Último reset", value=ultimo_reset, inline=True)
    
    # Informações adicionais
    if p["status"] == "pendente":
        embed.description = "Sua aplicação está pendente de aprovação."
    elif p["status"] == "aprovado":
        if p["rodadas"] > 0 and not p["sala_ativa"]:
            embed.description = "Você pode abrir uma sala com `/sala_privada_abrir`"
        elif p["sala_ativa"]:
            # Mostra informação da sala ativa
            if uid in S2_SALAS_ATIVAS:
                sala_info = S2_SALAS_ATIVAS[uid]
                canal = sala_info.get("canal")
                if canal:
                    embed.add_field(name="Sala atual", value=f"{canal.mention}", inline=False)
                    
                    # Calcula tempo restante usando horário de Brasília
                    tempo_passado = (agora - sala_info["aberta_em"]).total_seconds()
                    tempo_restante = max(0, S2_TEMPO_SALA - tempo_passado)
                    minutos = int(tempo_restante // 60)
                    segundos = int(tempo_restante % 60)
                    
                    # Horário de expiração
                    if "expira_em" in sala_info:
                        expira_str = sala_info["expira_em"].strftime("%H:%M:%S")
                    else:
                        expira_em = sala_info["aberta_em"] + timedelta(seconds=S2_TEMPO_SALA)
                        expira_str = expira_em.strftime("%H:%M:%S")
                    
                    embed.add_field(name="⏰ Tempo restante", value=f"{minutos}m {segundos}s", inline=True)
                    embed.add_field(name="⏳ Expira em (BR)", value=expira_str, inline=True)
            embed.description = "Você tem uma sala ativa no momento."
        else:
            embed.description = "Você não tem rodadas disponíveis hoje."
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------- DEBUG SALAS ----------
@bot.tree.command(name="debug_salas", description="Debug: mostra informações das salas ativas (apenas administradores).")
@app_commands.checks.has_permissions(administrator=True)
async def debug_salas(interaction: discord.Interaction):
    """Comando de debug para verificar salas ativas."""
    agora = agora_brasil()
    
    if not S2_SALAS_ATIVAS:
        await interaction.response.send_message("📭 Nenhuma sala ativa no momento.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🔍 Debug - Salas Ativas",
        description=f"Total: {len(S2_SALAS_ATIVAS)} sala(s)\nHorário Brasil: {agora.strftime('%H:%M:%S')}",
        color=discord.Color.orange()
    )
    
    for uid, info in S2_SALAS_ATIVAS.items():
        usuario = interaction.guild.get_member(int(uid))
        nome_usuario = usuario.display_name if usuario else "Desconhecido"
        
        if "aberta_em" in info:
            tempo_passado = (agora - info["aberta_em"]).total_seconds()
            minutos_passados = int(tempo_passado // 60)
            segundos_passados = int(tempo_passado % 60)
            
            tempo_restante = max(0, S2_TEMPO_SALA - tempo_passado)
            minutos_restantes = int(tempo_restante // 60)
            segundos_restantes = int(tempo_restante % 60)
            
            # Horário de expiração
            if "expira_em" in info:
                expira_str = info["expira_em"].strftime("%H:%M:%S")
            else:
                expira_em = info["aberta_em"] + timedelta(seconds=S2_TEMPO_SALA)
                expira_str = expira_em.strftime("%H:%M:%S")
            
            status = f"✅ Ativa ({minutos_restantes}m {segundos_restantes}s restantes)" if tempo_restante > 0 else f"⚠️ Expirada há {abs(minutos_restantes)}m"
            detalhes = f"Abertura: {info['aberta_em'].strftime('%H:%M:%S')}\nExpira: {expira_str}"
        else:
            status = "❌ Sem horário de abertura"
            detalhes = "Informação incompleta"
        
        cargo_nome = info.get("cargo", "Cargo não encontrado").name if hasattr(info.get("cargo"), 'name') else "N/A"
        canal_nome = info.get("canal", "Canal não encontrado").name if hasattr(info.get("canal"), 'name') else "N/A"
        
        embed.add_field(
            name=f"👤 {nome_usuario}",
            value=f"**ID:** {uid}\n**Status:** {status}\n**Cargo:** {cargo_nome}\n**Canal:** {canal_nome}\n**Detalhes:** {detalhes}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# === EVENTOS === 
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        # Registro automático da Mudae em salas privadas
        if message.author.id == MUDAE_BOT_ID and message.embeds:
            # Verifica se a mensagem está em uma sala privada
            for uid, info in S2_SALAS_ATIVAS.items():
                if info.get("canal") and message.channel.id == info["canal"].id:
                    personagem = s2_extrair_personagem_do_embed(message.embeds[0])
                    if personagem:
                        tipo = s2_definir_tipo_personagem(message.embeds[0])
                        s2_registro_automatico(uid, personagem, tipo)
                    break
        
        return

    if message.content.lower().startswith("$imao "):
        canais_permitidos = [1430256427967975526]
        if message.channel.id not in canais_permitidos:
            return

        partes = message.content.split(" ", 1)
        if len(partes) < 2:
            return
        nome_serie = partes[1].strip().lower()

        series = carregar_json("series.json")
        if nome_serie not in series:
            series[nome_serie] = {}

        await message.channel.send(f"🔍 Iniciando coleta da série `{nome_serie}`... aguardando páginas da Mudae.")

        paginas_coletadas = 0
        personagens_total = 0
        ultima_mensagem_mudae = None

        def eh_mudae_edit(before, after):
            return (
                after.author.bot
                and after.author.name.lower() == "mudae"
                and after.embeds
                and after.channel == message.channel
            )

        try:
            # Primeiro tenta achar mensagem da Mudae já existente
            async for msg in message.channel.history(limit=10):
                if msg.author.bot and msg.author.name.lower() == "mudae" and msg.embeds:
                    ultima_mensagem_mudae = msg
                    print(f"[DEBUG] Mensagem da Mudae encontrada no histórico ({msg.id})")
                    break

            # Se não achou, espera uma nova mensagem
            if not ultima_mensagem_mudae:
                ultima_mensagem_mudae = await bot.wait_for(
                    "message",
                    check=lambda m: m.author.bot and m.author.name.lower() == "mudae" and m.embeds,
                    timeout=30,
                )
                print(f"[DEBUG] Mensagem da Mudae recebida ({ultima_mensagem_mudae.id})")

            while True:
                await asyncio.sleep(1)

                embed = ultima_mensagem_mudae.embeds[0]
                descricao = embed.description or ""
                linhas = descricao.split("\n")

                personagens_encontrados = 0
                for linha in linhas:
                    match = re.search(r"(.+?)\s*💞?\s*=>\s*(.+)", linha)
                    if match:
                        personagem, usuario = match.groups()
                        usuario = usuario.strip().replace("@", "").replace("<", "").replace(">", "")
                        if usuario not in series[nome_serie]:
                            series[nome_serie][usuario] = []
                        if personagem not in series[nome_serie][usuario]:
                            series[nome_serie][usuario].append(personagem)
                            personagens_encontrados += 1
                            personagens_total += 1

                if personagens_encontrados > 0:
                    paginas_coletadas += 1
                    await message.channel.send(
                        f"📄 Página {paginas_coletadas} coletada ({personagens_encontrados} personagens)."
                    )

                # Aguarda nova edição (mudança de página)
                try:
                    before, after = await bot.wait_for("message_edit", check=eh_mudae_edit, timeout=20)
                    ultima_mensagem_mudae = after
                    print(f"[DEBUG] Nova edição detectada ({after.id})")
                except asyncio.TimeoutError:
                    print("[DEBUG] Timeout sem novas edições — encerrando coleta.")
                    break

            salvar_json("series.json", series)
            await message.channel.send(
                f"✅ Coleta finalizada! Série: `{nome_serie}` — **{paginas_coletadas} páginas** e **{personagens_total} personagens** processados."
            )

        except asyncio.TimeoutError:
            await message.channel.send("⚠️ Nenhuma resposta da Mudae após 30s. Tente novamente.")

            
    # ====================================
    # === ATUALIZAÇÃO DE ATIVIDADE
    # ====================================
    roll_prefixes = ("$w", "$wg", "$wa", "$ha", "$hg", "$h")
    if message.content.startswith(roll_prefixes):
        try:
            # === Atualiza atividade individual ===
            atividade = carregar_json(ARQUIVO_ATIVIDADE)
            atividade[str(message.author.id)] = {
                "usuario": message.author.name,
                "data": agora_brasil().strftime("%Y-%m-%d %H:%M:%S")
            }
            salvar_json(ARQUIVO_ATIVIDADE, atividade)

            # === Atualiza histórico dos últimos 6 dias ===
            historico = carregar_json(ARQUIVO_ATIVIDADE_6DIAS)
            hoje = agora_brasil().strftime("%Y-%m-%d")

            # Se o dia ainda não existe, cria
            if hoje not in historico:
                historico[hoje] = {}

            # Marca o usuário como ativo hoje
            historico[hoje][str(message.author.id)] = message.author.name

            # Mantém apenas os últimos 6 dias
            dias_validos = sorted(
                [d for d in historico.keys() if re.match(r"\d{4}-\d{2}-\d{2}", d)]
            )
            if len(dias_validos) > 6:
                for dia_antigo in dias_validos[:-6]:
                    del historico[dia_antigo]

            salvar_json(ARQUIVO_ATIVIDADE_6DIAS, historico)
            print(f"📆 Histórico de 6 dias atualizado ({len(historico)} dias mantidos).")

        except Exception as e:
            print(f"⚠️ Erro ao atualizar histórico: {e}")

                        

    # ====================================
    # === DETECTOR AUTOMÁTICO DE $IM
    # ====================================
    if message.content.lower().startswith("$im "):
        await asyncio.sleep(3)
        
        personagem, footer_text, descricao = await obter_ultima_embed_mudae(message.channel)
        if not personagem or not footer_text:
            return
            
        # Melhor regex para capturar o nome completo (até o ~)
        match = re.search(r"Pertence a ([^~\n]+)", footer_text)
        if not match:
            return
            
        dono_completo = match.group(1).strip()
        # Remove underscores e espaços extras
        dono_nome = dono_completo.replace("_", "").strip()
        
        guild_id = str(message.guild.id)
        imunes = carregar_json(ARQUIVO_IMUNES)
        if guild_id not in imunes:
            return
            
        personagem_normalizado = normalizar_texto(personagem)
        
        for user_id, dados in imunes[guild_id].items():
            if normalizar_texto(dados["personagem"]) == personagem_normalizado:
                usuario_imune = message.guild.get_member(int(user_id))
                if not usuario_imune:
                    continue

                # Remove da lista de imunidades (SEM VERIFICAR SE É O DONO)
                del imunes[guild_id][user_id]
                salvar_json(ARQUIVO_IMUNES, imunes)

                # Aplica cooldown de 3 dias
                definir_cooldown(user_id, dias=3)

                # Envia aviso no canal configurado
                config = carregar_json(ARQUIVO_CONFIG)
                canal_id = config.get(guild_id)
                canal = message.guild.get_channel(canal_id) if canal_id else None

                if canal:
                    await canal.send(
                        f" {usuario_imune.mention}, seu personagem imune "
                        f"**{dados['personagem']} ({dados['origem']})** já foi pego. "
                        f"Você agora está em cooldown de **3 dias** para usar `/imune_add` novamente."
                    )
                
                print(f"[REMOVIDO] {dados['personagem']} removido das imunidades. Cooldown aplicado a {usuario_imune}.")
                break
    
    # Permite que outros comandos Slash e prefixados funcionem
    await bot.process_commands(message)

    # === EVENTO DE CASAMENTO DA MUDAE VIA EMBED ===
@bot.event
async def on_message_edit(before, after):
    # Só processa mensagens da Mudae
    if after.author.bot and after.author.name.lower() == "mudae" and after.embeds:
        imunes = carregar_json(ARQUIVO_IMUNES)
        guild_id = str(after.guild.id)
        if guild_id not in imunes:
            return

        embed = after.embeds[0]
        if embed.description and "Pertence a" in embed.description:
            # Extrai nome do dono
            m = re.search(r"Pertence a (.+)", embed.description)
            if not m:
                return
            dono_nome = m.group(1).strip()

            # Extrai nome do personagem
            personagem = embed.author.name if embed.author and embed.author.name else embed.title
            if not personagem:
                return

            personagem_normalizado = normalizar_texto(personagem)

            # Verifica se é um personagem imune
            personagem_encontrado = None
            for uid, dados in imunes[guild_id].items():
                if normalizar_texto(dados["personagem"]) == personagem_normalizado:
                    personagem_encontrado = (uid, dados)
                    break
            if not personagem_encontrado:
                return

            user_id, dados_p = personagem_encontrado
            canal_id = carregar_json(ARQUIVO_CONFIG).get(guild_id)
            if not canal_id:
                return
            canal = after.guild.get_channel(canal_id)
            if not canal:
                return

            usuario_imune = after.guild.get_member(int(user_id))
            pegador = discord.utils.find(
                lambda m: normalizar_texto(m.name) == normalizar_texto(dono_nome)
                          or normalizar_texto(m.display_name) == normalizar_texto(dono_nome),
                after.guild.members
            )

            # Mensagem personalizada
            if pegador and pegador.id == usuario_imune.id:
                texto = (
                    f"💖 {usuario_imune.mention}, você se casou com seu personagem imune "
                    f"**{dados_p['personagem']} ({dados_p['origem']})**! A imunidade foi removida e você está em cooldown por 3 dias."
                )
            elif pegador:
                texto = (
                    f"{usuario_imune.mention}, seu personagem imune **{dados_p['personagem']} ({dados_p['origem']})** "
                    f"se casou com {pegador.mention}! A imunidade foi removida e você está em cooldown por 3 dias."
                )
            else:
                texto = (
                    f"{usuario_imune.mention}, seu personagem imune **{dados_p['personagem']} ({dados_p['origem']})** "
                    f"se casou com **{dono_nome}**! A imunidade foi removida e você está em cooldown por 3 dias."
                )

            await canal.send(texto)

            # Remove imunidade e aplica cooldown de 3 dias
            del imunes[guild_id][user_id]
            salvar_json(ARQUIVO_IMUNES, imunes)
            definir_cooldown(user_id, dias=3)

# === LOOP DE VERIFICAÇÃO ===
@tasks.loop(hours=1)
async def verificar_imunidades():
    print(f"⏳ Verificação ({agora_brasil().strftime('%d/%m/%Y %H:%M:%S')})")

# === LOOP DE VERIFICAÇÃO DE COOLDOWN ===
@tasks.loop(minutes=30)
async def verificar_cooldowns():
    """Verifica se algum cooldown expirou e avisa o usuário apenas uma vez."""
    cooldowns = carregar_json(ARQUIVO_COOLDOWN)
    config = carregar_json(ARQUIVO_CONFIG)
    agora = agora_brasil()

    expirados = []

    # === IDENTIFICA COOLDOWNS EXPIRADOS ===
    for user_id, data in cooldowns.items():
        # Agora todos devem ser dicionários
        if isinstance(data, dict):
            expira_str = data.get("expira")
            avisado = data.get("avisado", False)
            
            if not expira_str:
                continue
                
            try:
                expira = datetime.strptime(expira_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue

            if agora >= expira and not avisado:
                expirados.append(user_id)
        # Mantém compatibilidade com formato antigo por segurança
        elif isinstance(data, str):
            try:
                expira = datetime.strptime(data, "%Y-%m-%d %H:%M:%S")
                if agora >= expira:
                    expirados.append(user_id)
            except Exception:
                continue

    # === ENVIA AVISO PARA COOLDOWNS EXPIRADOS ===
    for user_id in expirados:
        user_id_int = int(user_id)
        aviso_enviado = False

        # Procura o membro em todos os servidores
        for guild in bot.guilds:
            membro = guild.get_member(user_id_int)
            if not membro:
                continue

            canal_id = config.get(str(guild.id))
            canal = guild.get_channel(canal_id) if canal_id else None

            try:
                if canal:
                    await canal.send(f" {membro.mention}, seu cooldown acabou! Você já pode usar `/imune_add` novamente.")
                    print(f"✅ Cooldown avisado para {membro} no canal {canal.name}")
                else:
                    await membro.send(" Seu cooldown acabou! Você já pode usar `/imune_add` novamente.")
                    print(f"✅ Cooldown avisado por DM para {membro}")
                aviso_enviado = True
                break
            except Exception as e:
                print(f"⚠️ Erro ao notificar cooldown de {membro}: {e}")
                continue

        # Marca como avisado mesmo se não encontrou o usuário
        if user_id in cooldowns:
            # Converte formato antigo para novo se necessário
            if isinstance(cooldowns[user_id], str):
                cooldowns[user_id] = {"expira": cooldowns[user_id], "avisado": aviso_enviado}
            else:
                cooldowns[user_id]["avisado"] = aviso_enviado
    
    # === ATUALIZA O ARQUIVO COM OS AVISOS ===
    salvar_json(ARQUIVO_COOLDOWN, cooldowns)

    # === LIMPEZA DEFINITIVA DE COOLDOWNS EXPIRADOS E JÁ AVISADOS ===
    cooldowns_limpos = {}
    agora = agora_brasil()  # Atualiza o tempo para verificação

    for uid, data in cooldowns.items():
        manter = True
        
        if isinstance(data, dict):
            expira_str = data.get("expira")
            avisado = data.get("avisado", False)
            
            if expira_str:
                try:
                    expira = datetime.strptime(expira_str, "%Y-%m-%d %H:%M:%S")
                    # Remove se expirou E já foi avisado
                    if agora >= expira and avisado:
                        manter = False
                        print(f"🧹 Cooldown removido para usuário {uid} (expirado e avisado)")
                except Exception:
                    pass
                    
        elif isinstance(data, str):
            try:
                expira = datetime.strptime(data, "%Y-%m-%d %H:%M:%S")
                # Remove se expirou (formato antigo sempre remove quando expira)
                if agora >= expira:
                    manter = False
                    print(f"🧹 Cooldown antigo removido para usuário {uid}")
            except Exception:
                pass
        
        if manter:
            cooldowns_limpos[uid] = data

    # Salva apenas os cooldowns que devem ser mantidos
    salvar_json(ARQUIVO_COOLDOWN, cooldowns_limpos)
    
    # Log informativo
    if len(cooldowns) != len(cooldowns_limpos):
        print(f"🧹 Cooldowns limpos: {len(cooldowns)} → {len(cooldowns_limpos)}")
    print(f"[LOOP] Verificação de cooldowns concluída: {len(expirados)} expirados | {datetime.now()}")

# === LOOP YOUTUBE ===
@tasks.loop(minutes=5)
async def verificar_youtube():
    novos_videos = verificar_novos_videos()
    if not novos_videos:
        return

    for guild in bot.guilds:
        config = carregar_json(ARQUIVO_CONFIG)
        canal_id = None

        if "youtube" in config and str(guild.id) in config["youtube"]:
            canal_id = config["youtube"][str(guild.id)]

        if canal_id:
            canal = guild.get_channel(canal_id)
            if canal:
                for video in novos_videos:
                    if video["tipo"] == "Short":
                        mensagem = (
                            f"📹 @everyone Saiu Novo Short do Canal!\n"
                            f"**{video['title']}**\n{video['link']}"
                        )
                    else:
                        mensagem = (
                            f"🎬 @everyone Saiu Novo Vídeo do Canal!\n"
                            f"**{video['title']}**\n{video['link']}"
                        )

                    await canal.send(mensagem)

# === ON READY ===
@bot.event
async def on_ready():
    print(f"✅ Logado como {bot.user}")
    
    # Carrega configuração de categoria
    config = s2_load(ARQ_S2_CONFIG)
    for guild in bot.guilds:
        guild_id = str(guild.id)
        if "categoria_salas" in config and guild_id in config["categoria_salas"]:
            global S2_CATEGORIA_SALAS_ID
            S2_CATEGORIA_SALAS_ID = config["categoria_salas"][guild_id]
            print(f"✅ [{agora_brasil().strftime('%H:%M:%S')}] Categoria de salas carregada para {guild.name}: {S2_CATEGORIA_SALAS_ID}")
            break

def web_server():
    """Servidor web simples para manter a instância ativa"""
    def app(environ, start_response):
        status = '200 OK'
        headers = [('Content-type', 'text/plain')]
        start_response(status, headers)
        # Use texto ASCII simples
        return [b"Bot rodando!"]
    
    port = int(os.environ.get("PORT", 8080))
    with make_server('', port, app) as httpd:
        print(f"Servidor web rodando na porta {port}")
        httpd.serve_forever()

if __name__ == "__main__":
    if not TOKEN:
        print("ERRO: DISCORD_BOT_TOKEN ausente!")
    else:
        # Inicia o bot na thread principal
        print("Iniciando bot Discord...")
        
        # Cria thread para o servidor web
        web_thread = Thread(target=web_server, daemon=True)
        web_thread.start()
        
        # Executa o bot (bloqueante)
        bot.run(TOKEN)
