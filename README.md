# Gamma Levels — Swing CALL Scanner

Para retomar o projeto em outra sessão, leia primeiro [`PROJECT_MEMORY.md`](PROJECT_MEMORY.md).

Dashboard local para analisar várias ações da B3 com dados públicos de D-1 e
encontrar compras de CALL para operações swing. O fluxo principal não depende de
RTD, Profit, cotações ao vivo ou acompanhamento intraday.

## Abrir o dashboard

Dê dois cliques em `Iniciar_Dashboard.cmd`. Na primeira execução, o botão
**Atualizar D-1** monta uma base de 120 pregões; as próximas atualizações baixam
somente os dias ausentes.

O dashboard apresenta:

- os 20 ativos com maior liquidez de CALL nos últimos 20 pregões;
- no máximo cinco sinais `COMPRAR CALL` por data;
- estados `AGUARDAR` e `DESCARTAR` com motivos numéricos;
- CALLs com 10–60 DTE e delta entre 0,55 e 0,80;
- suporte, resistência, invalidação, alvos e relação retorno/risco;
- projeções de prêmio em 3, 5 e 10 pregões e preços do ativo necessários para
  ganhos de 10%, 25%, 50% e 100%;
- backtest walk-forward e exportação para Excel.

## Backtest anual por ativo

Na aba **Histórico**, selecione PETR4, VALE3, ITUB4 ou BBDC4 e use o botão de backtest anual para completar uma base de
aproximadamente 345 pregões e avaliar cerca de 252 datas com vencimento já
conhecido. A carga é retomável e preserva os arquivos brutos da B3. Como
alternativa ao dashboard, dê dois cliques em
`Executar_Backtest_Anual_PETR4.cmd`.

O estudo usa ordem limitada pelo prêmio máximo de D-1, mantém cada CALL em
acompanhamento até o vencimento e compara seis saídas: vencimento, saída
calculada, parcial em +25%, parcial em +50%, escada +25/+50/+100 e parcial
com saída calculada. Resultados são exibidos tanto para sinais independentes
quanto para uma carteira que não abre duas posições simultâneas no mesmo ativo. Cada ativo usa banco separado,
preservando integralmente as execuções anteriores.

Os relatórios brutos são convertidos uma única vez para o cache Parquet em `data/parsed`.
Indicadores, regiões, juros e trajetórias comuns às variações também são reutilizados durante o estudo.

Indicadores técnicos usam preços ajustados por eventos corporativos efetivos;
preços de execução e exercício permanecem brutos. Custos e derrapagem são
configuráveis e começam em zero.

Os arquivos brutos, checksums, banco SQLite e histórico ficam em `data/`. O
sistema lê o relatório completo de preços, o prêmio de referência e o cadastro
de instrumentos da Pesquisa por Pregão da B3. Arquivos autoextraíveis são lidos
como ZIP e nunca executados.

## Regras padrão

Um sinal só recebe `COMPRAR CALL` quando reúne score bullish mínimo de 80,
setup confirmado no fechamento, relação retorno/risco mínima de 1,5, projeção
conservadora de pelo menos 10% e todos os filtros de liquidez. Se preço, IV,
posição em aberto ou cotação estiverem incompletos, o ativo permanece em
`AGUARDAR — dados incompletos`; volume não substitui OI.

PUTs podem ser carregadas apenas para os cálculos internos de GEX. Elas nunca são
mostradas como operação sugerida.

## Desenvolvimento

```powershell
python -m pip install -e ".[dev]"
pytest

cd dashboard
npm install
npm run dev
```

O backend local usa `http://127.0.0.1:8000` e o dashboard
`http://localhost:3000`.

## Motor de cadeia existente

O analisador auditável de GEX, DEX, Vanna, Charm, Gamma Flip, Max Pain e níveis
por strike permanece disponível pela linha de comando:

```powershell
python -m gamma_levels exemplo_cadeia.csv --valuation-date 2026-07-27 --rate 0.15
```

A antiga planilha RTD continua no repositório somente para compatibilidade; ela
não participa do dashboard swing.
