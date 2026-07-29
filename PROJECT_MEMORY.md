# Memória persistente — Gamma Levels Swing CALL

Atualizado em 28/07/2026, fuso America/Sao_Paulo.

## Objetivo e decisões do usuário

- Operação exclusivamente swing trade; não focar intraday.
- Somente compra de CALL a seco para expectativa de alta.
- Dados de fechamento D-1 são suficientes; não depender de RTD nem de dados ao vivo.
- Considerar opções com no mínimo 10 dias até o vencimento (janela operacional atual: 10–60 DTE).
- O usuário é experiente, conhece o risco e aceita perder integralmente o prêmio destinado à opção.
- A análise deve usar números para identificar entrada e saída, incluindo parciais.
- Objetivo de movimentos nas opções entre 10% e 100%, conforme os cálculos.
- Prioridade: poucos sinais seletivos, várias ações líquidas e validação histórica auditável.
- Estudos devem usar as mesmas regras entre ativos para permitir comparação justa.

## Sistema atual

- Projeto: `E:\gamma levels`
- Repositório privado: `https://github.com/zxtheuxz/gamma-levels`, branch `main`.
- API local: `http://127.0.0.1:8000`
- Dashboard: `http://localhost:3000`
- Versão ativa: 0.3.3
- Iniciador: `scripts/start_dashboard.ps1`
- Execução manual PETR4: `Executar_Backtest_Anual_PETR4.cmd`
- Dashboard alterna PETR4, VALE3, ITUB4 e BBDC4 na aba Histórico.
- A API é multiativo; usar `?ticker=TICKER` nos endpoints anuais.

### VPS planejada para processamento em lote

- Sistema operacional: Ubuntu.
- CPU: 16 vCPUs dedicadas.
- Memória: 64 GB de RAM.
- Disco: Amazon EBS SSD gp3 de 500 GB.
- Estratégia inicial: preparar o projeto para Linux e executar uma fila com 8–10 workers,
  aumentando para 12 somente depois de medir CPU, RAM e espera de disco.
- Código, documentação, `AGENTS.md` e `PROJECT_MEMORY.md` irão para repositório privado;
  dados B3, caches, SQLite, planilhas, segredos e dependências geradas ficarão fora do Git.

Endpoints principais:

- `GET /api/health`
- `POST /api/backtest`
- `GET /api/backtest/status?ticker=PETR4`
- `GET /api/backtest/latest?ticker=PETR4`
- `GET /api/backtest/trades/{trade_id}?ticker=PETR4`
- `GET /api/backtest/export.xlsx?ticker=PETR4`

## Metodologia do estudo anual

- 345 pregões carregados, 50 de aquecimento e 254 datas avaliáveis.
- Contexto formado até D-1; ordem limitada em D0.
- Entrada na abertura se `open <= limite`; entrada tardia no limite se `low <= limite`.
- Entrada tardia não recebe alvo intradiário no mesmo dia por ambiguidade do OHLC.
- Sinal não executado fica fora das métricas oficiais, mas conserva trajetória de referência.
- Acompanhamento diário até o vencimento: MFE, MAE, drawdown, retorno e evidências de saída.
- Custos atuais iguais a zero, mas configuráveis.
- Ações corporativas e Selic histórica são incorporadas.
- Amostras: período completo, treino 126, validação 1, validação 2 e fora da amostra.
- Modos de sobreposição: operações independentes e apenas uma posição por vez.

Seis estratégias de saída:

1. `HOLD_TO_EXPIRY`
2. `CALCULATED_EXIT`
3. `PARTIAL_25`
4. `PARTIAL_50`
5. `LADDER_25_50_100`
6. `PARTIAL_25_CALCULATED`

São testadas 19 variantes: baseline, região padrão, três pares de EMA, dois períodos
de RSI, dois pisos de RSI, duas tolerâncias ATR, lookbacks de região 20 e 50,
dois filtros de volume, scores 75/85 e RR 1,25/2,00.

## Resultados preservados

### PETR4 — banco `data/pilot_petr4/gamma_levels.db`

- Execução oficial: run 4, `COMPLETE`.
- Período: 11/03/2025 a 27/07/2026; 1.140 métricas.
- Melhor combinação: `score_85 + CALCULATED_EXIT`.
- 11 operações, 6 vencedoras, 54,5% de acerto.
- Expectativa +14,47%; PF 1,49; ganho médio +80,84%; perda média -65,17%.
- `score_85 + PARTIAL_25_CALCULATED`: 72,7% de acerto, expectativa +2,07%, PF 1,08.
- A referência antiga de aproximadamente +49,8% permanece no piloto, mas não é entrada oficial quando o limite não executa.

### VALE3 — banco `data/pilot_vale3/gamma_levels.db`

- Execução oficial: run 1, `COMPLETE`.
- Período: 11/03/2025 a 27/07/2026; 1.140 métricas.
- Melhor combinação: `region_lookback_20 + CALCULATED_EXIT`.
- 29 operações, 21 vencedoras, 72,4% de acerto.
- Expectativa +53,84%; PF 3,87; ganho médio +100,24%; perda média -67,97%.
- `region_lookback_20 + HOLD_TO_EXPIRY`: 62,1% de acerto, expectativa +55,75%, PF 2,90.
- Fora da amostra, saída calculada: 13 operações, 61,5% de acerto, expectativa +94,54%, PF 4,09.
- Atenção: validation_2 teve somente quatro operações e resultado negativo; não ignorar instabilidade da amostra.
- Baseline até o vencimento: 18 operações, 66,7% de acerto, expectativa +43,51%, PF 2,51.

