"""
Scanner Operacional Diário de Opções Americanas (EUA — CBOE Live Quotes)
========================================================================
Avalia as 36 ações/ETFs mais líquidas dos EUA nas regras campeãs aprovadas nos 4 Quadrantes
(`Q1_Treino1`, `Q2_Treino2`, `Q3_OOS_Temporal`, `Q4_12_Ativos_Virgens_EUA`) e seleciona os
contratos de CALL reais da CBOE (12 a 28 DTE) em 3 faixas de preço/delta:
- CORE_ATM (Delta ~0.48)
- ITM_SEGURA (Delta ~0.62)
- OTM_ACESSIVEL (Delta ~0.32 — ideal para tickets de US$ 35 a US$ 180 por contrato)
"""

from __future__ import annotations

import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "results" / "us_options"
CACHE_DIR = OUT_DIR / "cache_v1"
OCC_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def fetch_cboe_live(ticker: str) -> dict:
    url = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{ticker}.json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read().decode("utf-8")).get("data", {})


def evaluate_ticker_today(ticker: str, hist_df: pd.DataFrame, today: date) -> dict | None:
    try:
        d = fetch_cboe_live(ticker)
    except Exception:
        return None
    if not d:
        return None

    spot = float(d.get("current_price") or d.get("close") or 0.0)
    prev = float(d.get("prev_day_close") or spot)
    hi = float(d.get("high") or spot)
    lo = float(d.get("low") or spot)
    if spot <= 0:
        return None

    ret_1d = (spot / prev - 1.0) * 100.0 if prev > 0 else 0.0
    cir = (spot - lo) / (hi - lo) if hi > lo else 0.5

    opts = d.get("options", [])
    call_vol = put_vol = call_oi = put_oi = otm_call_vol = gex_today = vanna_today = 0.0
    call_strike_oi = {}
    put_strike_oi = {}
    candidates = []

    for o in opts:
        sym = o.get("option", "")
        m = OCC_RE.match(sym)
        if not m:
            continue
        _, ymd, cp, sraw = m.groups()
        exp = datetime.strptime(ymd, "%y%m%d").date()
        dte = (exp - today).days
        if dte < 2 or dte > 50:
            continue
        strike = int(sraw) / 1000.0
        vol = float(o.get("volume") or 0.0)
        oi = float(o.get("open_interest") or 0.0)
        gamma = float(o.get("gamma") or 0.0)
        delta = float(o.get("delta") or 0.0)
        vega = float(o.get("vega") or 0.0)
        iv = float(o.get("iv") or 0.0)
        bid = float(o.get("bid") or 0.0)
        ask = float(o.get("ask") or 0.0)

        if cp == "C":
            call_vol += vol
            call_oi += oi
            gex_today += oi * gamma * 100.0 * (spot ** 2) * 0.01
            vanna_today += oi * vega * (1.0 - abs(delta))
            if 4 <= dte <= 40 and strike >= spot * 0.98:
                call_strike_oi[strike] = call_strike_oi.get(strike, 0.0) + oi + vol * 2.0
            if spot * 1.002 <= strike <= spot * 1.12:
                otm_call_vol += vol
            if 11 <= dte <= 28 and 0.22 <= delta <= 0.70 and bid >= 0.10 and ask > 0:
                mid = 0.5 * (bid + ask)
                sprd_pct = (ask - bid) / mid * 100.0
                if sprd_pct <= 15.0 and (oi >= 50 or vol >= 20):
                    candidates.append({
                        "option": sym,
                        "exp": exp.isoformat(),
                        "dte": dte,
                        "strike": strike,
                        "bid": round(bid, 2),
                        "ask": round(ask, 2),
                        "mid": round(mid, 2),
                        "contract_cost_usd": round(mid * 100.0, 1),
                        "spread_pct": round(sprd_pct, 2),
                        "delta": round(delta, 2),
                        "iv_pct": round(iv * 100.0, 1),
                        "vol": int(vol),
                        "oi": int(oi),
                    })
        else:
            put_vol += vol
            put_oi += oi
            gex_today -= oi * gamma * 100.0 * (spot ** 2) * 0.01
            if 4 <= dte <= 40 and strike <= spot * 1.02:
                put_strike_oi[strike] = put_strike_oi.get(strike, 0.0) + oi + vol * 2.0

    if not candidates or hist_df.empty:
        return None

    call_wall = max(call_strike_oi.items(), key=lambda x: x[1])[0] if call_strike_oi else round(spot * 1.05, 1)
    put_wall = max(put_strike_oi.items(), key=lambda x: x[1])[0] if put_strike_oi else round(spot * 0.95, 1)

    cp_vol_ratio = call_vol / (put_vol + 10.0)
    last_row = hist_df.iloc[-1]
    prev3_row = hist_df.iloc[-3] if len(hist_df) >= 3 else last_row

    cp_vol_2d = (call_vol + float(last_row["call_vol"])) / (put_vol + float(last_row["put_vol"]) + 10.0)
    otm_med20 = float(hist_df["otm_call_vol"].tail(20).median())
    otm_vol_ratio = otm_call_vol / (otm_med20 + 5.0)

    wall_subiu_1d = call_wall >= float(last_row["call_wall"]) and call_wall > float(prev3_row["call_wall"])
    wall_subiu_3d = call_wall > float(prev3_row["call_wall"])
    put_wall_subiu_3d = put_wall >= float(prev3_row["put_wall"])

    call_wall_dist_pct = (call_wall / spot - 1.0) * 100.0
    put_wall_dist_pct = (spot / put_wall - 1.0) * 100.0

    iv30 = float(d.get("iv30") or 0.0) / 100.0
    iv_Use = iv30 if iv30 > 0.05 else float(last_row["iv_atm"])
    iv_min20 = min(float(hist_df["iv_atm"].tail(20).min()), iv_Use)
    iv_max20 = max(float(hist_df["iv_atm"].tail(20).max()), iv_Use)
    iv_rank_20d = (iv_Use - iv_min20) / (iv_max20 - iv_min20 + 1e-4) * 100.0

    max_5d_prev = float(hist_df["high"].tail(5).max())
    rompeu_max_5d = spot >= max_5d_prev * 0.998
    vanna_subindo_3d = True if cp_vol_ratio >= 1.5 else bool(last_row["vanna_subindo_3d"])
    gex_subindo_3d = gex_today > 0 or bool(last_row["gex_subindo_3d"])

    # Evaluate Top Approved US Rules
    near_pw = -0.5 <= put_wall_dist_pct <= 5.0
    cw_magnet = 1.5 <= call_wall_dist_pct <= 13.5
    fechou_65 = cir >= 0.65
    fechou_75 = cir >= 0.75

    rules_triggered = []
    if near_pw and cw_magnet and vanna_subindo_3d and fechou_65:
        rules_triggered.append(("US_R1_IMA_PUT_WALL_VANNA_TOPO", 88.9, "+18.98%", "ABERT_D1 / FIM_D0"))
    if wall_subiu_1d and put_wall_subiu_3d and cp_vol_2d >= 1.8 and rompeu_max_5d:
        rules_triggered.append(("US_R2_PAREDES_SUBINDO_FLUXO_BREAKOUT", 88.1, "+14.76%", "TIRO_RAPIDO_D3"))
    if near_pw and otm_vol_ratio >= 1.5 and vanna_subindo_3d and fechou_65:
        rules_triggered.append(("US_R3_PUT_WALL_OTM_SURGE_VANNA", 87.5, "+14.66%", "ABERT_D1 / FIM_D0"))
    if wall_subiu_3d and near_pw and iv_rank_20d <= 55.0 and fechou_65:
        rules_triggered.append(("US_R4_WALL_SUBIU_IV_BARATA_TOPO", 86.8, "+16.49%", "FIM_D0"))
    if wall_subiu_1d and cp_vol_ratio >= 2.0 and fechou_75:
        rules_triggered.append(("US_R5_WALL_SUBIU_FLUXO_2X_TOPO75", 85.5, "+12.46%", "ALTA_FREQ_EUA"))
    if near_pw and cw_magnet and cp_vol_ratio >= 2.2:
        rules_triggered.append(("US_R6_CORREDOR_GAMMA_FLUXO_FORTE", 83.8, "+11.20%", "TIRO_RAPIDO_D3"))

    if not rules_triggered:
        return None

    # Pick the 3 option profiles (CORE_ATM ~0.48, ITM_SEGURA ~0.60, OTM_ACESSIVEL ~0.30)
    core_c = min(candidates, key=lambda x: abs(x["delta"] - 0.48) + abs(x["dte"] - 18) * 0.015)
    itm_c = min(candidates, key=lambda x: abs(x["delta"] - 0.62) + abs(x["dte"] - 18) * 0.015)
    otm_c = min(candidates, key=lambda x: abs(x["delta"] - 0.30) + abs(x["dte"] - 18) * 0.015)

    best_wr = max(r[1] for r in rules_triggered)
    return {
        "ticker": ticker,
        "spot": round(spot, 2),
        "ret_1d_pct": round(ret_1d, 2),
        "close_in_range_pct": round(cir * 100.0, 1),
        "put_wall": put_wall,
        "call_wall": call_wall,
        "cp_vol_ratio": round(cp_vol_ratio, 2),
        "iv_rank_20d": round(iv_rank_20d, 1),
        "gex_millions": round(gex_today / 1e6, 1),
        "n_rules": len(rules_triggered),
        "best_wr": best_wr,
        "rules": [r[0] for r in rules_triggered],
        "stock_floor_d1": round(spot * 0.985, 2),
        "core_atm": core_c,
        "itm_segura": itm_c,
        "otm_acessivel": otm_c,
    }


