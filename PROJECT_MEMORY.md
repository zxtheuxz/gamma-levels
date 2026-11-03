# Memória persistente — Gamma Levels Swing CALL

Atualizado em 03/11/2026, fuso America/Sao_Paulo.

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

### Listas de ativos definidas em 30/07/2026

- Cesta candidata operacional definida pelo usuário: VALE3, BBDC4, PETR3, BBAS3, B3SA3,
  CMIG4, ITUB4, PRIO3, USIM5, PETR4 e ITSA4. A inclusão na cesta não substitui o sinal:
  uma operação continua exigindo que a regra global/operacional gere entrada e cumpra os filtros.
- Nível de evidência dentro da cesta: VALE3 e BBDC4 são os mais consistentes; PETR3, BBAS3,
  B3SA3, CMIG4 e ITUB4 ficaram positivos em treino e OOS no ranking descritivo; PRIO3, USIM5
  e PETR4 ficaram positivos apenas no agregado; ITSA4 é inclusão exploratória de baixa amostra.
- Fila separada para aprofundar estudos, ainda fora da cesta candidata operacional: RENT3,
  SUZB3 e DIRR3. Seus resultados atuais são, respectivamente, +279,90% com 1 operação,
  +136,13% com 2 e +122,22% com 1; são observações exploratórias, não evidência suficiente.
- O snapshot antigo de 27–28/07 foi superado pela atualização oficial iniciada em 30/07/2026.
  A API principal completou 120 pregões e incorporou o fechamento de 29/07/2026. O scanner
  baseline do universo top-20 encontrou zero `COMPRAR CALL`, 9 `AGUARDAR` e 11 `DESCARTAR`.
  A validação histórica de 69 datas continuou em segundo plano depois que o ranking atual já
  havia sido calculado e persistido.
- Recalculo somente leitura da cesta operacional na data 29/07, usando para cada ticker a variante
  que o colocou na lista: zero ativações; BBDC4, PETR3, BBAS3, ITUB4, PRIO3 e PETR4 ficaram em
  `AGUARDAR`; VALE3, B3SA3, CMIG4, USIM5 e ITSA4 ficaram em `DESCARTAR`.
- Mais próximos nesse snapshot: PETR4 tinha score 79,52 ante piso 85, CALL `PETRH427`, RR 1,98
  e projeção conservadora de 5 dias +65,25%, mas ainda sem setup; BBAS3 tinha score 68,76 ante
  piso 75, CALL `BBASH205`, RR 1,98 e projeção +19,28%, também sem setup; PRIO3 tinha score
  79,31 ante piso 80 e RR 1,58, mas sem setup e sem CALL aprovada. Nenhum deles estava pronto
  para entrada; não antecipar sinal.

## Rotina diária D-1 da cesta (criada em 30/07/2026)

- Script: `scripts/daily_basket_scan.py`. O usuário decidiu que ele é disparado sob demanda
  nesta sessão, sem agendamento no Windows e sem `.cmd` na raiz.
- O script ingere todo pregão publicado entre a última sessão do banco e ontem, varrendo dia
  a dia. Isso é deliberado: `latest_available_date()` da B3 às vezes ignora o pregão mais
  recente — em 30/07/2026 ele devolveu 28/07 mesmo com 29/07 já publicado e carregado.
- Cada ticker é lido duas vezes no mesmo pregão: com a variante que o colocou na cesta e com
  a regra global `score_85`. As duas leituras aparecem lado a lado; nenhuma substitui a outra.
- As variantes não são redefinidas no script: ele importa `standard_variants()` de `study.py`,
  então o cálculo diário usa exatamente o mesmo código do backtest anual.
- Ativação exige o conjunto completo da regra: score >= piso, RSI >= piso da variante, setup
  presente, CALL aprovada nos filtros, RR >= mínimo e projeção conservadora de 5 dias >= 10%.
  Quando não ativa, o script imprime qual condição faltou. Não antecipar sinal.
- Alerta por Telegram só quando algum ticker vira `COMPRAR CALL`; `--sempre` força o envio.
  Credenciais em `.env.telegram` na raiz, ignorado pelo Git via `.env.*`; nunca commitar.
  Canal validado com envio real em 30/07/2026. Outras opções (`--sem-download`, `--sem-telegram`,
  `--data`, `--tickers`) existem para auditoria pontual.
- O usuário optou por não gerar JSON, Markdown ou Excel diário; a saída é console mais Telegram.
  Portanto não há histórico persistido das verificações diárias até que ele peça.
- `scripts/extend_daily_history.py` elevou o banco diário de 120 para 150 pregões em 30/07/2026,
  cobrindo agora 18/12/2025 a 29/07/2026. O motivo é que o estudo anual usa 140 pregões de
  contexto e o banco diário nascera com 120, produzindo números levemente diferentes.
- Leitura oficial de 29/07/2026 já com 150 pregões: zero ativações nas 20 leituras. `AGUARDAR`
  em BBDC4, PETR3, BBAS3, ITUB4, PRIO3 e PETR4; `DESCARTAR` em VALE3, B3SA3, CMIG4, USIM5 e
  ITSA4. Nenhum ativo tinha setup — esse foi o bloqueio comum a todos.
- A janela maior mudou levemente os scores ante o recálculo com 120 pregões: PETR4 79,39 (era
  79,52), BBAS3 69,01 (era 68,76) e PRIO3 81,81 (era 79,31). Pela regra global, PRIO3 marcou
  88,27 acima do piso 85, mas continuou sem setup e sem CALL aprovada, logo sem entrada.
- Observação a vigiar: a projeção de 5 dias de PETR3 saiu em +741,24% com a CALL `PETRH452` e
  RR 1,19. É um número de CALL muito barata, não um sinal; o RR abaixo do mínimo já a bloqueava.

## Sistema atual

- Projeto: `E:\gamma levels`
- Repositório privado: `https://github.com/zxtheuxz/gamma-levels`, branch `main`.
- API local: `http://127.0.0.1:8000`
- Dashboard: `http://localhost:3000`
- Versão ativa: 0.4.0
- Iniciador: `scripts/start_dashboard.ps1`
- Execução manual PETR4: `Executar_Backtest_Anual_PETR4.cmd`
- Dashboard lista dinamicamente os 75 estudos completos disponíveis na aba Histórico.
- A API é multiativo; usar `?ticker=TICKER` nos endpoints anuais.
- `GET /api/backtest/tickers` lista os bancos com run final `COMPLETE`.

### VPS Ubuntu temporária

- A instância VPS e seu armazenamento foram excluídos pelo usuário em 30/07/2026, apó a
  validação dos backups. O antigo IP `18.216.112.18` não deve mais ser usado nem tratado como
  ambiente disponível. Os 88 GB de dados brutos e o cache remoto foram deliberadamente descartados.
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
- Antes do encerramento, o código não commitado existente apenas na VPS também foi preservado
  separadamente em `vps/results/gamma-vps-uncommitted-code-20260730.tar.gz`, SHA-256
  `d49aba544d836f89d0502db3823001359ec48c838190fe6206040478843ed552`. Ele parte do commit
  remoto `f5805cf248cdf471935c5130d25adb5dd25458ae` e contém os utilitários `batch_cli.py`,
  `monitor_cli.py`, `prefetch_cli.py`, ajustes em `b3.py`/`pyproject.toml` e respectivos testes.
  O pacote foi listado e conferido no Windows sem sobrescrever o código atual.
- Na verificação final de 30/07/2026 não havia Python de estudo, fila, monitor ou prefetch
  ativo na VPS; restavam somente processos do sistema e a sessão `tmux`. A API do Windows
  estava saudável e listava os 75 estudos completos. A VPS pode ser encerrada se não houver
  interesse em preservar os 88 GB brutos/cache para recálculos futuros.

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
- Somente VALE3 e BBDC4 passaram o critério estrito do relatório com amostra >=10. Nenhum dos
  71 ativos novos passou simultaneamente treino, validation_1 e validation_2 nesse tamanho de
  amostra. Isso descreve apenas essa régua conservadora por ativo; não significa que a cesta falhou.
- Entre os novos, PETR3, CMIG4, BBAS3 e B3SA3 tiveram combinação com >=10 operações e resultado
  positivo no treino e no OOS agregado, mas falharam estabilidade por validation_2 negativa ou
  sem operações. PRIO3 teve treino negativo; USIM5 não teve operações no treino.
- ITSA4 é o destaque exploratório de baixa amostra: `score_75 + PARTIAL_25_CALCULATED`,
  7 operações, 85,7% de acerto, expectativa +44,93%, PF 70,56 e OOS +59,79%, com todas as
  divisões positivas; ainda assim, sete operações não permitem tratá-la como evidência robusta.
- PRIO3 também produziu números brutos muito altos com nove operações no baseline até o
  vencimento, mas permanece abaixo da amostra mínima e não deve ser promovida só pelo retorno.
- Auditoria adicional dos 34 ativos `LOW_SAMPLE` em 30/07/2026: somente 10 tinham pelo menos
  três operações no treino para permitir uma escolha minimamente auditável por ativo. Escolhendo
  a combinação exclusivamente pela maior expectativa no treino, eles somaram 35 operações,
  74,3% de acerto, expectativa +41,48% e PF 3,66. A mesma escolha no OOS somou 21 operações,
  28,6% de acerto, expectativa -41,90% e PF 0,20; oito ativos operaram e somente BRAV3 ficou
  positivo (`score_75 + LADDER_25_50_100`, 3 trades OOS, +58,33%). CSNA3 e RADL3 não tiveram
  trade OOS. Isso confirma forte sobreajuste quando se tenta otimizar individualmente os ativos
  com pouca amostra.
- ITSA4 não entrou nessa auditoria train-only porque sua combinação destacada tinha apenas duas
  operações no treino. Continua sendo candidata a validação futura, não regra comprovada.

### Auditoria corretiva da interpretação da cesta em 30/07/2026

- A conclusão inicial de que "nenhum dos 71 funcionou" estava errada: ela comparava o melhor
  resultado exploratório entre 114 combinações dos quatro ativos originais com uma exigência
  posterior muito mais dura aplicada aos 71. Não repetir essa comparação assimétrica.
- Integridade confirmada nos dois ativos com raiz sobreposta: nos 344 pregões comuns,
  PETR4 teve 344/344 linhas do subjacente e 804.464/804.464 cotações de opções idênticas;
  BBDC4 teve 344/344 e 538.092/538.092, respectivamente. `study.py`, `swing.py` e `storage.py`
  também tinham SHA-256 idêntico no Windows e na VPS. Não foi encontrada corrupção ou
  diferença de cálculo na VPS.
- Auditoria honesta por ativo, escolhendo a combinação somente pelo treino com >=3 operações
  e avaliando a mesma combinação no OOS: os quatro originais somaram 32 operações no treino,
  expectativa +61,25%, mas 18 no OOS com expectativa -25,29%; apenas 1/4 ficou positivo. Logo,
  a impressão de que os quatro haviam funcionado decorreu em grande parte de seleção retrospectiva.
- Pela mesma auditoria nos 71 novos, 15 ativos tinham escolha elegível no treino: 77 operações,
  expectativa +42,70%. A mesma escolha no OOS somou 37 operações, expectativa +37,96%, com
  seis ativos positivos entre os 13 que efetivamente operaram no OOS.
- Como o objetivo da cesta é capturar poucos sinais em muitos ativos, a unidade principal deve ser
  uma regra global agregada, e não exigir dez operações de cada ticker. Nos 71 da VPS,
  `baseline_v0 + CALCULATED_EXIT` teve no treino 36 operações, expectativa +13,05% e PF 2,04;
  no OOS, 61 operações, expectativa +3,93% e PF 1,31. Limitando cronologicamente a uma única
  posição global por vez, o OOS permaneceu positivo: 17 operações, 52,9% de acerto,
  expectativa +5,66% e PF 1,47.
- Nos 75 ativos, uma regra escolhida pelo treino, `score_85 + CALCULATED_EXIT`, teve 48 operações
  no treino com expectativa +13,87% e PF 1,59; no OOS foram 46 operações, expectativa +9,44%
  e PF 1,36. Com uma posição global por vez no OOS: 13 operações, expectativa +8,74% e PF 1,30.
- Análise de concentração da mesma regra global em 30/07/2026: 20 ativos efetivamente
  operaram no OOS, sendo 11 com expectativa positiva e 9 negativa. Excluindo apenas os ativos
  com uma única operação OOS, restaram 37 operações com expectativa +9,52% e PF 1,41;
  portanto, a vantagem agregada não depende dos resultados isolados de um único trade.
  O teste leave-one-asset-out permaneceu positivo em todos os casos: a menor expectativa foi
  +4,13% sem BBAS3, +4,99% sem RENT3, +5,09% sem VALE3 e +6,59% sem BBDC4.
- Maiores contribuições OOS independentes para `score_85 + CALCULATED_EXIT`: BBAS3 (3 trades,
  +85,67%), VALE3 (7, +33,72%), BBDC4 (4, +39,43%) e RENT3 (1, +209,95%). Maiores detratores:
  PETR3 (2, -56,41%), BEEF3 (1, -100%), CSAN3 (1, -100%), BRAP4 (2, -48,16%) e PETR4
  (3, -27,01%). Não excluir ou promover tickers com base nessa observação OOS isolada,
  pois isso voltaria a introduzir seleção retrospectiva.
- O campo `selected_*` do ranking consolidado é descritivo, não uma recomendação direta:
  para `POSITIVE_TRAIN_AND_OOS`, o script escolhe entre as combinações consistentes aquela com
  maior expectativa OOS; para `STRICTLY_STABLE`, usa todas as divisões. Esses campos servem para
  descobrir candidatos, mas não constituem uma validação OOS intocada para selecionar regra por ativo.
- Esses percentuais são retornos por operação em opções e ainda não representam retorno de
  carteira, pois faltam dimensionamento, capital compartilhado, custos, slippage e curva patrimonial.
  O próximo teste correto é uma simulação de portfólio cronológica com essas restrições.

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

### Módulo independente de índice futuro implementado em 30/07/2026

- Foi criado um fluxo separado do scanner de CALLs para mapear zonas do WIN com dados D-1.
  O banco próprio é `data/index_futures/gamma_index.db`; nenhuma regra, tabela ou resultado
  do scanner anterior foi substituído.
- Hierarquia implementada: opções do IBOV como fonte primária, BOVA11 como confirmação e
  opções de todos os componentes da carteira IBOV ponderadas pelo peso oficial. O cadastro
  IN resolve o subjacente exato, incluindo PETR3/PETR4, e normaliza o código técnico de ETF
  `BOVA9` para o ticker canônico `BOVA11`.
- O IndexReport `IR` passou a ser interpretado diretamente. Não usar `IBOV11` do PriceReport
  como spot. No smoke de 29/07/2026, o fechamento oficial foi 173.885,34 e o valor de ajuste
  174.629, preservados em campos distintos; WINQ26 fechou em 174.000.
- Horizontes são independentes: `SHORT` 2–9 DTE e `SWING` 10–45 DTE. O motor reutiliza
  GEX/DEX/Vanna/Charm/Gamma Flip e paredes existentes, calcula beta de 60 sessões quando há
  pelo menos 40 observações e marca explicitamente `beta=1 fallback` quando não há histórico.
- Níveis mapeados a mais de 4 ATR do WIN são excluídos da camada operacional, com contagem
  preservada no contexto. Zonas usam distância de 0,20 ATR, padding de 0,05 ATR e tipos
  `BUYER`, `SELLER`, `BATTLE` ou `NEUTRAL`. No smoke real final, 549 níveis brutos foram obtidos,
  429 ficaram operacionais e 120 níveis distantes foram excluídos; IBOV, BOVA e componentes
  apareceram conjuntamente nas regiões relevantes.
- O footprint aceita CSV/Parquet no leiaute negócio a negócio, aplica cancelamentos e agrega
  em bins de 25 pontos. O arquivo público não fornece agressor: buy volume, sell volume e delta
  são sempre rotulados como estimativa por tick rule. Sem arquivo fornecido, o estado correto é
  `UNAVAILABLE`; não fabricar footprint. O antigo portal negócio a negócio foi desativado em
  31/03/2026, portanto essa base deve ser acumulada prospectivamente/importada do capítulo oficial.
- Backtest implementado para qualidade da zona (toque, reação >=0,5 ATR antes da quebra,
  breakout, falso breakout, MFE/MAE) e estratégias WIN long/short de rejeição e breakout com
  reteste. Entrada é na abertura seguinte; stop fica 0,25 ATR além da zona; há parcial em 1R,
  alvo seguinte/2R, time stop de 5 ou 10 sessões e, em candle ambíguo, o stop é processado antes.
  O valor financeiro usa R$ 0,20 por ponto do mini índice e inclui cenários de slippage de
  0/25/50 pontos.
- Ablações do backtest: `IBOV`, `IBOV_BOVA`, `IBOV_TOP5` e `FULL`, com amostras cronológicas
  `TRAIN_126`, `VALIDATION_1`, `VALIDATION_2` e `OUT_OF_SAMPLE`. O backtest lê somente mapas
  D-1 já persistidos para não introduzir carteira futura. O smoke de 29/07 reconstruiu 86 zonas
  candidatas nas quatro ablações, mas avaliou zero e gerou zero trades porque não há pregão
  posterior armazenado no novo banco; zonas sem barra futura não contam como falhas.
- Comandos: `python scripts/index_futures_daily.py` e
  `python scripts/index_futures_backtest.py`. Saídas auditáveis ficam em JSON/CSV sob
  `results/index_futures`. O Excel planejado não foi gerado porque o componente obrigatório
  `@oai/artifact-tool` não estava exposto nesta sessão; não substituir silenciosamente por
  openpyxl/pandas. Gerar o `.xlsx` quando esse componente estiver disponível.
- Caches novos ficam em `data/parsed/index_futures`. A primeira leitura do IN/PR/PE completo é
  demorada; execuções seguintes reutilizam Parquet. A suíte passou a ter 37 testes aprovados.
- Execução operacional feita por Matheus em 30/07/2026 terminou às 20:04:52 e completou as 80
  sessões de contexto, de 06/04/2026 a 29/07/2026. `PRAGMA integrity_check` retornou `ok`.
  O mapa final de 29/07 contém 549 níveis brutos, 406 níveis operacionais, 143 descartados por
  distância e 38 zonas: SHORT com 9 BUYER, 3 NEUTRAL e 7 SELLER; SWING com 9 BUYER,
  1 NEUTRAL, 8 SELLER e 1 BATTLE. As três famílias `IBOV`, `BOVA` e `COMPONENT` estão presentes.
  IBOV e BOVA11 foram válidos nos dois horizontes; PETR3 ficou válido no SWING e sem opções no
  SHORT, enquanto PETR4 foi válido nos dois, confirmando que as classes não foram misturadas.
- Em seguida foram gerados, a pedido, os mapas de 27 e 28/07/2026 para comparação visual com
  29/07. O novo banco passou a ter três mapas: 27/07 com 416 níveis/38 zonas, 28/07 com
  428 níveis/40 zonas e 29/07 com 406 níveis/38 zonas. Para 27 e 28, a carteira de componentes
  disponível é a fotografia de 30/07; portanto esses dois painéis são exploração visual e não
  podem ser tratados como backtest causal dos componentes. As walls diretas IBOV/BOVA vêm das
  cadeias dos próprios pregões. A visualização interativa foi criada com seletor SHORT/SWING,
  candles WIN, zonas de alta confiança e walls IBOV/BOVA para os três dias.
- Cobertura conferida após esses mapas: existem 347 pares brutos PR/PE entre 11/03/2025 e
  29/07/2026; o banco principal tem 150 pregões entre 18/12/2025 e 29/07/2026; o banco de
  índice possui 82 contextos WIN entre 01/04/2026 e 29/07/2026, mas somente três mapas de
  walls já calculados (27, 28 e 29/07). Footprint continua com zero dias por falta do arquivo
  negócio a negócio.
- Convenção operacional que deve ficar explícita nos gráficos: a data do mapa é a data-fonte
  D-1, calculada após o fechamento, e seus níveis são usados somente no pregão seguinte.
  Assim, mapa 27/07 aplica-se a 28/07, mapa 28/07 a 29/07 e mapa 29/07 a 30/07. Os valores
  exibidos já estão convertidos para o contrato WIN ativo (`WINQ26` nesses dias), não para o
  IBOV spot nem para uma série contínua retroajustada. No mapa de 27 aplicado a 28, o WINQ26
  negociou de 177.010 a 179.625 e tocou as zonas de briga 177.047–178.428 e 178.295–179.224.
- Validação visual feita por Matheus no intraday de 28/07: a primeira zona `SHORT/SELLER`
  calculada em 27/07 era 179.473–180.432 (`MEDIUM`, fonte componentes). O WINQ26 fez máxima
  179.625, entrou 152 pontos na zona, ficou 807 pontos abaixo da borda superior e fechou em
  177.645, recuo de 1.980 pontos desde a máxima. O OHLC diário confirma a entrada e rejeição;
  os dois toques vistos por Matheus exigem dados intraday para validação independente. Tratar
  como evidência promissora, não como vantagem comprovada antes de ampliar a amostra.

### Handoff completo da conversa sobre índice futuro — 30/07/2026

- Matheus decidiu priorizar o estudo de regiões compradoras, vendedoras, brigas e walls para
  o índice futuro. A pergunta inicial era se as walls deveriam vir do BOVA11 ou das maiores
  ações; a arquitetura final usa IBOV como fonte principal, BOVA11 como confirmação e todos
  os componentes ponderados. O módulo é independente do scanner swing de CALLs.
