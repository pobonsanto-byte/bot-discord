import discord
from discord import app_commands
from discord.ext import tasks
from datetime import datetime, timedelta
import json
import os

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ARQUIVO_IMUNES = "imunidades.json"
CANAL_AVISOS_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))

class ImuneBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        verificar_imunidades.start()

bot = ImuneBot()

def carregar_imunes():
    if not os.path.exists(ARQUIVO_IMUNES):
        return {}
    with open(ARQUIVO_IMUNES, "r", encoding="utf-8") as f:
        return json.load(f)

def salvar_imunes(imunes):
    with open(ARQUIVO_IMUNES, "w", encoding="utf-8") as f:
        json.dump(imunes, f, indent=4, ensure_ascii=False)

@bot.tree.command(name="imune_add", description="Adiciona um personagem imune (1 por jogador).")
@app_commands.describe(nome_personagem="Nome do personagem", jogo_anime="Nome do jogo/anime")
async def imune_add(interaction: discord.Interaction, nome_personagem: str, jogo_anime: str):
    imunes = carregar_imunes()

    user_id = str(interaction.user.id)
    if user_id in imunes:
        await interaction.response.send_message(f"⚠️ {interaction.user.mention}, você já possui um personagem imune!", ephemeral=True)
        return

    imunes[user_id] = {
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
async def imune_lista(interaction: discord.Interaction):
    imunes = carregar_imunes()
    if not imunes:
        await interaction.response.send_message("📭 Nenhum personagem imune no momento.")
        return

    embed = discord.Embed(title="🧾 Lista de Personagens Imunes", color=0x5865F2)
    for dados in imunes.values():
        data_criacao = datetime.strptime(dados["data"], "%Y-%m-%d %H:%M:%S")
        tempo_passado = datetime.now() - data_criacao
        horas_restantes = max(0, 48 - int(tempo_passado.total_seconds() // 3600))
        embed.add_field(
            name=f"{dados['personagem']} ({dados['origem']})",
            value=f"Dono: **{dados['usuario']}**\n⏳ Expira em: {horas_restantes}h",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="imune_remover", description="Remove sua imunidade manualmente.")
async def imune_remover(interaction: discord.Interaction):
    imunes = carregar_imunes()
    user_id = str(interaction.user.id)

    if user_id not in imunes:
        await interaction.response.send_message("❌ Você não possui imunidade ativa.", ephemeral=True)
        return

    del imunes[user_id]
    salvar_imunes(imunes)
    await interaction.response.send_message(f"✅ {interaction.user.mention}, sua imunidade foi removida.", ephemeral=False)

@tasks.loop(hours=1)
async def verificar_imunidades():
    imunes = carregar_imunes()
    agora = datetime.now()
    alterado = False

    canal = bot.get_channel(CANAL_AVISOS_ID)
    if not canal:
        print("⚠️ Canal de avisos não encontrado (verifique o ID).")
        return

    for user_id, dados in list(imunes.items()):
        data_inicial = datetime.strptime(dados["data"], "%Y-%m-%d %H:%M:%S")
        if agora - data_inicial >= timedelta(days=2):
            await canal.send(f"🕒 A imunidade de **{dados['personagem']} ({dados['origem']})** do jogador **{dados['usuario']}** expirou!")
            del imunes[user_id]
            alterado = True
            print(f"🔁 Imunidade expirada: {dados['usuario']} ({dados['personagem']})")

    if alterado:
        salvar_imunes(imunes)

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    await bot.change_presence(activity=discord.Game(name="/imune_add | /imune_lista"))

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERRO: DISCORD_BOT_TOKEN não encontrado nas variáveis de ambiente!")
        exit(1)
    if CANAL_AVISOS_ID == 0:
        print("⚠️ AVISO: DISCORD_CHANNEL_ID não definido. Notificações não funcionarão.")
    
    bot.run(TOKEN)
