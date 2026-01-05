import json
import os
from datetime import datetime, timezone, timedelta

# =============================
# JSON
# =============================

def carregar_json(caminho: str):
    """
    Carrega um JSON e retorna dict.
    Se não existir ou estiver inválido, retorna {}.
    """
    if not os.path.exists(caminho):
        return {}

    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def salvar_json(caminho: str, dados: dict):
    """
    Salva um dict em JSON (cria o arquivo se não existir).
    """
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)


# =============================
# DATA / HORA (BRASIL - UTC-3)
# =============================

def agora_brasil():
    """
    Retorna datetime atual no fuso do Brasil (UTC-3 fixo).
    """
    return datetime.now(timezone(timedelta(hours=-3)))


def hoje_brasil():
    """
    Retorna data atual no formato YYYY-MM-DD (Brasil).
    """
    return agora_brasil().strftime("%Y-%m-%d")


def hora_brasil():
    """
    Retorna hora atual no formato HH:MM (Brasil).
    """
    return agora_brasil().strftime("%H:%M")


# =============================
# GARANTIA DE JSON
# =============================

def garantir_json(caminho: str, conteudo_padrao):
    """
    Garante que um JSON exista.
    Se não existir, cria com conteúdo padrão.
    """
    if not os.path.exists(caminho):
        salvar_json(caminho, conteudo_padrao)
