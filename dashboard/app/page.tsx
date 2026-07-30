"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

type Status = {
  running: boolean;
  phase: string;
  message: string;
  progress: number;
  error?: string | null;
  latest_market_date?: string | null;
  loaded_sessions?: number;
};

type Call = {
  ticker: string;
  strike: number;
  expiration: string;
  dte: number;
  delta: number;
  iv: number;
  reference_price: number;
  bid: number;
  ask: number;
  spread_pct: number;
  open_interest: number;
  financial_volume: number;
  score: number;
  dividend_yield?: number;
  carry_source?: string;
};

type Projection = {
  horizons: Record<string, { conservative: number; base: number; optimistic: number }>;
  required_underlying: Record<string, number | null>;
  expected_range_10d: [number, number];
  max_entry_premium: number;
};

type Asset = {
  rank: number;
  ticker: string;
  asset_root: string;
  status: "COMPRAR CALL" | "AGUARDAR" | "DESCARTAR";
  setup?: string | null;
  score: number;
  liquidity_score: number;
  spot?: number;
  support?: number;
  resistance?: number;
  invalidation?: number;
  entry_zone?: [number, number];
  targets?: number[];
  reward_risk?: number;
  reasons: string[];
  data_quality: string;
  selected_call?: Call | null;
  projections?: Projection | null;
  components?: Record<string, number>;
  levels?: Record<string, number | null>;
};

type SignalsPayload = {
  trade_date: string | null;
  source: string;
  counts: Record<string, number>;
  assets: Asset[];
};

type HistoryPayload = {
  signals: number;
  completed: number;
  hit_rates: Record<string, number | null>;
  rows: Record<string, unknown>[];
};

type StudyStatus = Status & {
  completed?: number;
  total?: number;
  missing_dates?: string[];
  run_id?: number | null;
};

type StudyMetric = {
  variant: string;
  strategy: string;
  overlap_mode: string;
  sample: string;
  trades: number;
  wins: number;
  win_rate: number | null;
  expectancy: number | null;
  profit_factor: number | null;
  max_drawdown: number | null;
  mfe_capture: number | null;
};

type StudyPayload = {
  run: Record<string, unknown> | null;
  metrics: StudyMetric[];
  trades: Record<string, unknown>[];
};

type StudyTicker = string;
const defaultStudyTickers: StudyTicker[] = ["PETR4", "VALE3", "ITUB4", "BBDC4"];

const initialStatus: Status = {
  running: false,
  phase: "idle",
  message: "Conectando ao motor local",
  progress: 0,
};

const money = (value?: number | null) =>
  value == null || !Number.isFinite(value)
    ? "—"
    : value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

const number = (value?: number | null, digits = 2) =>
  value == null || !Number.isFinite(value)
    ? "—"
    : value.toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });

const percent = (value?: number | null, signed = false) => {
  if (value == null || !Number.isFinite(value)) return "—";
  const prefix = signed && value > 0 ? "+" : "";
  return `${prefix}${(value * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
};

function StatusPill({ value }: { value: Asset["status"] }) {
  const className = value === "COMPRAR CALL" ? "buy" : value === "AGUARDAR" ? "wait" : "discard";
  return <span className={`status-pill ${className}`}><span className="status-dot" />{value}</span>;
}

function ScoreRing({ value }: { value: number }) {
  const angle = Math.max(0, Math.min(100, value)) * 3.6;
  return (
    <div className="score-ring" style={{ background: `conic-gradient(var(--green) ${angle}deg, var(--line) ${angle}deg)` }}>
      <span>{Math.round(value)}</span>
    </div>
  );
}

export default function Home() {
  const [tab, setTab] = useState<"signals" | "assets" | "history" | "data">("signals");
  const [status, setStatus] = useState<Status>(initialStatus);
  const [signals, setSignals] = useState<SignalsPayload>({ trade_date: null, source: "B3 D-1", counts: {}, assets: [] });
  const [history, setHistory] = useState<HistoryPayload>({ signals: 0, completed: 0, hit_rates: {}, rows: [] });
  const [studyStatus, setStudyStatus] = useState<StudyStatus>({ ...initialStatus, message: "Backtest anual não iniciado" });
  const [study, setStudy] = useState<StudyPayload>({ run: null, metrics: [], trades: [] });
  const [studyTicker, setStudyTicker] = useState<StudyTicker>("PETR4");
  const [studyTickers, setStudyTickers] = useState<StudyTicker[]>(defaultStudyTickers);
  const [sessions, setSessions] = useState<Record<string, unknown>[]>([]);
  const [selected, setSelected] = useState<Asset | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  const loadSignals = useCallback(async () => {
    const response = await fetch(`${API}/api/signals`, { cache: "no-store" });
    if (!response.ok) throw new Error("Não foi possível carregar os sinais locais.");
    setSignals(await response.json());
  }, []);

  const loadSecondary = useCallback(async () => {
    const [historyResponse, qualityResponse, studyResponse, studyStatusResponse, tickersResponse] = await Promise.all([
      fetch(`${API}/api/history`, { cache: "no-store" }),
      fetch(`${API}/api/data-quality`, { cache: "no-store" }),
      fetch(`${API}/api/backtest/latest?ticker=${studyTicker}`, { cache: "no-store" }),
      fetch(`${API}/api/backtest/status?ticker=${studyTicker}`, { cache: "no-store" }),
      fetch(`${API}/api/backtest/tickers`, { cache: "no-store" }),
    ]);
    if (historyResponse.ok) setHistory(await historyResponse.json());
    if (qualityResponse.ok) setSessions((await qualityResponse.json()).sessions ?? []);
    if (studyResponse.ok) setStudy(await studyResponse.json());
    if (studyStatusResponse.ok) setStudyStatus(await studyStatusResponse.json());
    if (tickersResponse.ok) {
      const payload = await tickersResponse.json();
      const available = (payload.tickers ?? []).map((item: { ticker: string }) => item.ticker);
      if (available.length) setStudyTickers(available);
    }
  }, [studyTicker]);

  const loadStatus = useCallback(async () => {
    const response = await fetch(`${API}/api/status`, { cache: "no-store" });
    if (!response.ok) throw new Error("Motor local indisponível.");
    const next: Status = await response.json();
    setStatus(next);
    return next;
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      Promise.all([loadStatus(), loadSignals(), loadSecondary()])
        .then(() => setApiError(null))
        .catch((error) => setApiError(error instanceof Error ? error.message : "Falha de conexão local"));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadSecondary, loadSignals, loadStatus]);

  useEffect(() => {
    if (!status.running) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await loadStatus();
        if (!next.running && next.phase === "complete") {
          await Promise.all([loadSignals(), loadSecondary()]);
        }
      } catch (error) {
        setApiError(error instanceof Error ? error.message : "Falha ao acompanhar a atualização");
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [loadSecondary, loadSignals, loadStatus, status.running]);

  useEffect(() => {
    if (!studyStatus.running) return;
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`${API}/api/backtest/status?ticker=${studyTicker}`, { cache: "no-store" });
        if (!response.ok) return;
        const next: StudyStatus = await response.json();
        setStudyStatus(next);
        if (!next.running) await loadSecondary();
      } catch {
        // A faixa de status principal já informa eventual queda do motor local.
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [loadSecondary, studyStatus.running, studyTicker]);

  const buys = useMemo(() => signals.assets.filter((asset) => asset.status === "COMPRAR CALL"), [signals.assets]);

  async function refresh() {
    setApiError(null);
    try {
      const response = await fetch(`${API}/api/refresh`, { method: "POST" });
      if (!response.ok && response.status !== 409) throw new Error("A B3 não iniciou a atualização.");
      await loadStatus();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Falha ao atualizar");
    }
  }

  async function runAnnualStudy() {
    setApiError(null);
    try {
      const assetRoot = studyTicker.slice(0, 4);
      const response = await fetch(`${API}/api/backtest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: studyTicker, asset_root: assetRoot, target_loaded_sessions: 345,
          warmup_sessions: 50, evaluation_sessions: 252,
          costs: { buy_pct: 0, sell_pct: 0, slippage_pct: 0, fixed_per_order_brl: 0, capital_per_trade_brl: 1000 },
        }),
      });
      if (!response.ok && response.status !== 409) throw new Error("O backtest anual não foi iniciado.");
      const statusResponse = await fetch(`${API}/api/backtest/status?ticker=${studyTicker}`, { cache: "no-store" });
      if (statusResponse.ok) setStudyStatus(await statusResponse.json());
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Falha ao iniciar backtest anual");
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">Γ</span><div><strong>Gamma Levels</strong><small>Swing CALL scanner</small></div></div>
        <nav aria-label="Navegação principal">
          <button className={tab === "signals" ? "active" : ""} onClick={() => setTab("signals")}><span>01</span>Sinais</button>
          <button className={tab === "assets" ? "active" : ""} onClick={() => setTab("assets")}><span>02</span>Ativos</button>
          <button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}><span>03</span>Histórico</button>
          <button className={tab === "data" ? "active" : ""} onClick={() => setTab("data")}><span>04</span>Dados</button>
        </nav>
        <div className="sidebar-foot">
          <span className={`connection ${apiError ? "offline" : ""}`} />
          <div><strong>{apiError ? "Motor desconectado" : "Sistema local"}</strong><small>Sem RTD · Sem intraday</small></div>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">MERCADO B3 · FECHAMENTO</p><h1>{tab === "signals" ? "Sinais de alta convicção" : tab === "assets" ? "Universo de liquidez" : tab === "history" ? "Validação histórica" : "Qualidade dos dados"}</h1></div>
          <div className="header-actions">
            <a className="ghost-button" href={tab === "history" ? `${API}/api/backtest/export.xlsx?ticker=${studyTicker}` : `${API}/api/export.xlsx`} aria-label="Exportar resultados em Excel">Exportar XLSX</a>
            {tab === "history" && <select className="ghost-button study-select" aria-label="Selecionar ativo do estudo anual" value={studyTicker} onChange={(event) => setStudyTicker(event.target.value)}>{studyTickers.map((ticker) => <option value={ticker} key={ticker}>{ticker}</option>)}</select>}
            {tab === "history" && <button className="ghost-button" disabled={studyStatus.running} onClick={runAnnualStudy}>{studyStatus.running ? `Processando ${studyTicker}…` : `Backtest anual ${studyTicker}`}</button>}
            <button className="refresh-button" disabled={status.running} onClick={refresh}>{status.running ? "Atualizando…" : "Atualizar D-1"}</button>
          </div>
        </header>

        <div className="date-strip">
          <div><span>DATA-BASE</span><strong>{signals.trade_date ? new Date(`${signals.trade_date}T12:00:00`).toLocaleDateString("pt-BR") : "Sem carga"}</strong></div>
          <div><span>FONTE</span><strong>B3 D-1</strong></div>
          <div><span>JANELA</span><strong>10–60 DTE</strong></div>
          <div><span>DELTA</span><strong>0,55–0,80</strong></div>
          <div className="market-state"><span className="pulse" /><strong>{status.running ? status.message : "Fechamento processado"}</strong></div>
        </div>

        {(status.running || status.error) && (
          <div className={`process-banner ${status.error ? "error" : ""}`}>
            <div><strong>{status.error ? "Atualização interrompida" : status.message}</strong><small>{status.error ?? `${status.loaded_sessions ?? 0} pregões armazenados`}</small></div>
            {!status.error && <div className="progress"><span style={{ width: `${status.progress ?? 0}%` }} /></div>}
          </div>
        )}
        {apiError && <div className="process-banner error"><div><strong>Dashboard sem conexão</strong><small>{apiError} Abra pelo arquivo Iniciar_Dashboard.cmd.</small></div></div>}
        {studyStatus.running && <div className="process-banner"><div><strong>{studyStatus.message}</strong><small>{studyStatus.completed ?? 0}/{studyStatus.total ?? 345} pregões · processo retomável</small></div><div className="progress"><span style={{ width: `${studyStatus.progress ?? 0}%` }} /></div></div>}
        {!studyStatus.running && studyStatus.error && <div className="process-banner error"><div><strong>Backtest anual interrompido</strong><small>{studyStatus.error}</small></div></div>}

        {tab === "signals" && (
          <>
            <section className="metric-grid">
              <article className="metric featured"><p>ACIONADOS HOJE</p><strong>{buys.length.toString().padStart(2, "0")}</strong><small>limite de 5 sinais</small></article>
              <article className="metric"><p>EM OBSERVAÇÃO</p><strong>{signals.counts["AGUARDAR"] ?? 0}</strong><small>gatilho ou prêmio pendente</small></article>
              <article className="metric"><p>UNIVERSO</p><strong>{signals.assets.length}</strong><small>ativos por liquidez de CALL</small></article>
              <article className="metric"><p>HISTÓRICO</p><strong>{status.loaded_sessions ?? 0}</strong><small>pregões no banco local</small></article>
            </section>

            <section className="section-block">
              <div className="section-heading"><div><p className="eyebrow">PRIORIDADE DO DIA</p><h2>CALLs acionadas</h2></div><p>Somente sinais confirmados pelo fechamento de D‑1 e pelos filtros de liquidez.</p></div>
              {buys.length ? (
                <div className="signal-grid">
                  {buys.map((asset) => (
                    <button className="signal-card" key={asset.ticker} onClick={() => setSelected(asset)}>
                      <div className="card-top"><StatusPill value={asset.status} /><span>#{asset.rank.toString().padStart(2, "0")}</span></div>
                      <div className="asset-title"><div><h3>{asset.ticker}</h3><p>{asset.setup}</p></div><ScoreRing value={asset.score} /></div>
                      <div className="call-code"><span>CALL SELECIONADA</span><strong>{asset.selected_call?.ticker}</strong><em>{asset.selected_call?.dte} DTE</em></div>
                      <div className="card-numbers"><div><span>Referência</span><strong>{money(asset.selected_call?.reference_price)}</strong></div><div><span>Prêmio máx.</span><strong>{money(asset.projections?.max_entry_premium)}</strong></div><div><span>RR</span><strong>{number(asset.reward_risk)}x</strong></div></div>
                      <div className="projection-line"><span>Cenário conservador · 5 pregões</span><strong>{percent(asset.projections?.horizons?.["5"]?.conservative, true)}</strong></div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="empty-state"><span>Γ</span><h3>Nenhuma CALL acionada</h3><p>{signals.assets.length ? "Os filtros estão funcionando: nenhum ativo reuniu estrutura, liquidez e retorno mínimo ao mesmo tempo." : "Faça a primeira atualização. A carga inicial buscará 120 pregões públicos da B3 e montará o ranking automaticamente."}</p><button onClick={refresh} disabled={status.running}>{status.running ? "Carga em andamento" : "Iniciar análise D-1"}</button></div>
              )}
            </section>

            {!!signals.assets.length && <AssetTable assets={signals.assets.slice(0, 10)} onSelect={setSelected} title="Radar completo" />}
          </>
        )}

        {tab === "assets" && <AssetTable assets={signals.assets} onSelect={setSelected} title="Top 20 por liquidez de CALL" />}

        {tab === "history" && (
          <section className="history-view">
            <StudyHistory study={study} legacy={history} onRun={runAnnualStudy} running={studyStatus.running} ticker={studyTicker} />
          </section>
        )}

        {tab === "data" && (
          <section className="data-view">
            <div className="data-intro"><div><p className="eyebrow">AUDITORIA</p><h2>Fonte e integridade</h2></div><p>Cada pregão mantém os arquivos brutos, checksums e o manifesto usados nos cálculos. O sistema nunca usa volume como substituto de posição em aberto.</p></div>
            <div className="quality-grid"><article><span>ÚLTIMO PREGÃO</span><strong>{status.latest_market_date ?? "—"}</strong><small>detectado automaticamente</small></article><article><span>SESSÕES LOCAIS</span><strong>{status.loaded_sessions ?? 0}</strong><small>meta inicial: 120</small></article><article><span>DEPENDÊNCIA AO VIVO</span><strong>NENHUMA</strong><small>sem RTD ou Profit</small></article></div>
            <div className="table-card"><table><thead><tr><th>Pregão</th><th>Status</th><th>Carregado em</th><th>Manifesto</th></tr></thead><tbody>{sessions.slice(0, 30).map((session, index) => <tr key={index}><td><strong>{String(session.trade_date)}</strong></td><td><span className="quality-ok">OK</span></td><td>{String(session.loaded_at)}</td><td className="mono">{String(session.manifest_json).slice(0, 78)}…</td></tr>)}</tbody></table>{!sessions.length && <p className="table-empty">Nenhum arquivo carregado ainda.</p>}</div>
          </section>
        )}
      </section>

      {selected && <DetailPanel asset={selected} onClose={() => setSelected(null)} />}
    </main>
  );
}

function StudyHistory({ study, legacy, onRun, running, ticker }: { study: StudyPayload; legacy: HistoryPayload; onRun: () => void; running: boolean; ticker: string }) {
  const [detail, setDetail] = useState<{ trade: Record<string, unknown>; path: Record<string, unknown>[]; strategies: Record<string, unknown>[] } | null>(null);
  const fullIndependent = study.metrics.filter((item) => item.sample === "full" && item.overlap_mode === "INDEPENDENT" && item.trades > 0);
  const eligible = fullIndependent.filter((item) => item.trades >= 10);
  const anchor = [...(eligible.length ? eligible : fullIndependent)].sort((left, right) => eligible.length
    ? (right.expectancy ?? Number.NEGATIVE_INFINITY) - (left.expectancy ?? Number.NEGATIVE_INFINITY)
    : right.trades - left.trades || (right.expectancy ?? Number.NEGATIVE_INFINITY) - (left.expectancy ?? Number.NEGATIVE_INFINITY))[0];
  const primaryVariant = anchor?.variant;
  const primary = study.metrics.filter((item) => item.variant === primaryVariant && item.sample === "full" && item.overlap_mode === "INDEPENDENT");
  const hold = primary.find((item) => item.strategy === "HOLD_TO_EXPIRY");
  const calculated = primary.find((item) => item.strategy === "CALCULATED_EXIT");
  const annualTrades = study.trades.filter((row) => row.variant === primaryVariant && row.strategy === "HOLD_TO_EXPIRY" && row.overlap_mode === "INDEPENDENT");
  const runStatus = String(study.run?.status ?? "NÃO INICIADO");
  async function openTrade(row: Record<string, unknown>) {
    const response = await fetch(`${API}/api/backtest/trades/${encodeURIComponent(String(row.trade_id))}?ticker=${ticker}`, { cache: "no-store" });
    if (response.ok) setDetail(await response.json());
  }
  return (
    <>
      <div className="history-stats">
        <article><span>STATUS ANUAL</span><strong>{runStatus}</strong></article>
        <article><span>OPERAÇÕES</span><strong>{hold?.trades ?? (ticker === "PETR4" ? legacy.signals : 0)}</strong></article>
        <article><span>ACERTO · VENCIMENTO</span><strong>{percent(hold?.win_rate)}</strong></article>
        <article><span>EXPECTATIVA · VENCIMENTO</span><strong>{percent(hold?.expectancy, true)}</strong></article>
        <article><span>ACERTO · SAÍDA CALCULADA</span><strong>{percent(calculated?.win_rate)}</strong></article>
        <article><span>EXPECTATIVA · CALCULADA</span><strong>{percent(calculated?.expectancy, true)}</strong></article>
      </div>
      <div className="method-note"><strong>Walk-forward, sem olhar o futuro</strong><p>Contexto formado até D‑1, ordem limitada em D0, acompanhamento até o vencimento e saída calculada executada na abertura seguinte. Operações ainda abertas não entram na expectativa oficial.</p></div>
      {primary.length ? (
        <>
          <div className="section-heading"><div><p className="eyebrow">SEIS REGRAS · {primaryVariant}</p><h2>Comparação de saídas</h2></div><p>Variante com maior expectativa entre as que têm ao menos 10 operações; abaixo disso, prevalece a maior amostra.</p></div>
          <div className="table-card"><table><thead><tr><th>Estratégia</th><th>Operações</th><th>Acerto</th><th>Expectativa</th><th>Fator lucro</th><th>Drawdown</th><th>Captura MFE</th></tr></thead><tbody>{primary.map((row) => <tr key={row.strategy}><td><strong>{row.strategy}</strong></td><td>{row.trades}</td><td>{percent(row.win_rate)}</td><td className={(row.expectancy ?? 0) >= 0 ? "positive" : "negative"}>{percent(row.expectancy, true)}</td><td>{number(row.profit_factor)}</td><td className="negative">{percent(row.max_drawdown, true)}</td><td>{percent(row.mfe_capture)}</td></tr>)}</tbody></table></div>
          <div className="section-heading study-operations-heading"><div><p className="eyebrow">AUDITORIA</p><h2>Operações até o vencimento</h2></div></div>
          <div className="table-card"><table><thead><tr><th>Sinal</th><th>CALL</th><th>Score</th><th>Entrada</th><th>Status</th><th>MFE</th><th>MAE</th><th>Vencimento</th></tr></thead><tbody>{annualTrades.slice(0, 100).map((row, index) => <tr key={`${String(row.trade_id)}-${index}`} tabIndex={0} onClick={() => openTrade(row)} onKeyDown={(event) => event.key === "Enter" && openTrade(row)}><td>{String(row.signal_date ?? "—")}</td><td className="mono">{String(row.option_ticker ?? "—")}</td><td>{number(Number(row.signal_score))}</td><td>{money(row.entry_price == null ? null : Number(row.entry_price))}</td><td>{String(row.fill_status ?? "—")}</td><td className="positive">{percent(row.mfe == null ? null : Number(row.mfe), true)}</td><td className="negative">{percent(row.mae == null ? null : Number(row.mae), true)}</td><td>{percent(row.expiry_return == null ? null : Number(row.expiry_return), true)}</td></tr>)}</tbody></table></div>
          {ticker === "PETR4" && !!legacy.rows.length && <><div className="section-heading study-operations-heading"><div><p className="eyebrow">REFERÊNCIA PRESERVADA</p><h2>Piloto pelo primeiro negócio de D0</h2></div><p>Leitura antiga mantida para comparação; não participa da carteira oficial com ordem limitada.</p></div><div className="table-card"><table><thead><tr><th>Data</th><th>CALL</th><th>Score</th><th>Máx. ganho conhecido</th><th>Máx. perda registrada</th><th>Invalidada</th></tr></thead><tbody>{legacy.rows.map((row, index) => <tr key={index}><td>{String(row.trade_date ?? "—")}</td><td className="mono">{String(row.option_ticker ?? "—")}</td><td>{number(Number(row.score))}</td><td className="positive">{percent(row.max_gain == null ? null : Number(row.max_gain), true)}</td><td className="negative">{percent(row.max_loss == null ? null : Number(row.max_loss), true)}</td><td>{row.invalidated ? "SIM" : "NÃO"}</td></tr>)}</tbody></table></div></>}
        </>
      ) : (
        <div className="empty-state"><span>Γ</span><h3>{runStatus === "COMPLETE" ? `Estudo completo de ${ticker}, sem operações elegíveis` : `Estudo anual de ${ticker} ainda não executado`}</h3><p>{runStatus === "COMPLETE" ? "As 254 datas foram avaliadas, mas nenhuma entrada executada passou pelos filtros das variantes testadas." : "O banco é separado por ativo. A carga reutiliza os arquivos brutos já baixados, mantém os estudos anteriores e processa as mesmas seis saídas."}</p>{runStatus !== "COMPLETE" && <button onClick={onRun} disabled={running}>{running ? "Carga em andamento" : `Iniciar backtest anual ${ticker}`}</button>}</div>
      )}
      {detail && <TradePathDrawer detail={detail} onClose={() => setDetail(null)} />}
    </>
  );
}

function TradePathDrawer({ detail, onClose }: { detail: { trade: Record<string, unknown>; path: Record<string, unknown>[]; strategies: Record<string, unknown>[] }; onClose: () => void }) {
  return <div className="drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><aside className="detail-drawer trade-path-drawer"><div className="drawer-head"><div><p className="eyebrow">TRAJETÓRIA COMPLETA</p><h2>{String(detail.trade.option_ticker ?? "CALL")}</h2></div><button onClick={onClose} aria-label="Fechar trajetória">×</button></div><div className="level-grid"><div><span>Entrada</span><strong>{money(detail.trade.entry_price == null ? null : Number(detail.trade.entry_price))}</strong></div><div><span>Limite</span><strong>{money(detail.trade.entry_limit == null ? null : Number(detail.trade.entry_limit))}</strong></div><div><span>Status</span><strong>{String(detail.trade.fill_status ?? "—")}</strong></div><div><span>Vencimento</span><strong>{String(detail.trade.expiration ?? "—")}</strong></div></div><section className="drawer-section"><h3>Pregão a pregão</h3><div className="table-card"><table><thead><tr><th>Data</th><th>DTE</th><th>CALL fech.</th><th>Retorno</th><th>MFE</th><th>Devolução</th><th>Saída</th></tr></thead><tbody>{detail.path.map((row, index) => <tr key={index}><td>{String(row.trade_date)}</td><td>{String(row.dte)}</td><td>{money(row.option_close == null ? null : Number(row.option_close))}</td><td>{percent(row.return_close == null ? null : Number(row.return_close), true)}</td><td className="positive">{percent(row.mfe == null ? null : Number(row.mfe), true)}</td><td className="negative">{percent(row.drawdown_from_peak == null ? null : Number(row.drawdown_from_peak), true)}</td><td>{String(row.exit_state ?? "—")}</td></tr>)}</tbody></table></div></section></aside></div>;
}

function AssetTable({ assets, onSelect, title }: { assets: Asset[]; onSelect: (asset: Asset) => void; title: string }) {
  return (
    <section className="section-block table-section">
      <div className="section-heading"><div><p className="eyebrow">RANKING MULTIATIVO</p><h2>{title}</h2></div><p>Clique em um ativo para abrir os cálculos completos.</p></div>
      <div className="table-card"><table><thead><tr><th>#</th><th>Ativo</th><th>Status</th><th>Setup</th><th>Score</th><th>Liquidez</th><th>CALL</th><th>Delta</th><th>DTE</th><th>Retorno 5d</th></tr></thead><tbody>{assets.map((asset) => <tr key={asset.ticker} onClick={() => onSelect(asset)} tabIndex={0} onKeyDown={(event) => event.key === "Enter" && onSelect(asset)}><td className="muted">{asset.rank.toString().padStart(2, "0")}</td><td><strong>{asset.ticker}</strong><small>{money(asset.spot)}</small></td><td><StatusPill value={asset.status} /></td><td>{asset.setup ?? "Sem gatilho"}</td><td><strong>{number(asset.score, 0)}</strong></td><td>{number(asset.liquidity_score, 0)}</td><td className="mono">{asset.selected_call?.ticker ?? "—"}</td><td>{number(asset.selected_call?.delta)}</td><td>{asset.selected_call?.dte ?? "—"}</td><td className={(asset.projections?.horizons?.["5"]?.conservative ?? 0) > 0 ? "positive" : "muted"}>{percent(asset.projections?.horizons?.["5"]?.conservative, true)}</td></tr>)}</tbody></table>{!assets.length && <p className="table-empty">O ranking será preenchido após a atualização inicial.</p>}</div>
    </section>
  );
}

function DetailPanel({ asset, onClose }: { asset: Asset; onClose: () => void }) {
  const call = asset.selected_call;
  return (
    <div className="drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="detail-drawer" aria-label={`Detalhes de ${asset.ticker}`}>
        <div className="drawer-head"><div><p className="eyebrow">ANÁLISE COMPLETA</p><h2>{asset.ticker}</h2></div><button onClick={onClose} aria-label="Fechar detalhes">×</button></div>
        <div className="drawer-summary"><StatusPill value={asset.status} /><ScoreRing value={asset.score} /></div>
        <p className="setup-name">{asset.setup ?? "Estrutura ainda sem confirmação"}</p>
        <div className="level-grid"><div><span>Spot D-1</span><strong>{money(asset.spot)}</strong></div><div><span>Suporte</span><strong>{money(asset.support)}</strong></div><div><span>Resistência</span><strong>{money(asset.resistance)}</strong></div><div><span>Invalidação</span><strong>{money(asset.invalidation)}</strong></div></div>
        <section className="drawer-section"><h3>CALL escolhida</h3>{call ? <><div className="selected-option"><strong>{call.ticker}</strong><span>{call.dte} DTE · strike {money(call.strike)}</span></div><div className="detail-list"><p><span>Prêmio referência</span><strong>{money(call.reference_price)}</strong></p><p><span>Prêmio máximo hoje</span><strong>{money(asset.projections?.max_entry_premium)}</strong></p><p><span>Delta / IV</span><strong>{number(call.delta)} / {percent(call.iv)}</strong></p><p><span>Spread / OI</span><strong>{percent(call.spread_pct)} / {number(call.open_interest, 0)}</strong></p><p><span>Carrego implícito</span><strong>{percent(call.dividend_yield)} · {call.carry_source}</strong></p></div></> : <p className="drawer-empty">Nenhuma CALL passou simultaneamente delta, vencimento, spread, OI e volume financeiro.</p>}</section>
        {asset.projections && <section className="drawer-section"><h3>Retorno projetado no alvo</h3><div className="projection-matrix"><span>Horizonte</span><span>IV −3</span><span>Base</span><span>IV +3</span>{["3", "5", "10"].map((days) => <div className="matrix-row" key={days}><strong>{days} pregões</strong><em>{percent(asset.projections?.horizons[days].conservative, true)}</em><em>{percent(asset.projections?.horizons[days].base, true)}</em><em>{percent(asset.projections?.horizons[days].optimistic, true)}</em></div>)}</div></section>}
        {asset.projections && <section className="drawer-section"><h3>Preço do ativo necessário</h3><div className="target-bands">{["10", "25", "50", "100"].map((level) => <div key={level}><span>CALL +{level}%</span><strong>{money(asset.projections?.required_underlying[level])}</strong></div>)}</div></section>}
        <section className="drawer-section"><h3>Leitura do score</h3><ul className="reason-list">{asset.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></section>
        <p className="execution-note">Os preços são do fechamento D‑1. Compare o prêmio máximo com a corretora antes da entrada; o dashboard não envia ordens.</p>
      </aside>
    </div>
  );
}
