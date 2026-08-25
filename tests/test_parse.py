"""
Teste de regressão do parser contra a estação 2749005 (Ibirama).

Esta estação é a "verdade conhecida" do projeto: série de 1941 a 2026 com
98,9% de cobertura, conferida manualmente. Se qualquer alteração no parser
quebrar estes números, o parser está errado — não o teste.

Rodar:  pytest -v      (ou:  python tests/test_parse.py)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from parse import parse_estacao, serie_continua  # noqa: E402

ARQUIVO = RAIZ / "data" / "raw" / "ibirama_1941_2026.csv"


@pytest.fixture(scope="module")
def ibirama():
    if not ARQUIVO.exists():
        pytest.skip(f"arquivo de referência ausente: {ARQUIVO}")
    return parse_estacao(ARQUIVO)


# --- estrutura do arquivo ---------------------------------------------------


def test_codigo_da_estacao(ibirama):
    _, rel = ibirama
    assert rel.estacao == "2749005"


def test_linhas_e_meses(ibirama):
    _, rel = ibirama
    assert rel.linhas_arquivo == 1753
    assert rel.meses_distintos == 1015
    # 738 meses aparecem duas vezes (bruto + consistido)
    assert rel.meses_duplicados == 738


def test_deduplicacao_removeu_as_duplicatas(ibirama):
    df, _ = ibirama
    assert not df.duplicated(subset=["estacao", "data"]).any()


def test_dias_inexistentes_foram_descartados(ibirama):
    """31/02, 31/04, 31/06... não podem existir na saída."""
    df, _ = ibirama
    assert (df["data"].dt.day <= df["data"].dt.days_in_month).all()
    assert df["data"].notna().all()


# --- cobertura temporal -----------------------------------------------------


def test_periodo_da_serie(ibirama):
    _, rel = ibirama
    assert rel.data_inicio == pd.Timestamp("1941-01-01")
    assert rel.data_fim == pd.Timestamp("2026-04-30")


def test_cobertura(ibirama):
    _, rel = ibirama
    assert rel.dias_com_valor == 30814
    assert rel.cobertura_pct == pytest.approx(98.9, abs=0.1)


# --- tratamento de status ---------------------------------------------------


def test_contagem_de_status(ibirama):
    _, rel = ibirama
    assert rel.contagem_status[1] == 30801  # real
    assert rel.contagem_status[4] == 9      # acumulado
    assert rel.contagem_status[3] == 4      # duvidoso


def test_acumulados_marcados_como_invalidos(ibirama):
    """Status 4 é a principal fonte de extremo falso — não pode passar."""
    df, _ = ibirama
    assert df.loc[df["status"] == 4, "valido_extremos"].sum() == 0
    assert df["flag_acumulado"].sum() == 9


def test_duvidosos_marcados_mas_mantidos(ibirama):
    """Status 3 é sinalizado, não descartado — permite teste de sensibilidade."""
    df, _ = ibirama
    assert df["flag_duvidoso"].sum() == 4
    assert df.loc[df["status"] == 3, "valido_extremos"].all()


# --- valores climatológicos -------------------------------------------------


def test_maxima_absoluta(ibirama):
    df, _ = ibirama
    s = serie_continua(df)
    assert s.max() == pytest.approx(192.0)
    assert s.idxmax() == pd.Timestamp("1995-01-15")


def test_percentis_de_dias_umidos(ibirama):
    """Limiar de 1 mm para dia úmido (padrão ETCCDI)."""
    df, _ = ibirama
    s = serie_continua(df)
    umidos = s[s >= 1]
    assert len(umidos) == 8465
    assert np.nanpercentile(umidos, 95) == pytest.approx(43.2, abs=0.05)
    assert np.nanpercentile(umidos, 99) == pytest.approx(67.0, abs=0.05)


def test_sem_precipitacao_negativa(ibirama):
    df, _ = ibirama
    assert (df["precipitacao"].dropna() >= 0).all()


# --- calendário contínuo ----------------------------------------------------


def test_serie_continua_sem_buracos_de_indice(ibirama):
    """Dias sem registro viram NaN explícito, não somem do índice."""
    df, _ = ibirama
    s = serie_continua(df)
    esperado = pd.date_range("1941-01-01", "2026-04-30", freq="D")
    assert len(s) == len(esperado)
    assert s.index.equals(esperado)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
