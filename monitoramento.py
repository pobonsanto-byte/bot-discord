import re
import json
import base64
import requests

ultimos_casamentos = {}

def carregar_json(nome_arquivo, repo_info):
    url = f"https://api.github.com/repos/{repo_info['REPO']}/contents/{nome_arquivo}?ref={repo_info['BRANCH']}"
    headers = {"Authorization": f"token {repo_info['GITHUB_TOKEN']}"}
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

async def monitorar_casamentos(bot, message, repo_info, arquivo_imunes):
    if message.author.bot:
        casamento_pattern = re.compile(r"💖\s(.+?)\se\s(.+?)\sagora\s(.*)casados", re.IGNORECASE)
        match = casamento_pattern.search(message.content)
        if match:
            personagem1 = match.group(1).strip()
            personagem2 = match.group(2).strip()

            imunes = carregar_json(arquivo_imunes, repo_info)
            guild_id = str(message.guild.id)
            if guild_id not in imunes:
                return

            encontrou_imune = None
            dono_imune = None
            for user_id, dados in imunes[guild_id].items():
                if dados["personagem"].strip().lower() == personagem1.lower():
                    encontrou_imune = personagem1
                    dono_imune = user_id
                    break
                if dados["personagem"].strip().lower() == personagem2.lower():
                    encontrou_imune = personagem2
                    dono_imune = user_id
                    break

            if encontrou_imune:
                dono_imune_usuario = message.guild.get_member(int(dono_imune))
                autor_id = ultimos_casamentos.get(guild_id)
                autor_casamento = message.guild.get_member(autor_id) if autor_id else None

                if autor_id and autor_id == int(dono_imune):
                    aviso = f"✅ {autor_casamento.mention} casou o personagem **{encontrou_imune}** que está imune."
                elif autor_id:
                    aviso = f"⚠️ {autor_casamento.mention} casou o personagem **{encontrou_imune}** que está imune! Imunidade atribuída a {dono_imune_usuario.mention}."
                else:
                    aviso = f"⚠️ O personagem **{encontrou_imune}** foi casado, mas não consegui identificar quem casou."

                await message.channel.send(aviso)

    else:
        # Detecta comandos de casamento para lembrar quem casou
        if message.content.lower().startswith(("$marry", "$marri", "$married")):
            ultimos_casamentos[str(message.guild.id)] = message.author.id