- Arquivos centrais implementados nesta conversa:
  `gamma_levels/index_futures.py`, `gamma_levels/index_futures_service.py`,
  `gamma_levels/index_futures_storage.py`, `gamma_levels/index_futures_backtest.py`,
  `gamma_levels/footprint.py`, `scripts/index_futures_daily.py`,
  `scripts/index_futures_backtest.py` e `tests/test_index_futures.py`.
- Alterações auxiliares: `gamma_levels/b3.py` agora lê IndexReport `IR`, reconhece `PUTT`,
  preserva multiplicador de futuros, resolve subjacentes exatos e distingue fechamento do
  IBOV de valor de ajuste. `README.md`, `.gitignore`, `pyproject.toml` e `__init__.py` também
  foram atualizados. A suíte final teve 37 testes aprovados e `compileall` passou.
- O worktree ainda contém todas essas mudanças sem commit. Não descartá-las nem executar
  reset/checkout. Antes de encerrar o desenvolvimento, revisar, commitar e enviar ao GitHub.
  `results/` e `data/` ficam ignorados pelo Git e permanecem apenas no Windows local.
- Banco do módulo: `data/index_futures/gamma_index.db`. Saídas por data:
  `results/index_futures/<AAAA-MM-DD>/daily_map.json`, `zones.csv`,
  `source_levels.csv`, `source_summary.csv`, `quality.csv` e `footprint.csv`.
  O último `PRAGMA integrity_check` retornou `ok`.
- Comando diário normal, depois que a B3 publicar D-1:
  `python scripts/index_futures_daily.py`. Não iniciar uma segunda cópia enquanto a primeira
  estiver ativa. A primeira carga é lenta por interpretar IN/PR/PE; depois usa cache Parquet.
  Para uma data específica: `python scripts/index_futures_daily.py --data 2026-07-29`.
- Backtest: `python scripts/index_futures_backtest.py`. Ele deve usar somente mapas causais
  já persistidos e barras futuras; uma zona sem pregão posterior não conta como falha.
- Interpretação acordada:
  - `BUYER` = região compradora/suporte potencial; procurar rejeição para long.
  - `SELLER` = região vendedora/resistência potencial; procurar rejeição para short.
  - `BATTLE` = forças compradora e vendedora relevantes no mesmo intervalo; não entrar no
    meio, esperar rejeição ou rompimento com aceitação/reteste.
  - `PUT wall` = maior concentração relevante do lado das puts, hipótese de suporte.
  - `CALL wall` = maior concentração relevante do lado das calls, hipótese de resistência.
  - Put e call wall no mesmo preço significam pivô/magnet/briga, não ordem simultânea de
    compra e venda. Dados públicos não revelam com certeza o lado líquido dos dealers.
  - No gráfico: `I P/I C` são put/call wall do IBOV; `B P/B C`, do BOVA11.
  - A região agregada é a referência principal; uma wall dentro dela reforça a confluência.
- Níveis SHORT principais apresentados ao usuário, sempre aplicados no pregão seguinte:
  - mapa 27/07 → pregão 28/07: long 174.964–176.249; primeira short
    179.473–180.432; briga 177.047–178.428; IBOV put/call wall 178.439;
    BOVA11 put/call wall 178.039.
  - mapa 28/07 → pregão 29/07: long 176.476–177.570; short 178.367–179.496;
    briga 177.510–178.499; IBOV put wall 175.065 e call wall 179.089;
    BOVA11 put/call wall 177.911.
  - mapa 29/07 → pregão 30/07: long 172.975–174.254; short 175.340–176.133;
    sem briga de alta confiança próxima; IBOV put wall 174.115 e call wall 178.117;
    BOVA11 put/call wall 173.439.
- A visualização comparativa dos três dias foi criada com seletor `SHORT`/`SWING`, candle
  do WIN, zonas e walls. A fonte canônica continua sendo o JSON/CSV por data; se o visual
  da conversa não estiver disponível na próxima sessão, reconstruí-lo desses arquivos.
- Confirmação visual importante feita por Matheus: no gráfico intraday de 28/07, a primeira
  short de 179.473–180.432 foi tocada duas vezes e não rompeu. O diário só comprova entrada
  e rejeição; para comprovar os dois toques e a sequência será necessário obter barras de
  1 minuto ou negócios/ticks.
- Cobertura real no fim da conversa:
  - 347 pregões brutos PR/PE, de 11/03/2025 a 29/07/2026;
  - 150 pregões no banco principal, de 18/12/2025 a 29/07/2026;
  - 82 contextos WIN, de 01/04/2026 a 29/07/2026;
  - somente três mapas de walls prontos: 27, 28 e 29/07;
  - footprint: zero dias.
- Limitações que não podem ser esquecidas:
  - níveis exibidos estão em pontos do contrato ativo `WINQ26`; não colocá-los no IBOV spot;
  - `WINFUT` contínuo do Profit pode divergir por rolagem/retroajuste, então conferir no
    contrato exato;
  - mapas são calculados após o fechamento e usados somente no pregão seguinte;
  - componentes dos mapas 27/28 usam a carteira disponível em 30/07, portanto servem para
    exploração visual, não para backtest causal completo;
  - walls diretas de IBOV/BOVA dos próprios pregões são auditáveis;
  - footprint depende de arquivo negócio a negócio e o agressor será apenas estimado por
    tick rule;
  - Excel do módulo não foi gerado porque `@oai/artifact-tool` não estava disponível;
    JSON/CSV/SQLite são as referências auditáveis.
- Próximo estudo correto: medir historicamente toque, reação, rompimento, falso rompimento,
  MFE/MAE e resultado dos playbooks. Para componentes sem lookahead, obter carteiras IBOV e
  cadastros IN históricos. Como primeira validação mais rápida, pode-se testar IBOV+BOVA
  diretos nos dados históricos. Para contar dois ou mais toques no mesmo pregão, acrescentar
  dados intraday de 1 minuto ou tick e custos/slippage.
- Em 30/07/2026 Matheus exportou `WINQ26_F_0_5min.csv` para iniciar a validação intraday.
  O arquivo usa ponto e vírgula, codificação Windows-1252 e números no padrão brasileiro.
  Foram auditadas 8.880 barras de cinco minutos, 113 datas entre 13/02/2026 14:55 e
  30/07/2026 18:20, sem timestamps duplicados. As 40 primeiras datas são esparsas; a partir
  de 16/04/2026 há 73 pregões com pelo menos 100 barras, chegando a 113 barras por sessão.
  Esse arquivo sozinho não serve como série causal do contrato ativo para todo 2026:
  o backtest YTD deve unir WING26, WINJ26, WINM26 e WINQ26 conforme o contrato ativo de cada
  pregão, preservando o ticker exato usado nos mapas. Cinco minutos é a granularidade inicial;
  não pedir outro timeframe antes de medir o que ela resolve.
- Em 31/07/2026 Matheus também obteve `WINM26_F_0_5min.csv`. Ele contém 8.898 barras,
  116 datas entre 08/12/2025 16:40 e 29/05/2026 18:20, sem duplicidades; há 69 pregões
  com pelo menos 100 barras, iniciados em 19/02/2026. O banco confirmou a rolagem usada
  pelo motor: WINJ26 até 14/04, WINM26 de 15/04 a 16/06 e WINQ26 desde 17/06.
- A união causal dos arquivos disponíveis produziu 61 pregões aplicados e completos:
  30 no WINM26, de 16/04 a 29/05, e 31 no WINQ26, de 18/06 a 30/07. O trecho sem
  WINM26 entre 01/06 e 16/06 e o dia de rolagem não foram aproximados, interpolados ou
  substituídos pelo contrato seguinte. WING26 e WINJ26 continuam faltando para chamar o
  estudo de anual/YTD completo.
- O download histórico do IndexReport `IR` de 15/04 expirou por timeout, embora o cadastro
  `IN260415.zip` tenha sido baixado, validado e interpretado. Para não usar `IBOV11` falso
  nem fabricar o spot oficial, o primeiro backtest intraday foi executado como ablação
  `BOVA` somente. Não rotular esses resultados como IBOV+BOVA.
- Foram criados `gamma_levels/index_futures_intraday.py`,
  `scripts/index_futures_intraday_backtest.py`, `scripts/index_futures_backfill.py` e
  `tests/test_index_futures_intraday.py`. O backfill preserva mapas existentes, suporta
  BOVA-only e workers paralelos. O avaliador lê CSV do Profit em Windows-1252, valida OHLC,
  usa o próximo pregão causal e o mesmo contrato, e calcula toques, visitas, reação em
  5/15/30/60 minutos, MFE/MAE, rompimento e falso rompimento.
- Backfill BOVA causal concluído para 61 datas-fonte entre 15/04 e 29/07; os mapas completos
  preexistentes de 27–29/07 foram preservados. O banco terminou com 61 mapas nesse intervalo,
  presença de BOVA nos 61 e `PRAGMA integrity_check = ok`. O backtest de cinco minutos avaliou
  371 zonas, zero exclusões e 61 pregões. Saídas: `results/index_futures/intraday_5min/`.
- Resultado bruto direcional BOVA, ainda sem filtros e sem simulação financeira: SHORT BUYER
  teve 38 zonas/23 toques, reação antes da quebra de 0,25/0,50/1,00 ATR em
  56,5%/26,1%/4,3% dos toques e breakout em 60,9%; SHORT SELLER, 37/14,
  71,4%/28,6%/7,1% e breakout em 50,0%. SWING BUYER teve 53/15,
  66,7%/33,3%/6,7% e breakout em 53,3%; SWING SELLER, 48/8,
  37,5%/12,5%/12,5% e breakout em 62,5%. BATTLE/NEUTRAL permanecem auditados,
  mas não entram nessa leitura direcional.
- Esses números medem comportamento de zona, não lucro, entrada pronta ou vantagem comprovada.
  A amostra é parcial, BOVA-only e tem poucos toques em vários subgrupos. Não escolher filtros
  a partir do resultado completo. Próximos passos: dividir cronologicamente treino/OOS,
  acrescentar playbooks e custos fixos, tentar recuperar IR histórico e ampliar WING/WINJ
  se os dados aparecerem.
- Matheus esclareceu em 31/07/2026 que seu operacional intraday no WIN usa stop fixo de
  300 pontos e gain fixo de 300 pontos. Portanto 0,25 ATR, que na amostra podia representar
  perto de mil pontos, não deve ser apresentado como alvo operacional; ATR permanece apenas
  na construção/avaliação estrutural das zonas.
- O backtest de cinco minutos passou a simular 300/300 em dois playbooks: entrada no primeiro
  preço executável dentro da zona (`FIRST_TOUCH`) e entrada na abertura do candle seguinte
  após rejeição confirmada por fechamento acima da região BUYER ou abaixo da SELLER
  (`REJECTION_5M`). Se stop e alvo aparecem no mesmo candle, o stop é processado primeiro;
  no primeiro toque o alvo do próprio candle não é creditado por ambiguidade do OHLC.
  Há cenários de custo total de 25 e 50 pontos por operação e seleção conservadora de no
  máximo uma entrada por pregão para cada horizonte/playbook.
- Na amostra BOVA-only de 61 pregões, o primeiro toque não mostrou vantagem agregada:
  em `FIRST_PER_DAY`, SHORT teve 29 trades, 44,8% de acerto, -31,0 pontos de expectativa
  bruta e -900 pontos totais; SWING teve 22 trades, 45,5%, -27,3 e -600 pontos.
  A rejeição de cinco minutos agregando BUYER+SELLER ficou praticamente no zero:
  SHORT 25 trades, 56,0%, +25,2 pontos brutos por trade, +630 pontos brutos,
  apenas +5 após custo de 25 pontos e -620 após custo de 50; SWING 20 trades,
  50,0% e zero bruto.
- O único recorte inicialmente promissor foi rejeição em zona BUYER. Em `FIRST_PER_DAY`,
  SHORT BUYER teve 18 trades, 66,7% de acerto, +85 pontos brutos por trade, PF 1,85,
  +1.530 pontos brutos, +1.080 após custo de 25 e +630 após custo de 50; SWING BUYER
  teve 13 trades, 61,5%, +69,2 pontos, PF 1,60, +900 brutos, +575 após 25 e +250 após 50.
  SHORT SELLER e SWING SELLER foram negativos. Uma divisão diagnóstica cronológica 70/30
  do SHORT BUYER manteve 66,7% de acerto nos dois trechos, mas as amostras foram somente
  12 e 6 trades. Tratar como hipótese para validação, não como setup aprovado.
- As novas saídas auditáveis são
  `results/index_futures/intraday_5min/fixed_points_trades.csv` e
  `fixed_points_metrics.csv`. O script aceita `--stop-pontos` e `--gain-pontos`.
- A pedido de Matheus, foi executada em 31/07/2026 uma grade de 80 combinações:
  stops de 150, 200, 250, 300, 350, 400, 500 e 600 pontos contra gains de
  150, 200, 250, 300, 350, 400, 500, 600, 750 e 900. O corte cronológico usou
  42 pregões de treino até 03/07 e 19 pregões OOS depois disso. Foram mantidos
  os cenários de custo total de 25 e 50 pontos, stop primeiro em candle ambíguo
  e no máximo o primeiro sinal de cada horizonte/playbook por pregão.
- A melhor faixa, ainda exploratória, foi `SWING BUYER + REJECTION_5M` com stop
  entre 250–350 e gain entre 750–900. O ponto 250/900 teve 13 trades:
  5 alvos, 7 stops e 1 fechamento de sessão em -20; 38,5% de acerto,
  expectativa bruta +210 pontos, PF 2,54, drawdown bruto de 520 pontos e
  +2.730 pontos totais. Após 50 pontos de custo por trade, restaram
  +160 pontos de expectativa e +2.080 pontos totais. Treino teve 7 trades e
  +192,9 pontos por trade após custo de 50; OOS teve 6 e +121,7. WINM26 e
  WINQ26 ficaram positivos separadamente. As vizinhas 300/900, 350/900 e
  250/750 também ficaram positivas no treino e OOS após custo de 50, reduzindo
  a aparência de um pico isolado. Nenhum dos 13 trades teve candle de saída
  contendo simultaneamente stop e alvo.
- A alternativa de maior frequência foi `SHORT BUYER + REJECTION_5M`.
  Stop 400/gain 300 teve 18 trades, 72,2% positivos, PF bruto 1,82,
  +1.630 pontos brutos e +730 após custo de 50, mas drawdown bruto de
  1.300 pontos. O 300/300 teve os mesmos 18 trades, 66,7% positivos,
  PF 1,85, +1.530 brutos, +630 após custo de 50 e drawdown menor, de
  900 pontos. A melhora total do 400/300 sobre 300/300 foi somente 100 pontos;
  portanto 300/300 permanece a opção mais simples/balanceada para teste manual.
- O primeiro toque não foi escolhido: seus melhores resultados dependeram
  excessivamente do OOS e o treino foi fraco. A combinação SELLER 150/900
  apareceu positiva, mas tinha somente 7 trades depois de pesquisar 80 pares
  e não é evidência suficiente. O operacional candidato principal para nova
  validação é: somente zona BUYER do mapa SWING, esperar um candle de 5 minutos
  fechar acima da borda superior após tocar a zona, entrar na abertura seguinte,
  stop 250 e gain 900, encerrando no fechamento se nenhum for atingido.
  O candidato secundário é a mesma confirmação em BUYER do mapa SHORT com
  300/300. Não tratar nenhum dos dois como aprovado antes de ampliar a amostra.
- Script reproduzível: `scripts/index_futures_stop_gain_grid.py`. Saídas:
  `stop_gain_grid_trades.csv`, `stop_gain_grid_metrics.csv`,
  `stop_gain_grid_ranked.csv` e `stop_gain_grid_summary.json` sob
  `results/index_futures/intraday_5min/`.
- Em seguida Matheus perguntou se, pensando como swing trader, alvos de
  1.000/2.000/3.000 pontos seriam melhores. Foi implementado um teste separado
  que carrega a posição por no máximo 1, 2, 3, 5 ou 10 pregões, com stops de
  250 a 1.500 pontos. Gaps que atravessam stop/alvo saem pela abertura real,
  candle ambíguo processa stop primeiro, sinais sem futuro suficiente são
  censurados e a leitura operacional usa uma única posição por vez.
- Resultado: alvo grande no mesmo dia e swing verdadeiro não são equivalentes.
  Stop 400/alvo 3.000 com saída obrigatória no fim do primeiro pregão teve
  13 trades, +2.480 pontos após custo de 50 e drawdown de 1.505, mas somente
  um trade atingiu 3.000; sete pararam no stop e cinco saíram no fechamento.
  Portanto o número alto veio principalmente de deixar lucros correrem até o
  fechamento, não de o alvo de 3.000 ser alcançado com frequência.
- No swing verdadeiro, stop 400/alvo 3.000 foi a melhor combinação de alvo
  grande: 13 sinais, 12 trades válidos e 1 censurado; 2 alvos, 10 stops,
  16,7% de acerto, expectativa bruta +139,6, PF 1,39, +1.675 pontos brutos
  e +1.075 após custo de 50, com drawdown bruto de 3.125 pontos. Treino e OOS
  ficaram positivos, mas com apenas 6 trades válidos em cada trecho. Todos os
  trades válidos terminaram até o segundo pregão, por isso permanências máximas
  de 2, 3, 5 e 10 dias deram o mesmo resultado.
- Stop 250/alvo 1.000 carregado teve +625 pontos após custo de 50, mas ficou
  negativo no OOS. Stop 400/alvo 2.000 carregado perdeu 925 pontos após custo.
  Assim, aumentar o alvo não melhorou a relação entre retorno e risco:
  o candidato anterior 250/900 encerrado no mesmo pregão teve +2.080 pontos
  após custo, PF 2,54 e drawdown de apenas 520, contra +1.075, PF 1,39 e
  drawdown 3.125 do swing 400/3.000. O 400/3.000 é uma hipótese agressiva,
  não substitui o 250/900 como candidato principal na amostra atual.
- Script: `scripts/index_futures_swing_target_grid.py`. Saídas:
  `swing_large_target_trades.csv`, `swing_large_target_metrics.csv`,
  `swing_large_target_ranked.csv` e `swing_large_target_summary.json`.

### Auditoria multi-agente do módulo de índice — 31/07/2026 (15 agentes, verificação adversarial)

- Fato central descoberto: os 58 mapas BOVA-only foram construídos com o cadastro IN de
  15/04 para todos os pregões. O filtro de subjacente em `build_chain`
  (`index_futures.py:265-267`) descartou silenciosamente toda opção BOVA listada depois:
  em 23/07 eliminou 100% da cadeia SHORT (146/146 opções DTE 2-9) e 54% da SWING;
  21 de 61 pregões ficaram sem cadeia SHORT alguma, concentrados no fim da amostra.
  Todos os resultados intraday BOVA-only anteriores foram medidos sobre mapas mutilados.
- O suposto bloqueio "IR histórico expira por timeout" era falha transitória da B3.
  Em 31/07 todos os IRs baixaram em ~0,1-1s (~24 KB cada). Baixados IR das 152 datas de
  `market_context` e IN por data das 73 datas de 15/04 a 29/07 (INs ~25-34 MB), zero erros.
- O IR (BVBG-087) NÃO contém a carteira teórica do IBOV: `parse_index_report` lê apenas
  `IndxInf`, e o XML real confirma que não há pesos/quantidades por componente. A tabela
  `composition_snapshots` tem um único snapshot (as_of 30/07). Logo, backfill histórico
  `--com-componentes` é lookahead por construção (carteira de 30/07 atravessando o
  rebalanceamento de maio) e a contaminação não é separável por família: cluster mescla
  famílias, então zona tocada por nível COMPONENT contaminado fica não-causal inteira.
  O backfill causal máximo é IBOV+BOVA. Para componentes causais no futuro, arquivar a
  carteira diariamente a partir de agora.
- Confidence HIGH exige `family_count >= 2` (`index_futures.py:506-511`) — era
  matematicamente impossível nos mapas BOVA-only; os 37 HIGH vinham 100% dos 3 dias FULL.
  Nos 61 pregões antigos, confidence era proxy de disponibilidade de fonte, não de
  qualidade. O estrato HIGH nunca teve resultado medido em artefato algum do projeto.
- Bordas de zona são min/max NÃO ponderados + padding (`index_futures.py:488-489`);
  81% das bordas são definidas por níveis com menos de metade da strength máxima do
  cluster (tipicamente gamma_flip, side NEUTRAL). O âncora mais forte do lado fica em
  mediana ~554 pts para dentro da borda (p90 ~1000, máx 1482); em 66,7% das zonas BUYER
  ele está a mais de 300 pts da borda. Hipótese registrada: avaliar toque/rejeição no
  nível-âncora ± ~0,05 ATR usando a zona larga só como contexto (dados já existem em
  `source_levels`).
- O motor intraday resolve 100% da ambiguidade contra o trade: stop antes do alvo no
  mesmo candle e alvo proibido no candle de entrada (`index_futures_intraday.py:356-363`).
  16 trades com MFE >= 300 saíram como STOP; girá-los vale 9.600 pts — mais que o
  resultado líquido do book FIRST_PER_DAY. Toda conclusão de PF deve ser reportada em
  banda pessimista/otimista. Parte da assimetria é defensável (anti-lookahead quando o
  candle abre fora da zona); quando abre dentro, é pessimismo puro.
