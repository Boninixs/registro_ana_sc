"""
Parser do formato de chuvas diárias da ANA (HidroWeb).

O formato nativo é WIDE: uma linha por mês, com 31 colunas Chuva01..Chuva31.
Este módulo converte para LONG (uma linha por dia) e resolve as duas
armadilhas principais do formato:

  1. Duplicidade por nível de consistência (o mesmo mês aparece como bruto
     e como consistido). Regra adotada: preferir sempre nível 2.
  2. Status = 4 ("Acumulado"), em que o valor de um dia é a soma de vários
     dias anteriores. Sem tratamento, isso gera EXTREMOS FALSOS.

Ver docs/DECISOES.md para a justificativa de cada regra.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constantes do formato
# ---------------------------------------------------------------------------

HEADER_TOKEN = "EstacaoCodigo;"
ENCODINGS = ("latin-1", "cp1252", "utf-8")

DIAS = range(1, 32)
COLS_CHUVA = [f"Chuva{d:02d}" for d in DIAS]
COLS_STATUS = [f"Chuva{d:02d}Status" for d in DIAS]

NIVEL_CONSISTENCIA = {1: "bruto", 2: "consistido"}

STATUS_LABEL = {
    0: "branco",
    1: "real",
    2: "estimado",
    3: "duvidoso",
    4: "acumulado",
}

# Status que NÃO devem entrar em análise de extremos.
# 4 = acumulado (soma de vários dias num só registro -> extremo falso)
# 0 = branco (ausência de leitura)
STATUS_DESCARTE_EXTREMOS = {0, 4}


@dataclass
class RelatorioParse:
    """Resumo do que aconteceu ao ler um arquivo. Alimenta o log do pipeline."""

    estacao: str
    linhas_arquivo: int
    meses_distintos: int
    meses_duplicados: int
    dias_gerados: int
    dias_com_valor: int
    data_inicio: pd.Timestamp | None
    data_fim: pd.Timestamp | None
    cobertura_pct: float
    contagem_status: dict

    def __str__(self) -> str:
        ini = self.data_inicio.date() if self.data_inicio is not None else "-"
        fim = self.data_fim.date() if self.data_fim is not None else "-"
        st = ", ".join(
            f"{STATUS_LABEL.get(k, k)}={v}" for k, v in sorted(self.contagem_status.items())
        )
        return (
            f"Estação {self.estacao} | {ini} a {fim}\n"
            f"  linhas no arquivo : {self.linhas_arquivo}\n"
            f"  meses distintos   : {self.meses_distintos} "
            f"({self.meses_duplicados} com bruto+consistido)\n"
            f"  dias com valor    : {self.dias_com_valor} "
            f"({self.cobertura_pct:.1f}% do período)\n"
            f"  status            : {st}"
        )


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def _localizar_header(path: Path) -> tuple[int, str]:
    """Descobre em que linha começa o cabeçalho real e qual encoding funciona.

    O arquivo da ANA vem com ~14 linhas de preâmbulo institucional antes do
    cabeçalho de verdade, e o número de linhas varia conforme a consulta.
    """
    ultimo_erro: Exception | None = None
    for enc in ENCODINGS:
        try:
            with open(path, encoding=enc) as f:
                for i, linha in enumerate(f):
                    if linha.lstrip("\ufeff").startswith(HEADER_TOKEN):
                        return i, enc
        except (UnicodeDecodeError, LookupError) as exc:  # pragma: no cover
            ultimo_erro = exc
            continue
    raise ValueError(
        f"Cabeçalho '{HEADER_TOKEN}' não encontrado em {path}. "
        f"O arquivo pode estar vazio ou em formato diferente. Último erro: {ultimo_erro}"
    )


def ler_bruto(path: str | Path) -> pd.DataFrame:
    """Lê o CSV da ANA no formato wide, sem transformar nada."""
    path = Path(path)
    skip, enc = _localizar_header(path)
    df = pd.read_csv(
        path,
        sep=";",
        skiprows=skip,
        encoding=enc,
        dtype=str,
        keep_default_na=False,
        na_values=[""],
    )
    df.columns = [c.strip() for c in df.columns]
    return df


# ---------------------------------------------------------------------------
# Transformação
# ---------------------------------------------------------------------------


def _para_float(serie: pd.Series) -> pd.Series:
    """Converte '33,0' -> 33.0. O formato brasileiro usa vírgula decimal."""
    return pd.to_numeric(
        serie.astype("string").str.strip().str.replace(",", ".", regex=False),
        errors="coerce",
    )


def wide_para_long(df: pd.DataFrame) -> pd.DataFrame:
    """Converte o formato mensal (31 colunas) para uma linha por dia."""
    faltando = [c for c in ("EstacaoCodigo", "Data", "NivelConsistencia") if c not in df.columns]
    if faltando:
        raise ValueError(f"Colunas obrigatórias ausentes: {faltando}")

    base = df[["EstacaoCodigo", "Data", "NivelConsistencia"]].copy()
    base["Data"] = pd.to_datetime(base["Data"], format="%d/%m/%Y", errors="coerce")
    base["NivelConsistencia"] = pd.to_numeric(base["NivelConsistencia"], errors="coerce")

    if base["Data"].isna().any():
        n = int(base["Data"].isna().sum())
        raise ValueError(f"{n} linha(s) com data inválida — verifique o arquivo de origem.")

    valores = df.reindex(columns=COLS_CHUVA).apply(_para_float)
    status = df.reindex(columns=COLS_STATUS).apply(
        lambda s: pd.to_numeric(s, errors="coerce")
    )

    valores.columns = list(DIAS)
    status.columns = list(DIAS)

    v_long = valores.stack(future_stack=True).rename("precipitacao")
    s_long = status.stack(future_stack=True).rename("status")

    long = pd.concat([v_long, s_long], axis=1).reset_index()
    long = long.rename(columns={"level_0": "_i", "level_1": "dia"})

    long = long.join(base, on="_i").drop(columns="_i")
    long = long.rename(
        columns={
            "EstacaoCodigo": "estacao",
            "NivelConsistencia": "nivel_consistencia",
        }
    )

    # Monta a data real e elimina dias inexistentes (31/02, 31/04, ...)
    long["data"] = pd.to_datetime(
        dict(year=long["Data"].dt.year, month=long["Data"].dt.month, day=long["dia"]),
        errors="coerce",
    )
    long = long.dropna(subset=["data"]).drop(columns=["Data", "dia"])

    return long[["estacao", "data", "precipitacao", "status", "nivel_consistencia"]]


def deduplicar(long: pd.DataFrame) -> pd.DataFrame:
    """Resolve o mesmo dia registrado como bruto e como consistido.

    Regra: prefere nível 2 (consistido). Se o consistido não tiver valor mas o
    bruto tiver, mantém o consistido mesmo assim — a ausência no consistido é
    informação (o operador removeu o dado de propósito).
    """
    ordenado = long.sort_values(
        ["estacao", "data", "nivel_consistencia"], na_position="first"
    )
    return (
        ordenado.drop_duplicates(subset=["estacao", "data"], keep="last")
        .sort_values(["estacao", "data"])
        .reset_index(drop=True)
    )


def marcar_flags(long: pd.DataFrame) -> pd.DataFrame:
    """Adiciona colunas de rastreabilidade. NÃO remove nada.

    Regra do projeto: nunca apagar dado, apenas marcar. A remoção é decisão
    da etapa de análise, e precisa ser reversível para testes de sensibilidade.
    """
    out = long.copy()
    out["status_label"] = out["status"].map(STATUS_LABEL).fillna("desconhecido")
    out["nivel_label"] = out["nivel_consistencia"].map(NIVEL_CONSISTENCIA).fillna("desconhecido")
    out["flag_acumulado"] = out["status"].eq(4)
    out["flag_duvidoso"] = out["status"].eq(3)
    out["flag_estimado"] = out["status"].eq(2)
    # Serve para as análises de extremo: o dia é utilizável?
    out["valido_extremos"] = out["precipitacao"].notna() & ~out["status"].isin(
        STATUS_DESCARTE_EXTREMOS
    )
    return out


# ---------------------------------------------------------------------------
# API principal
# ---------------------------------------------------------------------------


def parse_estacao(path: str | Path) -> tuple[pd.DataFrame, RelatorioParse]:
    """Lê um CSV da ANA e devolve a série diária limpa + relatório de leitura."""
    path = Path(path)
    bruto = ler_bruto(path)
    long = wide_para_long(bruto)
    dedup = deduplicar(long)
    final = marcar_flags(dedup)

    datas = pd.to_datetime(bruto["Data"], format="%d/%m/%Y", errors="coerce")
    meses_por_data = datas.value_counts()

    if len(final):
        ini, fim = final["data"].min(), final["data"].max()
        esperado = len(pd.date_range(ini, fim, freq="D"))
        cobertura = 100.0 * final["precipitacao"].notna().sum() / esperado
    else:  # pragma: no cover
        ini = fim = None
        cobertura = 0.0

    rel = RelatorioParse(
        estacao=str(bruto["EstacaoCodigo"].iloc[0]) if len(bruto) else "?",
        linhas_arquivo=len(bruto),
        meses_distintos=int(meses_por_data.size),
        meses_duplicados=int((meses_por_data > 1).sum()),
        dias_gerados=len(final),
        dias_com_valor=int(final["precipitacao"].notna().sum()),
        data_inicio=ini,
        data_fim=fim,
        cobertura_pct=cobertura,
        contagem_status=final["status"].value_counts().dropna().astype(int).to_dict(),
    )
    return final, rel


def serie_continua(long: pd.DataFrame, apenas_validos: bool = True) -> pd.Series:
    """Devolve a série diária reindexada em calendário completo.

    Dias ausentes viram NaN explícito — essencial para calcular falhas
    corretamente. Com apenas_validos=True, descarta acumulados e brancos.
    """
    df = long.copy()
    if apenas_validos:
        df.loc[~df["valido_extremos"], "precipitacao"] = np.nan
    s = df.set_index("data")["precipitacao"].sort_index()
    return s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("uso: python src/parse.py <arquivo.csv> [saida.parquet]")
        raise SystemExit(1)

    df, relatorio = parse_estacao(sys.argv[1])
    print(relatorio)

    if len(sys.argv) > 2:
        df.to_parquet(sys.argv[2], index=False)
        print(f"\nsalvo em {sys.argv[2]}")
