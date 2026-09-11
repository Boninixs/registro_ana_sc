"""
Ingestão em massa das séries de chuva (estações convencionais) da ANA.

Lê o inventário de estações de SC (data/interim/estacoes_sc_inventario.parquet),
baixa a série completa de cada estação pluviométrica via HidroSerieChuva/v1
(paginada em blocos de até 366 dias, limite da API) e salva o retorno CRU
da API — sem parsing, sem deduplicação por nível de consistência — em
data/raw/<codigoestacao>.csv. Esse é o "CSV original" equivalente ao download
manual, só que obtido pela API; o parsing/tratamento (Fase 0) continua sendo
responsabilidade de um parser separado, que lê esses CSVs depois.

Idempotente: uma estação cujo CSV já existe em data/raw/ é pulada, a menos
que --forcar seja passado. Isso permite interromper e retomar a ingestão.

Uso:
    python data/src/ana_ingest.py                # todas as estações
    python data/src/ana_ingest.py --limit 10      # só as 10 primeiras (teste)
    python data/src/ana_ingest.py --forcar        # rebaixa mesmo se já existe
    python data/src/ana_ingest.py --delay 0.5     # pausa entre requisições (s)
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "data" / "src"))

from ana_auth import AutenticacaoError, autenticar  # noqa: E402

BASE_URL = "https://www.ana.gov.br/hidrowebservice/EstacoesTelemetricas"
ROTA_SERIE_CHUVA = f"{BASE_URL}/HidroSerieChuva/v1"

DIAS_POR_JANELA = 366
TENTATIVAS_POR_JANELA = 5
ESPERA_BASE_S = 8
TOKEN_VALIDADE_MIN = 55  # token dura 60min; reautentica com folga

INVENTARIO = RAIZ / "data" / "interim" / "estacoes_sc_inventario.parquet"
DIR_RAW = RAIZ / "data" / "raw"
LOG = RAIZ / "data" / "interim" / "log_ingestao_raw.csv"


class SessaoAna:
    """Mantém o token da ANA válido, reautenticando com folga antes de expirar."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._obtido_em: float = 0.0

    def headers(self) -> dict[str, str]:
        agora = time.monotonic()
        if self._token is None or (agora - self._obtido_em) > TOKEN_VALIDADE_MIN * 60:
            self._token = autenticar()
            self._obtido_em = agora
        return {"Authorization": f"Bearer {self._token}"}


def janelas(ini: date, fim: date, dias: int = DIAS_POR_JANELA):
    """Gera intervalos [inicio, fim] de no máximo `dias` dias cobrindo [ini, fim]."""
    cursor = ini
    while cursor <= fim:
        fim_janela = min(cursor + timedelta(days=dias - 1), fim)
        yield cursor, fim_janela
        cursor = fim_janela + timedelta(days=1)


def buscar_janela(
    sessao: SessaoAna, codigo: str, ini: date, fim: date
) -> list[dict]:
    """Busca uma janela de até 366 dias, com retentativas em erro transitório."""
    ultimo_erro: Exception | None = None
    for tentativa in range(1, TENTATIVAS_POR_JANELA + 1):
        try:
            resp = requests.get(
                ROTA_SERIE_CHUVA,
                headers=sessao.headers(),
                params={
                    "Código da Estação": codigo,
                    "Tipo Filtro Data": "DATA_LEITURA",
                    "Data Inicial (yyyy-MM-dd)": ini.isoformat(),
                    "Data Final (yyyy-MM-dd)": fim.isoformat(),
                },
                timeout=90,
            )
            resp.raise_for_status()
            corpo = resp.json()
            return corpo.get("items") or []
        except (
            requests.exceptions.ReadTimeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
        ) as e:
            ultimo_erro = e
            status = getattr(e.response, "status_code", None) if hasattr(e, "response") else None
            if status is not None and status not in (503, 429) and status < 500:
                raise
            espera = ESPERA_BASE_S * tentativa
            print(
                f"    janela {ini}..{fim}: tentativa {tentativa}/{TENTATIVAS_POR_JANELA} "
                f"falhou ({e!r}); aguardando {espera}s...",
                file=sys.stderr,
            )
            time.sleep(espera)
    raise RuntimeError(f"estação {codigo}, janela {ini}..{fim}: esgotadas as tentativas") from ultimo_erro