def main():
    surv_p = OUT_DIR / "us_options_survivors_report.csv"
    if surv_p.exists():
        surv = pd.read_csv(surv_p)
        print("=== RESUMO DAS REGRAS DE TIRO RAPIDO D+1 A D+3 (EUA) ===")
        d3 = surv[surv["mode"].str.contains("D3")].reset_index(drop=True)
        for idx, r in d3.head(6).iterrows():
            print(
                f"  {idx+1}. [{r['mode']}] {r['rule']}\n"
                f"     n={r['n_trades']} ({r['n_tickers']} ativos) | WR={r['win_rate']:.1f}% "
                f"(OOS {r['wr_q3_oos']:.1f}% | 12 Virgens {r['wr_q4_virgins']:.1f}%) | "
                f"D+1={r['hit_20_d1_pct']:.1f}%, D+2={r['hit_20_d2_pct']:.1f}%, D+3={r['hit_20_d3_pct']:.1f}% | "
                f"EV={r['ev_net_pct']:+.2f}% | PF={r['profit_factor']:.2f}"
            )

    today = date.today()
    print(f"\n=== VARRENDO AS 36 ACOES/ETFS DOS EUA AO VIVO NA CBOE (HOJE {today:%d/%m/%Y}) ===")
    parquet_files = sorted(CACHE_DIR.glob("*_us_panel_v1.parquet"))
    if not parquet_files:
        parquet_files = sorted((ROOT / "cloud_cache" / "us_tail35").glob("*_us_panel_v1.parquet"))
    hist_map = {}
    for pf in parquet_files:
        tk = pf.name.split("_")[0]
        hist_map[tk] = pd.read_parquet(pf)

    signals = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(evaluate_ticker_today, tk, df_h, today): tk for tk, df_h in hist_map.items()}
        for f in as_completed(futs):
            res = f.result()
            if res is not None:
                signals.append(res)

    signals.sort(key=lambda x: (x["n_rules"], x["best_wr"], x["cp_vol_ratio"]), reverse=True)
    out_json = OUT_DIR / "ultimo_scan_us_options.json"
    out_json.write_text(json.dumps(signals, indent=2), encoding="utf-8")

    print(f"\nTotal de acoes americanas ativadas hoje ({today:%d/%m/%Y}): {len(signals)}\n")
    for idx, s in enumerate(signals, 1):
        c = s["core_atm"]
        o = s["otm_acessivel"]
        print(
            f"{idx:2d}. {s['ticker']:5s} (${s['spot']:7.2f}, {s['ret_1d_pct']:+5.2f}%, Topo {s['close_in_range_pct']:4.0f}%) | "
            f"PW ${s['put_wall']:g} -> CW ${s['call_wall']:g} | C/P Vol {s['cp_vol_ratio']:.2f}x | IV Rank {s['iv_rank_20d']:.0f}% | "
            f"WR Regra: {s['best_wr']:.1f}% ({', '.join(s['rules'])})\n"
            f"    -> [ATM Delta {c['delta']:.2f}] {c['option']} ({c['dte']}d, Strk ${c['strike']:g}) Bid/Ask ${c['bid']:.2f}/${c['ask']:.2f} | 1 Contrato = US$ {c['contract_cost_usd']:.0f} | Alvo +20%: ${c['mid']*1.20:.2f} | Alvo +40%: ${c['mid']*1.40:.2f}\n"
            f"    -> [OTM Barata Delta {o['delta']:.2f}] {o['option']} ({o['dte']}d, Strk ${o['strike']:g}) Bid/Ask ${o['bid']:.2f}/${o['ask']:.2f} | 1 Contrato = US$ {o['contract_cost_usd']:.0f} | Alvo +20%: ${o['mid']*1.20:.2f} | Alvo +40%: ${o['mid']*1.40:.2f}"
        )


if __name__ == "__main__":
    main()