- Escala: o stop fixo de 250-300 pts fica aquém da borda oposta da zona em ~82% dos
  trades da grade (100% no combo 250/900 e no REJECTION_5M BUYER); ~47-56% dos stopados
  atingiram o alvo original depois, sem a estrutura violada. Correção conceitual:
  stop 300 é restrição de risco financeiro (dimensionamento), não posicionamento; o stop
  estrutural correto é além da zona + 0,25 ATR com posição reduzida (~1/4). As zonas da
  ablação BOVA tinham largura mediana ~317 pts (não ~1000; isso vale para multi-família),
  então stop 300 ≈ 1 largura por coincidência — ao avaliar mapas IBOV+BOVA (mais largos),
  comparar em unidades estruturais/ATR ou o mapa melhor parecerá pior por artefato.
- REJECTION_5M confirma com close além da borda distante e entra a mercado no candle
  seguinte, sem reteste: entrada mediana 127 pts acima da borda e 436 pts acima da base
  (1,40x a largura). O backtest diário já exige reteste; o intraday não. Nos 12 BUYER
  estopados, porém, ~10 sessões romperam a zona de verdade — o playbook já é lucrativo e
  o ganho de mecânica não deve ser vendido como "muitos bons trades estopados".
- FIRST_PER_DAY não esconde ouro: descarta só 16/112 sinais com P&L líquido zero.
  Hipótese encerrada com números. Mas o dedupe ignora zone_type (1 vaga/dia atravessando
  direções): a amostra SELLER cai de 13-14 para 7 e uma célula FIRST_TOUCH SHORT SELLER
  inverte de PF 0,75 (n=7) para 1,17 (n=13) com contabilidade por direção. Corrigir a
  medição (dedupe por direção) em passo separado e rotulado, sem misturar com a correção
  de dados.
- SELLER não é ausência de sinal, é escala errada: mfe_eod mediano 1.268 pts (maior que
  BUYER), mas mae_60m 619 pts ≈ 2x o stop de 300 (BUYER: 254). "SELLER não funciona"
  deve ser lido como "SELLER não é mensurável em 300 pts/60 min".
- REFUTADO com teste placebo: "zonas NEUTRAL/BATTLE têm o sinal direcional mais forte
  (97,7% breakout, continuação 1.448 pts)". Uma banda da mesma largura na abertura do
  dia dá 99,1%/1.746 pts — a estatística mede o range diário a partir de banda estreita,
  não informação de opções. Único resíduo: false-breakout das zonas reais (4,8%) menor
  que placebos (14-24%) — indício fraco, olhar apenas descritivamente em OOS.
- Beta: fallback silencioso beta=1 desloca nível de componente com beta 1,4 a 3% do spot
  em ~1.490 pts; a série do índice misturava ibov_close com win_close e os gaps de
  rolagem (+1,2% a +1,9%) viravam retorno falso. Em 31/07 o `market_context` foi
  re-hidratado com os IRs: 149 linhas ganharam ibov_open/low/high/close/settlement
  oficiais (0 NULL restantes; integrity ok). A série do beta agora é IBOV puro.
- Cobertura: apenas 61 de 152 datas com contexto entram no backtest e o ledger de
  exclusões não enxerga dias sem mapa (`zone_exclusions.csv` vazio ≠ nada excluído).
  Recuperação mais barata: re-exportar WINM26_F_0_5min cobrindo 01-16/06 (+11 sessões
  imediatas). Com WING26 + WINJ26 + WINM26 completo, a amostra chega a ~148 sessões
  (2,43x), ~87 delas genuinamente out-of-sample ante a grade já rodada. Não usar WINQ26
  como substituto no buraco de junho (basis de ~2 meses de CDI).
- Ações executadas em 31/07: backup `data/index_futures/backups/gamma_index_pre_recalc_20260731.db`;
  baseline BOVA-only arquivada em `results/index_futures/_baseline_bova_only/`;
  mapas FULL 27-29/07 arquivados em `results/index_futures/_full_maps_pre_recalc/`;
  re-hidratação do market_context; backfill `--recalcular` IBOV+BOVA de 15/04 a 29/07
  (73 mapas, incluindo 12 datas novas de 29/05 e 01-16/06 que ficam à espera do WINM26).
  Os 3 mapas FULL do banco foram substituídos por IBOV+BOVA para uniformidade do dataset
  científico; a versão FULL segue no backup e no arquivamento.
- Método da re-medição: código do motor intocado na primeira comparação (isolar o efeito
  da correção de dados). Três pontas nos mesmos pregões: baseline arquivada (BOVA sobre
  mapas mutilados), ablação BOVA sobre mapas corrigidos (efeito do IN) e ablação
  IBOV_BOVA (efeito da fonte primária). O cache Parquet é fragmentado por raízes
  (`PR_<sha1(roots)>.parquet`), então a rodada IBOV+BOVA não reutiliza cache BOVA-only.
  Só depois aplicar correções de medição (dedupe por direção, bandas) e mudanças de
  mecânica (âncoras, reteste, stop estrutural), cada uma rotulada e validada na amostra
  ampliada, nunca re-otimizando stop/gain nos mesmos 61 pregões.

### Re-medição pós-correção — 31/07/2026 (Fase 1 + escavação de 14 agentes, Fase 2)

- Execução: 73/73 mapas causais IBOV+BOVA reconstruídos (15/04-29/07, IN por data,
  IR oficial, integrity ok; 12 datas 29/05-16/06 sem barras intraday ficam censuradas
  aguardando re-export do WINM26). Rodadas com motor intocado e 61 sessões idênticas:
  A=`results/index_futures/intraday_5min_rerun_bova` (BOVA corrigida),
  B=`intraday_5min_ibov_bova`, C=`intraday_5min_ibov`; grades pré-registradas
  250/300 x 300/900 em `prereg_grid_{bova,ibov_bova,ibov}`.
- A baseline mutilada era OTIMISTA, não pessimista: agregado INDEPENDENT FULL
  BASELINE -870 (112 tr) vs A -3.900 pts (157 tr). O grosso do otimismo estava na fatia
  OOS (BASELINE +2.700 → A 0). Qualquer número derivado da baseline está formalmente
  invalidado; a referência BOVA é a rodada A. A censura SHORT da baseline era
  estruturada por calendário de vencimento (dois blocos, 10/19 pregões OOS não medidos),
  não aleatória.
- Candidato pré-registrado (i) SHORT BUYER REJECTION_5M 300/300: REBAIXADO/aposentado.
  No dado corrigido o treino tem PF 1,00 exato (A e B); total negativo após custo de
  50 pts em todas as rodadas; resta OOS de n=8-14 que não sustenta operação. Os +1.530
  antigos eram artefato (apenas 11 dos 26 trades corrigidos coincidem com a baseline).
- Candidato pré-registrado (ii) SWING BUYER REJECTION_5M 250/900: SOBREVIVEU só no
  modelo BOVA, enfraquecido: n=17, WR 35,3%, exp +155,9, PF 1,96 (era 2,54), maxDD
  1.250 (era 520), positivo em treino (+2.100, PF 2,40) e OOS (+550, PF 1,44, n=7,
  +200 após custo 50 — carregado por 2 acertos). NÃO transfere para fontes IBOV
  (OOS -700 em B; 0/6 em C). Vizinhas 300/900 BOVA também positivas nas duas fatias.
  Manter em observação OOS contínua; não reotimizar.
- Resultados NEGATIVOS robustos: FIRST_TOUCH perde em todos os estratos/rodadas
  corrigidas; o sistema agregado é negativo após custos em todas as rodadas; hipótese
  das âncoras de wall NÃO confirmada nos mapas corrigidos (âncora ≈ centro da zona,
  distância mediana à borda 159 pts e não 554; nenhuma reação extra atribuível; ~61-62%
  de violação em qualquer linha) — lente encerrada sem mudança no sistema.
- PRINCIPAL VEIO NOVO (EXPLORATÓRIO, direção oposta ao pré-registro): REJECTION_5M
  SHORT SELLER melhora monotonicamente com a fonte primária: A -1.200 → B +1.200 →
  C +2.700 (n=13, WR 84,6%, PF 5,5; treino +900, OOS +1.800 com 6/6; sobrevive a custo
  50). Corroboração mecânica independente: reação 0,50 ATR das zonas SELLER tocadas
  sobe A 25% → B 41% → C 53% enquanto BUYER cai. p≈0,011 pré-multiplicidade, n pequeno,
  OOS 6/6 compatível com sorte; e o OOS forte coincide com os pregões recém-restaurados
  de julho (pode ser regime). NADA disso é sinal aprovado.
- Hipótese SELLER estrutural PRÉ-REGISTRADA para a amostra ampliada (formulação
  corrigida pelo verificador): fade no 1º toque de zona SELLER SHORT do mapa IBOV_BOVA,
  stop 0,35-0,40 ATR além do centro, alvo 0,25-0,30 ATR, time-stop 120 min, custos
  25/50, SEM preferência por confidence HIGH (HIGH tem risco PIOR: mae_60m 0,236 vs
  0,115 ATR) e SEM ajustar os múltiplos na amostra atual. Geometria exige WR >=58-62%;
  EV-marginal; só a amostra ampliada decide. Maturação da excursão favorável ~120 min
  nos mapas corrigidos (97-100% do MFE de EOD).
- Multi-família/HIGH (medição inaugural; colinear: todos os 138 HIGH são fc=2):
  multi-família reage mais em ATR (react025 SHORT 65% vs 39%) mesmo após ajuste de
  meia-largura, mas são 1,9x mais largas e rendem menos por unidade de largura. Único
  recorte lucrativo: REJECTION_5M em zona multi-família n=35, WR 60%, +60 pts/trade,
  PF 1,50 em treino E OOS, positivo após custos — 1 célula positiva de 4, OOS n=10,
  EXPLORATÓRIO. FIRST_TOUCH em multi é pior que em mono.
- Contabilidade FIRST_PER_DAY corrigida (1 vaga/dia por direção): aumenta capacidade
  (47→59 tr em B REJ SHORT), piora levemente totais após custos, não inverte rankings.
- Fila de validação forward pré-registrada (rodar na amostra ampliada WINM26/WING/WINJ
  ANTES de qualquer ajuste): (1) SWING BUYER 250/900 modelo BOVA; (2) fade SELLER SHORT
  estrutural em ATR (formulação acima); (3) REJECTION_5M SHORT SELLER 300/300 modelos
  B/C como está; (4) REJECTION_5M em zona multi-família. Qualquer outro recorte que
  apareça é nova hipótese, não validação.

### Validação forward — tranche 1 (11 sessões virgens de junho), 31/07/2026

- Matheus obteve o WINM26 via export MT5 (`WINM26_M5_202512081640_202606171655.csv`).
  Validação de fonte: 99,865% de OHLC idêntico ao Profit em 8.885 timestamps comuns;
  12 divergências, todas em barras finas de dez/2025-fev/2026, fora da janela útil.
  As 11 sessões faltantes (01-16/06, 113 barras cada) foram convertidas para o formato
  Profit em `WINM26_junho_gap_5min.csv` (raiz), somente a janela sem sobreposição.
- Rodadas forward em `results/index_futures/forward_{bova,ibov_bova,ibov}` e grades em
  `forward_grid_*` (72 sessões de aplicação). Sanidade: adicionar o CSV NÃO mudou o
  passado (linhas não-virgens byte-idênticas às rodadas de 61 sessões nas 3 ablações e
  nas 3 grades); 17/06 excluído como CONTRACT_ROLL; únicas exclusões restantes são rolls.
- Resultado da tranche virgem (medições verificadas adversarialmente, todas reproduzidas
  do zero):
  - H1 SWING BUYER 250/900 BOVA: NEUTRO — n=1 trade, STOP -250 (zona LOW). Com WR de
    referência ~35%, uma perda é o desfecho modal; quase não atualiza a crença.
    Acumulado 72 sessões: 18 trades, PF 1,80 (era 1,96).
  - H2 fade SELLER SHORT estrutural: CONTRA — 3 trades, negativo nas 4 combinações de
    canto ([0,35/0,25] -529; [0,40/0,25] -677; alvo 0,30 ~-2.400). Fragilidade de
    parametrização evidente (alvo 0,25→0,30 vira +780 em -1.025 no mesmo trade).
    12 das 15 zonas SELLER SHORT nunca foram tocadas (junho caiu/lateralizou abaixo
    delas). Acumulado 72: [0,40/0,25] +2.380 após custo 50 (WR 65,7%).
  - H3 REJECTION SHORT SELLER 300/300: CONTRA — 4 trades (3 em B, 1 em C), 4 STOPs,
    0 alvos. O trade de C é a mesma configuração do 3º de B (15/06 09:25) — modelos não
    independentes na fatia. Corroboração de zona também virou: 2 de 3 toques SELLER
    viraram breakout UP. Acumulado: B cai a PF 1,07 (bruto +300); C cai de PF 5,50 para
    3,67 (14 tr, WR 78,6%, +1.700 após custo 50 — ainda positivo, mas ferido).
  - H4 REJECTION multi-família: CONTRA — 5 trades, 1/5, -900 pts, PF 0,25 na fatia.
    Acumulado 72: PF 1,22, +200 após custo 25, -800 após custo 50.
- Leitura conjunta honesta: a tranche de junho votou CONTRA 3 das 4 hipóteses e neutro
  na 4ª. Cada resultado isolado é compatível com azar (p≈8-15%), mas o conjunto sustenta
  a suspeita registrada na Fase 2: o OOS forte de julho era possivelmente regime, não
  robustez. Nenhuma hipótese está morta (n=1-5), nenhuma está aprovada, três estão
  feridas. PROIBIDO ajustar parâmetros em resposta a esta tranche.
- Próximo passo decisivo: exports WING26 e WINJ26 do MT5/Profit (~76 sessões virgens
  fev-abr/2026, regimes diferentes de junho). Até lá, não há mais nada honesto para
  minerar nos 72 pregões atuais — qualquer nova busca neles é dragagem de dados.

### Validação forward — tranche 2 (76 sessões virgens dez-abr) — VEREDITO FINAL, 31/07/2026

- Matheus entregou WING26 e WINJ26 via MT5. Infra executada: 175 downloads (79 INs +
  96 IRs de aquecimento, zero erros), pré-aquecimento de 96 pregões de contexto,
  79 mapas novos em 3 blocos (zero erros). Banco final: 152 mapas causais IBOV+BOVA
  (16/12/2025 a 29/07/2026), 231 datas de contexto, integrity ok. Rodadas finais com
  5 CSVs em `results/index_futures/final_{bova,ibov_bova,ibov}` e `final_grid_*`:
  148 sessões de aplicação (76 virgens + 72 vistas).
- Sanidade PERFEITA: passado byte-idêntico ao forward nas 3 ablações e grades; únicas
  exclusões são as 4 rolagens esperadas (17/12, 18/02, 15/04, 17/06); fatia virgem com
  76 sessões reais (WING26 38 + WINJ26 38), 10 dias ausentes todos explicados
  (3 rolagens + 7 feriados B3).
- VEREDITO: as 4 hipóteses pré-registradas votaram CONTRA na maior fatia virgem que o
  projeto terá. Todas as medições verificadas adversarialmente, reproduzidas do zero:
  - H1 SWING BUYER 250/900 BOVA: n=16, WR 18,8% (abaixo até do breakeven bruto de
    21,7%), -395 bruto, -1.195 após custo 50. Só dezembro positivo (n=3). Em janeiro
    (rali) gerou 12 zonas e zero toques — não opera em regime de alta. Virgens somadas
    (t1+t2): 17 trades, 3/17, -645 bruto. Total geral 148 sessões: +305 após custo 50
    (~9 pts/trade) — economicamente nulo.
  - H2 fade SELLER estrutural ATR: n=62, NEGATIVO nas 4 combinações JÁ NO BRUTO
    (-2.599 a -4.929; após custo 50: -5.699 a -8.029). WR 48-50% vs 58-62% exigidos.
    4 de 5 meses negativos — não é um mês ruim, é o padrão.
  - H3 REJECTION SHORT SELLER 300/300: TODAS as 12 células (2 modelos x 2 seleções x
    3 custos) negativas, inclusive bruto. B PF 0,66; C PF 0,88 na fatia virgem.
    Detalhe fatal: março (queda/lateralização, o regime que deveria favorecer venda)
    foi o PIOR mês nos dois modelos — a defesa de regime caiu. O WR 84,6%/PF 5,5 das
    61 vistas não existe fora delas.
  - H4 multi-família: n=31, WR 48,4%, -300 bruto, -1.850 após custo 50. Todo o lucro
    em janeiro (6/7); março devolve tudo. Virgens combinadas: PF 0,80.
- Nota transversal da sanidade: o agregado fixed_points das 72 sessões vistas já era
  negativo em todos os modelos (BOVA -2.400; IBOV_BOVA -11.400; IBOV -9.600 somando
  todos os estratos). Com 148 sessões, nenhum estrato pré-registrado sobrevive.
- CONCLUSÃO REGISTRADA: com todos os dados existentes (148 sessões causais, pipeline
  íntegro, fonte validada), os mapas D-1 de opções IBOV/BOVA, nos playbooks e escalas
  testados, NÃO produzem edge intraday mecânico no WIN. O brilho de mai-jul/2026 era
  regime + seleção — o pré-registro e as fatias virgens fizeram exatamente o trabalho
  de impedir que isso virasse dinheiro perdido. PROIBIDO reabrir a caça a parâmetros
  nas mesmas 148 sessões; qualquer resultado novo ali é dragagem por construção.
- O que o projeto GANHOU e permanece válido: (a) pipeline causal completo e auditável
  (152 mapas, IN/IR por data, 3 ablações, grades, bancos íntegros) pronto para gerar
  o mapa diário em ~1 min; (b) resultados negativos robustos que valem dinheiro por
  prevenção; (c) a descoberta de que o backtest antigo era inválido e OTIMISTA;
  (d) fonte MT5 validada contra Profit (99,865%).
- Caminhos honestos que restam (nenhum é continuação da caça): (1) rodar o backtest
  DIÁRIO original do módulo (`scripts/index_futures_backtest.py`, playbooks com stop
  estrutural além da zona + 0,25 ATR, horizonte multi-dia) sobre os 152 mapas — é o
  desenho original do módulo, nunca executado no dataset corrigido; tratar como
  medição descritiva com corte cronológico, não como nova caça; (2) acompanhamento
  prospectivo: continuar gerando o mapa diário e registrando desfechos sem operar
  (paper forward) — o único teste realmente virgem daqui em diante; (3) uso do mapa
  como CONTEXTO discricionário (como Matheus já fazia visualmente), sem gatilho
  mecânico; (4) arquivar carteira IBOV diariamente para habilitar COMPONENT causal
  futuro; (5) o scanner swing de CALLs (projeto principal) segue intocado e válido.

- Após a integração da cesta, 27 testes Python foram aprovados no Windows; lint e build do
  dashboard também foram aprovados.
- Auditoria de equivalência local versus VPS em 30/07/2026: os 71 runs completos da VPS
  registram a mesma configuração dos quatro locais (345 sessões carregadas, 50 de aquecimento,
  `standard_v1`, custos zero, ações corporativas e juros completos) e usam as mesmas 19 variantes,
  6 estratégias de saída, 2 modos de sobreposição e 5 amostras quando essas variantes geram trades.
  Dos 71, 20 materializaram as 1.140 linhas de métricas, 20 materializaram subconjuntos em múltiplos
  de 60 e 31 ficaram com zero métricas por não terem gerado trades. Isso ocorre porque `_metrics`
  itera somente pelas variantes presentes em `backtest_trades`; não significa que a configuração
  ou a metodologia da VPS era diferente. Sessenta e oito tiveram 254 datas avaliáveis e CYRE4,
  RENT4 e VAMO3 tiveram 253 por disponibilidade/calendário do ativo.
- Um sinal VALE3 de 08/07/2025 foi recalculado após a otimização e manteve exatamente
  status, score 81,5, CALL VALEG565, prêmio máximo, suporte e resistência.
- `scripts/validate_result_banks.py` valida integridade, run final, contagens e SHA-256 dos bancos.
- `scripts/analyze_result_universe.py` reproduz a classificação e a planilha consolidada.
- A API reiniciada em 30/07/2026 respondeu 75 ativos em `/api/backtest/tickers`; BBAS3 foi
  consultada pela API e retornou run `COMPLETE` com 1.140 métricas.

### Scanner diário — PRIO3 em 31/07/2026, decisão na abertura de 03/08/2026

- A varredura completa da cesta em 31/07 produziu somente dois ativos únicos marcados como
  `COMPRAR CALL`: PRIO3 e PETR3 (quatro linhas porque cada um passou na variante própria e
  na regra global). Todos os demais ficaram em `AGUARDAR` ou `DESCARTAR`.
- PETR3 ativou nas réguas `score_75` e `score_85`, score 85,85, RR 2,42, setup
  `REVERSÃO EM SUPORTE`, CALL `PETRH477`, strike ajustado R$ 46,61, vencimento 21/08/2026
  e prêmio máximo calculado R$ 0,43. Essa ativação NÃO deve ser operada sem auditoria:
  com PETR3 a R$ 49,04 em D-1, o valor intrínseco aparente da CALL seria cerca de R$ 2,43,
  incompatível com a cotação de referência implícita de aproximadamente R$ 0,37 que gerou
  projeção absurda de +830,19%. Tratar como provável inconsistência de ajuste/cotação, não
  como oportunidade barata, até validar a série e incluir filtro de no-arbitrage.