### ITUB4 — banco `data/pilot_itub4/gamma_levels.db`

- Execução oficial: run 1, `COMPLETE`.
- Período: 11/03/2025 a 27/07/2026; 1.140 métricas.
- Melhor combinação: `score_75 + PARTIAL_25_CALCULATED`.
- 12 operações, 9 vencedoras, 75% de acerto.
- Expectativa +12,91%; PF 2,11; ganho médio +32,67%; perda média -46,36%.
- `score_75 + CALCULATED_EXIT`: 50% de acerto, expectativa +11,25%, PF 1,50.
- Fora da amostra, score 75 com parcial calculada: 7 operações, 71,4% de acerto, expectativa +7,78%, PF 1,48.
- Baseline original foi negativo; filtro e saída foram essenciais.

### BBDC4 — banco `data/pilot_bbdc4/gamma_levels.db`

- Execução oficial: run 1, `COMPLETE`; duração aproximada de 58 minutos e 53 segundos.
- Período: 11/03/2025 a 27/07/2026; 254 datas avaliáveis e 1.140 métricas.
- Estudo executado com as mesmas regras para comparar o setor bancário com ITUB4.
- Motivo da escolha em 27/07/2026: aproximadamente R$ 16,0 milhões de volume financeiro em CALLs,
  8 mil negócios e 586 milhões de posição em aberto somada.
- Melhor expectativa bruta: `ema_9_21 + HOLD_TO_EXPIRY`: 18 operações, 61,1% de acerto,
  expectativa +56,15%, PF 2,70 e ganho médio +145,99%; porém, fez 0/2 em `validation_2`
  e implica perdas médias de -85,03%, portanto não é a combinação mais estável.
- Combinação mais equilibrada: `region_lookback_50 + CALCULATED_EXIT`: 17 operações,
  15 vencedoras, 88,2% de acerto, expectativa +37,43%, PF 5,62, ganho médio +51,60%
  e perda média -68,82%. Fora da amostra: 7 operações, 6 vencedoras, 85,7% de acerto,
  expectativa +21,70% e PF 2,52. Permaneceu positiva em treino, validation_1 e validation_2,
  embora as subamostras sejam pequenas.
- Alternativa mais seletiva: `score_85 + CALCULATED_EXIT`: 10 operações, 8 vencedoras,
  80% de acerto, expectativa +33,04%, PF 15,49, ganho médio +44,15% e perda média -11,40%.
  Com `PARTIAL_25_CALCULATED`: 10 operações, 9 vencedoras, 90% de acerto,
  expectativa +27,00% e PF 18,66. Fora da amostra são apenas 4 operações, todas positivas.
- Baseline com saída calculada ficou negativo: 11 operações, 36,4% de acerto,
  expectativa -1,24% e PF 0,94. Os filtros fizeram diferença material.
- Alvos atingidos pela combinação de região 50: 10% em 17/17, 25% em 16/17,
  50% em 12/17 e 100% em 7/17.

## Dados e preservação

- PETR4, VALE3, ITUB4 e BBDC4 usam bancos separados; um estudo não sobrescreve outro.
- Arquivos brutos B3 ficam em `data/raw` (última medição: 1.036 arquivos, cerca de 3,05 GB).
- Cache interpretado por ativo/pregão fica em `data/parsed` usando Parquet com Zstandard.
- `GET /api/backtest/latest` limita a lista exibida; 1.000 linhas retornadas não são o total oficial.
- Métricas e trajetórias oficiais ficam no SQLite de cada ativo.
- Os dados estão persistidos localmente, mas não constituem backup externo.

## Otimizações implementadas

- Modelo binomial americano vetorizado, com preços idênticos à implementação anterior.
- Benchmark unitário: aproximadamente 4,2 vezes mais rápido.
- Busca binária reduzida de 60 para 32 passos, mantendo precisão abaixo de um centavo.
- Cache de barras ajustadas, indicadores, regiões, juros, mercado de opções, projeções e trajetórias.
- Variantes que mudam apenas limiar reaproveitam cálculos-base.
- Ativo único não recalcula desnecessariamente o universo amplo.
- Cache Parquet real ITUB4: primeira interpretação 7,87 s; releitura 0,17 s.
- Três leituras ZIP paralelas foram testadas, ficaram mais lentas por disputa de disco e foram removidas.

## Validação técnica

- 26 testes Python aprovados; lint e build do dashboard aprovados.
- Um sinal VALE3 de 08/07/2025 foi recalculado após a otimização e manteve exatamente
  status, score 81,5, CALL VALEG565, prêmio máximo, suporte e resistência.

## Como retomar rapidamente

1. Ler este arquivo inteiro.
2. Consultar `http://127.0.0.1:8000/api/health`.
3. Consultar o status do ativo em andamento, atualmente BBDC4.
4. Se os serviços não responderem, executar `scripts/start_dashboard.ps1`.
5. Se o estudo foi interrompido, reenviar `POST /api/backtest` com ticker, raiz, 345 sessões,
   aquecimento 50, avaliação 252 e custos zero; ele retoma os pregões persistidos.
6. Quando BBDC4 terminar, atualizar aqui os melhores resultados completos e fora da amostra.
7. Não escolher apenas o maior número: observar operações, PF, expectativa, estabilidade e drawdown.

Próximos candidatos líquidos observados em 27/07/2026: PRIO3, BBAS3, GGBR4, WEGE3 e B3SA3.
BRAV3 tinha volume muito alto, mas exige avaliar continuidade histórica e eventos corporativos antes do anual.
