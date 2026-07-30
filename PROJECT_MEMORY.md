# Memória persistente — Gamma Levels Swing CALL

Atualizado em 30/07/2026, fuso America/Sao_Paulo.

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
- Dashboard lista dinamicamente os 75 estudos completos disponíveis na aba Histórico.
- A API é multiativo; usar `?ticker=TICKER` nos endpoints anuais.
- `GET /api/backtest/tickers` lista os bancos com run final `COMPLETE`.

### VPS Ubuntu temporária

- VPS criada e acessada em uma sessão separada do Codex; esta sessão do Windows não controla a VPS.
- A pasta local `vps/` foi criada para conexão e transferência e contém material SSH privado;
  ela e arquivos `*.pem` devem permanecer ignorados pelo Git e nunca enviados ao GitHub.
- CPU informada: Intel Xeon Platinum 8259CL, 8 núcleos/16 threads, tratada como 16 vCPUs
  dedicadas conforme confirmação do usuário.
- Memória real: aproximadamente 62 GiB utilizáveis (plano comercial de 64 GB), com cerca
  de 60 GiB disponíveis no diagnóstico inicial.
- Disco: Amazon EBS SSD gp3 de 500 GB, com aproximadamente 481 GiB livres no diagnóstico inicial.
- Carga inicial praticamente ociosa; swap não configurado.
- O usuário pediu uso de `tmux` para manter processos após desconexão SSH; instalação efetiva
  deve ser confirmada na própria VPS.
- Estratégia de workers: começar com 8, medir CPU/RAM/espera de disco, depois testar 10 e 12.
- Inventário informado na VPS: cerca de 93 GB no total, sendo 88 GB de arquivos brutos B3
  dos 345 pregões, 834 MB de cache interpretado, 3,9 GB de bancos de estudos/resultados
  e aproximadamente 13 MB de logs.
- Os créditos da VPS são temporários e o usuário pretende encerrá-la. Antes de terminar a
  instância ou apagar o EBS, preservar obrigatoriamente bancos, logs, rankings, manifestos,
  configurações e hashes; confirmar tamanho e SHA-256 depois da transferência.
- Para analisar estudos como PETR4/VALE3/ITUB4/BBDC4, os bancos SQLite completos são suficientes:
  permitem métricas, operações, entradas, saídas, MFE, MAE, drawdown e divisões amostrais.
  Os 88 GB brutos e o cache não são necessários para examinar resultados já calculados, mas
  seriam necessários para recalcular com novas regras ou auditar novamente a fonte B3.
- Código, documentação, `AGENTS.md` e `PROJECT_MEMORY.md` ficam no repositório privado;
  dados B3, caches, SQLite, planilhas, segredos e dependências geradas ficam fora do Git.
- Em 30/07/2026 a fila da VPS já havia terminado e foi consultada por SSH. Não havia
  `batch_cli`, `monitor_cli` ou backtest ativo; somente a sessão tmux/Codex permaneceu aberta.
- O pacote validado foi transferido para `vps/results/gamma-results-20260730.tar.zst` no Windows:
  606.342.028 bytes, SHA-256 `e60163293ca3ef3e68e192b885bb13d591254be8bed5cedaa573ae72b8d80754`.
  O pacote contém os 71 bancos completos, logs, lista, status e manifestos, mas não contém
  `.env.telegram`, dados brutos ou caches. Não é necessário baixá-lo novamente.

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

### Cesta da VPS — 71 bancos integrados em 30/07/2026

- Fila final: 71/79 estudos completos e 8 erros. Os 71 bancos foram abertos em modo somente
  leitura, passaram `PRAGMA quick_check`, tiveram SHA-256 calculado na VPS e foram novamente
  validados após a extração no Windows; houve zero divergência de hash.
- Os oito excluídos da integração oficial foram AXIA3, AXIA6, AXIA7, EMBJ3, MBRF3, MOTV3,
  NATU3 e POMO4. Os sete primeiros não completaram a janela histórica; POMO4 tem banco íntegro,
  mas run final `INCOMPLETE`, 780 métricas e mensagem de resultado parcial, por isso não entra.
- Total local após a integração: 75 bancos `COMPLETE` e íntegros — os 71 da VPS mais PETR4,
  VALE3, ITUB4 e BBDC4. Os quatro bancos originais permaneceram intocados.
- Relatório consolidado: `resultado_excel/ranking_consolidado_75_ativos.xlsx`, com as abas
  `Resumo_Ativos`, `Ranking_Estavel`, `Treino_e_OOS`, `Todas_Combinacoes` e `Metodologia`.
  Versão auditável em JSON: `resultado_excel/ranking_consolidado_75_ativos.json`.
- A estrutura e os valores da planilha foram reabertos programaticamente, mas a verificação
  visual especializada com `artifact-tool` não pôde ser executada porque o carregador obrigatório
  dessa ferramenta não estava disponível na sessão; o JSON é a referência auditável principal.