- O scanner diário incorporou os pregões de 30 e 31/07/2026; o banco passou a 152 sessões,
  de 18/12/2025 a 31/07/2026. Em 31/07, PRIO3 ativou `COMPRAR CALL` nas duas leituras:
  `region_lookback_50` (score 81,59/80, RR 4,92) e regra global `score_85`
  (87,83/85, RR 5,13). Setup: `REVERSÃO EM SUPORTE`; CALL selecionada `PRIOH590`,
  strike 59, vencimento 21/08/2026, prêmio máximo R$ 3,86 e projeção conservadora de
  cinco sessões +26,46%.
- Parâmetros D-1 do papel: fechamento R$ 60,85, suporte aproximadamente R$ 60,93–60,94,
  zona de entrada R$ 60,50–61,28, invalidação aproximadamente R$ 60,50 e alvos
  R$ 62,56 e R$ 64,28. Na abertura de 03/08, Matheus informou PRIO3 a R$ 58,65,
  abaixo da invalidação já no gap. Decisão operacional: **não comprar a CALL nessa abertura**;
  o prêmio mais barato seria consequência da quebra do setup, não oportunidade de executar
  o sinal. Aguardar nova estrutura/sinal D-1, sem perseguir a opção. Transparência metodológica:
  esse veto por gap é uma proteção estrutural discricionária ainda não validada no backtest;
  o motor histórico atual decide o fill apenas pelo prêmio da opção (`open/low <= entry_limit`)
  e não revalida o subjacente contra a invalidação em D0.

### Scanner diário 06/08/2026 e bug de raiz compartilhada PETR3/PETR4

- Varredura de 06/08 (banco em 156 pregões, 18/12/2025 a 06/08/2026): uma ativação,
  PETR3 na régua própria `score_75` (score 77,22/75, RR 1,57, CALL `PETRI439`,
  projeção 5 dias +240,27%). Telegram disparado. A ativação foi VETADA na auditoria.
- Causa raiz encontrada: `Database.current_options()` (`storage.py:468`) filtra a cadeia
  apenas por `asset_root`, e PETR3/PETR4 compartilham a raiz `PETR`. O scanner avaliou
  PETR3 (fech. 47,31) contra uma CALL de PETR4: `PETRI439` tem strike 42,86 e prêmio 1,66,
  o que implicaria intrínseco aparente de R$ 4,45 por R$ 1,66 e viola no-arbitrage.
  Na cadeia de 18/09 as duas séries convivem: ATM de PETR4 em ~42,1 (`PETRI432` 2,04) e
  ATM de PETR3 em ~47,3 (`PETRI473` 2,35). A projeção absurda é consequência do erro.
- Este é o mesmo defeito por trás do +830,19% de PETR3 em 31/07 (`PETRH477`, strike 46,61,
  prêmio 0,43 — também série de PETR4). Não tratar como oportunidade barata.
- Correção pendente: resolver o subjacente exato como o módulo de índice futuro já faz
  pelo cadastro IN. Enquanto não for corrigida, toda ativação de PETR3/PETR4 exige auditoria
  manual da CALL selecionada. Demais leituras de 06/08: 12 `AGUARDAR`, 7 `DESCARTAR`;
  PETR4 com score 90,97/85 e RR 2,37 travado apenas por falta de setup.

### Hipóteses de Matheus testadas e DESCARTADAS em 07/08/2026

- Hipótese 1, alvo pequeno: realizar entre 5% e 30% no prêmio em vez de esperar 10-100%.
  Medida sem recalcular sinal algum — `scripts/target_exit_replay.py` relê `backtest_trades`
  e `trade_path` dos 11 bancos oficiais (somente leitura) e resimula as saídas novas
  `TARGET_05/10/15/20/30` ao lado das seis oficiais. Comparação pareada: mesmos sinais,
  mesmas entradas, mesmas trajetórias; só muda quando se vende. As seis saídas oficiais
  foram reproduzidas com divergência zero, o que valida a leitura.
- Resultado nas 146 operações da régua da cesta (72 OOS), modo INDEPENDENT: a frequência que
  Matheus intuiu existe — 93,8% das operações tocam +5% e +10%, 90,4% tocam +15%, 85,6%
  tocam +20% — mas realizar ali destrói a expectativa. `TARGET_05` dá 93,8% de acerto e
  expectativa NEGATIVA (-1,47%; OOS -3,75%), porque os 9 trades que não tocam o alvo perdem
  100%. `TARGET_10` fica em +3,22% (OOS +0,83%) e `TARGET_30` em +2,68%, contra +26,33%
  (OOS +40,29%) do `CALCULATED_EXIT` atual. Em R$ 1.000 por operação: -2.150 no alvo de 5%,
  +4.700 no de 10% e +38.449 na saída atual. Na regra global `score_85` o quadro se repete.
- Razão estrutural: a expectativa mora na cauda. Das 146 operações, 65,8% tocam +50%,
  45,2% tocam +100% e 20,5% tocam +200%; a mediana até o vencimento é -59%. Os 5 melhores
  trades respondem por 34% de todo o resultado da saída calculada. Vender cedo trava o ganho
  que paga os -100% e não reduz a perda. O teste ainda foi generoso com a hipótese: assume
  execução no máximo intradiário e custo zero, ignorando o spread real da opção.
- Hipótese 2, dispensar o setup: a exigência de `REVERSÃO EM SUPORTE` ou `ROMPIMENTO/RETESTE`
  é obrigatória e hard-coded (`swing.py`), e nenhuma das 19 variantes jamais a testou. Foi
  criada a flag `SwingConfig.require_setup` (default `True`, comportamento oficial intocado)
  e `scripts/no_setup_study.py`, que roda em cópia (`data/nosetup_<ticker>/`) a régua da cesta
  e a global com e sem setup, no mesmo run.
- Piloto ITSA4 (20 min, 4 variantes): sem setup surgiram 3 sinais a mais (7 → 10) e todos
  pioraram o resultado — `CALCULATED_EXIT` caiu de +64,86% para +29,97% no completo, de
  +94,59% para +59,80% no OOS e de -9,45% para -39,63% no treino. Em `score_85` o resultado
  foi idêntico com e sem setup: sem gatilho a nota de estrutura cai e o score não alcança 85,
  então nenhum sinal novo nasce. Amostra de um ativo; não é prova, é mau começo.
- Hipótese 3, opção de 2 a 11 dias com alvo pequeno: NÃO foi medida. `scripts/short_dte_study.py`
  ficou pronto com o controle 2x2 (DTE normal/curto x alvo grande/pequeno) e a janela 2-11 DTE
  escolhida por Matheus, mas ele decidiu descartar a linha inteira antes de gastar as ~4h de
  máquina. Se alguém retomar, o script está pronto e o desenho pré-registrado.
- Decisão de Matheus em 07/08/2026: descartar a hipótese de alvo pequeno / entrada sem setup.
  O sistema continua com as seis saídas oficiais e com o setup obrigatório. Suporte no motor:
  `StudyConfig.extra_strategies` e as saídas `TARGET_*` ficam disponíveis mas desligadas por
  padrão. A suíte seguiu com 42 testes aprovados após as duas mudanças.

### Operação direcional em BOVA11 para o 2º turno (18/10/2026 — base D-1 16/10/2026)

- Contexto macro/eleitoral: após o 1º turno (04/10/2026, com Flávio Bolsonaro em 1º lugar com
  47,03% ante 45,16% de Lula), o Ibovespa disparou +7,70% em 05/10 (rompendo 200 mil pontos) e
  o `BOVA11` saltou de R$ 190,00 para máxima de R$ 207,00 (fech. R$ 204,35). Nos 8 pregões
  seguintes (06/10 a 16/10), o `BOVA11` consolidou acima da Put Wall de R$ 200,00 (mínimas de
  R$ 200,00 em 15/10 e R$ 200,17 em 16/10) e fechou em **R$ 202,30** na sexta-feira 16/10/2026
  (abertura R$ 200,22, máxima R$ 203,19, volume R$ 818,17 milhões).
- Leitura do motor (`SwingScanner` + `RegionEngine` + `analyze_chain`) em 16/10/2026:
  - Setup acionado: **`REVERSÃO EM SUPORTE`** (região de suporte centrada em R$ 200,45, banda
    R$ 199,08–R$ 201,81, 16 toques históricos, ancorada na Put Wall).
  - Indicadores: ATR(14) = R$ 3,89; EMA20 = R$ 194,50; EMA50 = R$ 185,63 (`trend = 85/100`);
    RSI(14) = 69,8 virando para cima (`momentum = 100/100`); `structure = 76,01/100`.
  - Status nas réguas: **`COMPRAR CALL` ativado na régua `score_75`** (score 75,42/75, RR 1,63,
    projeção conservadora 5d +10,69%); `AGUARDAR` em `region_v1` (75,42/80) e `score_85`
    (75,42/85) porque o spot (R$ 202,30) ainda está abaixo do Gamma Flip (R$ 204,32).
  - Níveis de Gamma e estrutura no `BOVA11`:
    - **Invalidação / Stop estrutural:** **R$ 199,47** (-1,40%)
    - **Put Wall (Suporte):** **R$ 200,00**
    - **Zona de Entrada D0 (segunda 19/10):** **R$ 201,33 a R$ 203,27** (vetar compra na
      abertura se houver gap de baixa perdendo R$ 199,47)
    - **Gamma Flip:** **R$ 204,32**
    - **Alvo 1 (Resistência / Topo 05/10):** **R$ 206,90** (+2,27%, RR 1,63)
    - **Alvo 2 (Expansão 2x ATR):** **R$ 210,07** (+3,84%, RR 2,75)
    - **Alvo 3 (Call Wall):** **R$ 220,00** (+8,75%, RR 6,26)
- Seleção de vencimento e ativo: descartadas as semanais `30/10/2026` (`BOVAJ...W5`, 14 DTE)
  por IV inflada (43%–46%), spreads largos e risco severo de *IV crush* na segunda pós-2º turno
  (26/10). Escolhida a série mensal **`19/11/2026` (`BOVAK`, 34 DTE)**, que concentra R$ 193,4M
  de volume diário, IV ~9–10 pontos menor (33,5%–36,4%) e atravessa a eleição (25/10) com
  25 DTE restantes.
- **Decisão operacional de Matheus (Opção 1 — Capital alocado: R$ 600,00):**
  - **Ativo escolhido:** 100% em **`BOVAK205`** (CALL Americana, Strike **R$ 205,00**, vencimento
    **19/11/2026**, Delta **0,50**, IV **35,0%**, fechamento 16/10 **R$ 8,55**, ref. B3 **R$ 8,37**,
    bid/ask **R$ 8,10 / R$ 8,55**, spread 5,4%, giro R$ 16,62M, OI 4,98M, lote padrão = 1).
  - **Entrada planejada (segunda 19/10/2026):**
    - Comprar **70 quantidades de `BOVAK205`** limitada até **R$ 8,55** (custo **R$ 598,50**;
      se executar a R$ 8,30 no meio do book, **72 quantidades = R$ 597,60**; teto máximo se
      abrir com leve alta até R$ 203,30: **R$ 8,85**).
  - **Plano de saídas e parciais para as 70 quantidades:**
    1. **1ª Parcial (Pré-urna, até sexta 23/10, se `BOVA11` buscar R$ 209,50–R$ 210,00):**
       vender **30 quantidades** entre **R$ 11,00 e R$ 11,60** (embolsa **~R$ 345,00** com IV
       cheia antes do domingo eleitoral).
    2. **2ª Saída (Segunda pós-2º turno, 26/10, nas 40 quantidades restantes — já descontando
       *IV crush* de -8 pts de vol):**
       - Se `BOVA11` em **R$ 215,00 (+6,3%)**: `BOVAK205` projetada a **~R$ 13,20** → vende 40 qtds
         por **R$ 528,00** (total operação **R$ 873,00**, lucro líquido **+R$ 274,50 / +46%**).
       - Se `BOVA11` repetir os **+7,5% do 1º turno (R$ 217,50)**: `BOVAK205` projetada a
         **~R$ 15,25** → vende 40 qtds por **R$ 610,00** (total operação **R$ 955,00**, lucro
         líquido **+R$ 356,50 / +60%**; ou **R$ 1.067,50 / +R$ 469,00 (+78%)** caso carregue
         as 70 qtds sem parcial prévia).
       - Se `BOVA11` buscar a **Call Wall (R$ 220,00–R$ 222,50)**: `BOVAK205` projetada entre
         **R$ 17,40 e R$ 19,64** (+104% a +130%, valor total de **R$ 1.218 a R$ 1.375** nas 70 qtds).
    3. **Referência de invalidação antes da urna:** perda de **R$ 199,47** no `BOVA11` (quebra da
       Put Wall de R$ 200,00), ponto em que a `BOVAK205` recua para ~R$ 6,40–R$ 6,60 (~-23%).
- **Acompanhamento de 19/10/2026 (Matheus informou em 20/10 que não entrou na segunda 19/10):**
  - **`BOVA11` em 19/10/2026 (`PR261019.zip`):** abriu com gap de alta em **R$ 203,50**, bateu
    máxima em **R$ 204,24** (rejeitado a R$ 0,08 do Gamma Flip de sexta em R$ 204,32), recuou até
    a mínima de **R$ 201,02** (defendendo a banda de suporte e a Put Wall de R$ 200,00) e fechou
    em **R$ 202,42** (+0,06% no dia; VWAP R$ 202,35; bid/ask R$ 202,42 / R$ 202,46; giro de
    R$ 910,61M em 63.727 negócios). `IBOV` oficial (`IR261019.zip`) fechou em 205.079,25 (-0,17%).
  - **`BOVAK205` em 19/10/2026 (`PR261019.zip` + `PE261019.ex_`, 31 DTE):** abriu a **R$ 8,23**,
    fez máxima de **R$ 10,00** (+21,5% sobre a abertura no teste dos R$ 204,24 do papel, sem
    alcançar a 1ª parcial planejada de R$ 11,00–R$ 11,60), mínima de **R$ 7,66**, VWAP **R$ 8,17**
    e fechou a **R$ 8,22** (-3,86% ante os R$ 8,55 de sexta). Preço de referência B3 recuou de
    R$ 8,37 para **R$ 8,17**; book no fechamento melhorou para **R$ 8,22 / R$ 8,38** (spread caiu
    de 5,4% para 1,93%); IV praticamente estável em **34,88%** (era 35,00%); giro financeiro de
    **R$ 13,33M** (2.513 negócios) e Open Interest subiu +13,5%, de 4.981.170 para **5.654.661**.
  - **Atualização do motor em 19/10/2026 (`region_v1` / `score_85`):** o score estrutural subiu de
    **75,42** para **87,72** (Tendência 85, Momentum 100 com RSI 70,0, Estrutura 85,04 com 17
    toques no suporte R$ 200,54, Derivativos **100/100**), porque o **GEX Total virou positivo**
    (`+7,00 bilhões` ante `-5,94 bilhões` em 16/10) e o **Gamma Flip caiu para R$ 201,28** (deixando
    o spot R$ 202,42 em regime de gamma positivo). O status automático marcou `AGUARDAR` apenas
    porque o candle de segunda fechou abaixo da abertura (`202,42 < 203,50`, exigência mecânica
    `close > open` de `reversal`), mas a estrutura seguiu intacta, com invalidação atualizada em
    **R$ 199,58**, zona de entrada **R$ 201,46–R$ 203,38** e prêmio da `BOVAK205` mais barato
    (permitindo **72–73 quantidades** com R$ 600,00 na faixa R$ 8,22–R$ 8,30).
- **Acompanhamento de 20/10, 21/10 e manhã de 22/10/2026 (Matheus informou às 11h00 de 22/10 que ainda não havia comprado):**
  - **Terça-feira 20/10/2026 (`PR261020.zip` + `PE261020.ex_`):** `BOVA11` abriu com gap de alta em
    **R$ 204,54**, mínima em **R$ 203,21**, máxima em **R$ 205,76** e fechou em **R$ 205,01** (giro
    R$ 1,25 bi). `BOVAK205` abriu na mínima a **R$ 8,69**, bateu máxima em **R$ 10,47** e fechou a
    **R$ 10,05** (ref. B3 **R$ 9,57**, bid/ask R$ 9,80 / R$ 10,19, IV 35,96%, giro R$ 18,01M, OI 5,69M).
    Como às 11h45 de terça o ativo já estava em R$ 204,80–R$ 204,95 (opção a ~R$ 9,35), a orientação de
    não perseguir topo evitou comprar no pico da semana.
  - **Quarta-feira 21/10/2026 (`PR261021.zip` + `PE261021.ex_`, 29 DTE):** `BOVA11` abriu em
    **R$ 205,88**, bateu máxima em **R$ 206,20** (rejeitando antes do Alvo 1 de R$ 206,90) e recuou
    forte até a mínima de **R$ 202,62**, fechando em **R$ 203,50** (giro R$ 1,08 bi). `BOVAK205` bateu
    máxima de **R$ 10,83** na abertura (sem atingir a 1ª parcial planejada de R$ 11,00–R$ 11,60),
    mínima de **R$ 9,58** e fechou a **R$ 10,05** no último negócio de tela (bid/ask R$ 10,05 / R$ 10,07),
    mas com o **Preço de Referência oficial B3 recuando para R$ 8,99** e a IV subindo para **38,13%**
    no arquivo oficial (~41,9% implícita no último negócio de tela por procura pré-2º turno; OI subiu
    para **6.062.804**). No `SwingScanner` de 21/10, score ficou em **86,99** (Tendência 85, Momentum 85,
    Estrutura 84,55, Derivativos 100 com **GEX Total +25,72 bilhões**, **Gamma Flip em R$ 200,72** e
    pivô/wall curta em **R$ 205,00**).
  - **Manhã de Quinta-feira 22/10/2026 (~11h00, 28 DTE):** `BOVA11` abriu em queda a **R$ 202,29**,
    fez máxima de **R$ 203,07** às 10h30, mínima de **R$ 201,99** às 10h40 e negocia a **R$ 202,19**
    — devolvendo **100% da puxada de terça e quarta** e voltando a ficar **R$ 0,11 abaixo do preço
    de sexta-feira 16/10 (R$ 202,30)**, exatamente dentro da Zona de Entrada original (R$ 201,33–R$ 203,27)
    e acima do suporte estrutural (R$ 200,54) e do Gamma Flip (R$ 200,72). Com `BOVA11` a R$ 202,19,
    a `BOVAK205` calibrada pela referência B3 (IV 38,13%) vale **~R$ 8,10–R$ 8,30** e pela IV inflada
    de tela de quarta (~41,9%) vale **~R$ 8,95–R$ 9,15** (enquanto a `BOVAK210` vale **~R$ 6,00–R$ 6,60**).
  - **POSIÇÃO EXECUTADA E ABERTA em 22/10/2026 (~12h36):** Ordem limitada executada no book:
    - **Ativo:** **`BOVAK205`** (CALL Americana, Strike **R$ 205,00**, vencimento **19/11/2026**, 28 DTE).
    - **Quantidade comprada:** **67 quantidades**.
    - **Preço de entrada:** **R$ 8,90** (Custo bruto total: **R$ 596,30**).
    - **Spot `BOVA11` no momento da execução:** **R$ 200,33** (mínima do dia R$ 200,14 — compra feita exatamente sobre o suporte estrutural de R$ 200,54, o Gamma Flip de R$ 200,72 e a Put Wall de R$ 200,00).
    - **Plano de saídas e parciais para as 67 quantidades (@ R$ 8,90):**
      1. **Parcial Opcional Pré-Urna (hoje à tarde ou sexta 23/10, aproveitando IV pré-eleição ~42%):**
         - Se `BOVA11` repicar até **R$ 205,00–R$ 207,00** antes da urna, `BOVAK205` vai a **R$ 10,45–R$ 11,60 (+17% a +30%)** → vender **27 quantidades** entre **R$ 10,80 e R$ 11,50** (embolsa **~R$ 292 a R$ 310**) e carregar **40 quantidades** para segunda-feira (26/10).
      2. **Alvos de Segunda-feira pós-2º turno (26/10, já descontando *IV crush* para 30%):**
         - `BOVA11` em **R$ 210,00**: `BOVAK205` projetada a **~R$ 10,44 (+17,4%)** (total 67x = **R$ 699,81**, lucro **+R$ 103,51**).
         - `BOVA11` em **R$ 212,50**: `BOVAK205` projetada a **~R$ 12,23 (+37,4%)** (total 67x = **R$ 819,13**, lucro **+R$ 222,83**).
         - `BOVA11` em **R$ 215,00**: `BOVAK205` projetada a **~R$ 14,13 (+58,8%)** (total 67x = **R$ 946,76**, lucro **+R$ 350,46**).
         - `BOVA11` em **R$ 217,50 (repete +7,5% do 1º turno)**: `BOVAK205` projetada a **~R$ 16,15 (+81,4%)** (total 67x = **R$ 1.081,75**, lucro **+R$ 485,45**).
         - `BOVA11` na **Call Wall (R$ 220,00)**: `BOVAK205` projetada a **~R$ 18,26 (+105,1%)** (total 67x = **R$ 1.223,09**, lucro **+R$ 626,79**).
      3. **Referência de invalidação estrutural antes da urna:** perda confirmada de **R$ 199,50–R$ 199,59** no `BOVA11` (quebra da Put Wall de R$ 200,00).
