"""
Teste da autenticação na API da ANA — sem bater na rede de verdade.

Rodar:  pytest -v tests/test_ana_auth.py
"""

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "data" / "src"))

from ana_auth import AutenticacaoError, autenticar  # noqa: E402


def test_autenticar_falha_sem_credenciais(monkeypatch):
    monkeypatch.delenv("ANA_IDENTIFICADOR", raising=False)
    monkeypatch.delenv("ANA_SENHA", raising=False)
    with pytest.raises(AutenticacaoError, match="não configurados"):
        autenticar()


def test_autenticar_retorna_token(monkeypatch):
    monkeypatch.setenv("ANA_IDENTIFICADOR", "usuario_teste")
    monkeypatch.setenv("ANA_SENHA", "senha_teste")

    class RespostaFalsa:
        def raise_for_status(self):
            pass

        def json(self):
            return {"items": {"tokenautenticacao": "token-abc123"}}

    def get_falso(url, headers, timeout):
        assert headers == {"Identificador": "usuario_teste", "Senha": "senha_teste"}
        return RespostaFalsa()

    monkeypatch.setattr("ana_auth.requests.get", get_falso)
    assert autenticar() == "token-abc123"


def test_autenticar_falha_sem_token_na_resposta(monkeypatch):
    monkeypatch.setenv("ANA_IDENTIFICADOR", "usuario_teste")
    monkeypatch.setenv("ANA_SENHA", "senha_teste")

    class RespostaFalsa:
        def raise_for_status(self):
            pass

        def json(self):
            return {"items": {}}

    monkeypatch.setattr(
        "ana_auth.requests.get", lambda url, headers, timeout: RespostaFalsa()
    )
    with pytest.raises(AutenticacaoError, match="sem token"):
        autenticar()
