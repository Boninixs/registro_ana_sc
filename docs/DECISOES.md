# Registro de decisões metodológicas

> **Como usar:** toda escolha metodológica entra aqui, com data e justificativa,
> **no momento em que é tomada**. Na Fase 7 este arquivo vira o capítulo de
> Metodologia quase por transcrição — e é o que te salva na arguição quando
> a banca perguntar "por que 1 mm?".
>
> Formato: `AAAA-MM-DD — [Fase X] Decisão. Justificativa. (Referência)`

---

## Fase 0 — Fundação

**2026-08-23 — [Fase 0] Estação de referência para validação do parser: 2749005 (Ibirama).**
Série de 1941-01-01 a 2026-04-30 com 98,9% de cobertura (30.814 dias com valor),
conferida manualmente. Serve como teste de regressão: qualquer alteração no parser
que quebre estes números indica erro no código, não no teste.
Valores travados em `tests/test_parse.py`.

**2026-08-23 — [Fase 0] Deduplicação por nível de consistência: preferir sempre nível 2.**
O formato da ANA repete o mesmo mês como bruto (nível 1) e consistido (nível 2).
Em Ibirama, 738 dos 1.015 meses estão duplicados. Sem a regra, os registros
duplicariam e distorceriam toda contagem de frequência.
Caso o consistido exista mas sem valor, mantém-se o consistido: a ausência é
informação (o operador removeu o dado deliberadamente).

**2026-08-23 — [Fase 0] Status 4 ("acumulado") descartado das análises de extremos.**
Nesse status, o valor registrado num dia é a soma de vários dias anteriores,
gerando extremos falsos — exatamente o fenômeno que o trabalho quer medir.
Ibirama tem 9 ocorrências. Status 0 ("branco") também é descartado por ser
ausência de leitura.

**2026-08-23 — [Fase 0] Status 3 ("duvidoso") é marcado, não removido.**
Mantido em `flag_duvidoso` para permitir teste de sensibilidade na Fase 5
(rodar as tendências com e sem esses dias e verificar se o resultado muda).
Ibirama tem 4 ocorrências.

**2026-08-23 — [Fase 0] Princípio geral: o parser nunca apaga dado, apenas marca.**
Toda exclusão é decisão da etapa de análise e precisa ser reversível.
A coluna `valido_extremos` consolida a regra vigente sem destruir o original.

---

## Fase 1 — Aquisição

<!-- Registrar: fonte usada (API HidroWebService ou download manual), data da
     extração, versão/endpoint, nº de estações no inventário de SC. -->

---

## Fase 2 — Pipeline ETL

<!-- Registrar: formato de armazenamento, particionamento, tratamento de
     estações com formato divergente. -->

---

## Fase 3 — Qualidade e seleção

<!-- Registrar: limiar físico implausível adotado; critérios de seleção
     (anos mínimos, % de falhas, lacuna máxima); período comum escolhido e a
     curva estações × ano de início que embasou a escolha; resultado dos testes
     de homogeneidade; DECISÃO DE ESCOPO (estadual vs. bacia). -->

---

## Fase 4 — Índices de extremos

<!-- Registrar: limiar de dia úmido; período-base dos percentis; regra de ano
     válido; resultado da validação contra RClimDex/xclim. -->

---

## Fase 5 — Tendências

<!-- Registrar: variante de Mann-Kendall (TFPW ou Hamed-Rao); nível de
     significância; método de correção para múltiplos testes. -->

---

## Fase 6 — Espacial e sazonal

<!-- Registrar: recorte regional adotado (mesorregiões IBGE ou bacias) e por quê;
     decisão de não interpolar. -->