- **Fechamento oficial de Quinta-feira 22/10 e Sexta-feira 23/10/2026 (pré-2º turno):**
  - **Quinta-feira 22/10/2026 (`PR261022.zip` + `PE261022.ex_`, 28 DTE):** após a entrada das **67 `BOVAK205` a R$ 8,90** (~12h36 com `BOVA11` a R$ 200,33), o `BOVA11` chegou a tocar mínima de **R$ 199,89** intradiária, defendeu a Put Wall de R$ 200,00 e fechou em **R$ 200,96** (abertura R$ 202,29, máxima R$ 203,07, VWAP R$ 200,90, bid/ask R$ 200,80 / R$ 200,97, giro R$ 1,51 bi em 81.513 negócios; `IBOV` oficial em 204.120,12). A `BOVAK205` fez mínima de **R$ 8,72**, máxima de **R$ 10,05**, VWAP **R$ 9,35** e fechou a **R$ 9,01** (+1,24% sobre a entrada de R$ 8,90; ref. B3 **R$ 9,03**, bid/ask **R$ 9,01 / R$ 9,40**, IV B3 **45,37%**, giro R$ 16,45M e OI subindo forte para **6.516.176**).
  - **Sexta-feira 23/10/2026 (`PR261023.zip` + `PE261023.ex_`, 27 DTE — último pregão antes do 2º turno de domingo 25/10):**
    - **`BOVA11`:** abriu em **R$ 201,13**, defendeu novamente a zona de suporte com mínima em **R$ 200,23**, bateu máxima em **R$ 202,67** e fechou em **R$ 201,69** (+0,36% no dia e **+R$ 1,36 / +0,68%** acima do spot de entrada R$ 200,33; VWAP R$ 201,55; bid/ask R$ 201,68 / R$ 201,69; giro recorde na semana de **R$ 1,58 bilhão** em 128.352 negócios). `IBOV` oficial (`IR261023.zip`) fechou em **205.082,56** (+0,47%).
    - **`BOVAK205`:** abriu a **R$ 9,10**, oscilou entre mínima de **R$ 7,96** e máxima de **R$ 9,61** (+8,0% sobre a entrada, sem acionar a parcial pré-urna de R$ 10,80–R$ 11,50), VWAP **R$ 9,00** e **fechou em R$ 9,10** — com book travado em **R$ 9,10 (compra) x R$ 9,11 (venda)** (spread de apenas R$ 0,01 / 0,11%). Preço de referência B3 em **R$ 8,34**, IV oficial B3 em **41,96%** (~43,85% implícita no fechamento de tela R$ 9,10; Delta **0,506**, Gamma **0,0166**), giro de **R$ 9,99M** (1.647 negócios) e Open Interest recorde em **6.575.410** contratos.
    - **Marcação a mercado da posição (67x `BOVAK205` @ R$ 8,90 = R$ 596,30) no fechamento de sexta 23/10:**
      - Valor da posição a R$ 9,10: **R$ 609,70** (**+R$ 13,40 / +2,25%** líquido no verde, carregando **100% das 67 quantidades** para segunda-feira 26/10).
      - Na máxima de sexta (R$ 9,61): chegou a valer **R$ 643,87** (**+R$ 47,57 / +7,98%**).
    - **Leitura do motor (`SwingScanner` / `region_v1` / `score_85`) no fechamento de 23/10/2026:**
      - Setup reacendido: **`REVERSÃO EM SUPORTE`** confirmado no fechamento pré-urna!
      - **Score subiu para `92,73 / 100`** (o maior da série: Tendência 85, Momentum **100/100** com RSI 63,5 virando para cima, Estrutura **85,92/100** com 18 toques no suporte R$ 200,30, Volume **100/100** em 1,57x a mediana, Derivativos **100/100**).
      - **Mapa de Gamma atualizado para segunda-feira 26/10:** **GEX Total virou fortemente positivo em `+13,61 bilhões`** (era `-1,21 bi` na quinta); **Gamma Flip recuou para R$ 195,68** (deixando o spot R$ 201,69 com mais de R$ 6,00 de folga em regime de gamma positivo); **Max Pain em R$ 200,00** (piso institucional); **Pivô/Wall curta em R$ 205,00** (nosso strike); e **Call Walls mensais (`BOVAK`) em R$ 220,00 (OI 9,80M) e R$ 225,00 (OI 11,18M)**. Invalidação estrutural atualizada em **R$ 199,38**.
  - **Domingo de 2º Turno à noite (`25/10/2026`, 22h51 — Pós-apuração das urnas):**
    - Matheus informou que a esquerda venceu o 2º turno e que o contrato perpétuo 24h `OKX:EWZUSDT.P` despencou **`-15%`** após o resultado das urnas.
    - **Conversão para a abertura de segunda-feira (`26/10/2026`, 24 DTE para `BOVAK205`):**
      - Como `-15%` no `EWZ` em dólar combina alta do Dólar (`USD/BRL` projetado entre `+4%` e `+6%`) com queda do Ibovespa em reais, o `BOVA11` (fech. `R$ 201,69`) projeta abertura entre **`-8%` (`R$ 185,55`) e `-10%` (`R$ 181,52`)** (ou até `-12%` em `R$ 177,49` se o câmbio subir menos), perdendo já no gap de abertura a Put Wall (`R$ 200,00`), a invalidação estrutural (`R$ 199,38`) e o Gamma Flip (`R$ 195,68`).
      - **Precificação binomial da `BOVAK205` (`67x @ R$ 8,90 = R$ 596,30`) para `26/10` (`24 DTE`):**
        - Em **`-6%` (`R$ 189,59`)**: vale **`R$ 1,72` (IV 32%) a `R$ 2,30` (IV 36%)** $\to$ posição entre **`R$ 115,19` e `R$ 153,78`** (-74% a -81%).
        - Em **`-8%` (`R$ 185,55`)**: vale **`R$ 1,04` (IV 32%) a `R$ 1,49` (IV 36%)** $\to$ posição entre **`R$ 69,36` e `R$ 99,68`** (-83% a -88%).
        - Em **`-10%` (`R$ 181,52`)**: vale **`R$ 0,58` (IV 32%) a `R$ 0,91` (IV 36%)** $\to$ posição entre **`R$ 38,70` e `R$ 60,79`** (-90% a -93%).
        - Em **`-12%` (`R$ 177,49`)**: vale **`R$ 0,31` (IV 32%) a `R$ 0,53` (IV 36%)** $\to$ posição entre **`R$ 20,44` e `R$ 35,70`** (-94% a -97%).
      - **Plano de contenção para segunda-feira `26/10`:** (1) risco máximo total da operação está estritamente travado nos **`R$ 596,30`** alocados na CALL a seco (sem chamada de margem que ocorreria no WIN/ações); (2) não vender no leilão cego dos primeiros 2 minutos (10h00–10h03); se abrir com prêmio residual relevante (`R$ 1,20–R$ 2,30` em queda de `-6%` a `-8%` ou em repique técnico matinal), avaliar zeragem de recuperação de caixa porque abaixo de `R$ 195,68` o mercado entra em Gamma Negativo; se abrir já virada em pó (`< R$ 0,35`), aguardar estabilização/repique de short-covering para decidir; (3) **VETO AUTOMÁTICO (`🔴 ABORTAR`)** para todas as 8 entradas da **Mesa 2 (`ABERT_D1`)** do Scanner de Tiro Rápido caso abram abaixo do Piso da Ação (`-1,5%`).
  - **Segunda-feira pós-2º Turno (`26/10/2026`, ~11h10 — Crise Eleitoral/Institucional e Pausa Operacional):**
    - Matheus informou às 11h10 que o mercado entrou em pânico severo cogitando crise/contestação nas eleições, levando o `BOVA11` / Ibovespa para a faixa de **`R$ 168,00` (`168 mil pontos`, queda de ~`-16,7%`)** e travando a **`BOVAK205`** repetidamente em leilões automáticos de túnel de oscilação da B3.
    - **Posição `67x BOVAK205` (`@ R$ 8,90 = R$ 596,30`):** confirmado a Matheus que, por ser titular de CALL comprada a seco, **é impossível perder além dos `R$ 596,30` já investidos** (sem ajuste diário, sem chamada de margem e sem obrigação no vencimento). Como a opção já caiu para a faixa de centavos no pânico e ainda restam **24 dias corridos até `19/11/2026`**, a orientação adotada é **não vender a preço de pó nos leilões de pânico** e mantê-la quieta na custódia caso ocorra repique/reviravolta até o vencimento.
    - **DECISÃO DE MATHEUS EM `26/10/2026` (`11h12`) — PAUSA OPERACIONAL NAS RECOMENDAÇÕES DE OPÇÕES:** ficam **PAUSADAS todas as entradas e recomendações operacionais de opções** (tanto da **Mesa 2 de Abertura `ABERT_D1`** quanto da **Mesa 1 de Final de Tarde `FIM_D0`**, além do scanner swing da cesta) **até que a crise político-institucional se resolva ou o mercado da B3 volte a estabilizar**.

### Mineração de Padrões Matemáticos Puros de Opções — 24/10/2026

- **Diretriz estratégica de Matheus:** substituir a dependência de indicadores gráficos tradicionais (EMA 20/50, RSI, figuras de candle) por **mineração matemática pura de causa e efeito na grade de opções** ("toda vez que acontece X nas opções em D-1, o que acontece com o papel e com a CALL em D+1 e em D+5?"), buscando padrões repetitivos de:
  1. Tiro de dia seguinte (`D+1` com máxima $\ge +1\%$ no papel e $+20\%$ na CALL);
  2. Explosão em até 5 dias (`D+5` com $+30\%, +50\%, +100\%$ na CALL e saída no alvo ou no fechamento do 5º dia, sem carregar até virar pó no vencimento);
  3. Ações em "V" (exaustão estatística da ação combinada com entrada anormal de fluxo em Calls) e "Parede subindo" (deslocamento de Call Wall / strike dominante para cima).
- **Script implementado:** `scripts/mine_option_patterns.py`. Saídas auditáveis em `results/option_patterns/pattern_discovery_report.json` e `pattern_discovery_all.csv`; painéis diários limpos em cache Parquet sob `results/option_patterns/cache/*.parquet` (releitura completa em 0,6s).
- **Desambiguação automática ON/PN:** o minerador elimina contaminação entre classes da mesma raiz (`PETR3`/`PETR4`, `BBDC3`/`BBDC4`, `ITUB3`/`ITUB4`, `CMIG3`/`CMIG4`) combinando o prefixo `ISIN` da tabela `instruments` (`BR` + `TICKER`) com validação histórica de preço BSM contra o spot exato de cada classe e filtro de *no-arbitrage*.
- **Amostra auditada:** 23 ações líquidas $\times$ 320 pregões úteis = **7.360 ativo-pregões** (7.329 com CALL líquida 10–48 DTE selecionada matematicamente), divididos cronologicamente em **Treino (60%, até 13/01/2026)** e **Fora da Amostra / OOS (40%, a partir de 14/01/2026)**. Foram avaliados 507 cenários matemáticos.
- **Baseline incondicional (qualquer dia, sem filtro):**
  - `D+1` máxima da ação $\ge +1,0\%$: **55,2%** | $\ge +1,5\%$: **40,9%** | `D+1` CALL $\ge +20\%$: **32,2%**.
  - `D+5` CALL $\ge +30\%$: **56,8%** | $\ge +50\%$: **40,7%** | $\ge +100\%$: **18,4%**.
  - Expectativa matemática 5d sem filtro (alvo ou saída no fechamento de D+5): Alvo +30% = **-1,42%** | Alvo +50% = **-0,23%**.
- **Principais padrões matemáticos descobertos (aprovados simultaneamente no Treino e no OOS):**
  1. **Padrão "Parede Subindo + Fluxo 3x + GEX Subindo" (`WALL_SUBIU_1D + CALL_PUT_3X + GEX_SUBINDO`):**
     - Condição: Call Wall subiu de strike no dia + Volume Financeiro em Calls $\ge 3\times$ Puts + GEX líquido subindo em 3 dias.
     - Amostra: **56 ocorrências em 20 ativos** (29 Treino / 27 OOS).
     - Desfecho em até 5 dias (`D+5`): CALL bate **$\ge +30\%$ em 71,4% das vezes** (**75,9% Treino / 66,7% OOS**), **$\ge +50\%$ em 57,1%** e **$\ge +100\%$ em 26,8%**.
     - Expectativa 5d: **+11,90%** (alvo +30%), **+18,49%** no alvo +50% (**+23,50% Treino / +13,10% OOS**) e **+19,62%** no alvo +100%.
  2. **Padrão "Ação em V + Explosão de Calls OTM" (`VOL_OTM_CALL_2.0X + ACAO_ESTI_QUEDA_Z2.0`):**
     - Condição: Ação caiu $\ge 2$ desvios-padrão em 3 dias ($Z \le -2,0$) + Volume em Calls OTM (+0,5% a +10% acima do spot) $\ge 2,0\times$ a mediana de 20 dias.
     - Amostra: **41 ocorrências em 20 ativos** (33 Treino / 8 OOS).
     - Desfecho no dia seguinte (`D+1`): Ação bate **máxima $\ge +1,0\%$ em 82,9% das vezes** (**81,8% Treino / 87,5% OOS**) e CALL bate $\ge +20\%$ já no `D+1` em **41,5%** das vezes.
     - Desfecho em 5 dias (`D+5`): CALL bate **$\ge +30\%$ em 61,0%** e **$\ge +50\%$ em 53,7%**, com Expectativa 5d (alvo +50%) de **+9,85%** (**+9,06% Treino / +13,07% OOS**).
  3. **Padrão "Parede Subindo + Fluxo 3x (Amplo)" (`CALL_PUT_VOL_3X + WALL_SUBIU_1D`):**
     - Amostra: **137 ocorrências em 21 ativos** (79 Treino / 58 OOS); com filtro de Alta Convexidade (`WALL_SUBIU_1D + CALL_PUT_3X + ALTA_CONVEX`, $n=135$), CALL bate **$\ge +30\%$ em 66,7%** (**69,2% Treino / 63,2% OOS**), **$\ge +50\%$ em 46,7%** e Expectativa 5d (alvo +50%) de **+10,00%** (**+10,71% Treino / +9,03% OOS**).
  4. **Padrão "Desmonte de Parede (Unwind) + Fechamento no Topo" (`WALL_UNWIND + FECHOU_MAXIMA_DIA`):**
     - Condição: Open Interest na Call Wall cai $\ge -3\%$ no dia (destravando o teto) + ação fecha nos 25% superiores do range diário.
     - Amostra: **59 ocorrências em 19 ativos** (34 Treino / 25 OOS). CALL bate **$\ge +30\%$ em 59,3%**, **$\ge +50\%$ em 44,1%**, Expectativa 5d (alvo +50%) de **+9,09%** (**+10,30% Treino / +7,43% OOS**).
- **Auditoria Econométrica e Estatística Profunda (`scripts/deep_statistical_options_analysis.py` / `results/option_patterns/deep_statistical_analysis.json`):**
  - **Teste Fama-MacBeth transversal por pregão e Monotonicidade por Quintis ($Q_1 \to Q_5$ em 7.329 observações):**
    - Maiores $t$-stats de Fama-MacBeth para excursão da CALL em 5 dias (`opt_d5_max_ret`): `ret_3d_z` ($\text{IC} = +0,0649, t = +4,52$, $Q_1 \text{ EV} = -6,35\% \to Q_5 = +5,93\%$), `call_put_vol_ratio` ($\text{IC} = +0,0495, t = +3,79$, $Q_1 = -2,73\% \to Q_5 = +1,84\%$), `idio_ret_3d_z` ($\text{IC} = +0,0490, t = +3,39$, $Q_1 = -3,50\% \to Q_5 = +3,95\%$), `convexity_ratio_30` ($\text{IC} = -0,0476, t = -3,28$, menor movimento exigido gera maior MFE), `call_vol_ratio` ($\text{IC} = +0,0418, t = +3,14$, $Q_1 = -5,24\% \to Q_5 = +2,85\%$) e `call_trades_ratio` ($\text{IC} = +0,0395, t = +3,01$, $Q_1 = -2,20\% \to Q_5 = +2,93\%$).
    - `vwap_strike_dist_pct` isolado tem $\text{IC}$ positivo para tiro de `D+1` ($\text{IC}_{D+1} = +0,0760$, $Q_1 = 50,5\% \to Q_5 = 61,6\%$ de máxima $\ge +1\%$), mas negativo para 5 dias ($t = -6,21$) porque comprar strikes excessivamente fora do dinheiro sem queda prévia sofre decaimento de Theta.
  - **Significância Formal (Welch $t$, Binomial Exato, FDR de Benjamini-Hochberg e Block Bootstrap por Data com 2.000 reamostragens):**
    1. **`P1_PAREDE_SUBINDO_GEX_FLUXO` ($n=56$ em 48 datas únicas, 20 ativos):** Welch $t = +3,17$ ($p = 0,00076$, **FDR $q = 0,0061$**); Binomial Hit $\ge +30\%$ ($71,4\%, p = 0,0187$) e Hit $\ge +50\%$ ($57,1\%, p = 0,0090$); Block Bootstrap 95% CI por data **$[+5,42\%, +31,08\%]$**, probabilidade de expectativa negativa $P(\text{EV} \le 0) = 0,40\%$; pior *Leave-One-Ticker-Out* $= +14,23\%$; Quantis de MFE 5d: $P_{10}=+10,8\%, P_{25}=+25,0\%, \text{Mediana } P_{50}=+59,2\%, P_{75}=+111,0\%, P_{90}=+187,1\%$; perda média quando não atinge +50% em 5d $= -23,5\%$; Fração de Kelly $= 37,0\%$ (Half-Kelly $= 18,5\%$). Ponto ótimo da curva de alvos em 5d: **+50%** ($\text{Sharpe/trade} = +0,42$, $\text{EV} = +18,49\%$) e **+100%** ($\text{EV} = +19,62\%$).
    2. **`P2_PAREDE_SUBINDO_CONVEXIDADE` ($n=135$ em 94 datas únicas, 21 ativos):** Welch $t = +2,59$ ($p = 0,0048$, **FDR $q = 0,0135$**); Binomial Hit $\ge +30\%$ ($66,7\%, p = 0,0127$); Block Bootstrap $P(\text{EV} \le 0) = 2,55\%$; pior *Leave-One-Ticker-Out* $= +7,36\%$; Mediana MFE 5d $= +42,4\%$ ($P_{75}=+80,8\%, P_{90}=+141,4\%$); Half-Kelly $= 10,0\%$.
    3. **`P7_GIRO_CALL_2X_GEX_SUBINDO` ($n=518$ em 235 datas únicas, 23 ativos):** Welch $t = +2,57$ ($p = 0,0051$, **FDR $q = 0,0135$**); Binomial Hit $\ge +30\%$ ($62,5\%, p = 0,0045$) e Hit $\ge +50\%$ ($47,3\%, p = 0,0013$); Block Bootstrap 95% CI **$[+0,38\%, +10,60\%]$**, $P(\text{EV} \le 0) = 1,95\%$; pior *Leave-One-Ticker-Out* $= +4,33\%$; melhor alvo em **+100% em 5d** ($\text{Hit} = 23,2\%, \text{EV} = +10,80\%$, Treino $+9,67\%$ / OOS $+12,47\%$).
    4. **`P4_ACAO_EM_V_Z2_CALL_OTM_2X` ($n=41$ em 37 datas únicas, 20 ativos) e `P5_ACAO_EM_V_IDIOSSINCRATICO_CALL_FLOW` ($n=49$ em 43 datas únicas):** provam estatisticamente ser **padrões de tiro curto (`D+1`)** — Binomial exato para máxima $\ge +1\%$ no dia seguinte tem **$p = 0,00033$ (82,9% de acerto)** em `P4` e **$p = 0,00052$ (79,6% de acerto)** em `P5` (e em `P4` a expectativa em `D+1` buscando $+30\%$ na CALL é $+4,65\%$ em 1 único dia: Treino $+3,08\%$ / OOS $+11,10\%$), mas para 5 dias o teste de Welch em `P4` tem $t = +1,30$ ($p = 0,097$, FDR $q = 0,129$) por amostra menor ($n=41$).
