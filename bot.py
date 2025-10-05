import discord
from discord import app_commands
from discord.ext import tasks
from datetime import datetime, timedelta
import json
import os

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ARQUIVO_IMUNES = "imunidades.json"
CANAIS_BLOQUEADOS_FILE = "canais_bloqueados.json"

channel_id_env = os.getenv("DISCORD_CHANNEL_ID", "0")
if channel_id_env.startswith("http"):
    print("⚠️ DISCORD_CHANNEL_ID parece ser uma URL de webhook, não um ID de canal.")
    print("   Por favor, forneça apenas o ID numérico do canal.")
    CANAL_AVISOS_ID = 0
else:
    try:
        CANAL_AVISOS_ID = int(channel_id_env)
    except ValueError:
        print(f"⚠️ DISCORD_CHANNEL_ID inválido: {channel_id_env}")
        CANAL_AVISOS_ID = 0

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

def carregar_canais_bloqueados():
    if not os.path.exists(CANAIS_BLOQUEADOS_FILE):
        return []
    try:
        with open(CANAIS_BLOQUEADOS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError) as e:
        print(f"⚠️ Erro ao carregar {CANAIS_BLOQUEADOS_FILE}: {e}")
        return []

def salvar_canais_bloqueados(canais):
    try:
        with open(CANAIS_BLOQUEADOS_FILE, "w", encoding="utf-8") as f:
            json.dump(canais, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"❌ Erro ao salvar {CANAIS_BLOQUEADOS_FILE}: {e}")

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

@bot.tree.command(name="bloquear", description="Bloqueia o bot de enviar mensagens neste canal.")
async def bloquear(interaction: discord.Interaction):
    if not interaction.channel:
        await interaction.response.send_message("❌ Erro ao identificar o canal.", ephemeral=True)
        return
    
    canais_bloqueados = carregar_canais_bloqueados()
    canal_id = interaction.channel.id

    if canal_id in canais_bloqueados:
        await interaction.response.send_message("⚠️ Esse canal já está bloqueado.", ephemeral=True)
        return

    canais_bloqueados.append(canal_id)
    salvar_canais_bloqueados(canais_bloqueados)
    await interaction.response.send_message(f"🔒 Bot bloqueado neste canal.", ephemeral=False)

@bot.tree.command(name="desbloquear", description="Desbloqueia o bot neste canal.")
async def desbloquear(interaction: discord.Interaction):
    if not interaction.channel:
        await interaction.response.send_message("❌ Erro ao identificar o canal.", ephemeral=True)
        return
    
    canais_bloqueados = carregar_canais_bloqueados()
    canal_id = interaction.channel.id

    if canal_id not in canais_bloqueados:
        await interaction.response.send_message("⚠️ Esse canal não está bloqueado.", ephemeral=True)
        return

    canais_bloqueados.remove(canal_id)
    salvar_canais_bloqueados(canais_bloqueados)
    await interaction.response.send_message(f"🔓 Bot desbloqueado neste canal.", ephemeral=False)

@tasks.loop(hours=1)
async def verificar_imunidades():
    imunes = carregar_imunes()
    agora = datetime.now()
    alterado = False
    expirados = []

    for user_id, dados in list(imunes.items()):
        try:
            data_inicial = datetime.strptime(dados["data"], "%Y-%m-%d %H:%M:%S")
            if agora - data_inicial >= timedelta(days=2):
                expirados.append((user_id, dados))
                del imunes[user_id]
                alterado = True
                print(f"🔁 Imunidade expirada: {dados['usuario']} ({dados['personagem']})")
        except (KeyError, ValueError) as e:
            print(f"⚠️ Dados inválidos para user_id {user_id}: {e}")

    if alterado:
        salvar_imunes(imunes)

    if expirados and CANAL_AVISOS_ID != 0:
        canais_bloqueados = carregar_canais_bloqueados()
        
        if CANAL_AVISOS_ID in canais_bloqueados:
            print(f"⚠️ Canal {CANAL_AVISOS_ID} bloqueado — pulando envio de mensagens.")
            return
        
        canal = bot.get_channel(CANAL_AVISOS_ID)
        if canal and isinstance(canal, (discord.TextChannel, discord.Thread)):
            for user_id, dados in expirados:
                try:
                    await canal.send(f"🕒 A imunidade de **{dados['personagem']} ({dados['origem']})** do jogador **{dados['usuario']}** expirou!")
                except discord.errors.HTTPException as e:
                    print(f"❌ Erro ao enviar mensagem de expiração: {e}")
        else:
            print("⚠️ Canal de avisos não encontrado ou inválido. Notificações não foram enviadas.")

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    await bot.change_presence(activity=discord.Game(name="/imune_add | /bloquear"))

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERRO: DISCORD_BOT_TOKEN não encontrado nas variáveis de ambiente!")
        print("   Configure o token do bot nas variáveis de ambiente do Replit.")
        exit(1)
    if CANAL_AVISOS_ID == 0:
        print("⚠️ AVISO: DISCORD_CHANNEL_ID não definido. Notificações não funcionarão.")
    
    print(f"🔑 Token configurado (primeiros 10 caracteres): {TOKEN[:10]}...")
    print("🚀 Tentando conectar ao Discord...")
    
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("\n❌ ERRO DE AUTENTICAÇÃO!")
        print("   O token do bot está inválido ou expirou.")
        print("   Por favor, gere um novo token em:")
        print("   https://discord.com/developers/applications")
        print("   1. Selecione sua aplicação")
        print("   2. Vá em 'Bot'")
        print("   3. Clique em 'Reset Token' e copie o novo token")
        print("   4. Cole o token nas variáveis de ambiente do Replit")
        exit(1)
