"""
Autenticação na API HidroWebService da ANA (EstacoesTelemetricas — séries de estações).

Credenciais NUNCA ficam no código nem no repositório: são lidas de variáveis
de ambiente (ANA_IDENTIFICADOR, ANA_SENHA), carregadas de um arquivo .env
local que fica fora do git (ver .env.example e .gitignore).

Endpoint confirmado no manual oficial "Tutorial de Serviço para Consumo de
Dados - API HidroWebService" (ANA, versão 20.02.2026): GET
/EstacoesTelemetricas/OAUth/v1, credenciais nos headers Identificador/Senha,
token em items.tokenautenticacao, válido por 60 minutos. O cadastro de acesso
é feito por e-mail a hidro@ana.gov.br (ver item 1.1 do manual) — é um cadastro
separado do usado em www.snirh.gov.br/dadoshidrometereologicos.

Ver docs/DECISOES.md, Fase 1.
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