- **Backtest Cronológico e Teste de Estresse nos 45 Ativos com Opções dos 75 Bancos (`scripts/backtest_mathematical_patterns.py` / `results/option_patterns/backtest_45_tickers_report.json`):**
  - Foram reconstruídas dia a dia (`D+1` a `D+5`) **1.940 operações completas** nos **45 ativos** com cadeia ativa (os 23 ativos líquidos iniciais + os **22 ativos virgens** que nunca participaram da descoberta), aplicando **custo/slippage de 2% roundtrip**, trava de abertura limitada (`opt_open <= 1,15 * ref_d0` e `stock_open >= 0,985 * spot_d0`), modo ultra-conservador em `D+1` (sem alvo intradiário no dia da entrada) e **Carteira Real com máximo de 3 posições simultâneas (R$ 1.000/operação)**:
  - **1º Aprovado em Todas as Frentes — `P2_PAREDE_SUBINDO_CONVEXIDADE` (Alvo +50% em até 5d, Custo 2%):**
    - Consolidado 45 ativos: $n=327$, Win Rate **56,9%** (Alvo +50% atingido em **45,0%**), Expectativa **+6,27%**, **PF 1,34**, prazo médio **3,9 dias**.
    - Com Trava de Abertura Limitada: $n=259$, Win Rate **56,8%**, Expectativa **+6,34%**, **PF 1,35**.
    - Modo Ultra-Conservador `D+1` (custo 2%): Expectativa **+5,30%**.
    - Positivo em todas as divisões amostrais: **Treino Original (23 ativos)**: $n=78$, WR 62,8%, EV **+9,52%**, PF **1,62** | **OOS Temporal (23 ativos)**: $n=57$, WR 56,1%, EV **+8,04%**, PF **1,44** | **22 Ativos Virgens**: $n=192$, WR 54,7%, EV **+4,43%**, PF **1,22** (nos virgens líquidos destacaram-se `CXSE3`, `BBSE3`, `SBSP3`, `CEAB3`, `BEEF3`; papéis defensivos de baixa vol como `EGIE3`, `VIVT3`, `ABEV3` foram negativos) | **Soma Não-Vista (`OOS + Virgens`, $n=249$)**: WR 55,0%, EV **+5,26%**, PF **1,27**.
    - **Carteira Cronológica (Máx. 3 posições simultâneas, R$ 1.000/trade, Custo 2%):** Completo ($n=170$): **R$ +17.138,87 líquidos**, Max Drawdown **R$ -3.685,94**, EV **+10,08%**, **PF 1,60**. Somente Não-Visto (`OOS + Virgens`): **R$ +9.595,72 líquidos**, **PF 1,36**.
  - **2º Aprovado — `P3_PAREDE_SUBINDO_3D_FLUXO_5X` (Alvo +50% em até 5d, Custo 2%):**
    - Positivo em Treino (**+9,62% / PF 1,65**), OOS Temporal (**+7,18% / PF 1,44**), 22 Virgens (**+0,15% / PF 1,01**) e Carteira 3 slots Não-Vista (**R$ +4.242,76 / PF 1,18**; Completo **R$ +8.517,68 / PF 1,35**).
  - **3º Aprovado nos 23 Líquidos (Exige Universo Líquido) — `P1_PAREDE_SUBINDO_GEX_FLUXO` e `P7_GIRO_CALL_2X_GEX_SUBINDO`:**
    - `P1` teve excelente performance nos 23 ativos líquidos (**Treino +21,47% / PF 3,42** e **OOS +10,92% / PF 1,61**, Carteira 3 slots **R$ +5.933,75 / PF 1,30**), mas caiu para **-4,02% (PF 0,83)** nos 22 ativos secundários virgens, provando que sem filtro de liquidez/volatilidade do ativo-objeto não deve ser operado fora das ~20 ações mais líquidas.
    - `P7` (Alvo +100% em 5d) fez **+8,42% (PF 1,37)** no Treino e **+10,82% (PF 1,52)** no OOS dos 23 líquidos, e subiu de `+5,04%` para **+7,80% (PF 1,34)** em 731 trades ao aplicar a Trava de Abertura Limitada.
  - **Reprovado na Execução Real de Opções — `P4_ACAO_EM_V_Z2_CALL_OTM_2X`:**
    - Embora a ação repique $\ge +1\%$ em `D+1` em 82,9% dos casos, na opção real com custo de 2% perdeu **-4,10% (PF 0,65)** em `D+1` e **-14,04% (PF 0,47)** em `D+5` nos 22 ativos virgens (e `-3,32%` no modo ultra-conservador `D+1`), devido a *IV crush* pós-pânico e spread de abertura. Só fica positivo (+3,92%, PF 1,20) com trava estrita de ordem limitada na abertura e restrito aos papéis de alta liquidez.
- **Segunda Rodada de Mineração — Padrões de Alta Taxa de Acerto (70% a 83%+) e Ensembles Multi-Padrões (`scripts/mine_high_winrate_patterns.py` e `scripts/backtest_high_winrate_systems.py` / `results/option_patterns/high_winrate_systems_report.json`):**
  - Ao enriquecer o painel de **13.896 ativo-pregões nos 45 ativos** com 47 blocos atômicos (geometria de Call Wall como ímã `+2% a +10%`, apoio sobre a Put Wall `-0,5% a +3%`, elevação da Put Wall em 3d, `IV Rank 20d <= 35% / 50%` contra *IV crush*, estoque `Call OI >= 1,5x Put OI`, abertura líquida `Delta OI > +1%` e `Virada em V Confirmada` quando a ação caiu até ontem e virou positiva hoje fechando nos 30% superiores do dia), **330 combinações** passaram simultaneamente em Treino, OOS Temporal e nos 22 Ativos Virgens (com custo de 2% incluso):
  - **8 Novos Padrões Individuais de Alta Assertividade (`HWR_1` a `HWR_8`, todos com custo de 2% descontado):**
    1. **`HWR_1_IMA_PUT_WALL_FLUXO_3.5X` (`CALL_WALL_IMÃ_2_10PCT + PERTO_PUT_WALL + CP_VOL_3.5X`):** **108 operações** (42 Treino / 10 OOS / 56 Virgens) | Bate +20% em **80,6%** e +30% em **72,2%** | Saída Alvo +20%: **Win Rate 83,3%** (Tr 83,3% / OOS 90,0% / Vir 82,1%), EV **+5,04%**, PF **1,54** | Saída Alvo +30%: **Win Rate 76,9%** (Tr 81,0% / OOS 80,0% / Vir 73,2%), EV **+8,33%** (Tr +11,46% / OOS +10,15% / Vir +5,65%), PF **1,70**.
    2. **`HWR_2_PAREDE_SUBIU_OTM_3X_IV_BARATA` (`WALL_SUBIU_1D + OTM_VOL_3.0X + IV_RANK_BAIXO_50`):** **88 operações** em 36 ativos (20 Treino / 12 OOS / 56 Virgens) | Bate +15% em **85,2%**, +20% em **80,7%**, +30% em **70,5%** e +50% em **53,4%** | Saída Alvo +20%: **Win Rate 80,7%**, EV **+6,27%**, PF **1,79** | Saída Alvo +30%: **Win Rate 72,7%**, EV **+9,02%**, PF **1,86** | Saída Alvo +50%: **Win Rate 63,6%**, EV **+14,55%** (Tr +9,26% / OOS +9,80% / Vir **+17,45%**), PF **2,17** (Carteira 3 slots: **R$ +9.515,85** com DD de apenas **R$ -1.211,14**).
    3. **`HWR_3_PUT_WALL_FLUXO_5X_GEX_SUBINDO` (`PERTO_PUT_WALL + CP_VOL_5.0X + GEX_SUBINDO_3D`):** **88 operações** (22 Treino / 8 OOS / 58 Virgens) | Bate +20% em **79,5%**, +30% em **70,5%** e +50% em **55,7%** | Saída Alvo +20%: **Win Rate 80,7%**, EV **+4,55%** | Saída Alvo +30%: **Win Rate 76,1%** (Tr 81,8% / OOS 75,0% / Vir 74,1%), EV **+8,89%**, PF **1,81** | Saída Alvo +50%: **Win Rate 68,2%**, EV **+12,89%** (Tr +20,86% / OOS +16,82% / Vir +9,32%), PF **1,83**.
    4. **`HWR_4_PAREDE_SUBIU_CALL_OI_TOPO_70` (`WALL_SUBIU_1D + CALL_OI_DOMINA + FECHOU_TOPO_70`):** **130 operações** (34 Treino / 27 OOS / 69 Virgens) | Bate +20% em **79,2%** e +30% em **70,0%** | Saída Alvo +30%: **Win Rate 72,3%** (Tr 73,5% / OOS 70,4% / Vir 72,5%), EV **+5,45%**, PF **1,39** | Saída Alvo +50%: EV **+6,38%** (OOS +10,04% / Vir +6,93%).
    5. **`HWR_5_PAREDE_SUBIU_FLUXO_2.5X_CALL_OI` (`WALL_SUBIU_1D + CP_VOL_2.5X + CALL_OI_DOMINA`):** **114 operações** (31 Treino / 26 OOS / 57 Virgens) | Bate +20% em **78,9%** e +30% em **71,1%** | Saída Alvo +30%: **Win Rate 73,7%**, EV **+7,87%**, PF **1,66** | Saída Alvo +50%: **Win Rate 62,3%**, EV **+9,52%**, PF **1,58**.
    6. **`HWR_6_VIRADA_EM_V_CONFIRMADA_IV_BAIXA` (`VIRADA_V_CONFIRMADA + CP_VOL_2.5X + IV_RANK_BAIXO_35`):** resolveu a falha do "V" bruto exigindo confirmação da virada (`prev_ret_3d <= -1,5%`, `ret_1d > 0` e `close_in_range >= 0,65`) com IV barata (`IV Rank <= 35%`): **91 operações** | Saída Alvo +20%: **Win Rate 76,9%** (Tr 82,4% / **OOS 100,0%** / Vir 70,5%) | Saída Alvo +30%: **Win Rate 70,3%** (Tr 70,6% / **OOS 84,6%** / Vir 67,2%), EV **+3,12%** (+13,86% no OOS).
    7. **`HWR_7_PISO_SUBINDO_3D_FLUXO_3.5X_DOI_POS` (`PUT_WALL_SUBIU_3D + CP_VOL_3.5X + DOI_CALL_POS`):** alta frequência com **248 operações** (55 Treino / 34 OOS / 159 Virgens) | Saída Alvo +20%: **Win Rate 75,8%** | Saída Alvo +30%: **Win Rate 69,0%**, EV **+4,19%**, PF **1,30** | Saída Alvo +50%: **Win Rate 61,7%**, EV **+9,18%** (Tr +6,84% / OOS +9,78% / Vir +9,85%), PF **1,56** (Carteira 3 slots: **147 ops**, **R$ +13.000,02**, sendo **R$ +12.002,61 nos Não-Vistos**).
    8. **`HWR_8_PAREDE_SUBIU_FLUXO_3.5X_ULTRA_CONVEX` (`WALL_SUBIU_1D + CP_VOL_3.5X + CONVEX_055`):** **194 operações** (42 Treino / 32 OOS / 120 Virgens) | Saída Alvo +30%: **Win Rate 69,1%**, EV **+4,67%**, PF **1,34** | Saída Alvo +50%: **Win Rate 60,3%**, EV **+8,06%** (OOS +15,41% / Vir +6,47%), PF **1,46**.
  - **3 Sistemas Combinados (Ensembles Multi-Padrões sem duplicar ativo-dia, Custo 2% incluso):**
    - **`ENSEMBLE_A_6_PADROES_ELITE` (União de `HWR_1` a `HWR_6`):** **484 operações** em 43 ativos (127 Treino / 75 OOS / 282 Virgens) | Alvo +20%: **Win Rate 79,3%** (EV +3,90%, PF 1,39) | Alvo +30%: **Win Rate 72,7%** (Tr 77,2% / OOS 72,0% / Vir 70,9%), EV **+6,47%**, PF **1,51** | Carteira 3 slots (Alvo +50%, 200 ops): **R$ +14.068,63** (Não-Visto: **R$ +10.112,12**).
    - **`ENSEMBLE_B_8_PADROES_COMPLETO` (União de `HWR_1` a `HWR_8`):** **760 operações** em 44 ativos (188 Treino / 116 OOS / 456 Virgens) | Alvo +20%: **Win Rate 76,8%** | Alvo +30%: **Win Rate 70,1%** (EV +4,81%, PF 1,35; Carteira 3 slots: **260 ops**, WR **69,6%**, **R$ +11.586,14**) | Alvo +50%: **Win Rate 60,0%**, EV **+6,81%** (Carteira 3 slots: **226 ops**, **R$ +18.426,81**, DD **R$ -4.241,46**, Não-Visto: **R$ +12.100,60**).
    - **`ENSEMBLE_C_CONFLUENCIA_2_OU_MAIS` (Super Confluência: $\ge 2$ dos 8 padrões disparando juntos no mesmo ativo e dia):** **205 operações** em 38 ativos (56 Treino / 32 OOS / 117 Virgens) | Atinge +20% em **81,5%**, +30% em **74,6%** e +50% em **56,1%** | Na **Carteira Real de 3 posições (R$ 1.000/trade, Custo 2%)**:
      - **Alvo +20%:** **157 operações**, **Win Rate `82,2%`** (Não-Visto: **79,5%**), **R$ +10.272,21**, DD **R$ -1.833,02**, EV **+6,54%**, PF **1,84**, prazo **2,8 dias**.
      - **Alvo +30%:** **153 operações**, **Win Rate `78,4%`** (Não-Visto: **74,1%**), **R$ +17.238,45** (Não-Visto: **R$ +8.882,33**), DD **R$ -2.690,33**, EV **+11,27%**, PF **2,16**, prazo **3,2 dias**.
      - **Alvo +50%:** **136 operações**, **Win Rate `69,1%`** (Não-Visto: **67,0%**), **R$ +21.248,83** (Não-Visto: **R$ +14.316,49**), DD **R$ -2.886,33**, EV **+15,62%**, PF **2,22**, prazo **4,0 dias**.
- **Terceira Rodada (Super Rodada — 2.347.932 Estratégias com 4 Quadrantes + Teste de Platô $\pm 10\%$, `scripts/super_round_500k_miner.py` / `results/option_patterns/super_round_500k_report.json`):**
  - Extraídos painéis diários v2 de todos os 75 bancos SQLite, encontrando **67 ativos com opções** e **19.136 ativo-pregões** (persistidos em `results/option_patterns/cache_v2/*.parquet`, releitura `< 1s`), incluindo: Ticket Médio Institucional por negócio (`financial_volume / trades` em Calls vs Puts), Concentração da Call Wall (`call_wall_oi / call_oi`), Estrutura a Termo de IV (`iv_term_slope`: curta 8–24d vs média 25–60d), Vanna e Charm líquidos ponderados por OI, **3 Perfis Reais de Delta por pregão** (`ITM_ATM` Delta ~0,63, `CORE` Delta ~0,52, `OTM_CONVEX` Delta ~0,40), tiro de 3 dias (`CORE_T25_3D`) e **Stop de Invalidação no 2º dia útil (`STOPD2`** caso a ação feche abaixo da mínima do dia do sinal `D0`).
  - Foram avaliadas **196.742 regras de entrada** $\times$ **12 modos de saída/delta/StopD2** = **2.347.932 estratégias completas** (em **41,1s** após o cache).
  - Aplicando as duas travas simultâneas (**lucro líquido > +1,5% após 2% de custo nos 4 Quadrantes Independentes**: `Q1_Treino1`, `Q2_Treino2`, `Q3_OOS_Temporal` e `Q4_44_Ativos_Virgens`, mais **Teste de Platô $\pm 10\%$** em todos os limiares contínuos sem perder mais de 30% do EV), apenas **92 estratégias (0,0039%)** sobreviveram:
    1. **`LIQ_250K + WALL_SUBIU_1D + OTM_VOL_3.0X + ROMPEU_MAX_5D` (`CORE_T20_5D`):** **73 ops** (33 ativos) | **Win Rate 78,1%** (`Q1 83,3% | Q2 76,5% | OOS 84,2% | Virgens 74,2%`) | Platô WR **`[78,2%, 78,3%]`** | EV **+4,59%** (`OOS +7,81%`) | PF **1,50**.
    2. **`LIQ_250K + CP_VOL_3.5X + CALL_OI_DOMINA_2.0X + COMPRESSAO_RANGE` (`ITM_T20_5D`, Delta ~0,63):** **94 ops** | **Win Rate 75,5%** (`Q1 88,9% | Q2 75,0% | OOS 91,7% | Virgens 70,5%`) | Platô WR **`[74,5%, 74,5%]`** | EV **+4,67%** (`OOS +12,08%`) | PF **1,55**.
    3. **`GEX_SUBINDO_3D + VANNA_SUBINDO_3D + COMPRESSAO_RANGE + ROMPEU_MAX_5D` (`ITM_T20_5D`, Delta ~0,63):** **140 ops** (58 ativos) | **Win Rate 75,0%** (`Q1 75,0% | Q2 92,3% | OOS 88,0% | Virgens 68,9%`) | Platô WR **`[73,8%, 78,2%]`** | EV **+4,64%** (`OOS +9,64%`) | PF **1,56**.
    4. **`CALL_WALL_IMA_2_10 + CP_VOL_3.5X + VANNA_SUBINDO_3D + FECHOU_TOPO_80` (`CORE_T25_3D`, Tiro de 3 dias +25%):** **144 ops** (47 ativos) | **Win Rate 73,6%** (`Q1 72,7% | Q2 85,7% | OOS 80,0% | Virgens 71,6%`) | EV **+6,23%** (`OOS +10,29% | Virgens +5,59%`) | PF **1,68**.
    5. **`PERTO_PUT_WALL + TUBARAO_CP_TICKET_2.2X + GEX_SUBINDO_3D + VANNA_SUBINDO_3D` (`CORE_T30_5D`):** **153 ops** (48 ativos) | **Win Rate 72,5%** (`Q1 66,7% | Q2 88,9% | OOS 73,3% | Virgens 71,7%`) | Platô WR **`[71,6%, 75,2%]`** | EV **+8,18%** (`OOS +6,21% | Virgens +7,63%`) | PF **1,76**.
    6. **`CALL_TRADES_1.8X + VANNA_SUBINDO_3D + IV_CONTANGO + FECHOU_TOPO_80` (`CORE_T30_5D`):** **225 ops** (66 ativos) | **Win Rate 71,1%** (`Q1 100% | Q2 73,9% | OOS 79,2% | Virgens 68,4%`) | Platô WR **`[70,7%, 72,3%]`** | EV **+6,23%** (`OOS +11,50%`) | PF **1,51** (com `FECHOU_TOPO_70`: **330 ops**, WR **70,0%**, `OOS 75,9%`, EV **+5,50%**).
    7. **`LIQ_250K + WALL_SUBIU_1D + CP_VOL_3.5X + GEX_SUBINDO_3D` (`OTM_T50_5D`, Delta ~0,40, Alvo +50%):** **85 ops** (33 ativos) | **Win Rate 70,6%** (`Q1 87,5% | Q2 81,8% | OOS 75,0%`) | EV **+12,53%** (`OOS +15,87% | Virgens +5,53%`) | PF **1,76**.
    8. **`PERTO_PUT_WALL + CP_VOL_3.5X + TUBARAO_CP_TICKET_1.5X + FECHOU_TOPO_70` (`CORE_T30_5D_STOPD2`, com Stop em `D+2`):** **227 ops** | **Win Rate 70,0%** | EV **+7,03%** | PF **1,64**.
  - **Comparação Maçã com Maçã nos mesmos 45 ativos líquidos da 2ª rodada (`scripts/check_round3_winrates.py`):** a queda aparente de ~4 pontos na tabela bruta devia-se apenas à inclusão de 22 bancos extras sem liquidez (67 vs 45 ativos) e à exibição do Alvo +30% em vez do Alvo +20%. Nos mesmos 45 ativos líquidos, a taxa de acerto da 3ª rodada **subiu**:
    - **`R3_4` (`CALL_WALL_IMA_2_10 + CP_VOL_3.5X + VANNA_SUBINDO_3D + FECHOU_TOPO_80`, $n=69$):** Alvo +20% = **84,1% de acerto** (OOS **90,0%** / 22 Virgens **79,4%**) | Alvo +30% = **75,4% de acerto** (OOS **80,0%**) | EV50 = **+13,26%**.
    - **`R3_9` (`CALL_WALL_IMA_2_10 + PERTO_PUT_WALL + CP_VOL_3.5X + TUBARAO_CP_TICKET_1.5X`, $n=98$):** Alvo +20% = **83,7% de acerto** | Alvo +30% = **76,5% de acerto** (OOS **77,8%** / 22 Virgens **72,0%**), EV30 = **+8,05%**.
    - **`SUPER_CONFLUENCIA_R3_2_OU_MAIS` ($\ge 2$ padrões da 3ª rodada juntos nos 45 ativos, $n=85$):** Alvo +20% subiu de 82,4% para **`87,1% de acerto`** (**85,0% no OOS** e **85,0% nos 22 Ativos Virgens**); Alvo +30% subiu de 77,1% para **`82,4% de acerto`** (**85,0% no OOS** e **77,5% nos 22 Virgens**), com EV30 = **+12,41%** e EV50 = **+18,29%**.
    - **`ULTRA_CONFLUENCIA_R3_3_OU_MAIS` ($\ge 3$ padrões da 3ª rodada juntos nos 45 ativos, $n=21$):** **20 acertos em 21 operações (`95,2% de acerto`**, sendo **100,0% no OOS** [4/4] e **100,0% nos 22 Ativos Virgens** [10/10]), com EV30 = **+20,66%** e EV50 = **+21,33%**.
