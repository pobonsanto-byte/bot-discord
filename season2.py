import discord
from discord import app_commands
from discord.ext import tasks
import asyncio
import random
from datetime import datetime
import json
import pytz
from bot import carregar_json, salvar_json, agora_brasil


# =============================
# ARQUIVOS SEASON 2
# =============================
ARQ_S2_CONFIG = "season2_config.json"
ARQ_S2_PLAYERS = "season2_players.json"
ARQ_S2_PERSONAGENS = "season2_personagens.json"
ARQ_S2_VENDAS = "season2_vendas.json"
ARQ_S2_SALAS = "season2_salas.json"

# =============================
# CONFIGURAÇÕES
# =============================
S2_CATEGORIA_SALAS = None
S2_TEMPO_SALA = 60 * 60
MUDAE_BOT_ID = 432610292342587392

S2_ROLL_PREFIXES = ("$w", "$wa", "$wg", "$h", "$ha", "$hg")
S2_ROLL_FREE = ("$vote", "$daily")

S2_SALAS_CONSUMIDAS = set()

# =============================
# FUNÇÕES JSON (usa as suas)
# =============================

def s2_load(arq):
    return carregar_json(arq) or {}

def s2_save(arq, dados):
    salvar_json(arq, dados)


# =============================
# FUNÇÕES AUXILIARES
# =============================
def s2_get_sala_por_canal(channel_id):
    salas = s2_load(ARQ_S2_SALAS)
    for uid, info in salas.items():
        if info["canal_id"] == channel_id:
            return uid, info
    return None, None

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

# =============================
# REGISTRO DOS COMANDOS
# =============================
def setup_season2(bot: discord.Client, tree: app_commands.CommandTree):

    # ---------- APPLY ----------
    @tree.command(name="sala_privada_apply")
    async def sala_privada_apply(interaction: discord.Interaction):
        players = s2_load(ARQ_S2_PLAYERS)
        uid = str(interaction.user.id)

        players[uid] = {
            "status": "pendente",
            "rodadas": 0,
            "bonus_evento": 0,
            "ultimo_reset": None,
            "sala_ativa": False
        }
        s2_save(ARQ_S2_PLAYERS, players)
        await interaction.response.send_message(
            "📨 Aplicação enviada para a Sala Privada.", ephemeral=True
        )

    # ---------- APROVAR ----------
    @tree.command(name="sala_privada_aprovar")
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
        await interaction.response.send_message(
            f"✅ {usuario.mention} aprovado na Sala Privada."
        )

    # ---------- ABRIR SALA ----------
    @tree.command(name="sala_privada_abrir")
    async def sala_privada_abrir(interaction: discord.Interaction):
        uid = str(interaction.user.id)
        players = s2_load(ARQ_S2_PLAYERS)
        salas = s2_load(ARQ_S2_SALAS)

        p = players.get(uid)
        if not p or p["status"] != "aprovado" or p["rodadas"] <= 0 or p["sala_ativa"]:
            await interaction.response.send_message(
                "⛔ Você não pode abrir uma sala agora.", ephemeral=True
            )
            return

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True)
        }

        canal = await interaction.guild.create_text_channel(
            f"🔐-privada-{interaction.user.display_name}".lower(),
            overwrites=overwrites
        )

        p["sala_ativa"] = True
        salas[uid] = {
            "canal_id": canal.id,
            "aberta_em": agora_brasil().strftime("%Y-%m-%d %H:%M:%S")
        }

        s2_save(ARQ_S2_PLAYERS, players)
        s2_save(ARQ_S2_SALAS, salas)

        await interaction.response.send_message(
            f"🔓 Sala criada: {canal.mention}", ephemeral=True
        )

    # ---------- FECHAR SALA ----------
    @tree.command(name="sala_privada_fechar")
    async def sala_privada_fechar(interaction: discord.Interaction):
        uid = str(interaction.user.id)
        salas = s2_load(ARQ_S2_SALAS)
        players = s2_load(ARQ_S2_PLAYERS)

        sala = salas.get(uid)
        if not sala:
            await interaction.response.send_message("❌ Nenhuma sala ativa.", ephemeral=True)
            return

        canal = interaction.guild.get_channel(sala["canal_id"])

        players[uid]["rodadas"] -= 1
        players[uid]["sala_ativa"] = False

        S2_SALAS_CONSUMIDAS.discard(canal.id)

        del salas[uid]

        s2_save(ARQ_S2_PLAYERS, players)
        s2_save(ARQ_S2_SALAS, salas)

        await interaction.response.send_message("✅ Sala fechada.", ephemeral=True)
        if canal:
            await canal.delete()

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

    s2_reset.start()

    # ---------- ON_MESSAGE ----------
    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return

        uid_sala, _ = s2_get_sala_por_canal(message.channel.id)

        # Roll dentro da sala
        if uid_sala:
            if str(message.author.id) != uid_sala:
                await message.delete()
                return

            if message.content.lower().startswith(S2_ROLL_PREFIXES):
                if message.channel.id not in S2_SALAS_CONSUMIDAS:
                    S2_SALAS_CONSUMIDAS.add(message.channel.id)
                return

        # Registro automático da Mudae
        if message.author.id == MUDAE_BOT_ID and message.embeds:
            uid_sala, _ = s2_get_sala_por_canal(message.channel.id)
            if uid_sala:
                personagem = s2_extrair_personagem_do_embed(message.embeds[0])
                if personagem:
                    tipo = s2_definir_tipo_personagem(message.embeds[0])
                    s2_registro_automatico(uid_sala, personagem, tipo)

        await bot.process_commands(message)
