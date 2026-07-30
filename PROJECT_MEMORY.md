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
- Versão ativa: 0.3.3
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

Próximos candidatos líquidos observados em 27/07/2026: PRIO3, BBAS3, GGBR4, WEGE3 e B3SA3.
BRAV3 tinha volume muito alto, mas exige avaliar continuidade histórica e eventos corporativos antes do anual.