- **Quarta Rodada (523.625 Regras de Entrada $\times$ 22 Modos de Entrada `Abertura D+1` vs. `Final do Dia D0` e `Com Parcial` vs. `Sem Parcial` = 11.519.750 Estratégias nos 45 Ativos Líquidos, `scripts/super_round_45_liquid_parciais_entries.py` / `results/option_patterns/massive_523k_45stocks_survivors.csv`):**
  - Concluída em **143,9s**, com **5.571 regras sobreviventes** acima de 70% de acerto nos 4 Quadrantes + Teste de Platô ($\pm 10\%$).
  - **Comparativo Estrutural nas 5.571 Sobreviventes:**
    1. `Abertura D+1 | Sem Parcial (+30%)`: Win Rate médio **66,2%** | EV líquido **+1,89%**.
    2. `Final do Dia D0 | Sem Parcial (+30%)`: Win Rate médio **68,7%** | EV líquido **+3,59%** (+90% de eficiência por capturar o gap de `D+1`).
    3. `Abertura D+1 | Parcial 50% em +20% + Stop 0% Breakeven p/ +50% (PARCIAL_20_50_BE)`: Win Rate médio salta para **71,0%** | EV líquido **+4,39%**.
    4. `Final do Dia D0 | Parcial 50% em +20% + Stop 0% Breakeven p/ +50% (PARCIAL_20_50_BE)`: Win Rate médio salta para **73,1%** | EV líquido **+5,66%** ($3\times$ o retorno líquido do sem parcial na abertura).
  - **Destaques Campeões de 11,5 Milhões (4 Quadrantes + Platô $\pm 10\%$, Custo 2% incluso):**
    - **`PERTO_PUT_WALL + CALL_TRADES_2.5X + DOI_CALL_POS + ROMPEU_MAX_5D` (`FIM_DIA_D0__PARCIAL_20_50_BE`, $n=51$ em 24 ativos):** **Win Rate `88,2%`** (`OOS 72,7% | 22 Virgens 91,7%`), Platô `[84,0%, 88,6%]`, EV **+16,70%**, **PF 3,53**.
    - **`WALL_SUBIU_1D + DOI_CALL_FORTE + TUBARAO_CP_TICKET_3.0X + GEX_POS_ZERO` (`ABERT_D1__PARCIAL_20_50_BE`, $n=58$ em 22 ativos):** **Win Rate `86,2%`** (`OOS 90,0% | 22 Virgens 80,6%`), Platô `[84,1%, 90,7%]`, EV **+11,80%** (`OOS +16,84%`), **PF 2,33**.
    - **`TRAVA_ABERT_LIM + WALL_SUBIU_1D + OTM_VOL_3.0X + IV_RANK_BAIXO_50` (`ABERT_D1__PARCIAL_20_50_BE`, $n=78$ em 33 ativos):** **Win Rate `85,9%`** (`22 Virgens 87,8%`), Platô `[81,7%, 83,3%]`, EV **+17,86%** (`Virgens +20,98%`), **PF 5,40**.
    - **`PUT_WALL_SUBIU_3D + CP_VOL_2.5X + DOI_CALL_FORTE + VANNA_SUBINDO_3D` (`FIM_DIA_D0__PARCIAL_20_50_BE`, $n=148$ em 37 ativos):** **Win Rate `85,1%`** (`OOS 90,6% | 22 Virgens 83,3%`), Platô `[82,6%, 87,5%]`, EV **+14,44%** (`OOS +20,27% | Virgens +12,04%`), **PF 2,97**.
    - **`PUT_WALL_SUBIU_3D + CALL_VOL_2.5X + TUBARAO_CP_TICKET_1.5X + VANNA_SUBINDO_3D` (`FIM_DIA_D0__PARCIAL_20_50_BE`, $n=97$ em 35 ativos):** **Win Rate `83,5%`** (**`OOS 100,0% [17/17]`** | `22 Virgens 80,3%`), Platô `[81,2%, 81,9%]`, EV **+13,73%** (`OOS +25,32%`), **PF 2,77**.
  - **Destaques de Alta Frequência nas 5.571 Sobreviventes (`230 a 921 operações nos 320 pregões úteis` — 1 a 3 operações por dia útil, todas aprovadas nos 4 Quadrantes + Platô $\pm 10\%$ com `FIM_DIA_D0__PARCIAL_20_50_BE`):**
    - **`LIQ_250K + PUT_WALL_SUBIU_3D + CP_VOL_2.5X + DOI_CALL_FORTE` ($n=230$ em 320 pregões):** **Win Rate `82,2%`** (`OOS 84,7% | 22 Virgens 82,2%`), EV **+12,07%**, **PF 2,42**.
    - **`LIQ_100K + PUT_WALL_SUBIU_3D + CP_VOL_2.5X + DOI_CALL_FORTE` ($n=272$ em 320 pregões):** **Win Rate `80,9%`** (`OOS 84,7% | 22 Virgens 78,5%`), EV **+10,58%**, **PF 2,10**.
    - **`LIQ_250K + CALL_TRADES_2.5X + DOI_OTM_POS + CONVEX_050` ($n=317$ em 320 pregões, ~1 op/dia útil):** **Win Rate `79,2%`** (`OOS 75,9% | 22 Virgens 80,2%`), EV **+9,22%**, **PF 1,82**.
    - **`PUT_WALL_SUBIU_3D + PERTO_PUT_WALL_5PCT + DOI_CALL_FORTE + VANNA_SUBINDO_3D` ($n=383$ em 320 pregões, ~1,2 op/dia):** **Win Rate `78,1%`** (`OOS 82,7% | 22 Virgens 75,8%`), EV **+10,41%**, **PF 2,09**.
    - **`LIQ_250K + CALL_TRADES_1.8X + DOI_OTM_POS + CONVEX_050` ($n=583$ em 320 pregões, ~1,8 op/dia):** **Win Rate `76,8%`** (`OOS 76,8% | 22 Virgens 75,9%`), EV **+8,13%**, **PF 1,70**.
    - **`LIQ_250K + CALL_TRADES_1.8X + DOI_CALL_POS + CONVEX_050` ($n=921$ em 320 pregões, ~2,9 ops/dia):** **Win Rate `75,2%`** (`OOS 78,0% | 22 Virgens 73,2%`), EV **+6,81%**, **PF 1,55**.
- **Quinta Rodada — Tiro Rápido `D+1`, `D+2` e Máximo `D+3` com Alvo Mínimo `+20%` na CALL (`scripts/mine_fast_d1_d3_target20.py` / `results/option_patterns/fast_d1_d3_target20_survivors.csv`):**
  - **Pedido de Matheus:** assertividade máxima com **alvo mínimo de `+20%` na CALL** no modo mais rápido possível (**`D+1`, `D+2` ou no máximo `D+3`** — encerrando obrigatoriamente até o fechamento do 3º pregão).
  - Foram avaliadas **523.625 regras de entrada $\times$ 15 modos rápidos (`D+1`, `D+2`, `D+3` em Abertura D+1 e Final do Dia D0, com e sem parcial) = 7.854.375 estratégias** nos **45 ativos líquidos** (`320` pregões úteis, `13.896` ativo-pregões), com custo de 2% incluso. **288 estratégias** sobreviveram aos 4 Quadrantes Independentes + Teste de Platô ($\pm 10\%$), com **prazo médio de permanência entre `1,7 e 2,0 dias úteis`**.
  - **Campeãs Individuais de Tiro Rápido (`D+1` a `D+3`, Alvo Mínimo `+20%`, Custo 2% incluso):**
    1. **`TRAVA_ABERT_LIM + PERTO_PUT_WALL + CP_VOL_2D_2.5X + DOI_OTM_POS` (`ABERT_D1__PARCIAL_20_40_BE_D3`, $n=87$ em 25 ativos):** **Win Rate `81,6%`** (`OOS 90,0% | 22 Virgens 78,3%`), Platô `[74,2%, 88,2%]` | Bate `+20%` em **`37,9%` no `D+1`**, **`64,4%` até `D+2`** e **`77,0%` até `D+3`** | Prazo médio **`2,0 dias`** | EV **+10,40%** (`OOS +11,18%`), **PF 2,31**.
    2. **`PUT_WALL_SUBIU_3D + CALL_VOL_2.5X + TUBARAO_CP_TICKET_1.5X + VANNA_SUBINDO_3D` (`FIM_D0__PARCIAL_20_40_BE_D3`, $n=97$ em 35 ativos):** **Win Rate `80,4%`** (**`OOS 94,1%`** | `22 Virgens 78,7%`), Platô `[76,9%, 79,2%]` | Bate `+20%` em **`45,4%` no `D+1`**, **`68,0%` até `D+2`** e **`78,4%` até `D+3`** | Prazo médio **`1,9 dias`** | EV **+11,24%** (**`OOS +20,19%`**), **PF 2,72**.
    3. **`DOI_OTM_POS + CALL_OI_DOMINA_1.5X + TUBARAO_CP_TICKET_3.0X + IV_RANK_BAIXO_50` (`ABERT_D1__PARCIAL_20_40_BE_D3`, $n=86$ em 22 ativos):** **Win Rate `80,2%`** (`OOS 77,8% | 22 Virgens 79,1%`) | Bate `+20%` em **`41,9%` no `D+1`**, **`60,5%` até `D+2`** e **`74,4%` até `D+3`** | Prazo médio **`2,0 dias`** | EV **+10,27%**, **PF 2,54**.
    4. **`WALL_CONC_25PCT + VANNA_SUBINDO_3D + FECHOU_TOPO_80 + ROMPEU_MAX_5D` (`FIM_D0__PARCIAL_20_40_BE_D3`, $n=80$ em 26 ativos):** **Win Rate `78,8%`** (`OOS 80,0% | 22 Virgens 79,6%`) | Bate `+20%` em **`50,0%` já no `D+1`**, **`63,7%` até `D+2`** e **`72,5%` até `D+3`** | Prazo médio **`1,9 dias`** | EV **+7,73%**, **PF 1,83**.
    5. **`PERTO_PUT_WALL + CP_VOL_2D_2.5X + DOI_CALL_FORTE + TUBARAO_CP_TICKET_1.5X` (`ABERT_D1__PARCIAL_20_40_BE_D3`, $n=89$ em 25 ativos):** **Win Rate `78,7%`** (`OOS 77,8% | 22 Virgens 79,6%`) | Bate `+20%` em **`47,2%` no `D+1`**, **`67,4%` até `D+2`** e **`76,4%` até `D+3`** | Prazo médio **`1,9 dias`** | EV **+8,53%**, **PF 1,95**.
    6. **`PUT_WALL_SUBIU_3D + CALL_TRADES_2.5X + GEX_SUBINDO_3D + CONVEX_050` (`FIM_D0__PARCIAL_20_40_BE_D3`, $n=123$ em 41 ativos — Campeã de Velocidade `D+1`):** **Win Rate `77,2%`** (`OOS 78,6% | 22 Virgens 75,5%`) | Bate `+20%` em **`60,2%` já no `D+1` (1º dia!)**, **`70,7%` até `D+2`** e **`76,4%` até `D+3`** | Prazo médio **`1,7 dias`** | EV **+9,44%** (`OOS +12,97%`), **PF 2,15**.
    7. **Regras Rápidas de Alta Frequência (`256 a 317 ops` nos 320 pregões, ~1 op/dia, prazo médio `1,8 a 1,9 dias`):**
       - `LIQ_250K + CALL_TRADES_2.5X + DOI_OTM_POS + CONVEX_050` ($n=317$, ~21 ops/mês): **Win Rate `73,8%`** (`OOS 74,7% | Virgens 73,9%`), bate `+20%` em **`51,1%` no `D+1`**, **`63,7%` até `D+2`** e **`71,3%` até `D+3`**, prazo **`1,9 dias`**, EV **+6,06%**, **PF 1,58**.
       - `CALL_TRADES_2.5X + DOI_OTM_POS + VANNA_SUBINDO_3D + CONVEX_050` ($n=256$, ~17 ops/mês): **Win Rate `73,8%`** (`OOS 81,6% | Virgens 73,0%`), bate `+20%` em **`53,5%` no `D+1`**, **`65,2%` até `D+2`** e **`71,1%` até `D+3`**, prazo **`1,8 dias`**, EV **+5,64%** (`OOS +10,76%`).
  - **Sistema Unificado de Tiro Rápido (`D+1` a `D+3`, Prazo Médio `1,86 dias úteis`):**
    - **União das 6 Regras Rápidas (`1+ regra ativa`, $n=487$ em 320 pregões — ~30 ops/mês / 1,5 op/dia):** bate `+20%` em **`48,7%` no `D+1`**, **`64,9%` até `D+2`** e **`73,3%` até `D+3`** (prazo médio **`1,86 dias`**):
      - Saída 100% em `+20%` até `D+2`: Win Rate **`71,3%`** | EV **+3,54%**.
      - Saída 100% em `+20%` até `D+3`: Win Rate **`76,2%`** (`OOS 79,7% | Virgens 73,8%`) | EV **+4,31%**.
      - **Parcial `50% em +20%` + Stop 0% Breakeven p/ `+40%` até `D+3`:** Win Rate **`76,2%`** (`OOS 79,7% | Virgens 73,8%`) | EV **+8,15%** (`OOS +11,02%`) | **PF 1,93**.
    - **Confluência Rápida (`2+ regras rápidas juntas no mesmo dia`, $n=100$ em 320 pregões — ~7 ops/mês):** bate `+20%` em **`47,0%` no `D+1`**, **`67,0%` até `D+2`** e **`79,0%` até `D+3`** (prazo médio **`1,86 dias`**):
      - Saída 100% em `+20%` até `D+2`: Win Rate **`74,0%`** | EV **+4,89%**.
      - Saída 100% em `+20%` até `D+3`: Win Rate **`81,0%`** (`OOS 85,7% | Virgens 79,3%`) | EV **+7,02%**.
      - **Parcial `50% em +20%` + Stop 0% Breakeven p/ `+40%` até `D+3`:** Win Rate **`81,0%`** (`OOS 85,7% | Virgens 79,3%`) | EV **+11,38%** (`OOS +15,74%`) | **PF 2,62**.
  - **Documento consolidado criado e atualizado na raiz do projeto:** `descobertas_matematicas_opcoes/DESCOBERTAS_PADROES_MATEMATICOS_OPCOES.md` (Seções 1 a 10.4).
  - **Scanner Operacional Diário e Painel Visual Web Localhost de Tiro Rápido (`D+1` a `D+3`, Alvo Mínimo `+20%`) implementados e validados:**
    - **Motor do Scanner:** `scripts/scan_tiro_rapido_d3.py` (saídas persistidas em `results/option_patterns/ultimo_scan_tiro_rapido_d3.txt` e `.json`; cache diário enriquecido v2 dos 45 ativos em `results/option_patterns/daily_raw_cache/*_v2.parquet`, contendo até 3 perfis de CALL por ação: `CORE_ATM`, `ITM_SEGURA`, `OTM_EXPLOSIVA`).
    - **Painel Visual em Localhost (`http://127.0.0.1:8050`):** `scripts/servidor_tiro_rapido.py` e atalho 1-clique `abrir_painel_tiro_rapido.bat` na raiz do projeto. Exibe visualmente as 2 Mesas separadas em abas, explica em português por que cada ação ativou, permite alternar entre os 3 strikes de CALL da série vigente (`K` = `19/11/2026`), traz botão 1-clique para copiar o ticker para o Profit e inclui uma **Boleta/Calculadora Interativa de Leilão** em cada card (mostrando em tempo real se o preço do leilão está na **Faixa Boa / Ideal `🟢`**, **Aceitável até o Teto de +15% `🟡`** ou **Acima do Teto — Abortar `🔴`**, além dos lotes recomendados, Alvo 1 `+20%`, Stop `0x0` e Alvo 2 `+40%`).
    - **Ponte em Tempo Real com Profit RTD via Excel (`rtd.xlsx` + `scripts/rtd_bridge.py`):** gera e sincroniza automaticamente a planilha `rtd.xlsx` (com as abas `LEILAO_E_BOOK_RTD` e `STRIKES_ALTERNATIVOS_RTD`) contendo as fórmulas `=RTD("rtdtrading.rtdserver", , "ATIVO_B_0", "ATRIBUTO")` (`EST`, `PRT`, `QTE`, `ULT`, `QCP`, `OCP`, `OVD`, `QVD`, `ABE`, `MAX`) para as 13 ações ativadas + `BOVA11` e seus 33 códigos de CALL. O endpoint `GET /api/rtd` e o CLI `python scripts/rtd_bridge.py --ler` leem os preços do RTD em tempo real e emitem o veredito automático por ativo (validando se a ação abriu acima do piso de `-1,5%` e se a CALL está na Faixa Boa ou até o Teto de `+15%`).
    - Divide automaticamente os sinais diários nas **2 Mesas Independentes** pedidas por Matheus:
      1. **MESA 1 — Entrada no Fim do Dia (`D0`: 16h45 a 16h55):** 8 regras campeãs (`F1` a `F8`, Win Rate `73,8%` a `80,4%`);
      2. **MESA 2 — Entrada no Leilão / Abertura de `D+1` (`09h55 a 10h15`):** 12 regras campeãs (`A1` a `A12`, Win Rate `72,3%` a `81,6%`).
    - **Leitura oficial do fechamento de Sexta-feira `23/10/2026` (para Segunda-feira `26/10/2026`):**
      - **Mesa 2 (`ABERT_D1` para Segunda-feira `26/10` no Leilão `09h55` / Abertura `10h05` — 8 ações ativadas):**
        1. **`COGN3` (`COGNK332`, Strike R$ 3,31, 27 DTE, Fech D0 R$ 0,27, Giro R$ 302,3k; alternativas `COGNK290` @ R$ 0,43 e `COGNK360` @ R$ 0,16):** **Super Confluência de 3 regras (`A3, A7, A12`, WR `78,7%`, bate `+20%` em `47,2%` no `D+1`, `67,4%` até `D+2` e `76,4%` até `D+3`)** — **Preço Bom no Leilão:** `R$ 0,25 a R$ 0,28` | **Teto Máx (+15%):** `R$ 0,31` | **Piso da Ação:** `COGN3 >= R$ 3,05` | Alvo 1 (`+20%`): `R$ 0,32` | Alvo 2 (`+40%`): `R$ 0,38`;
        2. **`VIVT3` (`VIVTK336`, Strike R$ 33,47, 27 DTE, Fech D0 R$ 1,80):** **Super Confluência (`A9, A12`, WR `74,1%`)** — **Preço Bom no Leilão:** `R$ 1,69 a R$ 1,89` | **Teto Máx:** `R$ 2,07` | **Piso da Ação:** `VIVT3 >= R$ 31,94` | Alvo 1 (`+20%`): `R$ 2,16` | Alvo 2 (`+40%`): `R$ 2,52`;
        3. **`CEAB3` (`CEABK140`, Strike R$ 14,02, 27 DTE, Fech D0 R$ 1,80, Giro R$ 807,3k):** **Super Confluência (`A10, A12`, WR `73,6%`)** — **Preço Bom no Leilão:** `R$ 1,69 a R$ 1,89` | **Teto Máx:** `R$ 2,07` | **Piso da Ação:** `CEAB3 >= R$ 13,63` | Alvo 1 (`+20%`): `R$ 2,16` | Alvo 2 (`+40%`): `R$ 2,52`;
        4. **`DIRR3` (`DIRRK117`, Strike R$ 11,73, Fech D0 R$ 0,94, Giro R$ 137,4k):** Regra `A11` (`WR 72,7%`) — **Preço Bom no Leilão:** `R$ 0,88 a R$ 0,99` | **Teto Máx:** `R$ 1,08` | **Piso da Ação:** `DIRR3 >= R$ 11,39` | Alvo 1 (`+20%`): `R$ 1,13` | Alvo 2 (`+40%`): `R$ 1,32`;
        5. **`MRVE3` (`MRVEK830`, Strike R$ 8,30, Fech D0 R$ 1,37, Giro R$ 5,65M):** Regra `A12` (`WR 72,3%`) — **Preço Bom no Leilão:** `R$ 1,29 a R$ 1,44` | **Teto Máx:** `R$ 1,58` | **Piso da Ação:** `MRVE3 >= R$ 8,11` | Alvo 1 (`+20%`): `R$ 1,64` | Alvo 2 (`+40%`): `R$ 1,92`;
        6. **`MGLU3` (`MGLUK147`, Strike R$ 14,75, Fech D0 R$ 1,34, Giro R$ 3,39M):** Regra `A12` (`WR 72,3%`) — **Preço Bom no Leilão:** `R$ 1,26 a R$ 1,41` | **Teto Máx:** `R$ 1,61` | **Piso da Ação:** `MGLU3 >= R$ 12,50` | Alvo 1 (`+20%`): `R$ 1,61` | Alvo 2 (`+40%`): `R$ 1,88`;
        7. **`VAMO3` (`VAMOK641`, Strike R$ 6,41, Fech D0 R$ 0,92, Giro R$ 744,4k):** Regra `A12` (`WR 72,3%`) — **Preço Bom no Leilão:** `R$ 0,86 a R$ 0,97` | **Teto Máx:** `R$ 1,06` | **Piso da Ação:** `VAMO3 >= R$ 6,31` | Alvo 1 (`+20%`): `R$ 1,10` | Alvo 2 (`+40%`): `R$ 1,29`;
        8. **`CSNA3` (`CSNAK623`, Strike R$ 6,23, Fech D0 R$ 0,56, Giro R$ 80,1k):** Regra `A12` (`WR 72,3%`) — **Preço Bom no Leilão:** `R$ 0,53 a R$ 0,59` | **Teto Máx:** `R$ 0,66` | **Piso da Ação:** `CSNA3 >= R$ 5,98` | Alvo 1 (`+20%`): `R$ 0,67` | Alvo 2 (`+40%`): `R$ 0,78`.
      - **Mesa 1 (`FIM_D0` em `23/10` — 6 ações ativadas):**
        1. **`COGN3` (`COGNK332`, Strike R$ 3,31, 27 DTE, Fech R$ 0,27, Giro R$ 302,3 mil / 294 neg):** Regra `F2` (`WR 79,2%`, bate `+20%` em `58,5%` no `D+1` e `79,2%` até `D+3`) $\to$ Alvo 1 (`+20%`): `R$ 0,32` | Alvo 2 (`+40%`): `R$ 0,38`;
        2. **`BBDC4` (`BBDCK214`, Strike R$ 20,72, 27 DTE, Fech R$ 1,49, Giro R$ 11,02M / 385 neg):** Regra `F8` (`WR 73,8%`) $\to$ Alvo 1 (`+20%`): `R$ 1,79` | Alvo 2 (`+40%`): `R$ 2,09`;
        3. **`CYRE3` (`CYREK377`, Strike R$ 37,75, 27 DTE, Fech R$ 2,95, Giro R$ 601,4 mil / 1.024 neg):** Regra `F8` (`WR 73,8%`) $\to$ Alvo 1 (`+20%`): `R$ 3,54` | Alvo 2 (`+40%`): `R$ 4,13`;
        4. **`BBDC3` (`BBDCK185` @ R$ 1,29)**, **`CSAN3` (`CSANK540` @ R$ 0,56)** e **`CSNA3` (`CSNAK623` @ R$ 0,56)** na Regra `F8`.
      - **⚠️ STATUS ATUAL (`03/11/2026`, com dados B3 atualizados até `30/10/2026` — `02/11` feriado de Finados):**
        - Evolução real de `BOVA11` e `BOVAK205` na semana pós-2º turno (`PR`/`PE` `26/10` a `30/10/2026` baixados em `data/raw/`):
          - **`26/10` (segunda):** `BOVA11` abriu a `R$ 169,00`, bateu máxima `R$ 176,60`, mínima `R$ 165,06` e fechou em **`R$ 172,42`** (-14,51% no dia, giro recorde de `R$ 4,08 bilhões`). `BOVAK205` abriu a `R$ 0,25`, máxima `R$ 0,39`, mínima `R$ 0,05` e fechou a **`R$ 0,17`** (IV B3 caiu de `41,96%` para `35,61%`).
          - **`27/10` (terça):** `BOVA11` tentou repique até máxima `R$ 175,66` e fechou em **`R$ 173,00`**; `BOVAK205` abriu a `R$ 0,18` e fechou a **`R$ 0,04`** (IV B3 desabou para `26,04%`).
          - **`28/10` (quarta):** `BOVA11` caiu para **`R$ 168,47`** (`BOVAK205` fechou a **`R$ 0,03`**).
          - **`29/10` (quinta):** `BOVA11` caiu para **`R$ 166,51`** (`BOVAK205` fechou a **`R$ 0,02`**).
          - **`30/10` (sexta):** `BOVA11` fez mínima em `R$ 164,21` e fechou em **`R$ 165,40`** (-17,99% acumulados desde os `R$ 201,69` pré-urna). A `BOVAK205` fechou a **`R$ 0,02`** (book `R$ 0,01 x R$ 0,02`, ref. B3 `R$ 0,01`, IV `28,06%`, OI ainda em `6,30 milhões` de contratos presos).
        - Para `BOVAK205` (`67x @ R$ 8,90 = R$ 596,30`, vencimento `19/11/2026`) recuperar 50% (`R$ 4,45`) o `BOVA11` precisaria subir ~`+22% a +26%` (voltar a `R$ 201,30–R$ 209,45`); para empatar no `0x0` (`R$ 8,90`), precisaria subir ~`+27% a +29%` (`R$ 209,40–R$ 213,90`). Na prática, a posição já virou pó em preço de tela (`67x @ R$ 0,02 = R$ 1,34`).
        - **Auditoria / Backtest do Scanner de Tiro Rápido (`D+1` a `D+3`) na semana de crise (`26/10` a `30/10/2026`):**
          1. **Proteção da Mesa 2 (`ABERT_D1`) na segunda pós-urna (`26/10`):** as **8 ações** ativadas no fechamento de `23/10` (`COGN3`, `VIVT3`, `CEAB3`, `DIRR3`, `CSNA3`, `MGLU3`, `MRVE3`, `VAMO3`) foram **100% VETADAS (`8/8`) pela trava de piso da ação (`-1,5%`)** já no leilão de abertura de `26/10` (abriram com gaps entre `-7,8%` e `-50,0%`), gerando **R$ 0,00 de perda**. Já as 6 posições da **Mesa 1 (`FIM_D0`)** de sexta `23/10` (quem dormisse comprado no fim de semana do 2º turno) tomaram perda de `-93%` a `-100%`.
          2. **Operações geradas DENTRO da semana `26/10` a `29/10` (`10 sinais totais`: 8 na Mesa 1 `FIM_D0` e 2 na Mesa 2 `ABERT_D1`):** mesmo com o `BOVA11` caindo mais `-4,1%` entre `26/10` (`R$ 172,42`) e `30/10` (`R$ 165,40`), o filtro de fluxo institucional se adaptou à rotação setorial (exportadoras/commodities e techs):
             - **`26/10` (`FIM_D0`) — `TOTS3` (`TOTSK395` @ `R$ 1,07`, Regra `F8`):** bateu **`R$ 1,92` (`+79,4%`) já na abertura de `D+1` (`27/10`)**, cravando **Alvo 1 (`+20%`) e Alvo 2 (`+40%`)** (`+28,0%` líquidos na regra parcial).
             - **`27/10` (`FIM_D0`) — `B3SA3` (`B3SAK154` @ `R$ 0,80`), `MGLU3` (`MGLUK600` @ `R$ 0,84`) e `VAMO3` (`VAMOK306` @ `R$ 0,19`) na Regra `F8`:** falharam na tentativa de repique de domésticas em `28/10` e fecharam `D+3` (`30/10`) com **`-81,2%`**, **`-64,3%`** e **`-78,9%`**.
             - **`27/10` (`ABERT_D1` p/ `28/10`) — `PETR3` (`PETRK601` @ `R$ 2,45`, Regra `A12`):** bateu **`R$ 3,01` (`+22,9%`) em `D+3` (`30/10`)**, cravando **WIN Parcial `+20%`** e fechando a `R$ 2,75` (`+14,12%` líquidos). **`CXSE3` (`CXSEK24` @ `R$ 0,38`, Regra `A6`)** bateu máxima de `R$ 0,45` (`+18,4%` em `D+1`, a `R$ 0,01` do alvo `+20%` de `R$ 0,46`) e recuou para `R$ 0,23` (`-41,47%`).
             - **`28/10` (`FIM_D0`) — `SUZB3` (`SUZBK481` @ `R$ 1,77`, Regra `F3`):** explodiu com a disparada do dólar, batendo **`R$ 2,80` (`+58,2%`) em `D+1` (`29/10`)** e **`R$ 2,94` (`+66,1%`) em `D+2` (`30/10`)** — **WIN Completo `+40%`** (`+28,0%` líquidos). **`CYRE3` (`CYREK177` @ `R$ 0,95`, Regra `F8`)** abriu `D+1` (`29/10`) em **`R$ 1,21` (`+27,4%`)**, cravando **WIN Parcial `+20%`** (`+8,0%` líquidos).
             - **`29/10` (`FIM_D0`) — `CMIN3` (`CMINK436` @ `R$ 0,27`, Regra `F6`):** bateu **`R$ 0,35` (`+29,6%`) já em `D+1` (`30/10`)**, cravando **WIN Parcial `+20%`** (`+22,81%` líquidos). **`SUZB3` (`SUZBK501` @ `R$ 1,45`, Regra `F3`)** bateu **`R$ 1,71` (`+17,9%`) em `D+1` (`30/10`)**, a `R$ 0,03` do Alvo 1 (`R$ 1,74`), seguindo aberta para `D+2` hoje (`03/11`).
          3. **Sinal ativo do fechamento de Sexta-feira `30/10/2026` (para Terça-feira `03/11/2026`):**
             - **Mesa 1 (`FIM_D0` em `30/10`):** **`VALE3` (`VALEK641`, Strike `R$ 62,39`, Fech `R$ 1,76`, Spot `R$ 62,02`)** na Regra `F2` (`WR 79,2%` — desmonte da Call Wall `-3%` + abertura forte de OI em Calls `+2,5%` + ação positiva no dia). Alvo 1 (`+20%`): **`R$ 2,11`** | Alvo 2 (`+40%`): **`R$ 2,46`**.
             - **Mesa 2 (`ABERT_D1` para o leilão de `03/11`):** **0 sinais** (nenhuma ação cumpriu apoio de Put Wall + fluxo comprador para compra na abertura hoje).
        - Por decisão expressa de Matheus diante do *crash* pós-eleitoral na B3, **todas as entradas das Mesas de Abertura (`ABERT_D1`) e Final de Tarde (`FIM_D0`) na B3 permanecem em observação/pausa** até nova ordem.
