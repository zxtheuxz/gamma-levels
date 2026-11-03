"""Servidor Web Localhost — Painel Visual Operacional Tiro Rápido D+1 a D+3 (Alvo Mínimo +20%).

Inicia em http://127.0.0.1:8050 e abre automaticamente no navegador.
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.rtd_bridge import read_live_rtd_snapshot, sync_rtd_excel  # noqa: E402
from scripts.scan_tiro_rapido_d3 import run_scan_payload  # noqa: E402

app = FastAPI(title="Painel Tiro Rápido D+1 a D+3 (Alvo +20%)")


@app.get("/api/scan")
def api_scan(
    data: str | None = Query(default=None, description="Data base D0 YYYY-MM-DD"),
    download: bool = Query(default=False, description="Se True, consulta novos pregões na B3"),
) -> JSONResponse:
    payload = run_scan_payload(target_date=data, do_download=download)
    return JSONResponse(content=payload)


@app.get("/api/rtd")
def api_rtd() -> JSONResponse:
    snap = read_live_rtd_snapshot()
    return JSONResponse(content=snap)


@app.post("/api/rtd/sync")
def api_rtd_sync() -> JSONResponse:
    res = sync_rtd_excel()
    return JSONResponse(content=res)


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Painel Tiro Rápido D+1 a D+3 | Opções B3 (+20% a +40%)</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #070b14;
      --bg-card: #0f172a;
      --bg-card-alt: #131d35;
      --bg-panel: #1e293b;
      --border: #1e293b;
      --border-hi: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --emerald: #10b981;
      --emerald-bg: rgba(16, 185, 129, 0.12);
      --emerald-border: rgba(16, 185, 129, 0.35);
      --amber: #f59e0b;
      --amber-bg: rgba(245, 158, 11, 0.12);
      --amber-border: rgba(245, 158, 11, 0.35);
      --rose: #f43f5e;
      --rose-bg: rgba(244, 63, 94, 0.12);
      --rose-border: rgba(244, 63, 94, 0.35);
      --cyan: #06b6d4;
      --cyan-bg: rgba(6, 182, 212, 0.12);
      --indigo: #6366f1;
      --gold: #fbbf24;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: radial-gradient(circle at top right, #111c38 0%, var(--bg) 45%);
      color: var(--text);
      min-height: 100vh;
      padding-bottom: 60px;
    }
    .mono { font-family: 'JetBrains Mono', monospace; }

    /* Top Header */
    .topbar {
      position: sticky;
      top: 0;
      z-index: 50;
      background: rgba(7, 11, 20, 0.90);
      backdrop-filter: blur(14px);
      border-bottom: 1px solid var(--border-hi);
      padding: 14px 28px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .brand-badge {
      width: 42px;
      height: 42px;
      border-radius: 12px;
      background: linear-gradient(135deg, #10b981, #059669);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 18px;
      color: #04130d;
      box-shadow: 0 0 20px rgba(16, 185, 129, 0.35);
    }
    .brand-title h1 {
      font-size: 18px;
      font-weight: 800;
      letter-spacing: -0.02em;
    }
    .brand-title p {
      font-size: 12px;
      color: var(--text-muted);
    }
    .controls {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
    }
    .ctrl-group {
      display: flex;
      align-items: center;
      gap: 8px;
      background: var(--bg-card);
      border: 1px solid var(--border-hi);
      padding: 6px 12px;
      border-radius: 10px;
    }
    .ctrl-group label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      font-weight: 600;
    }
    .ctrl-group select, .ctrl-group input {
      background: #070b14;
      color: var(--text);
      border: 1px solid var(--border-hi);
      border-radius: 6px;
      padding: 5px 9px;
      font-size: 13px;
      font-weight: 600;
      font-family: 'JetBrains Mono', monospace;
    }
    .btn {
      cursor: pointer;
      border: none;
      border-radius: 10px;
      padding: 9px 15px;
      font-size: 13px;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.15s ease;
    }
    .btn-primary {
      background: linear-gradient(135deg, #10b981, #059669);
      color: #03150e;
    }
    .btn-primary:hover { filter: brightness(1.1); transform: translateY(-1px); }
    .btn-secondary {
      background: var(--bg-panel);
      color: var(--text);
      border: 1px solid var(--border-hi);
    }
    .btn-secondary:hover { background: #334155; }

    .container {
      max-width: 1440px;
      margin: 0 auto;
      padding: 24px 28px;
    }

    /* Summary Banner */
    .summary-strip {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin-bottom: 22px;
    }
    .stat-box {
      background: var(--bg-card);
      border: 1px solid var(--border-hi);
      border-radius: 14px;
      padding: 14px 18px;
    }
    .stat-box .lbl {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      font-weight: 600;
      margin-bottom: 6px;
    }
    .stat-box .val {
      font-size: 20px;
      font-weight: 800;
    }
    .stat-box .sub {
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 3px;
    }

    /* Tabs */
    .tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 22px;
      border-bottom: 1px solid var(--border-hi);
      padding-bottom: 14px;
    }
    .tab-btn {
      cursor: pointer;
      background: var(--bg-card);
      color: var(--text-muted);
      border: 1px solid var(--border-hi);
      padding: 12px 20px;
      border-radius: 12px;
      font-size: 14px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 10px;
      transition: all 0.15s ease;
    }
    .tab-btn.active {
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(6, 182, 212, 0.15));
      color: var(--text);
      border-color: var(--emerald);
      box-shadow: 0 0 22px rgba(16, 185, 129, 0.2);
    }
    .tab-count {
      background: rgba(255,255,255,0.1);
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-family: 'JetBrains Mono', monospace;
    }
    .tab-btn.active .tab-count {
      background: var(--emerald);
      color: #03150e;
      font-weight: 800;
    }

    /* Guide Box */
    .playbook-banner {
      background: linear-gradient(90deg, rgba(16, 185, 129, 0.10), rgba(99, 102, 241, 0.08));
      border: 1px solid var(--emerald-border);
      border-radius: 14px;
      padding: 16px 20px;
      margin-bottom: 24px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
    }
    .playbook-steps {
      display: flex;
      flex-wrap: wrap;
      gap: 18px;
      font-size: 13px;
      line-height: 1.45;
    }
    .playbook-steps div strong { color: var(--emerald); }

    /* Cards Grid */
    .cards-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(630px, 1fr));
      gap: 22px;
    }
    @media (max-width: 720px) {
      .cards-grid { grid-template-columns: 1fr; }
    }

    .signal-card {
      background: var(--bg-card);
      border: 1px solid var(--border-hi);
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
      display: flex;
      flex-direction: column;
    }
    .signal-card.confluencia {
      border: 1.5px solid var(--gold);
      box-shadow: 0 10px 35px rgba(251, 191, 36, 0.14);
    }

    .card-header {
      padding: 18px 22px;
      background: var(--bg-card-alt);
      border-bottom: 1px solid var(--border-hi);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .stock-id {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .stock-ticker {
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.02em;
    }
    .stock-price {
      font-size: 15px;
      font-weight: 700;
      color: var(--emerald);
      background: var(--emerald-bg);
      border: 1px solid var(--emerald-border);
      padding: 4px 10px;
      border-radius: 8px;
    }
    .badge-tier {
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 5px 11px;
      border-radius: 999px;
    }
    .badge-diamante {
      background: rgba(251, 191, 36, 0.18);
      color: var(--gold);
      border: 1px solid rgba(251, 191, 36, 0.5);
    }
    .badge-ouro {
      background: var(--cyan-bg);
      color: var(--cyan);
      border: 1px solid rgba(6, 182, 212, 0.4);
    }

    .walls-row {
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      padding: 10px 22px;
      background: rgba(15, 23, 42, 0.6);
      border-bottom: 1px solid var(--border);
      font-size: 12px;
      color: var(--text-muted);
    }
    .walls-row span strong { color: var(--text); }

    .card-body {
      padding: 20px 22px;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }

    /* Option Selector Box */
    .opt-box {
      background: #090e1a;
      border: 1px solid var(--border-hi);
      border-radius: 14px;
      padding: 15px 18px;
    }
    .opt-top {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }
    .opt-code-btn {
      cursor: pointer;
      background: linear-gradient(135deg, #10b981, #059669);
      color: #03150e;
      border: none;
      padding: 8px 16px;
      border-radius: 10px;
      font-size: 18px;
      font-weight: 800;
      font-family: 'JetBrains Mono', monospace;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: transform 0.12s ease;
    }
    .opt-code-btn:hover { transform: scale(1.03); }
    .opt-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      font-size: 12.5px;
      color: var(--text-muted);
    }
    .opt-meta span strong { color: var(--text); }

    .alt-strikes {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px dashed var(--border-hi);
      align-items: center;
    }
    .alt-lbl {
      font-size: 11px;
      color: var(--text-muted);
      font-weight: 600;
    }
    .alt-btn {
      cursor: pointer;
      background: var(--bg-card);
      color: var(--text-muted);
      border: 1px solid var(--border-hi);
      border-radius: 7px;
      padding: 4px 10px;
      font-size: 11.5px;
      font-weight: 600;
      font-family: 'JetBrains Mono', monospace;
    }
    .alt-btn.active {
      background: var(--emerald-bg);
      color: var(--emerald);
      border-color: var(--emerald);
    }

    /* Auction / Entry Price Guide (Where to enter & What price is good) */
    .entry-guide {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
    }
    @media (max-width: 580px) {
      .entry-guide { grid-template-columns: 1fr; }
    }
    .guide-pill {
      border-radius: 12px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .guide-good {
      background: var(--emerald-bg);
      border: 1px solid var(--emerald-border);
    }
    .guide-limit {
      background: var(--amber-bg);
      border: 1px solid var(--amber-border);
    }
    .guide-stop {
      background: var(--rose-bg);
      border: 1px solid var(--rose-border);
    }
    .guide-pill .g-title {
      font-size: 10.5px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .guide-good .g-title { color: var(--emerald); }
    .guide-limit .g-title { color: var(--amber); }
    .guide-stop .g-title { color: var(--rose); }
    .guide-pill .g-val {
      font-size: 16px;
      font-weight: 800;
      font-family: 'JetBrains Mono', monospace;
    }
    .guide-pill .g-sub {
      font-size: 11px;
      color: var(--text-muted);
    }

    /* Interactive Auction / Book Calculator */
    .calc-box {
      background: linear-gradient(180deg, #131d35 0%, #0d1527 100%);
      border: 1px solid var(--border-hi);
      border-radius: 14px;
      padding: 16px 18px;
    }
    .calc-header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 14px;
    }
    .calc-header h4 {
      font-size: 13px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--cyan);
    }
    .auction-status {
      font-size: 12px;
      font-weight: 800;
      padding: 4px 10px;
      border-radius: 8px;
    }
    .status-great { background: var(--emerald-bg); color: var(--emerald); border: 1px solid var(--emerald-border); }
    .status-ok { background: var(--amber-bg); color: var(--amber); border: 1px solid var(--amber-border); }
    .status-expensive { background: var(--rose-bg); color: var(--rose); border: 1px solid var(--rose-border); }

    .calc-inputs {
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      align-items: center;
      margin-bottom: 14px;
    }
    .calc-field {
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex: 1;
      min-width: 150px;
    }
    .calc-field label {
      font-size: 11px;
      color: var(--text-muted);
      font-weight: 600;
    }
    .calc-field input {
      background: #070b14;
      color: var(--text);
      border: 1px solid var(--cyan);
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 15px;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
    }

    .targets-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
    }
    @media (max-width: 580px) {
      .targets-grid { grid-template-columns: 1fr; }
    }
    .tgt-card {
      background: #080d19;
      border: 1px solid var(--border-hi);
      border-radius: 10px;
      padding: 11px 13px;
    }
    .tgt-card .t-lbl {
      font-size: 10.5px;
      text-transform: uppercase;
      color: var(--text-muted);
      font-weight: 700;
      margin-bottom: 4px;
    }
    .tgt-card .t-price {
      font-size: 17px;
      font-weight: 800;
      color: var(--emerald);
      font-family: 'JetBrains Mono', monospace;
    }
    .tgt-card .t-profit {
      font-size: 11.5px;
      color: var(--text-muted);
      margin-top: 3px;
    }

    /* Speed & WinRate Bars */
    .stats-strip {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
    }
    .s-pill {
      background: #090e1a;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 9px 10px;
      text-align: center;
    }
    .s-pill .sp-lbl {
      font-size: 10px;
      color: var(--text-muted);
      text-transform: uppercase;
      font-weight: 700;
    }
    .s-pill .sp-val {
      font-size: 16px;
      font-weight: 800;
      margin-top: 2px;
      font-family: 'JetBrains Mono', monospace;
    }

    /* Trigger Reasons */
    .reasons-box {
      background: rgba(15, 23, 42, 0.55);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 15px;
    }
    .reasons-title {
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--text-muted);
      margin-bottom: 8px;
    }
    .reasons-list {
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 5px;
      font-size: 12.5px;
      color: #cbd5e1;
    }
    .reasons-list li::before {
      content: "✔ ";
      color: var(--emerald);
      font-weight: 800;
    }

    .toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: var(--emerald);
      color: #03150e;
      padding: 12px 20px;
      border-radius: 12px;
      font-weight: 800;
      font-size: 13px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.4);
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.2s ease;
      z-index: 100;
    }
    .toast.show { opacity: 1; }
  </style>
</head>
<body>

  <header class="topbar">
    <div class="brand">
      <div class="brand-badge">D3</div>
      <div class="brand-title">
        <h1>PAINEL TIRO RÁPIDO (D+1 a D+3) — OPÇÕES B3</h1>
        <p>Alvo Mínimo +20% (1ª Saída) e +40% (2ª Saída c/ Stop no 0x0) • 45 Ações Líquidas Auditadas</p>
      </div>
    </div>

    <div class="controls">
      <div class="ctrl-group">
        <label for="dateSelect">Pregão Base (D0):</label>
        <select id="dateSelect" onchange="loadScan(false)"></select>
      </div>
      <div class="ctrl-group">
        <label for="globalCap">Capital / Trade (R$):</label>
        <input type="number" id="globalCap" value="600" step="100" min="100" style="width: 95px;" oninput="recalcAllCards()" />
      </div>
      <button class="btn btn-outline" onclick="pollRtdOnce(true)" id="btnRtdNow" title="Lê agora os preços do Profit RTD na planilha rtd.xlsx">
        📡 Ler RTD (rtd.xlsx)
      </button>
      <button class="btn btn-outline" onclick="toggleRtdAuto()" id="btnRtdAuto" style="border-color: var(--emerald-border); color: var(--emerald);">
        ⚡ Auto-RTD (2s): OFF
      </button>
      <button class="btn btn-primary" onclick="loadScan(true)" id="btnRefresh">
        🔄 Baixar B3 & Atualizar
      </button>
    </div>
  </header>

  <main class="container">
    <div id="rtdStatusBar" style="margin-bottom: 16px; padding: 10px 16px; border-radius: 12px; background: rgba(15, 23, 42, 0.85); border: 1px solid var(--border-hi); display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; font-size: 12.5px;">
      <div>
        <strong>📡 Ponte Profit RTD (<code>rtd.xlsx</code>):</strong>
        <span id="rtdStatusText" style="color: var(--text-muted); margin-left: 6px;">Pronta para o leilão! Deixe o <code>rtd.xlsx</code> aberto com o Profit RTD ativo (ou salve Ctrl+S no Excel) e clique em "📡 Ler RTD".</span>
      </div>
      <span id="rtdTimestamp" class="mono" style="font-size: 11px; color: var(--cyan);"></span>
    </div>
    <section class="summary-strip" id="summaryStrip"></section>

    <nav class="tabs">
      <button class="tab-btn active" id="tabBtnMesa2" onclick="switchTab('mesa2')">
        🌅 MESA 2: ENTRAR NO LEILÃO / ABERTURA (D+1 — 09h55 às 10h15)
        <span class="tab-count" id="countMesa2">0</span>
      </button>
      <button class="tab-btn" id="tabBtnMesa1" onclick="switchTab('mesa1')">
        🌇 MESA 1: ENTRAR NO FIM DO DIA (D0 — 16h45 às 16h55)
        <span class="tab-count" id="countMesa1">0</span>
      </button>
    </nav>

    <div id="playbookBanner" class="playbook-banner"></div>

    <section id="cardsContainer" class="cards-grid"></section>
  </main>

  <div id="toast" class="toast">Código copiado para o Profit!</div>

  <script>
    let currentData = null;
    let activeTab = 'mesa2';
    let selectedOptionByCard = {};

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.classList.add('show');
      setTimeout(() => t.classList.remove('show'), 2200);
    }

    function copyTicker(code) {
      navigator.clipboard.writeText(code);
      showToast(`Código ${code} copiado! Cole direto no Profit.`);
    }

    function fmtBRL(v) {
      return Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function fmtDateBR(iso) {
      if (!iso) return '-';
      const p = iso.split('-');
      return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : iso;
    }

    async function loadScan(doDownload = false) {
      const btn = document.getElementById('btnRefresh');
      const sel = document.getElementById('dateSelect');
      const chosenDate = sel.value || '';
      btn.textContent = doDownload ? '⏳ Baixando B3...' : '⏳ Carregando...';
      btn.disabled = true;

      try {
        const qs = new URLSearchParams();
        if (chosenDate && !doDownload) qs.set('data', chosenDate);
        if (doDownload) qs.set('download', 'true');
        const res = await fetch(`/api/scan?${qs.toString()}`);
        currentData = await res.json();

        // Populate dates dropdown
        const avail = currentData.available_dates || [];
        sel.innerHTML = avail.slice().reverse().map(d =>
          `<option value="${d}" ${d === currentData.eval_date ? 'selected' : ''}>${fmtDateBR(d)} (${d})</option>`
        ).join('');

        selectedOptionByCard = {};
        renderAll();
      } catch (e) {
        console.error(e);
        alert('Erro ao carregar o scanner: ' + e.message);
      } finally {
        btn.textContent = '🔄 Baixar B3 & Atualizar';
        btn.disabled = false;
      }
    }

    function switchTab(tab) {
      activeTab = tab;
      document.getElementById('tabBtnMesa2').classList.toggle('active', tab === 'mesa2');
      document.getElementById('tabBtnMesa1').classList.toggle('active', tab === 'mesa1');
      renderAll();
    }

    function selectAltOption(cardKey, idx) {
      selectedOptionByCard[cardKey] = idx;
      renderAll();
    }

    function renderAll() {
      if (!currentData) return;
      const m2 = currentData.mesa2_abert_d1 || [];
      const m1 = currentData.mesa1_fim_d0 || [];

      document.getElementById('countMesa2').textContent = m2.length;
      document.getElementById('countMesa1').textContent = m1.length;

      // Summary strip
      const summaryEl = document.getElementById('summaryStrip');
      summaryEl.innerHTML = `
        <div class="stat-box">
          <div class="lbl">Pregão Base Analisado (D0)</div>
          <div class="val mono">${fmtDateBR(currentData.eval_date)}</div>
          <div class="sub">${currentData.n_stocks} ações líquidas escaneadas</div>
        </div>
        <div class="stat-box">
          <div class="lbl">Próximo Pregão (Entrada D+1)</div>
          <div class="val mono" style="color: var(--emerald);">${fmtDateBR(currentData.next_session_d1)}</div>
          <div class="sub">Leilão 09h55 / Abertura 10h05</div>
        </div>
        <div class="stat-box">
          <div class="lbl">Ativados p/ Abertura D+1 (Mesa 2)</div>
          <div class="val mono" style="color: var(--gold);">${m2.length} ações</div>
          <div class="sub">${m2.filter(x => x.n_rules >= 2).length} com Super Confluência (2+ regras)</div>
        </div>
        <div class="stat-box">
          <div class="lbl">Ativados p/ Fim do Dia D0 (Mesa 1)</div>
          <div class="val mono" style="color: var(--cyan);">${m1.length} ações</div>
          <div class="sub">Janela 16h45 às 16h55 • Limite máx: ${fmtDateBR(currentData.session_d3)}</div>
        </div>
      `;

      // Playbook Banner
      const bannerEl = document.getElementById('playbookBanner');
      if (activeTab === 'mesa2') {
        bannerEl.innerHTML = `
          <div class="playbook-steps">
            <div><strong>1. No Leilão (09h55–10h05 de ${fmtDateBR(currentData.next_session_d1)}):</strong> Confira se a ação abre acima do <strong>Piso Mínimo (-1,5%)</strong>.</div>
            <div><strong>2. Valor Bom p/ Bater:</strong> Se a CALL estiver na <strong>Faixa Verde (Ideal)</strong> ou até o <strong>Teto Amarelo (+15%)</strong>, você já pode bater no leilão ou nos primeiros minutos!</div>
            <div><strong>3. Saída Rápida (D+1 a D+3):</strong> Assim que entrar, já deixe apregoada a venda de <strong>50% em +20%</strong> (e o resto em <strong>+40% com Stop no 0x0</strong>). Zeragem máxima em <strong>D+3</strong>.</div>
          </div>
        `;
      } else {
        bannerEl.innerHTML = `
          <div class="playbook-steps">
            <div><strong>1. Horário (16h45–16h55 de ${fmtDateBR(currentData.eval_date)}):</strong> Entre nos últimos 15 minutos do pregão pagando dentro da <strong>Faixa Verde</strong> da CALL.</div>
            <div><strong>2. Explosão no Dia Seguinte (D+1):</strong> De <strong>45% a 60%</strong> das vezes essas regras já batem <strong>+20% logo na manhã de D+1 (${fmtDateBR(currentData.next_session_d1)})</strong>!</div>
            <div><strong>3. Zeragem Máxima (Time-Stop D+3):</strong> Se não bater o alvo antes, encerre 100% até as 16h45 do 3º dia útil (<strong>${fmtDateBR(currentData.session_d3)}</strong>).</div>
          </div>
        `;
      }

      const list = activeTab === 'mesa2' ? m2 : m1;
      const container = document.getElementById('cardsContainer');

      if (!list.length) {
        container.innerHTML = `<div class="stat-box" style="grid-column: 1 / -1; text-align: center; padding: 40px;">Nenhuma ação acionou esta mesa na data selecionada.</div>`;
        return;
      }

      container.innerHTML = list.map((item, idx) => renderCard(item, idx)).join('');
      recalcAllCards();
    }

    function renderCard(item, idx) {
      const cardKey = `${activeTab}_${item.ticker}`;
      const cands = (item.option_candidates && item.option_candidates.length)
        ? item.option_candidates
        : [{
            profile: "CORE_ATM (Principal)",
            ticker: item.opt_ticker || "SELECIONAR_ATM",
            strike: item.opt_strike || 0,
            expiration: item.opt_exp || "-",
            dte: item.opt_dte || 0,
            delta: item.opt_delta || 0.5,
            iv_pct: Number((item.opt_iv || 0) * 100).toFixed(1),
            close: item.opt_close || 0,
            ref: item.opt_ref || 0,
            bid: item.opt_bid || 0,
            ask: item.opt_ask || 0,
            trades: item.opt_trades || 0,
            volume: item.opt_vol || 0,
            auction_ideal_min: item.ideal_buy_min || 0,
            auction_ideal_max: item.ideal_buy_max || 0,
            auction_max_limit: item.opt_max_open_d1 || item.max_buy_limit || 0,
          }];

      const selIdx = selectedOptionByCard[cardKey] || 0;
      const opt = cands[Math.min(selIdx, cands.length - 1)];
      const isConf = item.n_rules >= 2;
      const br = item.best_rule;

      const stockFloor = item.min_stock_open_d1 || Number(item.spot * 0.985).toFixed(2);
      const idealMin = opt.auction_ideal_min || Number(opt.close * 0.94).toFixed(2);
      const idealMax = opt.auction_ideal_max || Number(opt.close * 1.05).toFixed(2);
      const maxLimit = opt.auction_max_limit || Number(Math.max(opt.close, opt.ref || opt.close) * 1.15).toFixed(2);

      const altButtonsHtml = cands.length > 1 ? `
        <div class="alt-strikes">
          <span class="alt-lbl">Alternar Strike na Série:</span>
          ${cands.map((c, cIdx) => `
            <button class="alt-btn ${cIdx === selIdx ? 'active' : ''}" onclick="selectAltOption('${cardKey}', ${cIdx})">
              ${c.ticker} (K=${fmtBRL(c.strike)} | Δ ${c.delta} | R$ ${fmtBRL(c.close)})
            </button>
          `).join('')}
        </div>
      ` : '';

      const rulesBadges = (item.rules_detail || []).map(r =>
        `<span style="background: rgba(255,255,255,0.06); border: 1px solid var(--border-hi); padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 700;">
          <strong style="color: var(--emerald);">${r.code}</strong>: ${r.title_pt || r.desc} (${r.wr}% WR)
        </span>`
      ).join(' ');

      const reasonsHtml = (item.reasons_pt || []).map(txt => `<li>${txt}</li>`).join('');

      return `
        <article class="signal-card ${isConf ? 'confluencia' : ''}" data-cardkey="${cardKey}"
                 data-idealmin="${idealMin}" data-idealmax="${idealMax}" data-maxlimit="${maxLimit}"
                 data-optcode="${opt.ticker}">
          <div class="card-header">
            <div class="stock-id">
              <span class="stock-ticker mono">#${idx + 1} ${item.ticker}</span>
              <span class="stock-price mono">Fech D0: R$ ${fmtBRL(item.spot)} (${item.ret_1d_pct >= 0 ? '+' : ''}${item.ret_1d_pct}%)</span>
            </div>
            <span class="badge-tier ${isConf ? 'badge-diamante' : 'badge-ouro'}">
              ${isConf ? `💎 SUPER CONFLUÊNCIA (${item.n_rules} REGRAS)` : `🥇 SINAL ATIVO (${br.code})`}
            </span>
          </div>

          <div class="walls-row">
            <span>🛡️ Piso Put Wall: <strong class="mono">R$ ${fmtBRL(item.put_wall)}</strong></span>
            <span>🎯 Teto Call Wall: <strong class="mono">R$ ${fmtBRL(item.call_wall)}</strong></span>
            <span>📊 Giro Calls/Puts: <strong class="mono">${item.call_put_vol}x</strong></span>
            <span>🦈 Ticket Tubarão: <strong class="mono">${item.cp_ticket}x</strong></span>
            <span>⏱️ Zeragem Máx (D+3): <strong class="mono" style="color: var(--amber);">${fmtDateBR(item.d3_limit_date)} às 16h45</strong></span>
          </div>

          <div class="card-body">
            <div style="display: flex; flex-wrap: wrap; gap: 6px;">
              ${rulesBadges}
            </div>

            <!-- Bloco da Opção no Profit -->
            <div class="opt-box">
              <div class="opt-top">
                <div>
                  <div style="font-size: 10.5px; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin-bottom: 4px;">
                    Código da CALL p/ Digitar no Profit (Clique p/ Copiar):
                  </div>
                  <button class="opt-code-btn" onclick="copyTicker('${opt.ticker}')">
                    📋 ${opt.ticker}
                  </button>
                </div>
                <div class="opt-meta">
                  <span>Strike: <strong class="mono">R$ ${fmtBRL(opt.strike)}</strong></span>
                  <span>Venc: <strong class="mono">${fmtDateBR(opt.expiration)} (${opt.dte}d)</strong></span>
                  <span>Delta: <strong class="mono">${opt.delta}</strong></span>
                  <span>IV: <strong class="mono">${opt.iv_pct}%</strong></span>
                  <span>Fech D0: <strong class="mono" style="color: var(--emerald);">R$ ${fmtBRL(opt.close)}</strong></span>
                  <span>Giro B3: <strong class="mono">R$ ${Number(opt.volume).toLocaleString('pt-BR')} (${opt.trades} neg)</strong></span>
                </div>
              </div>
              ${altButtonsHtml}
            </div>

            <!-- Guia de Preço para Bater no Leilão / Abertura -->
            <div class="entry-guide">
              <div class="guide-pill guide-good">
                <span class="g-title">🟢 Preço Bom (Pode Bater no Leilão)</span>
                <span class="g-val">R$ ${fmtBRL(idealMin)} a R$ ${fmtBRL(idealMax)}</span>
                <span class="g-sub">Faixa ideal (sem gap caro sobre D0)</span>
              </div>
              <div class="guide-pill guide-limit">
                <span class="g-title">🟡 Teto Máximo Aceitável (+15%)</span>
                <span class="g-val">Até R$ ${fmtBRL(maxLimit)}</span>
                <span class="g-sub">Acima de R$ ${fmtBRL(maxLimit)} NÃO ENTRE!</span>
              </div>
              <div class="guide-pill guide-stop">
                <span class="g-title">🛡️ Piso da Ação na Abertura</span>
                <span class="g-val">${item.ticker} ≥ R$ ${fmtBRL(stockFloor)}</span>
                <span class="g-sub">Abortar se abrir abaixo de R$ ${fmtBRL(stockFloor)} (-1,5%)</span>
              </div>
            </div>

            <!-- Painel Ao Vivo RTD (Profit -> rtd.xlsx) -->
            <div id="rtdbox_${cardKey}" style="background: rgba(6, 182, 212, 0.07); border: 1px solid rgba(6, 182, 212, 0.30); border-radius: 12px; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px;">
              <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                <span style="font-size: 11px; font-weight: 800; text-transform: uppercase; color: var(--cyan); letter-spacing: 0.04em;">
                  📡 Leitura Ao Vivo do Profit RTD (<code>rtd.xlsx</code>): <strong class="mono">${item.ticker}</strong> &amp; <strong class="mono">${opt.ticker}</strong>
                </span>
                <span id="rtd_badge_${cardKey}" class="mono" style="font-size: 11px; padding: 2px 8px; border-radius: 6px; background: rgba(255,255,255,0.06); color: var(--text-muted);">
                  ⏳ Aguardando Leilão / RTD
                </span>
              </div>
              <div id="rtd_quotes_${cardKey}" class="mono" style="font-size: 12px; color: #e2e8f0; display: flex; flex-wrap: wrap; gap: 14px;">
                <span><strong>${item.ticker}:</strong> Leilão(PRT): - | Últ: - | Piso ≥ R$ ${fmtBRL(stockFloor)}</span>
                <span><strong>${opt.ticker}:</strong> Leilão(PRT): - | Book: - x - | Últ: -</span>
              </div>
              <div id="rtd_verdict_${cardKey}" style="font-size: 12.5px; font-weight: 700; padding: 8px 10px; border-radius: 8px; background: rgba(15, 23, 42, 0.75); border-left: 3px solid var(--cyan); color: #f8fafc;">
                ⏳ Assim que o Profit RTD enviar os preços do leilão para o <code>rtd.xlsx</code>, o veredito automático (<strong>Bater a Mercado / Limitado / Abortar</strong>) aparecerá aqui!
              </div>
            </div>

            <!-- Simulador de Boleta em Tempo Real -->
            <div class="calc-box">
              <div class="calc-header">
                <h4>⚡ Boleta Rápida de Leilão / Entrada e Saídas Apregoadas</h4>
                <span class="auction-status status-great" id="status_${cardKey}">🟢 PREÇO IDEAL NO LEILÃO</span>
              </div>
              <div class="calc-inputs">
                <div class="calc-field">
                  <label>Preço da CALL no Leilão / Book agora (R$):</label>
                  <input type="number" step="0.01" min="0.01" id="px_${cardKey}" value="${opt.close}" oninput="recalcCard('${cardKey}')" />
                </div>
                <div class="calc-field">
                  <label>Quantidade Recomendada (Lotes de 100):</label>
                  <input type="text" id="qty_${cardKey}" readonly style="border-color: var(--border-hi); color: var(--gold);" />
                </div>
              </div>
              <div class="targets-grid">
                <div class="tgt-card">
                  <div class="t-lbl">🎯 1ª Saída (+20% — Vender 50% ou 100%)</div>
                  <div class="t-price" id="t20_${cardKey}">R$ 0,00</div>
                  <div class="t-profit" id="p20_${cardKey}">Apregoar assim que comprar</div>
                </div>
                <div class="tgt-card">
                  <div class="t-lbl">🛡️ Stop da 2ª Metade (Após bater +20%)</div>
                  <div class="t-price" style="color: var(--cyan);" id="be_${cardKey}">R$ 0,00</div>
                  <div class="t-profit">Risco Zero no Breakeven (0x0)</div>
                </div>
                <div class="tgt-card">
                  <div class="t-lbl">🚀 2ª Saída (+40% até D+3)</div>
                  <div class="t-price" style="color: var(--gold);" id="t40_${cardKey}">R$ 0,00</div>
                  <div class="t-profit" id="p40_${cardKey}">Ou zerar no fechamento de D+3</div>
                </div>
              </div>
            </div>

            <!-- Velocidade Histórica D+1, D+2, D+3 -->
            <div class="stats-strip">
              <div class="s-pill">
                <div class="sp-lbl">Taxa de Acerto</div>
                <div class="sp-val" style="color: var(--emerald);">${br.wr.toFixed(1)}%</div>
              </div>
              <div class="s-pill">
                <div class="sp-lbl">Bate +20% no D+1</div>
                <div class="sp-val" style="color: var(--cyan);">${br.hit20_d1.toFixed(1)}%</div>
              </div>
              <div class="s-pill">
                <div class="sp-lbl">Bate +20% até D+2</div>
                <div class="sp-val" style="color: var(--gold);">${br.hit20_d2.toFixed(1)}%</div>
              </div>
              <div class="s-pill">
                <div class="sp-lbl">Prazo Médio</div>
                <div class="sp-val">${br.hold.toFixed(2)} dias</div>
              </div>
            </div>

            <!-- Explicação em Português -->
            <div class="reasons-box">
              <div class="reasons-title">Por que ${item.ticker} ativou o sinal matemático?</div>
              <ul class="reasons-list">
                ${reasonsHtml}
              </ul>
            </div>
          </div>
        </article>
      `;
    }

    function recalcCard(cardKey) {
      const card = document.querySelector(`.signal-card[data-cardkey="${cardKey}"]`);
      if (!card) return;
      const cap = parseFloat(document.getElementById('globalCap').value) || 600;
      const pxInput = document.getElementById(`px_${cardKey}`);
      const entryPx = parseFloat(pxInput.value) || 0;
      const idealMax = parseFloat(card.dataset.idealmax) || entryPx;
      const maxLimit = parseFloat(card.dataset.maxlimit) || entryPx;

      const statusEl = document.getElementById(`status_${cardKey}`);
      if (entryPx <= 0) {
        statusEl.textContent = 'Digite um preço válido';
        statusEl.className = 'auction-status status-expensive';
        return;
      }

      if (entryPx <= idealMax + 0.001) {
        statusEl.textContent = '🟢 PREÇO BOM / IDEAL — PODE BATER NO LEILÃO!';
        statusEl.className = 'auction-status status-great';
      } else if (entryPx <= maxLimit + 0.001) {
        statusEl.textContent = '🟡 PREÇO ACEITÁVEL (ATÉ O TETO DE +15%)';
        statusEl.className = 'auction-status status-ok';
      } else {
        statusEl.textContent = '🔴 ACIMA DO TETO (+15%) — GAP CARO, ABORTAR!';
        statusEl.className = 'auction-status status-expensive';
      }

      // Lotes de 100 opções (ou mínimo 100)
      let rawQty = Math.floor(cap / entryPx);
      let lotQty = Math.max(100, Math.round(rawQty / 100) * 100);
      if (entryPx > 5.0) {
        // Opções caras ou ETFs
        lotQty = Math.max(10, Math.round(rawQty / 10) * 10);
      }
      const totalCost = lotQty * entryPx;

      const t20 = Math.max(entryPx + 0.01, Math.round(entryPx * 1.20 * 100) / 100);
      const t40 = Math.max(t20 + 0.01, Math.round(entryPx * 1.40 * 100) / 100);

      const profitAll20 = (t20 - entryPx) * lotQty;
      const halfQty = Math.floor(lotQty / 2);
      const profitPartial = (t20 - entryPx) * halfQty + (t40 - entryPx) * (lotQty - halfQty);

      document.getElementById(`qty_${cardKey}`).value = `${lotQty} qtds (Custo: R$ ${fmtBRL(totalCost)})`;
      document.getElementById(`t20_${cardKey}`).textContent = `R$ ${fmtBRL(t20)}`;
      document.getElementById(`p20_${cardKey}`).textContent = `Lucro 100% no +20%: +R$ ${fmtBRL(profitAll20)} (+${(((t20/entryPx)-1)*100).toFixed(0)}%)`;
      document.getElementById(`be_${cardKey}`).textContent = `R$ ${fmtBRL(entryPx)}`;
      document.getElementById(`t40_${cardKey}`).textContent = `R$ ${fmtBRL(t40)}`;
      document.getElementById(`p40_${cardKey}`).textContent = `Lucro Parcial 20%/40%: +R$ ${fmtBRL(profitPartial)}`;
    }

    function recalcAllCards() {
      document.querySelectorAll('.signal-card').forEach(card => {
        recalcCard(card.dataset.cardkey);
      });
    }

    let rtdTimer = null;
    let lastRtdSnap = null;

    function toggleRtdAuto() {
      const btn = document.getElementById('btnRtdAuto');
      if (rtdTimer) {
        clearInterval(rtdTimer);
        rtdTimer = null;
        btn.textContent = '⚡ Auto-RTD (2s): OFF';
        btn.style.background = 'transparent';
        btn.style.color = 'var(--emerald)';
      } else {
        pollRtdOnce(true);
        rtdTimer = setInterval(() => pollRtdOnce(false), 2000);
        btn.textContent = '🟢 Auto-RTD (2s): ON';
        btn.style.background = 'var(--emerald)';
        btn.style.color = '#03150e';
      }
    }

    async function pollRtdOnce(notify = false) {
      try {
        const res = await fetch('/api/rtd');
        const snap = await res.json();
        lastRtdSnap = snap;
        applyRtdToCards(snap);
        if (notify) {
          showToast(snap.rtd_active ? '🟢 Preços RTD lidos ao vivo do Profit!' : '📡 rtd.xlsx lido (aguardando abertura do pregão/Profit RTD)');
        }
      } catch (e) {
        console.error('Erro RTD:', e);
      }
    }

    function applyRtdToCards(snap) {
      if (!snap) return;
      const statusTxt = document.getElementById('rtdStatusText');
      const tsEl = document.getElementById('rtdTimestamp');
      if (tsEl) tsEl.textContent = `Última leitura: ${snap.timestamp} (${snap.source_mode})`;

      if (snap.rtd_active) {
        statusTxt.innerHTML = `<strong style="color: var(--emerald);">🟢 SINAL RTD AO VIVO CONECTADO!</strong> Lendo Leilão (<code>PRT</code>), Book (<code>OCP x OVD</code>) e Último (<code>ULT</code>) em tempo real.`;
      } else if (snap.workbook_open) {
        statusTxt.innerHTML = `<strong style="color: var(--gold);">🟡 Planilha <code>rtd.xlsx</code> aberta no Excel!</strong> Aguardando o Profit enviar preços do leilão/pregão...`;
      } else {
        statusTxt.innerHTML = `Planilha <code>rtd.xlsx</code> pronta (${snap.n_options} opções configuradas). No pregão, deixe o <code>rtd.xlsx</code> aberto com o Profit RTD ligado (e dê Ctrl+S se quiser atualizar em disco).`;
      }

      document.querySelectorAll('.signal-card').forEach(card => {
        const cardKey = card.dataset.cardkey;
        const optCode = card.dataset.optcode;
        const optRtd = (snap.options || {})[optCode];
        if (!optRtd) return;
        const stockRtd = (snap.stocks || {})[optRtd.stock_ticker] || {};

        const badgeEl = document.getElementById(`rtd_badge_${cardKey}`);
        const quotesEl = document.getElementById(`rtd_quotes_${cardKey}`);
        const verdictEl = document.getElementById(`rtd_verdict_${cardKey}`);

        const sPrt = stockRtd.prt ? `R$ ${fmtBRL(stockRtd.prt)}` : '-';
        const sUlt = stockRtd.ult ? `R$ ${fmtBRL(stockRtd.ult)}` : '-';
        const sBidAsk = (stockRtd.bid || stockRtd.ask) ? `R$ ${fmtBRL(stockRtd.bid)} x R$ ${fmtBRL(stockRtd.ask)}` : '-';

        const oPrt = optRtd.prt ? `R$ ${fmtBRL(optRtd.prt)}` : '-';
        const oUlt = optRtd.ult ? `R$ ${fmtBRL(optRtd.ult)}` : '-';
        const oBid = optRtd.bid ? `R$ ${fmtBRL(optRtd.bid)}` : '-';
        const oAsk = optRtd.ask ? `R$ ${fmtBRL(optRtd.ask)}` : '-';
        const oQcp = optRtd.qcp ? `${optRtd.qcp}` : '';
        const oQvd = optRtd.qvd ? `${optRtd.qvd}` : '';

        if (quotesEl) {
          quotesEl.innerHTML = `
            <span>📈 <strong>${optRtd.stock_ticker}:</strong> Leilão(PRT): <strong>${sPrt}</strong> | Últ: <strong>${sUlt}</strong> | Book: ${sBidAsk}</span>
            <span>⚡ <strong>${optCode}:</strong> Leilão(PRT): <strong style="color: var(--gold);">${oPrt}</strong> | Book: <strong style="color: var(--emerald);">${oQcp ? oQcp + ' @ ' : ''}${oBid}</strong> x <strong style="color: var(--cyan);">${oAsk}${oQvd ? ' @ ' + oQvd : ''}</strong> | Últ: <strong>${oUlt}</strong></span>
          `;
        }

        if (verdictEl && optRtd.verdict_text) {
          verdictEl.textContent = optRtd.verdict_text;
          if (optRtd.verdict_tier === 'FIRE_IDEAL') {
            verdictEl.style.borderLeftColor = 'var(--emerald)';
            verdictEl.style.background = 'var(--emerald-bg)';
            verdictEl.style.color = '#6ee7b7';
            if (badgeEl) {
              badgeEl.textContent = '🟢 TUDO FAVORÁVEL — BATER!';
              badgeEl.style.background = 'var(--emerald-bg)';
              badgeEl.style.color = '#34d399';
            }
          } else if (optRtd.verdict_tier === 'OK_LIMIT') {
            verdictEl.style.borderLeftColor = 'var(--amber)';
            verdictEl.style.background = 'var(--amber-bg)';
            verdictEl.style.color = '#fcd34d';
            if (badgeEl) {
              badgeEl.textContent = '🟡 ACEITÁVEL ATÉ O TETO';
              badgeEl.style.background = 'var(--amber-bg)';
              badgeEl.style.color = '#fbbf24';
            }
          } else if (optRtd.verdict_tier === 'ABORT_STOCK' || optRtd.verdict_tier === 'ABORT_EXPENSIVE') {
            verdictEl.style.borderLeftColor = 'var(--rose)';
            verdictEl.style.background = 'var(--rose-bg)';
            verdictEl.style.color = '#fda4af';
            if (badgeEl) {
              badgeEl.textContent = '🔴 ABORTAR ENTRADA!';
              badgeEl.style.background = 'var(--rose-bg)';
              badgeEl.style.color = '#fb7185';
            }
          }
        }

        // Se chegou preço vivo do RTD (Ask, Leilão PRT ou Último), atualiza a Boleta automaticamente!
        if (optRtd.live_px && optRtd.live_px > 0) {
          const pxInput = document.getElementById(`px_${cardKey}`);
          if (pxInput) {
            pxInput.value = Number(optRtd.live_px).toFixed(2);
            recalcCard(cardKey);
          }
        }
      });
    }

    window.addEventListener('DOMContentLoaded', async () => {
      await loadScan(false);
      await pollRtdOnce(false);
    });
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(content=HTML_PAGE)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Servidor Web Localhost Tiro Rápido D+1 a D+3")
    parser.add_argument("--port", type=int, default=8050, help="Porta HTTP local (padrão: 8050)")
    parser.add_argument("--sem-navegador", action="store_true", help="Não abrir navegador automaticamente")
    args = parser.parse_args()

    url = f"http://127.0.0.1:{args.port}"
    print(f"Iniciando Painel Tiro Rápido em {url} ...", flush=True)
    if not args.sem_navegador:
        webbrowser.open(url)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")