def baixar_estacao(
    sessao: SessaoAna, codigo: str, ini: date, fim: date, delay_s: float
) -> pd.DataFrame:
    linhas: list[dict] = []
    for j_ini, j_fim in janelas(ini, fim):
        linhas.extend(buscar_janela(sessao, codigo, j_ini, j_fim))
        time.sleep(delay_s)
    if not linhas:
        return pd.DataFrame()
    df = pd.json_normalize(linhas)
    if "Data_Hora_Dado" in df.columns:
        df = df.sort_values("Data_Hora_Dado").reset_index(drop=True)
    return df


def carregar_inventario() -> pd.DataFrame:
    df = pd.read_parquet(INVENTARIO)
    pluv = df[df["Tipo_Estacao_Pluviometro"] == "1"].drop_duplicates("codigoestacao").copy()
    pluv["ini"] = pd.to_datetime(pluv["Data_Periodo_Pluviometro_Inicio"], errors="coerce")
    pluv["fim"] = pd.to_datetime(pluv["Data_Periodo_Pluviometro_Fim"], errors="coerce")
    pluv["fim"] = pluv["fim"].fillna(pd.Timestamp.today().normalize())
    pluv = pluv.dropna(subset=["ini"])
    return pluv.sort_values("codigoestacao")[["codigoestacao", "Estacao_Nome", "ini", "fim"]]


def registrar_log(codigo: str, status: str, n_linhas: int, mensagem: str) -> None:
    linha = pd.DataFrame(
        [
            {
                "codigoestacao": codigo,
                "timestamp": pd.Timestamp.now().isoformat(),
                "status": status,
                "n_linhas": n_linhas,
                "mensagem": mensagem,
            }
        ]
    )
    linha.to_csv(LOG, mode="a", header=not LOG.exists(), index=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="processar só as N primeiras estações")
    ap.add_argument("--forcar", action="store_true", help="rebaixar mesmo se o CSV já existir")
    ap.add_argument("--delay", type=float, default=0.4, help="pausa entre requisições, em segundos")
    args = ap.parse_args()

    DIR_RAW.mkdir(parents=True, exist_ok=True)
    inventario = carregar_inventario()
    if args.limit:
        inventario = inventario.head(args.limit)

    print(f"{len(inventario)} estações pluviométricas a processar.")
    sessao = SessaoAna()

    ok = pulada = erro = 0
    for i, row in enumerate(inventario.itertuples(index=False), start=1):
        codigo = row.codigoestacao
        destino = DIR_RAW / f"{codigo}.csv"
        if destino.exists() and not args.forcar:
            pulada += 1
            continue

        ini = row.ini.date()
        fim = row.fim.date()
        print(f"[{i}/{len(inventario)}] {codigo} ({row.Estacao_Nome}) — {ini}..{fim}")
        try:
            df = baixar_estacao(sessao, codigo, ini, fim, args.delay)
        except (AutenticacaoError, RuntimeError) as e:
            print(f"  ERRO: {e}", file=sys.stderr)
            registrar_log(codigo, "erro", 0, str(e))
            erro += 1
            continue

        if df.empty:
            registrar_log(codigo, "vazio", 0, "API não retornou registros")
            erro += 1
            continue

        df.to_csv(destino, index=False)
        registrar_log(codigo, "ok", len(df), "")
        ok += 1
        print(f"  salvo: {destino.name} ({len(df)} registros mensais)")

    print(f"\nResumo: {ok} ok, {pulada} puladas (já existiam), {erro} com erro.")
    print(f"Log detalhado em {LOG}")


if __name__ == "__main__":
    main()