- **Sexta Rodada — Mercado de Opções Americanas (EUA — Wall Street via CBOE + Yahoo Finance v8, `26/10/2026`):**
  - **Motivação de Matheus:** diante da pausa operacional na B3 por crise político-eleitoral, validar se a mesma matemática de `Call Wall`, `Put Wall`, `GEX`, `Vanna` e fluxo `Call/Put` funciona nas opções dos Estados Unidos (onde Matheus já teve conta na **Tastytrade**) usando **dados 100% gratuitos direto da CBOE (`cdn.cboe.com`) + histórico diário real de contratos de opções no Yahoo Finance v8 (`query1.finance.yahoo.com`)**.
  - **Scripts e Arquivos Criados (isolados da B3 sob `results/us_options/`):**
    - Minerador: `scripts/us_options_round_miner.py` (painéis cacheados em `results/us_options/cache_v1/*_us_panel_v1.parquet`, relatório em `results/us_options/us_options_survivors_report.csv`).
    - Scanner Ao Vivo CBOE: `scripts/scan_us_options_d3.py` (saída em `results/us_options/ultimo_scan_us_options.json`).
  - **Amostra e Divisão nos 4 Quadrantes Independentes dos EUA:**
    - **36 ações/ETFs líquidos dos EUA** = **7.199 ativo-pregões** (24 Ativos Principais: `NVDA, TSLA, AAPL, AMD, AMZN, META, MSFT, GOOGL, PLTR, NFLX, AVGO, COIN, SOFI, BAC, INTC, MARA, PFE, UBER, PYPL, F, SNAP, SPY, QQQ, IWM` + **12 Ativos Virgens de Holdout**: `ORCL, MU, SHOP, CRM, DIS, WMT, JPM, XOM, AAL, CCL, RIOT, SMH`).
    - Quadrantes: `Q1_Treino1` (`1.704`), `Q2_Treino2` (`1.584`), `Q3_OOS_Temporal` (`1.512`, após `20/07/2026`) e `Q4_12_Ativos_Virgens_EUA` (`2.399`), descontando `1,5%` de custo de spread roundtrip.
    - De **75.900 estratégias avaliadas**, **361 estratégias** passaram simultaneamente nos 4 Quadrantes Independentes dos EUA com Win Rate entre **`72,0%` e `88,9%`**.
  - **Campeãs Matemáticas nas Opções dos EUA (4 Quadrantes Aprovados):**
    1. **`TRAVA_ABERT_LIM + PERTO_PUT_WALL_4PCT + CALL_WALL_IMA_2_12PCT + VANNA_SUBINDO_3D + FECHOU_TOPO_65` (`ABERT__PARCIAL_20_50_BE_D5`, $n=54$ em 22 ativos EUA):** **Win Rate `88,9%`** (`Q1 100,0% | Q2 85,7% | OOS 85,0% | 12 Virgens 90,5%`) | Bate `+20%` em **`53,7%` no `D+1`**, **`81,5%` até `D+2`** e **`88,9%` até `D+5`** | EV **+18,98%** (`OOS +14,64% | Virgens +18,83%`), **PF 4,62**.
    2. **Campeã de Tiro Rápido `D+1 a D+3` (`ABERT__PARCIAL_20_40_BE_D3`): `TRAVA_ABERT_LIM + WALL_SUBIU_1D + PUT_WALL_SUBIU_3D + CP_VOL_2D_2.0X + ROMPEU_MAX_5D` ($n=59$ em 23 ativos EUA):** **Win Rate `88,1%`** (`Q1 100,0% | Q2 69,2% | OOS 80,0% | 12 Virgens 100,0%`) | Bate `+20%` em **`66,1%` já no `D+1`**, **`76,3%` até `D+2`** e **`88,1%` até `D+3`** | EV **+14,76%** (`OOS +9,58% | Virgens +22,35%`), **PF 4,89** (e no modo sem parcial `PURO_20_D3`: WR **`88,1%`**, EV **+12,51%**, **PF 4,30**).
    3. **`TRAVA_ABERT_LIM + PERTO_PUT_WALL_4PCT + OTM_VOL_1.8X_MED + VANNA_SUBINDO_3D + FECHOU_TOPO_65` (`ABERT__PARCIAL_20_50_BE_D5`, $n=72$ em 27 ativos EUA):** **Win Rate `87,5%`** (`OOS 88,2% | 12 Virgens 86,7%`), EV **+14,66%**, **PF 3,18**.
    4. **Campeã Fim do Dia (`FIM__PARCIAL_20_50_BE_D5`): `WALL_SUBIU_3D + PERTO_PUT_WALL_4PCT + IV_RANK_BAIXO_55 + FECHOU_TOPO_65` ($n=68$ em 25 ativos EUA):** **Win Rate `86,8%`** (`OOS 72,2% | 12 Virgens 88,5%`), bate `+20%` em **`61,8%` no `D+1`**, EV **+16,49%**, **PF 3,11**.
    5. **Alta Frequência EUA ($n=124$ em 33 ativos): `TRAVA_ABERT_LIM + WALL_SUBIU_1D + WALL_SUBIU_3D + CP_VOL_2.2X + FECHOU_TOPO_75`:** **Win Rate `85,5%`** (`OOS 81,8% | 12 Virgens 86,8%`), EV **+12,46%**, **PF 2,67**.
  - **Leitura Ao Vivo do Scanner EUA hoje (`26/10/2026` via CBOE):** 7 ativos ativados, com destaque para contratos de ticket baixo (`US$ 28 a US$ 122` por contrato de 100 opções): **`SOFI`** (`SOFI261113C00015000` @ `US$ 71` / OTM `$16` @ `US$ 38`, Confluência de 3 regras, WR `88,9%`), **`MARA`** (`MARA261113C00007500` @ `US$ 45` / OTM `$8` @ `US$ 30`, 3 regras, WR `88,9%`), **`BAC`** (`BAC261113C00051000` @ `US$ 122` / OTM `$53` @ `US$ 42`, IV Rank `16%`, C/P Vol `3,67x`, WR `83,8%`), **`F`** (`F261106C00012000` @ `US$ 28`, WR `87,5%`), além das gigantes **`AMZN`** (3 regras, WR `88,9%`), **`SPY`** (2 regras, WR `88,9%`) e **`XOM`** (WR `88,1%`).
  - **Leitura Ao Vivo do Scanner EUA em `03/11/2026` (via CBOE):** 3 ativos ativados: **`NFLX`** (`Spot $87,25`, Confluência `U1, U3` WR `88,9%` $\to$ `$63C` @ `$1,75` / `$65C` @ `$1,00`), **`PYPL`** (`Spot $59,75`, Confluência `U2, U5` WR `85,5%` $\to$ `$59C` @ `$1,70` / `$61C` @ `$0,87`) e **`AAL`** (`Spot $13,07`, Regra `U7` WR `83,8%` $\to$ `$13C` @ `$0,66` / `$14C` @ `$0,26`).
- **Sétima Rodada — Arquitetura 100% Nuvem ("Sócio Gamma Levels Cloud": GitHub Actions + n8n AI Agent + Telegram, `03/11/2026`):**
  - **Motivação de Matheus:** ter o Sócio Antigravity disponível no celular via Telegram mesmo com o PC desligado, recebendo o plano de voo antes da abertura (`09h45`), lembrete de execução/veto na abertura (`10h02`) e fechamento (`18h30/18h35`), além de poder conversar a qualquer hora pelo Telegram consultando os dados reais do repositório GitHub.
  - **Componentes Implementados e Ativos em Produção:**
    1. **Cache Leve de Nuvem (`cloud_cache/`, ~6,2 MB versionado no GitHub):**
       - `cloud_cache/b3_tail35/*.parquet` (últimos 35 pregões dos 45 ativos B3), `cloud_cache/us_tail35/*.parquet` (36 ativos US) e `cloud_cache/_isin_map.json`, permitindo rodar os scanners B3 e US no GitHub Actions em ~15 segundos sem precisar subir os 3 GB de bancos SQLite locais.
       - `scripts/scan_tiro_rapido_d3.py` e `scripts/scan_us_options_d3.py` foram atualizados para usar `cloud_cache/` automaticamente como fallback quando executados na nuvem.
    2. **Orquestrador Diário Cloud (`scripts/cloud_daily_runner.py` + `cloud_reports/`):**
       - Baixa novos arquivos oficiais `PR`/`PE` da B3 (quando disponíveis), roda o Scanner Tiro Rápido B3 (`Fim D0` e `Abertura D+1`) e o Scanner US Options D3 (CBOE ao vivo), atualiza `cloud_cache/`, grava `cloud_reports/latest_daily_briefing.json` e `cloud_reports/latest_daily_briefing.md`, e envia o briefing HTML completo para o Telegram do Matheus (`CHAT_ID=606807164`).
    3. **GitHub Actions (`.github/workflows/daily_scanner.yml` em `zxtheuxz/gamma-levels`):**
       - Roda automaticamente de segunda a sexta às **`09h40 BRT`** (`12:40 UTC`) e **`18h30 BRT`** (`21:30 UTC`), além de aceitar disparo manual (`workflow_dispatch`) pelo próprio Agente do Telegram.
       - Faz commit e push automático dos relatórios atualizados em `cloud_reports/` e `cloud_cache/` de volta para a branch `main`.
       - Secrets configurados no GitHub: `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
    4. **Agente IA Interativo + Alertas no n8n (`https://n8n-n8n.r7kz3f.easypanel.host/workflow/hsaixBPAtIGLuJHh`):**
       - **Workflow ID:** `hsaixBPAtIGLuJHh` (`SÓCIO GAMMA LEVELS — TELEGRAM AI & SCANNER`, publicado e ativo na versão `63969ac3-6cce-4fb1-86de-31dd899c2f17`).
       - **Webhook do Bot Telegram:** `https://n8n-n8n.r7kz3f.easypanel.host/webhook/socio-gamma-telegram` (registrado via `setWebhook` no bot, filtrado exclusivamente para `chat_id == 606807164`).
       - **Cérebro e Ferramentas:** `OpenRouter Chat Model` (`openai/gpt-4.1-mini`, credencial `IACLOUDVPS`) + `Memoria Conversa Socio` (`memoryBufferWindow` 10 mensagens) + leitura automática pré-carregada de `cloud_reports/latest_daily_briefing.json` + ferramenta `ler_memoria_projeto` (`PROJECT_MEMORY.md` direto do GitHub) + ferramenta `disparar_scanner_github` (`githubTool` que dispara `daily_scanner.yml` no GitHub Actions sob demanda).
       - **Gatilhos de Horários-Chave B3 (`Gatilho Horarios Chave B3`):** dispara segunda a sexta às **`09h45`**, **`10h02`** e **`18h35` BRT**, lendo `latest_daily_briefing.json` do GitHub e enviando o alerta tático de Pré-Abertura, Abertura (checagem de book/veto) e Fechamento no Telegram.
    5. **Agendamento Local Antigravity (`schedule` tool):**
       - Quando o PC do Matheus estiver ligado com o Antigravity aberto, há também dois crons locais ativos (`09h45` e `10h05` BRT, seg-sex) para despertar esta sessão proativamente.

## Como retomar rapidamente

1. Ler este arquivo inteiro.
2. Trabalhar no Windows local; a VPS Ubuntu foi excluída em 30/07/2026 e não existe mais.
3. O backup mínimo da VPS e o código remoto não commitado já foram transferidos e validados;
   não repetir. Os 88 GB brutos/cache da VPS foram descartados com a instância.
4. Garantir que alterações de código e desta memória foram commitadas e enviadas ao GitHub.
5. No Windows, consultar `http://127.0.0.1:8000/api/health`; se necessário, executar
   `scripts/start_dashboard.ps1`.
6. Não existe fila ou backtest na VPS, pois a instância foi excluída.
7. Os bancos da VPS já estão integrados ao dashboard e o ranking consolidado já foi gerado.
8. Não escolher apenas o maior número: observar operações, PF, expectativa, estabilidade e drawdown.
9. Para a verificação diária da cesta, rodar `python scripts/daily_basket_scan.py`; ele já baixa
   o pregão faltante, avalia os 11 nas duas réguas e avisa por Telegram se algum ativar.
10. Para o mapa diário do WIN, rodar `python scripts/index_futures_daily.py` depois da publicação
    D-1 e usar o mapa no pregão seguinte, sempre no contrato WIN exato.
11. Para retomar o índice futuro, verificar primeiro as datas em `daily_maps` e não recalcular
    27–29/07 sem necessidade. O foco seguinte é ampliar a amostra causal/intraday.

Próximos candidatos líquidos observados em 27/07/2026: PRIO3, BBAS3, GGBR4, WEGE3 e B3SA3.
BRAV3 tinha volume muito alto, mas exige avaliar continuidade histórica e eventos corporativos antes do anual.
