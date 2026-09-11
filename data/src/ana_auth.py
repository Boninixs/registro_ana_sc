"""
Autenticação na API HidroWebService da ANA 
"""

from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("ANA_API_BASE_URL", "https://www.ana.gov.br/hidrowebservice")
OAUTH_PATH = "/EstacoesTelemetricas/OAUth/v1"


class AutenticacaoError(RuntimeError):
    """Erro ao autenticar na API da ANA."""


def autenticar() -> str:
    """Troca ANA_IDENTIFICADOR/ANA_SENHA por um token de acesso.

    O token retornado deve ser enviado como header 'Authorization: Bearer <token>'
    nas chamadas seguintes aos endpoints de série (ex.: /Hidro/v1/SerieChuva).
    Ele expira após um tempo limitado — reautenticar quando a API responder 401.
    """
    identificador = os.environ.get("ANA_IDENTIFICADOR")
    senha = os.environ.get("ANA_SENHA")
    if not identificador or not senha:
        raise AutenticacaoError(
            "ANA_IDENTIFICADOR / ANA_SENHA não configurados. "
            "Copie .env.example para .env (na raiz do projeto) e preencha com "
            "suas credenciais da ANA."
        )

    resp = requests.get(
        f"{BASE_URL}{OAUTH_PATH}",
        headers={"Identificador": identificador, "Senha": senha},
        timeout=30,
    )
    resp.raise_for_status()
    corpo = resp.json()
    token = (corpo.get("items") or {}).get("tokenautenticacao")
    if not token:
        raise AutenticacaoError(f"Resposta da ANA sem token de autenticação: {corpo}")
    return token


if __name__ == "__main__":
    token = autenticar()
    print(f"Autenticado com sucesso. Token: {token[:12]}...")