- Critério comparativo principal do relatório: posições independentes, pelo menos 10 operações
  no período completo. Classificação estritamente estável exige treino >=3 operações,
  validation_1 >=2, validation_2 >=2 e expectativa positiva no completo e em cada divisão.
  A ordenação usa primeiro a pior expectativa entre as três divisões, evitando escolher apenas
  a maior expectativa bruta.
- Distribuição dos 75 ativos: 2 `STRICTLY_STABLE`, 5 `POSITIVE_TRAIN_AND_OOS`,
  3 `POSITIVE_FULL_ONLY`, 34 `LOW_SAMPLE` e 31 `NO_TRADES`.
- Somente VALE3 e BBDC4 passaram o critério estrito com amostra >=10. Nenhum dos 71 ativos novos
  passou simultaneamente treino, validation_1 e validation_2 nesse tamanho de amostra.
- Entre os novos, PETR3, CMIG4, BBAS3 e B3SA3 tiveram combinação com >=10 operações e resultado
  positivo no treino e no OOS agregado, mas falharam estabilidade por validation_2 negativa ou
  sem operações. PRIO3 teve treino negativo; USIM5 não teve operações no treino.
- ITSA4 é o destaque exploratório de baixa amostra: `score_75 + PARTIAL_25_CALCULATED`,
  7 operações, 85,7% de acerto, expectativa +44,93%, PF 70,56 e OOS +59,79%, com todas as
  divisões positivas; ainda assim, sete operações não permitem tratá-la como evidência robusta.
- PRIO3 também produziu números brutos muito altos com nove operações no baseline até o
  vencimento, mas permanece abaixo da amostra mínima e não deve ser promovida só pelo retorno.

## Dados e preservação

- Os 75 estudos completos usam bancos separados em `data/pilot_<ticker>/gamma_levels.db`;
  um estudo não sobrescreve outro.
- No Windows, arquivos brutos B3 ficam em `data/raw` (medição histórica: 1.036 arquivos,
  cerca de 3,05 GB). Não confundir esse conjunto local com os cerca de 88 GB informados na VPS.
- Cache interpretado por ativo/pregão fica em `data/parsed` usando Parquet com Zstandard.
- `GET /api/backtest/latest` limita a lista exibida; 1.000 linhas retornadas não são o total oficial.
- Métricas e trajetórias oficiais ficam no SQLite de cada ativo.
- Os dados estão persistidos localmente, mas não constituem backup externo.
- Para encerrar a VPS com segurança, o pacote mínimo deve conter os aproximadamente 3,9 GB
  de bancos, 13 MB de logs, rankings, manifestos, configurações e checksums. Não considerar
  o backup concluído até baixar o pacote e conferir o SHA-256 fora da VPS.
- Essa transferência mínima foi concluída e conferida no Windows em 30/07/2026. Os 88 GB brutos
  e o cache da VPS continuam dispensáveis para analisar os estudos já calculados, mas ainda são
  necessários se Matheus quiser recalcular novas regras sem baixar os pregões novamente.

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

- Após a integração da cesta, 27 testes Python foram aprovados no Windows; lint e build do
  dashboard também foram aprovados.
- Um sinal VALE3 de 08/07/2025 foi recalculado após a otimização e manteve exatamente
  status, score 81,5, CALL VALEG565, prêmio máximo, suporte e resistência.
- `scripts/validate_result_banks.py` valida integridade, run final, contagens e SHA-256 dos bancos.
- `scripts/analyze_result_universe.py` reproduz a classificação e a planilha consolidada.
- A API reiniciada em 30/07/2026 respondeu 75 ativos em `/api/backtest/tickers`; BBAS3 foi
  consultada pela API e retornou run `COMPLETE` com 1.140 métricas.

## Como retomar rapidamente

1. Ler este arquivo inteiro.
2. Identificar se a sessão está no Windows local ou na VPS Ubuntu; são ambientes separados.
3. O backup mínimo da VPS já foi transferido e validado; não repetir. Antes de encerrar a VPS,
   decidir apenas se os 88 GB brutos/cache também serão preservados para futuros recálculos.
4. Garantir que alterações de código e desta memória foram commitadas e enviadas ao GitHub.
5. No Windows, consultar `http://127.0.0.1:8000/api/health`; se necessário, executar
   `scripts/start_dashboard.ps1`.
6. A fila da VPS terminou; não existe backtest em andamento confirmado nesta memória.
7. Os bancos da VPS já estão integrados ao dashboard e o ranking consolidado já foi gerado.
8. Não escolher apenas o maior número: observar operações, PF, expectativa, estabilidade e drawdown.

Próximos candidatos líquidos observados em 27/07/2026: PRIO3, BBAS3, GGBR4, WEGE3 e B3SA3.
BRAV3 tinha volume muito alto, mas exige avaliar continuidade histórica e eventos corporativos antes do anual.
