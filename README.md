# Tendências de precipitação extrema em Santa Catarina

TCC — análise espaço-temporal de séries históricas de precipitação da rede da ANA.

## Ambiente

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Estrutura

```
data/raw/        CSVs originais da ANA — NUNCA editar
data/interim/    séries diárias em formato long, por estação
data/processed/  índices anuais e resultados de tendência
src/             código de produção
notebooks/       exploração (não é produção)
outputs/         figuras e tabelas que entram no texto
docs/            DECISOES.md — registro metodológico
tests/           testes de regressão
```

## Uso

```bash
# ler uma estação e ver o relatório
python src/parse.py data/raw/ibirama_1941_2026.csv

# ler e salvar em Parquet
python src/parse.py data/raw/ibirama_1941_2026.csv data/interim/2749005.parquet

# validar o parser
pytest -v
```

## Estação de referência

2749005 (Ibirama) — 1941-2026, 98,9% de cobertura. Usada como verdade conhecida
nos testes de regressão. Ver `docs/DECISOES.md`.
