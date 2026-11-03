"""Scanner Operacional Diário — Tiro Rápido D+1 a D+3 (Alvo Mínimo +20% na CALL).

Opera as 45 ações líquidas da B3 divididas em 2 Mesas Independentes:
  - MESA 1 (FIM DO DIA D0 - 16h45 a 16h55): 8 Regras Campeãs (F1 a F8, 73,8% a 80,4% WR)
  - MESA 2 (ABERTURA / LEILÃO D+1 - 09h55 a 10h15): 12 Regras Campeãs (A1 a A12, 72,3% a 81,6% WR)

Uso:
    python scripts/scan_tiro_rapido_d3.py                  # baixa pregões recentes da B3 e escaneia o último pregão
    python scripts/scan_tiro_rapido_d3.py --sem-download   # usa apenas os arquivos já baixados em data/raw
    python scripts/scan_tiro_rapido_d3.py --data 2026-10-23
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import sqlite3
import sys
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from gamma_levels.b3 import B3Client, parse_option_reference  # noqa: E402
from scripts.mine_option_patterns import _bsm_call_price  # noqa: E402

LIQUID_45: list[str] = [
    "ABEV3", "ASAI3", "B3SA3", "BBAS3", "BBDC3", "BBDC4", "BBSE3", "BEEF3", "BRAP4",
    "BRAV3", "BRKM5", "CEAB3", "CMIG4", "CMIN3", "COGN3", "CSAN3", "CSNA3", "CXSE3",
    "CYRE3", "DIRR3", "EGIE3", "EQTL3", "GGBR4", "GOAU4", "HAPV3", "IRBR3", "ITSA4",
    "ITUB4", "LREN3", "MGLU3", "MRVE3", "PETR3", "PETR4", "PRIO3", "RADL3", "RENT3",
    "SBSP3", "SUZB3", "TOTS3", "USIM5", "VALE3", "VAMO3", "VBBR3", "VIVT3", "WEGE3",
]

SHARED_ROOT_PAIRS: dict[str, str] = {
    "PETR3": "PETR4",
    "PETR4": "PETR3",
    "BBDC3": "BBDC4",
    "BBDC4": "BBDC3",
}

RAW_CACHE_DIR = ROOT / "results" / "option_patterns" / "daily_raw_cache"
HIST_CACHE_DIR = ROOT / "results" / "option_patterns" / "cache_v2"


def next_business_days(base_iso: str, n: int = 3) -> list[str]:
    dt = datetime.strptime(base_iso, "%Y-%m-%d").date()
    out: list[str] = []
    cur = dt
    while len(out) < n:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            out.append(cur.isoformat())
    return out


def load_global_isin_map() -> dict[str, str]:
    """Carrega mapa global de ISIN das opções a partir dos bancos SQLite ou cloud_cache."""
    for isin_cache in [RAW_CACHE_DIR / "_isin_map.json", ROOT / "cloud_cache" / "_isin_map.json"]:
        if isin_cache.exists():
            try:
                return json.loads(isin_cache.read_text(encoding="utf-8"))
            except Exception:
                pass

    isin_map: dict[str, str] = {}
    for tk in ["petr4", "petr3", "bbdc4", "bbdc3", "itub4", "vale3", "bbas3", "prio3"]:
        db_p = ROOT / "data" / f"pilot_{tk}" / "gamma_levels.db"
        if db_p.exists():
            try:
                con = sqlite3.connect(f"file:{db_p}?mode=ro", uri=True)
                df = pd.read_sql_query(
                    "SELECT ticker, isin FROM instruments WHERE instrument_type='option' AND isin IS NOT NULL",
                    con,
                )
                con.close()
                isin_map.update(dict(zip(df["ticker"], df["isin"])))
            except Exception:
                pass
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    isin_cache.write_text(json.dumps(isin_map), encoding="utf-8")
    return isin_map


def download_recent_b3_sessions(data_dir: Path, lookback_days: int = 10) -> list[str]:
    """Baixa automaticamente os pregões recentes disponíveis na B3 que ainda não estão em data/raw."""
    raw_root = data_dir / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    today = date.today()
    downloaded: list[str] = []

    with B3Client(data_dir) as client:
        for offset in range(lookback_days, -1, -1):
            cand = today - timedelta(days=offset)
            if cand.weekday() >= 5:
                continue
            d_iso = cand.isoformat()
            d_short = cand.strftime("%y%m%d")
            day_dir = raw_root / d_iso
            pr_file = day_dir / f"PR{d_short}.zip"
            pe_file = day_dir / f"PE{d_short}.ex_"
            if pr_file.exists() and pe_file.exists():
                continue
            try:
                if not client.is_available(cand):
                    continue
                print(f"  [B3] Baixando pregão {cand:%d/%m/%Y} ({d_iso})...", flush=True)
                client.load_session(cand, include_instruments=False)
                if pr_file.exists() and pe_file.exists():
                    downloaded.append(d_iso)
            except Exception:
                continue
    return downloaded


def _pick_profile_call(calls_df: pd.DataFrame, spot: float, min_d: float, max_d: float, target_d: float, label: str) -> dict[str, Any] | None:
    sub = calls_df.loc[
        calls_df["dte"].between(10, 48)
        & (calls_df["mkt_price"] >= 0.10)
        & ((calls_df["financial_volume"] >= 5_000) | (calls_df["trades"] >= 3))
        & calls_df["delta"].between(min_d, max_d)
    ].copy()
    if sub.empty:
        return None
    is_monthly = (~sub["ticker"].str.contains("W", regex=False)).astype(float)
    sub["liq_rank"] = sub["financial_volume"].fillna(0).rank(pct=True) * 0.6 + sub["trades"].fillna(0).rank(pct=True) * 0.4
    sub["delta_pref"] = 1.0 - (sub["delta"] - target_d).abs() / 0.25
    sub["score"] = 0.60 * sub["liq_rank"] + 0.32 * sub["delta_pref"] + 0.08 * is_monthly
    best = sub.sort_values(["score", "financial_volume"], ascending=False).iloc[0]

    close_px = float(best["close"]) if pd.notna(best["close"]) and best["close"] > 0 else float(best["mkt_price"])
    ref_px = float(best["reference_price"]) if pd.notna(best["reference_price"]) and best["reference_price"] > 0 else close_px
    bid_px = float(best["bid"]) if pd.notna(best["bid"]) and best["bid"] > 0 else 0.0
    ask_px = float(best["ask"]) if pd.notna(best["ask"]) and best["ask"] > 0 else 0.0
    base_px = close_px if close_px > 0 else ref_px

    return {
        "profile": label,
        "ticker": str(best["ticker"]),
        "strike": round(float(best["strike"]), 2),
        "expiration": str(best["expiration"])[:10],
        "dte": int(best["dte"]),
        "delta": round(float(best["delta"]), 2),
        "gamma": round(float(best["gamma"]), 4),
        "iv_pct": round(float(best["iv"]) * 100.0, 1),
        "close": round(close_px, 2),
        "ref": round(ref_px, 2),
        "bid": round(bid_px, 2),
        "ask": round(ask_px, 2),
        "trades": int(best["trades"] or 0),
        "volume": round(float(best["financial_volume"] or 0.0), 2),
        "open_interest": int(best["open_interest"] or 0),
        "auction_ideal_min": round(max(0.01, base_px * 0.94), 2),
        "auction_ideal_max": round(base_px * 1.05, 2),
        "auction_max_limit": round(max(base_px, ref_px) * 1.15, 2),
        "target_20": round(base_px * 1.20, 2),
        "target_40": round(base_px * 1.40, 2),
    }


def parse_raw_day_45(trade_date: str, isin_map: dict[str, str]) -> pd.DataFrame | None:
    """Extrai em 1 única passagem todas as 45 ações líquidas e suas cadeias de opções do arquivo B3 de `trade_date`."""
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = RAW_CACHE_DIR / f"{trade_date}_v2.parquet"
    if cache_file.exists():
        try:
            return pd.read_parquet(cache_file)
        except Exception:
            pass

    d_short = trade_date.replace("-", "")[2:]
    day_dir = ROOT / "data" / "raw" / trade_date
    pr_path = day_dir / f"PR{d_short}.zip"
    pe_path = day_dir / f"PE{d_short}.ex_"
    if not (pr_path.exists() and pe_path.exists()):
        return None

    t0 = time.time()
    roots = {tk[:4] for tk in LIQUID_45}
    pe_df = parse_option_reference(pe_path.read_bytes(), roots)
    if pe_df.empty:
        return None

    block_pat = re.compile(rb"<PricRpt>(.*?)</PricRpt>", re.DOTALL)
    sym_pat = re.compile(rb"<TckrSymb>([A-Z0-9]+)</TckrSymb>")
    tag_pat = re.compile(rb"<(\w+)[^>]*>([^<]+)</\1>")

    outer = zipfile.ZipFile(pr_path)
    inner_name = sorted([n for n in outer.namelist() if n.lower().endswith(".zip")])[-1]
    inner = zipfile.ZipFile(io.BytesIO(outer.read(inner_name)))
    xml_name = sorted([n for n in inner.namelist() if n.lower().endswith(".xml")])[-1]
    blob = inner.read(xml_name)

    pr_rows: list[dict[str, Any]] = []
    for m in block_pat.finditer(blob):
        block = m.group(1)
        sm = sym_pat.search(block)
        if not sm:
            continue
        tck = sm.group(1).decode()
        if len(tck) < 4 or tck[:4] not in roots:
            continue
        vals = {k.decode(): v.decode() for k, v in tag_pat.findall(block)}
        pr_rows.append(
            {
                "ticker": tck,
                "open": float(vals.get("FrstPric", 0) or 0),
                "high": float(vals.get("MaxPric", 0) or 0),
                "low": float(vals.get("MinPric", 0) or 0),
                "close": float(vals.get("LastPric", 0) or 0),
                "bid": float(vals.get("BestBidPric", 0) or 0),
                "ask": float(vals.get("BestAskPric", 0) or 0),
                "trades": float(vals.get("RglrTxsQty", 0) or 0),
                "contracts": float(vals.get("FinInstrmQty", 0) or 0),
                "financial_volume": float(vals.get("NtlFinVol", 0) or 0),
                "open_interest": float(vals.get("OpnIntrst", 0) or 0),
            }
        )
    if not pr_rows:
        return None

    pr_df = pd.DataFrame(pr_rows).drop_duplicates("ticker")
    eq_df = pr_df.loc[pr_df["ticker"].isin(LIQUID_45)].copy()
    spot_map = dict(zip(eq_df["ticker"], eq_df["close"]))

    opts = pe_df.merge(pr_df, on="ticker", how="left")
    for col in ["open", "high", "low", "close", "bid", "ask", "trades", "contracts", "financial_volume", "open_interest", "reference_price", "implied_volatility", "strike"]:
        if col in opts.columns:
            opts[col] = pd.to_numeric(opts[col], errors="coerce")

    opts["mkt_price"] = opts["reference_price"].where(opts["reference_price"] > 0, opts["close"])
    opts["dte"] = (pd.to_datetime(opts["expiration"]) - pd.to_datetime(trade_date)).dt.days
    opts = opts.loc[opts["dte"].between(1, 120) & (opts["strike"] > 0)].copy()
    opts["root"] = opts["ticker"].str[:4]
    opts["isin"] = opts["ticker"].map(isin_map)

    day_records: list[dict[str, Any]] = []
    for ticker in LIQUID_45:
        eq_row = eq_df.loc[eq_df["ticker"] == ticker]
        if eq_row.empty:
            continue
        r0 = eq_row.iloc[0]
        spot = float(r0["close"])
        if spot <= 0:
            continue

        root = ticker[:4]
        tk_opts = opts.loc[opts["root"] == root].copy()
        if tk_opts.empty:
            continue

        expected_prefix = f"BR{ticker}"
        tk_opts = tk_opts.loc[~(tk_opts["isin"].notna() & ~tk_opts["isin"].str.startswith(expected_prefix))].copy()

        other_tk = SHARED_ROOT_PAIRS.get(ticker)
        other_spot = spot_map.get(other_tk, 0.0) if other_tk else 0.0
        if other_spot > 0 and abs(spot - other_spot) / spot > 0.02:
            valid_bsm = (tk_opts["mkt_price"] > 0) & (tk_opts["implied_volatility"] > 0)
            if valid_bsm.any():
                sub = tk_opts.loc[valid_bsm]
                iv_s = np.where(sub["implied_volatility"] > 3.0, sub["implied_volatility"] / 100.0, sub["implied_volatility"])
                t_yr = sub["dte"] / 365.0
                is_c = sub["option_type"] == "call"
                c_main = _bsm_call_price(np.full(len(sub), spot), sub["strike"].to_numpy(), t_yr.to_numpy(), iv_s)
                p_main = c_main - spot + sub["strike"].to_numpy() * np.exp(-0.13 * t_yr.to_numpy())
                theo_main = np.where(is_c, c_main, np.maximum(p_main, 0.0))

                c_oth = _bsm_call_price(np.full(len(sub), other_spot), sub["strike"].to_numpy(), t_yr.to_numpy(), iv_s)
                p_oth = c_oth - other_spot + sub["strike"].to_numpy() * np.exp(-0.13 * t_yr.to_numpy())
                theo_oth = np.where(is_c, c_oth, np.maximum(p_oth, 0.0))

                err_main = np.abs(theo_main - sub["mkt_price"].to_numpy())
                err_oth = np.abs(theo_oth - sub["mkt_price"].to_numpy())
                belongs_other = (err_oth + 0.15 < err_main) & (err_main > 0.35)
                tk_opts = tk_opts.drop(index=sub.index[belongs_other])

        is_call_pre = tk_opts["option_type"] == "call"
        intrinsic_call = np.maximum(spot - tk_opts["strike"] * np.exp(-0.13 * tk_opts["dte"] / 365.0), 0.0)
        violates = is_call_pre & (tk_opts["mkt_price"] > 0) & (tk_opts["mkt_price"] < intrinsic_call * 0.82 - 0.15)
        tk_opts = tk_opts.loc[~violates].copy()

        tk_opts = tk_opts.loc[tk_opts["dte"].between(5, 65)].copy()
        if tk_opts.empty:
            continue

        tk_opts["iv"] = np.where(
            tk_opts["implied_volatility"] > 3.0,
            tk_opts["implied_volatility"] / 100.0,
            tk_opts["implied_volatility"],
        ).clip(0.05, 2.50)
        tk_opts["iv"] = tk_opts["iv"].fillna(0.35)

        strike_arr = tk_opts["strike"].to_numpy(float)
        t_arr = np.maximum((tk_opts["dte"] / 365.0).to_numpy(float), 1.0 / 365.0)
        vol_arr = tk_opts["iv"].to_numpy(float)
        sqrt_t = np.sqrt(t_arr)
        d1 = (np.log(max(spot, 1e-4) / np.maximum(strike_arr, 1e-4)) + (0.13 + 0.5 * vol_arr ** 2) * t_arr) / (vol_arr * sqrt_t)
        d2 = d1 - vol_arr * sqrt_t
        pdf_d1 = np.exp(-0.5 * d1 * d1) / np.sqrt(2.0 * np.pi)
        cdf_d1 = 0.5 * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (d1 + 0.044715 * np.power(d1, 3))))

        is_c_np = (tk_opts["option_type"] == "call").to_numpy(bool)
        tk_opts["delta"] = np.where(is_c_np, cdf_d1, cdf_d1 - 1.0)
        tk_opts["gamma"] = pdf_d1 / (spot * vol_arr * sqrt_t)

        oi_np = tk_opts["open_interest"].fillna(0.0).to_numpy(float)
        sign_np = np.where(is_c_np, 1.0, -1.0)
        tk_opts["gex"] = tk_opts["gamma"].to_numpy() * oi_np * 100.0 * (spot ** 2) * 0.01 * sign_np
        tk_opts["vanna_oi"] = -pdf_d1 * (d2 / vol_arr) * oi_np * sign_np
        tk_opts["charm_oi"] = -pdf_d1 * ((2.0 * 0.13 * t_arr - d2 * vol_arr * sqrt_t) / (2.0 * t_arr * vol_arr * sqrt_t)) * oi_np * sign_np

        calls = tk_opts.loc[tk_opts["option_type"] == "call"]
        puts = tk_opts.loc[tk_opts["option_type"] == "put"]
        if calls.empty:
            continue

        call_vol = float(calls["financial_volume"].fillna(0).sum())
        put_vol = float(puts["financial_volume"].fillna(0).sum())
        call_trades = float(calls["trades"].fillna(0).sum())
        put_trades = float(puts["trades"].fillna(0).sum())
        call_oi = float(calls["open_interest"].fillna(0).sum())
        put_oi = float(puts["open_interest"].fillna(0).sum())

        call_avg_ticket = call_vol / call_trades if call_trades > 0 else 0.0
        put_avg_ticket = put_vol / put_trades if put_trades > 0 else 0.0
        cp_ticket_ratio = call_avg_ticket / put_avg_ticket if put_avg_ticket > 0 else 1.0

        otm_calls = calls.loc[calls["strike"].between(spot * 1.005, spot * 1.10)]
        otm_call_vol = float(otm_calls["financial_volume"].fillna(0).sum())
        otm_call_trades = float(otm_calls["trades"].fillna(0).sum())
        otm_avg_ticket = otm_call_vol / otm_call_trades if otm_call_trades > 0 else 0.0
        otm_call_oi = float(otm_calls["open_interest"].fillna(0).sum())

        calls_above = calls.loc[calls["strike"] >= spot * 0.98]
        if not calls_above.empty and calls_above["open_interest"].fillna(0).sum() > 0:
            wall_by_strike = calls_above.groupby("strike").agg(
                oi=("open_interest", "sum"),
                vol=("financial_volume", "sum"),
            )
            call_wall_strike = float(wall_by_strike["oi"].idxmax())
            call_wall_oi = float(wall_by_strike.loc[call_wall_strike, "oi"])
            vol_wall_strike = float(wall_by_strike["vol"].idxmax()) if wall_by_strike["vol"].sum() > 0 else call_wall_strike
        else:
            call_wall_strike = spot * 1.05
            call_wall_oi = 0.0
            vol_wall_strike = spot * 1.02

        wall_concentration = call_wall_oi / call_oi if call_oi > 0 else 0.0

        puts_below = puts.loc[puts["strike"] <= spot * 1.02]
        if not puts_below.empty and puts_below["open_interest"].fillna(0).sum() > 0:
            put_wall_strike = float(puts_below.groupby("strike")["open_interest"].sum().idxmax())
        else:
            put_wall_strike = spot * 0.95

        vwap_call_strike = float(np.average(calls["strike"], weights=calls["financial_volume"].fillna(0))) if call_vol > 0 else spot

        gex_net = float(tk_opts["gex"].sum())
        gex_call = float(calls["gex"].sum())
        gex_put = float(puts["gex"].abs().sum())
        gex_imbalance = (gex_call - gex_put) / max(gex_call + gex_put, 1.0)
        vanna_net = float(tk_opts["vanna_oi"].sum())
        charm_net = float(tk_opts["charm_oi"].sum())

        atm_calls = calls.loc[calls["delta"].between(0.35, 0.65) & (calls["iv"] > 0.05)]
        atm_iv = float(atm_calls["iv"].median()) if not atm_calls.empty else np.nan
        iv_short = float(calls.loc[calls["dte"].between(8, 24) & calls["delta"].between(0.30, 0.70) & (calls["iv"] > 0.05), "iv"].median())
        iv_mid = float(calls.loc[calls["dte"].between(25, 60) & calls["delta"].between(0.30, 0.70) & (calls["iv"] > 0.05), "iv"].median())
        iv_term_slope = (iv_short - iv_mid) if pd.notna(iv_short) and pd.notna(iv_mid) else 0.0

        # 3 Perfis de CALL para o Painel Visual (ATM Principal, ITM Segura e OTM Explosiva)
        core_opt = _pick_profile_call(calls, spot, 0.35, 0.72, 0.52, "CORE_ATM (Recomendada - Delta ~0.52)")
        itm_opt = _pick_profile_call(calls, spot, 0.55, 0.78, 0.63, "ITM_SEGURA (Maior Assertividade - Delta ~0.63)")
        otm_opt = _pick_profile_call(calls, spot, 0.28, 0.46, 0.38, "OTM_EXPLOSIVA (Maior Alavancagem - Delta ~0.38)")

        candidates_list: list[dict[str, Any]] = []
        seen_tcks: set[str] = set()
        for c_opt in [core_opt, itm_opt, otm_opt]:
            if c_opt and c_opt["ticker"] not in seen_tcks:
                seen_tcks.add(c_opt["ticker"])
                candidates_list.append(c_opt)

        sel_ticker = core_opt["ticker"] if core_opt else None
        sel_strike = core_opt["strike"] if core_opt else np.nan
        sel_exp = core_opt["expiration"] if core_opt else None
        sel_dte = float(core_opt["dte"]) if core_opt else np.nan
        sel_close = core_opt["close"] if core_opt else np.nan
        sel_ref = core_opt["ref"] if core_opt else np.nan
        sel_bid = core_opt["bid"] if core_opt else np.nan
        sel_ask = core_opt["ask"] if core_opt else np.nan
        sel_delta = core_opt["delta"] if core_opt else np.nan
        sel_iv = (core_opt["iv_pct"] / 100.0) if core_opt else np.nan
        sel_trades = float(core_opt["trades"]) if core_opt else 0.0
        sel_vol = float(core_opt["volume"]) if core_opt else 0.0

        req_move_for_30pct = np.nan
        if core_opt:
            p = max(core_opt["close"], core_opt["ref"], 0.10)
            dl = max(core_opt["delta"], 0.05)
            gm = max(core_opt["gamma"], 1e-6)
            dc30 = p * 0.30
            a_c = 0.5 * gm
            req_move_for_30pct = ((-dl + math.sqrt(max(dl ** 2 + 4 * a_c * dc30, 0.0))) / (2 * a_c)) / spot

        day_records.append(
            {
                "ticker": ticker,
                "trade_date": trade_date,
                "spot": spot,
                "stock_open": float(r0["open"]),
                "stock_high": float(r0["high"]),
                "stock_low": float(r0["low"]),
                "stock_vol": float(r0["financial_volume"]),
                "call_vol": call_vol,
                "put_vol": put_vol,
                "otm_call_vol": otm_call_vol,
                "call_trades": call_trades,
                "put_trades": put_trades,
                "otm_call_trades": otm_call_trades,
                "call_avg_ticket": call_avg_ticket,
                "put_avg_ticket": put_avg_ticket,
                "cp_ticket_ratio": cp_ticket_ratio,
                "otm_avg_ticket": otm_avg_ticket,
                "call_oi": call_oi,
                "put_oi": put_oi,
                "otm_call_oi": otm_call_oi,
                "call_wall_strike": call_wall_strike,
                "call_wall_oi": call_wall_oi,
                "wall_concentration": wall_concentration,
                "vol_wall_strike": vol_wall_strike,
                "put_wall_strike": put_wall_strike,
                "vwap_call_strike": vwap_call_strike,
                "gex_net": gex_net,
                "gex_imbalance": gex_imbalance,
                "vanna_net": vanna_net,
                "charm_net": charm_net,
                "atm_iv": atm_iv,
                "iv_term_slope": iv_term_slope,
                "req_move_for_30pct": req_move_for_30pct,
                "sel_opt_ticker": sel_ticker,
                "sel_opt_strike": sel_strike,
                "sel_opt_exp": sel_exp,
                "sel_opt_dte": sel_dte,
                "sel_opt_close": sel_close,
                "sel_opt_ref": sel_ref,
                "sel_opt_bid": sel_bid,
                "sel_opt_ask": sel_ask,
                "sel_opt_delta": sel_delta,
                "sel_opt_iv": sel_iv,
                "sel_opt_trades": sel_trades,
                "sel_opt_vol": sel_vol,
                "candidates_json": json.dumps(candidates_list, ensure_ascii=False),
            }
        )

    out_df = pd.DataFrame(day_records)
    if not out_df.empty:
        out_df.to_parquet(cache_file, index=False)
        print(f"  [Cache] Pregão {trade_date} processado ({len(out_df)} ativos líquidos em {time.time() - t0:.1f}s).")
    return out_df


def build_live_panel(target_date: str | None = None) -> tuple[pd.DataFrame, str, list[str]]:
    """Constrói o painel atualizado das 45 ações líquidas combinando a base histórica v2 com os pregões recentes de data/raw."""
    isin_map = load_global_isin_map()
    raw_root = ROOT / "data" / "raw"
    raw_dates = sorted([p.name for p in raw_root.iterdir() if p.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", p.name)])
    recent_raw_dates = [d for d in raw_dates if d >= "2026-07-29"]

    raw_frames: list[pd.DataFrame] = []
    for d in recent_raw_dates:
        if target_date and d > target_date:
            continue
        df_d = parse_raw_day_45(d, isin_map)
        if df_d is not None and not df_d.empty:
            raw_frames.append(df_d)

    raw_all = pd.concat(raw_frames, ignore_index=True) if raw_frames else pd.DataFrame()

    all_ticker_dfs: list[dict[str, Any]] = []
    cloud_hist_dir = ROOT / "cloud_cache" / "b3_tail35"
    for ticker in LIQUID_45:
        hist_p = HIST_CACHE_DIR / f"{ticker}.parquet"
        if not hist_p.exists():
            hist_p = cloud_hist_dir / f"{ticker}.parquet"
        if not hist_p.exists():
            continue
        h_df = pd.read_parquet(hist_p).tail(25).copy()
        if target_date:
            h_df = h_df.loc[h_df["trade_date"] <= target_date].copy()

        if not raw_all.empty:
            r_tk = raw_all.loc[raw_all["ticker"] == ticker].copy()
            if not r_tk.empty:
                r_tk = r_tk.loc[~r_tk["trade_date"].isin(set(h_df["trade_date"]))].copy()
                if not r_tk.empty:
                    comb = pd.concat([h_df, r_tk], ignore_index=True).sort_values("trade_date").reset_index(drop=True)
                    last_raw = r_tk.sort_values("trade_date").iloc[-1]
                    for col_opt in [
                        "sel_opt_ticker", "sel_opt_strike", "sel_opt_exp", "sel_opt_dte",
                        "sel_opt_close", "sel_opt_ref", "sel_opt_bid", "sel_opt_ask",
                        "sel_opt_delta", "sel_opt_iv", "sel_opt_trades", "sel_opt_vol", "candidates_json",
                    ]:
                        if col_opt in last_raw:
                            comb.loc[comb["trade_date"] == last_raw["trade_date"], col_opt] = last_raw[col_opt]
                else:
                    comb = h_df.sort_values("trade_date").reset_index(drop=True)
            else:
                comb = h_df.sort_values("trade_date").reset_index(drop=True)
        else:
            comb = h_df.sort_values("trade_date").reset_index(drop=True)

        if len(comb) < 10:
            continue

        comb["ret_1d"] = comb["spot"].pct_change(1)
        comb["ret_3d"] = comb["spot"].pct_change(3)
        comb["ret_5d"] = comb["spot"].pct_change(5)
        comb["hv20"] = comb["ret_1d"].rolling(20, min_periods=10).std() * math.sqrt(252)

        rng = (comb["stock_high"] - comb["stock_low"]).replace(0, np.nan)
        comb["close_in_range"] = ((comb["spot"] - comb["stock_low"]) / rng).fillna(0.5)
        comb["break_high_5d"] = comb["spot"] > comb["stock_high"].shift(1).rolling(5, min_periods=3).max()

        comb["call_vol_med20"] = comb["call_vol"].rolling(20, min_periods=8).median().replace(0, np.nan)
        comb["call_vol_ratio"] = comb["call_vol"] / comb["call_vol_med20"]

        comb["otm_call_vol_med20"] = comb["otm_call_vol"].rolling(20, min_periods=8).median().replace(0, np.nan)
        comb["otm_call_vol_ratio"] = comb["otm_call_vol"] / comb["otm_call_vol_med20"]

        comb["call_trades_med20"] = comb["call_trades"].rolling(20, min_periods=8).median().replace(0, np.nan)
        comb["call_trades_ratio"] = comb["call_trades"] / comb["call_trades_med20"]

        comb["call_ticket_med20"] = comb["call_avg_ticket"].rolling(20, min_periods=8).median().replace(0, np.nan)
        comb["call_ticket_ratio"] = comb["call_avg_ticket"] / comb["call_ticket_med20"]

        comb["call_put_vol_ratio"] = comb["call_vol"] / (comb["put_vol"] + 1_000.0)
        comb["call_put_vol_2d_min"] = np.minimum(comb["call_put_vol_ratio"], comb["call_put_vol_ratio"].shift(1))
        comb["call_put_oi_ratio"] = comb["call_oi"] / (comb["put_oi"] + 100.0)

        comb["call_wall_dist_pct"] = comb["call_wall_strike"] / comb["spot"] - 1.0
        comb["vol_wall_dist_pct"] = comb["vol_wall_strike"] / comb["spot"] - 1.0
        comb["put_wall_dist_pct"] = comb["spot"] / comb["put_wall_strike"] - 1.0

        comb["call_wall_change_1d"] = comb["call_wall_strike"].pct_change(1)
        comb["call_wall_change_3d"] = comb["call_wall_strike"].pct_change(3)
        comb["put_wall_change_3d"] = comb["put_wall_strike"].pct_change(3)
        comb["vol_wall_change_1d"] = comb["vol_wall_strike"].pct_change(1)

        calc_total_doi_pct = comb["call_oi"].diff(1) / (comb["call_oi"].shift(1) + 100.0)
        if "total_call_doi_pct" in comb.columns:
            comb["total_call_doi_pct"] = comb["total_call_doi_pct"].fillna(calc_total_doi_pct)
        else:
            comb["total_call_doi_pct"] = calc_total_doi_pct

        if "otm_call_oi" in comb.columns:
            calc_otm_doi_pct = comb["otm_call_oi"].diff(1) / (comb["call_oi"].shift(1) + 100.0)
        else:
            calc_otm_doi_pct = calc_total_doi_pct * 0.5
        if "otm_doi_pct" in comb.columns:
            comb["otm_doi_pct"] = comb["otm_doi_pct"].fillna(calc_otm_doi_pct)
        else:
            comb["otm_doi_pct"] = calc_otm_doi_pct

        calc_wall_unwind = comb["call_wall_oi"].diff(1) / (comb["call_wall_oi"].shift(1) + 100.0)
        if "wall_unwind_pct" in comb.columns:
            comb["wall_unwind_pct"] = comb["wall_unwind_pct"].fillna(calc_wall_unwind)
        else:
            comb["wall_unwind_pct"] = calc_wall_unwind

        comb["gex_rising_3d"] = comb["gex_net"] > comb["gex_net"].shift(3)
        comb["vanna_rising_3d"] = comb["vanna_net"] > comb["vanna_net"].shift(3)

        comb["iv_vs_hv20"] = comb["atm_iv"] / comb["hv20"].replace(0, np.nan)
        iv_min20 = comb["atm_iv"].rolling(20, min_periods=8).min()
        iv_max20 = comb["atm_iv"].rolling(20, min_periods=8).max()
        comb["iv_rank_20d"] = ((comb["atm_iv"] - iv_min20) / (iv_max20 - iv_min20).replace(0, np.nan)).fillna(0.5)

        expected_5d_move = (comb["hv20"] * math.sqrt(5.0 / 252.0)).clip(lower=0.015)
        comb["convexity_ratio_30"] = comb["req_move_for_30pct"] / expected_5d_move

        all_ticker_dfs.append(comb)

    full_panel = pd.concat(all_ticker_dfs, ignore_index=True)
    avail_dates = sorted(full_panel["trade_date"].unique().tolist())
    eval_date = target_date if target_date else str(full_panel["trade_date"].max())
    day_slice = full_panel.loc[full_panel["trade_date"] == eval_date].sort_values("ticker").reset_index(drop=True)
    return day_slice, eval_date, avail_dates[-20:]


def _build_reasons_pt(row: pd.Series) -> list[str]:
    """Gera explicações claras em português com os números exatos do ativo no dia."""
    reasons: list[str] = []
    pw_dist = float(row.get("put_wall_dist_pct") or 0.0) * 100.0
    if -0.5 <= pw_dist <= 3.5:
        reasons.append(f"Apoiada no piso da Put Wall (R$ {row['put_wall_strike']:.2f}, distância de apenas {pw_dist:+.1f}%)")
    if float(row.get("put_wall_change_3d") or 0.0) >= 0.01:
        reasons.append(f"Piso institucional (Put Wall) subiu +{float(row['put_wall_change_3d'])*100:.1f}% nos últimos 3 pregões")
    if float(row.get("call_put_vol_ratio") or 0.0) >= 2.5:
        reasons.append(f"Fluxo comprador dominante: Volume em Calls foi {row['call_put_vol_ratio']:.1f}x maior que em Puts hoje")
    if float(row.get("call_put_vol_2d_min") or 0.0) >= 2.5:
        reasons.append(f"Acumulação contínua: Calls >= {row['call_put_vol_2d_min']:.1f}x Puts por 2 pregões seguidos")
    if float(row.get("call_trades_ratio") or 0.0) >= 1.8:
        reasons.append(f"Explosão de negócios em Calls: {row['call_trades_ratio']:.1f}x a mediana de 20 dias ({row['call_trades']:.0f} negócios)")
    if float(row.get("cp_ticket_ratio") or 0.0) >= 1.5:
        reasons.append(f"Tubarão nas Calls: Ticket médio por negócio em Calls foi {row['cp_ticket_ratio']:.1f}x maior que nas Puts")
    if float(row.get("total_call_doi_pct") or 0.0) >= 0.01:
        reasons.append(f"Abertura líquida de posição (Open Interest de Calls subiu +{float(row['total_call_doi_pct'])*100:.1f}% no dia)")
    if float(row.get("otm_doi_pct") or 0.0) >= 0.01:
        reasons.append(f"Entrada de dinheiro novo em Calls OTM (+{float(row['otm_doi_pct'])*100:.1f}% de aumento em OI OTM)")
    if float(row.get("wall_unwind_pct") or 0.0) <= -0.03:
        reasons.append(f"Destravamento de teto: Call Wall teve desmonte de {float(row['wall_unwind_pct'])*100:.1f}% no Open Interest")
    if bool(row.get("gex_rising_3d")):
        reasons.append("Gamma Exposure (GEX) líquido subindo nos últimos 3 pregões")
    if bool(row.get("vanna_rising_3d")):
        reasons.append("Vanna líquido positivo/subindo em 3 dias (empurrão de compra dos dealers)")
    if float(row.get("convexity_ratio_30") or 9.0) <= 0.55:
        reasons.append(f"Ultra Convexidade ({row['convexity_ratio_30']:.2f}x): opção precisa de pouco movimento da ação para pagar +20%/+30%")
    return reasons


def evaluate_mesas(day_df: pd.DataFrame, eval_date: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Avalia as 8 Regras da Mesa 1 (FIM DO DIA D0) e as 12 Regras da Mesa 2 (ABERTURA / LEILÃO D+1)."""
    next_days = next_business_days(eval_date, 4)
    d1_date, d2_date, d3_date, d4_date = next_days[0], next_days[1], next_days[2], next_days[3]

    mesa1_fim_d0_rules = [
        (
            "F1",
            "PUT_WALL_SUBIU_3D + CALL_VOL_2.5X + TUBARAO_CP_TICKET_1.5X + VANNA_SUBINDO_3D",
            "Piso Subiu 3d + Volume Calls 2,5x + Ticket Tubarão 1,5x + Vanna Subindo",
            80.4, 78.4, 45.4, 68.0, 1.87, 11.24, 2.72,
            lambda r: (r["put_wall_change_3d"] >= 0.01) and (r["call_vol_ratio"] >= 2.5) and (r["cp_ticket_ratio"] >= 1.5) and bool(r["vanna_rising_3d"]),
        ),
        (
            "F2",
            "LIQ_250K + WALL_UNWIND_3PCT + DOI_CALL_FORTE + ACAO_POS_HOJE",
            "Desmonte da Call Wall (-3%) + Abertura Forte de OI (+2,5%) + Ação Positiva",
            79.2, 79.2, 58.5, 66.0, 1.75, 8.48, 2.19,
            lambda r: (r["call_vol_med20"] >= 250_000) and (r["wall_unwind_pct"] <= -0.03) and (r["total_call_doi_pct"] >= 0.025) and (r["ret_1d"] >= 0.0001),
        ),
        (
            "F3",
            "LIQ_250K + PUT_WALL_SUBIU_3D + CALL_VOL_3.5X + TUBARAO_CP_TICKET_1.5X",
            "Piso Subiu 3d + Explosão Volume Calls 3,5x + Ticket Tubarão 1,5x",
            78.8, 78.8, 47.0, 71.2, 1.82, 9.99, 2.32,
            lambda r: (r["call_vol_med20"] >= 250_000) and (r["put_wall_change_3d"] >= 0.01) and (r["call_vol_ratio"] >= 3.5) and (r["cp_ticket_ratio"] >= 1.5),
        ),
        (
            "F4",
            "WALL_CONC_25PCT + VANNA_SUBINDO_3D + FECHOU_TOPO_80 + ROMPEU_MAX_5D",
            "Parede Concentrada (25%) + Vanna Subindo + Fechou no Topo + Rompeu Máx 5d",
            78.8, 72.5, 50.0, 63.7, 1.86, 7.73, 1.83,
            lambda r: (r["wall_concentration"] >= 0.25) and bool(r["vanna_rising_3d"]) and (r["close_in_range"] >= 0.80) and bool(r["break_high_5d"]),
        ),
        (
            "F5",
            "LIQ_250K + PUT_WALL_SUBIU_3D + CP_VOL_5.0X + DOI_CALL_FORTE",
            "Piso Subiu 3d + Volume Calls 5x Puts + Abertura Forte de OI",
            78.7, 76.0, 41.3, 64.0, 1.95, 10.45, 2.35,
            lambda r: (r["call_vol_med20"] >= 250_000) and (r["put_wall_change_3d"] >= 0.01) and (r["call_put_vol_ratio"] >= 5.0) and (r["total_call_doi_pct"] >= 0.025),
        ),
        (
            "F6",
            "PUT_WALL_SUBIU_3D + CALL_TRADES_2.5X + GEX_SUBINDO_3D + CONVEX_050",
            "Piso Subiu 3d + Negócios Calls 2,5x + GEX Subindo + Ultra Convexidade",
            77.2, 76.4, 60.2, 70.7, 1.69, 9.44, 2.15,
            lambda r: (r["put_wall_change_3d"] >= 0.01) and (r["call_trades_ratio"] >= 2.5) and bool(r["gex_rising_3d"]) and (r["convexity_ratio_30"] <= 0.50),
        ),
        (
            "F7",
            "PUT_WALL_SUBIU_3D + CP_VOL_2.5X + DOI_CALL_FORTE + VANNA_SUBINDO_3D",
            "Piso Subiu 3d + Volume Calls 2,5x Puts + Abertura Forte OI + Vanna Subindo",
            77.0, 75.0, 45.3, 64.2, 1.91, 8.96, 2.14,
            lambda r: (r["put_wall_change_3d"] >= 0.01) and (r["call_put_vol_ratio"] >= 2.5) and (r["total_call_doi_pct"] >= 0.025) and bool(r["vanna_rising_3d"]),
        ),
        (
            "F8",
            "LIQ_250K + CALL_TRADES_2.5X + DOI_OTM_POS + CONVEX_050",
            "Giro Diário: Negócios Calls 2,5x + Abertura OI OTM + Ultra Convexidade",
            73.8, 71.3, 51.1, 63.7, 1.86, 6.06, 1.58,
            lambda r: (r["call_vol_med20"] >= 250_000) and (r["call_trades_ratio"] >= 2.5) and (r["otm_doi_pct"] >= 0.01) and (r["convexity_ratio_30"] <= 0.50),
        ),
    ]

    mesa2_abert_d1_rules = [
        (
            "A1",
            "TRAVA_ABERT_LIM + PERTO_PUT_WALL + CP_VOL_2D_2.5X + DOI_OTM_POS",
            "Apoio na Put Wall + Fluxo Calls 2,5x por 2 dias + Abertura de OI OTM",
            81.6, 77.0, 37.9, 64.4, 1.98, 10.40, 2.31,
            lambda r: (-0.005 <= r["put_wall_dist_pct"] <= 0.03) and (r["call_put_vol_2d_min"] >= 2.5) and (r["otm_doi_pct"] >= 0.01),
        ),
        (
            "A2",
            "DOI_OTM_POS + CALL_OI_DOMINA_1.5X + TUBARAO_CP_TICKET_3.0X + IV_RANK_BAIXO_50",
            "Abertura OI OTM + Call OI Domina 1,5x + Ticket Tubarão 3,0x + IV Barata",
            80.2, 74.4, 41.9, 60.5, 1.98, 10.27, 2.54,
            lambda r: (r["otm_doi_pct"] >= 0.01) and (r["call_put_oi_ratio"] >= 1.5) and (r["cp_ticket_ratio"] >= 3.0) and (r["iv_rank_20d"] <= 0.50),
        ),
        (
            "A3",
            "PERTO_PUT_WALL + CP_VOL_2D_2.5X + DOI_CALL_FORTE + TUBARAO_CP_TICKET_1.5X",
            "Apoio na Put Wall + Fluxo Calls 2,5x (2d) + Abertura Forte OI + Ticket Tubarão 1,5x",
            78.7, 76.4, 47.2, 67.4, 1.85, 8.53, 1.95,
            lambda r: (-0.005 <= r["put_wall_dist_pct"] <= 0.03) and (r["call_put_vol_2d_min"] >= 2.5) and (r["total_call_doi_pct"] >= 0.025) and (r["cp_ticket_ratio"] >= 1.5),
        ),
        (
            "A4",
            "PERTO_PUT_WALL + CP_VOL_5.0X + DOI_OTM_POS + TUBARAO_CP_TICKET_3.0X",
            "Apoio na Put Wall + Fluxo Calls 5x Puts + Abertura OI OTM + Ticket Tubarão 3x",
            78.0, 72.0, 38.0, 64.0, 1.98, 10.22, 2.48,
            lambda r: (-0.005 <= r["put_wall_dist_pct"] <= 0.03) and (r["call_put_vol_ratio"] >= 5.0) and (r["otm_doi_pct"] >= 0.01) and (r["cp_ticket_ratio"] >= 3.0),
        ),
        (
            "A5",
            "PUT_WALL_SUBIU_3D + PERTO_PUT_WALL + CP_VOL_2D_2.5X + DOI_CALL_POS",
            "Piso Subiu 3d + Apoio na Put Wall + Fluxo Calls 2,5x (2d) + Abertura OI",
            77.9, 73.5, 38.2, 63.2, 1.99, 7.74, 1.88,
            lambda r: (r["put_wall_change_3d"] >= 0.01) and (-0.005 <= r["put_wall_dist_pct"] <= 0.03) and (r["call_put_vol_2d_min"] >= 2.5) and (r["total_call_doi_pct"] >= 0.01),
        ),
        (
            "A6",
            "PERTO_PUT_WALL + TUBARAO_CP_TICKET_2.2X + GEX_SUBINDO_3D + IV_CONTANGO",
            "Apoio na Put Wall + Ticket Tubarão 2,2x + GEX Subindo + IV em Contango",
            77.9, 70.9, 40.7, 60.5, 1.99, 11.53, 3.09,
            lambda r: (-0.005 <= r["put_wall_dist_pct"] <= 0.03) and (r["cp_ticket_ratio"] >= 2.2) and bool(r["gex_rising_3d"]) and (r["iv_term_slope"] <= 0.0),
        ),
        (
            "A7",
            "PERTO_PUT_WALL + CP_VOL_2D_2.5X + DOI_CALL_FORTE + GEX_POS_ZERO",
            "Apoio na Put Wall + Fluxo Calls 2,5x (2d) + Abertura Forte OI + GEX Positivo",
            77.7, 73.4, 43.6, 63.8, 1.93, 7.59, 1.79,
            lambda r: (-0.005 <= r["put_wall_dist_pct"] <= 0.03) and (r["call_put_vol_2d_min"] >= 2.5) and (r["total_call_doi_pct"] >= 0.025) and (r["gex_net"] >= 0.0),
        ),
        (
            "A8",
            "PERTO_PUT_WALL + CP_VOL_2D_2.5X + DOI_CALL_POS + DOI_OTM_POS",
            "Apoio na Put Wall + Fluxo Calls 2,5x (2d) + Abertura OI Total e OTM",
            75.7, 71.8, 41.7, 62.1, 1.96, 6.10, 1.56,
            lambda r: (-0.005 <= r["put_wall_dist_pct"] <= 0.03) and (r["call_put_vol_2d_min"] >= 2.5) and (r["total_call_doi_pct"] >= 0.01) and (r["otm_doi_pct"] >= 0.01),
        ),
        (
            "A9",
            "VOL_WALL_SUBIU_1D + CP_VOL_2D_2.5X + DOI_OTM_POS + TUBARAO_CP_TICKET_3.0X",
            "Strike de Giro Subiu + Fluxo Calls 2,5x (2d) + Abertura OI OTM + Ticket Tubarão 3x",
            74.1, 70.4, 42.6, 61.1, 1.96, 7.53, 1.92,
            lambda r: (r["vol_wall_change_1d"] >= 0.01) and (r["call_put_vol_2d_min"] >= 2.5) and (r["otm_doi_pct"] >= 0.01) and (r["cp_ticket_ratio"] >= 3.0),
        ),
        (
            "A10",
            "DOI_CALL_FORTE + CALL_OI_DOMINA_2.0X + IV_CONTANGO + ACAO_POS_HOJE",
            "Abertura Forte OI (+2,5%) + Call OI 2x Put OI + IV em Contango + Ação Positiva",
            73.6, 70.2, 41.3, 62.0, 1.96, 7.02, 1.79,
            lambda r: (r["total_call_doi_pct"] >= 0.025) and (r["call_put_oi_ratio"] >= 2.0) and (r["iv_term_slope"] <= 0.0) and (r["ret_1d"] >= 0.0001),
        ),
        (
            "A11",
            "LIQ_250K + CP_VOL_3.5X + CALL_TRADES_2.5X + DOI_OTM_POS",
            "Fluxo Calls 3,5x Puts + Explosão Negócios 2,5x + Abertura OI OTM",
            72.7, 70.9, 45.5, 61.8, 1.93, 4.84, 1.48,
            lambda r: (r["call_vol_med20"] >= 250_000) and (r["call_put_vol_ratio"] >= 3.5) and (r["call_trades_ratio"] >= 2.5) and (r["otm_doi_pct"] >= 0.01),
        ),
        (
            "A12",
            "CALL_TRADES_2.5X + TUBARAO_CP_TICKET_1.5X + GEX_POS_ZERO + VANNA_SUBINDO_3D",
            "Negócios Calls 2,5x + Ticket Tubarão 1,5x + GEX Positivo + Vanna Subindo 3d",
            72.3, 70.5, 48.2, 62.5, 1.89, 4.42, 1.44,
            lambda r: (r["call_trades_ratio"] >= 2.5) and (r["cp_ticket_ratio"] >= 1.5) and (r["gex_net"] >= 0.0) and bool(r["vanna_rising_3d"]),
        ),
    ]

    mesa1_hits: list[dict[str, Any]] = []
    mesa2_hits: list[dict[str, Any]] = []

    for _, row in day_df.iterrows():
        cands = []
        if pd.notna(row.get("candidates_json")) and str(row.get("candidates_json")).startswith("["):
            try:
                cands = json.loads(str(row["candidates_json"]))
            except Exception:
                cands = []
        reasons_pt = _build_reasons_pt(row)

        m1_triggered = []
        for code, formula, title_pt, wr, h20_d3, h20_d1, h20_d2, hold, ev, pf, fn in mesa1_fim_d0_rules:
            try:
                if fn(row):
                    m1_triggered.append(
                        {
                            "code": code,
                            "desc": formula,
                            "title_pt": title_pt,
                            "wr": wr,
                            "hit20_d3": h20_d3,
                            "hit20_d1": h20_d1,
                            "hit20_d2": h20_d2,
                            "hold": hold,
                            "ev": ev,
                            "pf": pf,
                        }
                    )
            except Exception:
                continue

        if m1_triggered:
            best_r = max(m1_triggered, key=lambda x: (x["wr"], x["ev"]))
            entry_px = float(row.get("sel_opt_close") or row.get("sel_opt_ref") or 0.0)
            ref_px = float(row.get("sel_opt_ref") or entry_px)
            mesa1_hits.append(
                {
                    "mesa": "MESA_1_FIM_D0",
                    "ticker": row["ticker"],
                    "spot": round(float(row["spot"]), 2),
                    "ret_1d_pct": round(float(row.get("ret_1d") or 0.0) * 100.0, 2),
                    "put_wall": round(float(row["put_wall_strike"]), 2),
                    "call_wall": round(float(row["call_wall_strike"]), 2),
                    "call_put_vol": round(float(row["call_put_vol_ratio"]), 2),
                    "cp_ticket": round(float(row["cp_ticket_ratio"]), 2),
                    "call_trades_ratio": round(float(row.get("call_trades_ratio") or 0.0), 2),
                    "doi_call_pct": round(float(row.get("total_call_doi_pct") or 0.0) * 100.0, 2),
                    "doi_otm_pct": round(float(row.get("otm_doi_pct") or 0.0) * 100.0, 2),
                    "n_rules": len(m1_triggered),
                    "rules": [x["code"] for x in m1_triggered],
                    "rules_detail": m1_triggered,
                    "best_rule": best_r,
                    "reasons_pt": reasons_pt,
                    "opt_ticker": row.get("sel_opt_ticker"),
                    "opt_strike": round(float(row.get("sel_opt_strike") or 0.0), 2),
                    "opt_exp": row.get("sel_opt_exp"),
                    "opt_dte": int(float(row.get("sel_opt_dte") or 0.0)),
                    "opt_delta": round(float(row.get("sel_opt_delta") or 0.0), 2),
                    "opt_iv": round(float(row.get("sel_opt_iv") or 0.0), 4),
                    "opt_close": round(entry_px, 2),
                    "opt_ref": round(ref_px, 2),
                    "opt_bid": round(float(row.get("sel_opt_bid") or 0.0), 2),
                    "opt_ask": round(float(row.get("sel_opt_ask") or 0.0), 2),
                    "opt_vol": round(float(row.get("sel_opt_vol") or 0.0), 2),
                    "opt_trades": int(float(row.get("sel_opt_trades") or 0.0)),
                    "ideal_buy_min": round(max(0.01, entry_px * 0.95), 2) if entry_px > 0 else 0.0,
                    "ideal_buy_max": round(entry_px * 1.03, 2) if entry_px > 0 else 0.0,
                    "max_buy_limit": round(max(entry_px, ref_px) * 1.08, 2) if entry_px > 0 else 0.0,
                    "target_20": round(entry_px * 1.20, 2) if entry_px > 0 else 0.0,
                    "target_40": round(entry_px * 1.40, 2) if entry_px > 0 else 0.0,
                    "d1_date": d1_date,
                    "d2_date": d2_date,
                    "d3_limit_date": d3_date,
                    "option_candidates": cands,
                }
            )

        m2_triggered = []
        for code, formula, title_pt, wr, h20_d3, h20_d1, h20_d2, hold, ev, pf, fn in mesa2_abert_d1_rules:
            try:
                if fn(row):
                    m2_triggered.append(
                        {
                            "code": code,
                            "desc": formula,
                            "title_pt": title_pt,
                            "wr": wr,
                            "hit20_d3": h20_d3,
                            "hit20_d1": h20_d1,
                            "hit20_d2": h20_d2,
                            "hold": hold,
                            "ev": ev,
                            "pf": pf,
                        }
                    )
            except Exception:
                continue

        if m2_triggered:
            best_r = max(m2_triggered, key=lambda x: (x["wr"], x["ev"]))
            ref_px = float(row.get("sel_opt_ref") or row.get("sel_opt_close") or 0.0)
            close_px = float(row.get("sel_opt_close") or ref_px)
            base_px = close_px if close_px > 0 else ref_px
            mesa2_hits.append(
                {
                    "mesa": "MESA_2_ABERT_D1",
                    "ticker": row["ticker"],
                    "spot": round(float(row["spot"]), 2),
                    "ret_1d_pct": round(float(row.get("ret_1d") or 0.0) * 100.0, 2),
                    "min_stock_open_d1": round(float(row["spot"]) * 0.985, 2),
                    "put_wall": round(float(row["put_wall_strike"]), 2),
                    "call_wall": round(float(row["call_wall_strike"]), 2),
                    "call_put_vol": round(float(row["call_put_vol_ratio"]), 2),
                    "cp_ticket": round(float(row["cp_ticket_ratio"]), 2),
                    "call_trades_ratio": round(float(row.get("call_trades_ratio") or 0.0), 2),
                    "doi_call_pct": round(float(row.get("total_call_doi_pct") or 0.0) * 100.0, 2),
                    "doi_otm_pct": round(float(row.get("otm_doi_pct") or 0.0) * 100.0, 2),
                    "n_rules": len(m2_triggered),
                    "rules": [x["code"] for x in m2_triggered],
                    "rules_detail": m2_triggered,
                    "best_rule": best_r,
                    "reasons_pt": reasons_pt,
                    "opt_ticker": row.get("sel_opt_ticker"),
                    "opt_strike": round(float(row.get("sel_opt_strike") or 0.0), 2),
                    "opt_exp": row.get("sel_opt_exp"),
                    "opt_dte": int(float(row.get("sel_opt_dte") or 0.0)),
                    "opt_delta": round(float(row.get("sel_opt_delta") or 0.0), 2),
                    "opt_iv": round(float(row.get("sel_opt_iv") or 0.0), 4),
                    "opt_close": round(close_px, 2),
                    "opt_ref": round(ref_px, 2),
                    "opt_bid": round(float(row.get("sel_opt_bid") or 0.0), 2),
                    "opt_ask": round(float(row.get("sel_opt_ask") or 0.0), 2),
                    "ideal_buy_min": round(max(0.01, base_px * 0.94), 2) if base_px > 0 else 0.0,
                    "ideal_buy_max": round(base_px * 1.05, 2) if base_px > 0 else 0.0,
                    "opt_max_open_d1": round(max(close_px, ref_px) * 1.15, 2) if base_px > 0 else 0.0,
                    "opt_vol": round(float(row.get("sel_opt_vol") or 0.0), 2),
                    "opt_trades": int(float(row.get("sel_opt_trades") or 0.0)),
                    "target_20_ref": round(base_px * 1.20, 2) if base_px > 0 else 0.0,
                    "target_40_ref": round(base_px * 1.40, 2) if base_px > 0 else 0.0,
                    "entry_session_date": d1_date,
                    "d1_date": d1_date,
                    "d2_date": d2_date,
                    "d3_limit_date": d4_date,
                    "option_candidates": cands,
                }
            )

    mesa1_hits.sort(key=lambda x: (x["n_rules"], x["best_rule"]["wr"], x["best_rule"]["ev"]), reverse=True)
    mesa2_hits.sort(key=lambda x: (x["n_rules"], x["best_rule"]["wr"], x["best_rule"]["ev"]), reverse=True)
    return mesa1_hits, mesa2_hits


def render_scan_report(eval_date: str, n_stocks: int, mesa1: list[dict[str, Any]], mesa2: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("=" * 108)
    lines.append(f"  SCANNER OPERACIONAL TIRO RÁPIDO (D+1 a D+3 | ALVO MÍNIMO +20%) — BASE D0: {eval_date} ({n_stocks} AÇÕES LÍQUIDAS)")
    lines.append("=" * 108)

    lines.append("")
    lines.append("┌──────────────────────────────────────────────────────────────────────────────────────────────────────────┐")
    lines.append("│ MESA 2 — PARA ENTRAR NO LEILÃO / ABERTURA DE D+1 (09h55 a 10h15) | ALVO +20% / +40% até D+3              │")
    lines.append("└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘")
    if not mesa2:
        lines.append("  Nenhuma ação acionou as regras de Abertura D+1 neste pregão.")
    else:
        for i, h in enumerate(mesa2, 1):
            conf_tag = " [SUPER CONFLUÊNCIA 2+ REGRAS!]" if h["n_rules"] >= 2 else ""
            br = h["best_rule"]
            lines.append(
                f"  {i}. {h['ticker']} (Fech D0: R$ {h['spot']:.2f} | PutWall: R$ {h['put_wall']:.2f} | CallWall: R$ {h['call_wall']:.2f}){conf_tag}"
            )
            lines.append(
                f"     • Regras Ativas ({h['n_rules']}): {', '.join(h['rules'])} -> {br['title_pt']} [{br['desc']}]"
            )
            lines.append(
                f"     • Estatística D+3: Taxa de Acerto = {br['wr']:.1f}% | Bate +20% (D+1: {br['hit20_d1']:.1f}% | D+2: {br['hit20_d2']:.1f}% | D+3: {br['hit20_d3']:.1f}%) | Prazo: {br['hold']:.2f}d | EV: +{br['ev']:.2f}% (PF {br['pf']:.2f})"
            )
            if h["opt_ticker"]:
                lines.append(
                    f"     • CALL NO PROFIT: {h['opt_ticker']} | Strike: R$ {h['opt_strike']:.2f} | Venc: {h['opt_exp']} ({h['opt_dte']} DTE) | Delta: {h['opt_delta']:.2f} | IV: {h['opt_iv']*100:.1f}% | Giro D0: R$ {h['opt_vol']:,.0f}"
                )
                lines.append(
                    f"     • FAIXA BOA P/ BATER NO LEILÃO/ABERTURA: R$ {h['ideal_buy_min']:.2f} a R$ {h['ideal_buy_max']:.2f} | TETO MÁXIMO (+15%): até R$ {h['opt_max_open_d1']:.2f} | Ação deve abrir >= R$ {h['min_stock_open_d1']:.2f}"
                )
                lines.append(
                    f"     • ALVOS (sobre Abertura D+1; ex. se abrir a R$ {h['opt_close']:.2f}):  ALVO 1 (+20%): R$ {h['target_20_ref']:.2f} (ou Abert x 1,20)  |  ALVO 2 (+40% c/ Stop 0x0): R$ {h['target_40_ref']:.2f} (ou Abert x 1,40)"
                )
            lines.append("")

    lines.append("┌──────────────────────────────────────────────────────────────────────────────────────────────────────────┐")
    lines.append("│ MESA 1 — ENTRADA NO FIM DO DIA (D0: 16h45 a 16h55) | ALVO +20% (50%) e +40% (50% c/ Stop 0x0) até D+3   │")
    lines.append("└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘")
    if not mesa1:
        lines.append("  Nenhuma ação acionou as 8 regras de Fim do Dia (F1 a F8) neste pregão.")
    else:
        for i, h in enumerate(mesa1, 1):
            conf_tag = " [SUPER CONFLUÊNCIA 2+ REGRAS!]" if h["n_rules"] >= 2 else ""
            br = h["best_rule"]
            lines.append(
                f"  {i}. {h['ticker']} (Fech: R$ {h['spot']:.2f} | PutWall: R$ {h['put_wall']:.2f} | CallWall: R$ {h['call_wall']:.2f}){conf_tag}"
            )
            lines.append(
                f"     • Regras Ativas ({h['n_rules']}): {', '.join(h['rules'])} -> {br['title_pt']} [{br['desc']}]"
            )
            lines.append(
                f"     • Estatística D+3: Taxa de Acerto = {br['wr']:.1f}% | Bate +20% (D+1: {br['hit20_d1']:.1f}% | D+2: {br['hit20_d2']:.1f}% | D+3: {br['hit20_d3']:.1f}%) | Prazo: {br['hold']:.2f}d | EV: +{br['ev']:.2f}% (PF {br['pf']:.2f})"
            )
            if h["opt_ticker"]:
                lines.append(
                    f"     • CALL NO PROFIT: {h['opt_ticker']} | Strike: R$ {h['opt_strike']:.2f} | Venc: {h['opt_exp']} ({h['opt_dte']} DTE) | Delta: {h['opt_delta']:.2f} | IV: {h['opt_iv']*100:.1f}% | Giro: R$ {h['opt_vol']:,.0f} ({h['opt_trades']} neg)"
                )
                lines.append(
                    f"     • EXECUÇÃO FIM DO DIA (16h45): Faixa Boa = R$ {h['ideal_buy_min']:.2f} a R$ {h['ideal_buy_max']:.2f} (Teto: R$ {h['max_buy_limit']:.2f}) ==> ALVO 1 (+20%): R$ {h['target_20']:.2f} | ALVO 2 (+40% c/ Stop 0x0): R$ {h['target_40']:.2f}"
                )
            lines.append("")

    lines.append("=" * 108)
    lines.append("  REGRA DE OURO DE SAÍDA (TIME-STOP D+3): Se não atingir o alvo antes, zerar 100% no fechamento do 3º dia útil (D+3).")
    lines.append("=" * 108)
    return "\n".join(lines)


def run_scan_payload(target_date: str | None = None, do_download: bool = False) -> dict[str, Any]:
    if do_download:
        download_recent_b3_sessions(ROOT / "data", lookback_days=10)
    day_df, eval_date, avail_dates = build_live_panel(target_date)
    mesa1, mesa2 = evaluate_mesas(day_df, eval_date)
    report_txt = render_scan_report(eval_date, len(day_df), mesa1, mesa2)
    next_days = next_business_days(eval_date, 3)

    payload = {
        "eval_date": eval_date,
        "next_session_d1": next_days[0],
        "session_d2": next_days[1],
        "session_d3": next_days[2],
        "available_dates": avail_dates,
        "n_stocks": len(day_df),
        "mesa2_abert_d1": mesa2,
        "mesa1_fim_d0": mesa1,
    }
    out_dir = ROOT / "results" / "option_patterns"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ultimo_scan_tiro_rapido_d3.txt").write_text(report_txt, encoding="utf-8")
    (out_dir / "ultimo_scan_tiro_rapido_d3.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        from scripts.rtd_bridge import sync_rtd_excel
        sync_rtd_excel(payload)
    except Exception:
        pass
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Scanner Operacional Diário — Tiro Rápido D+1 a D+3 (Alvo Mínimo +20%)")
    parser.add_argument("--data", type=str, default=None, help="Data base D0 no formato YYYY-MM-DD (padrão: último pregão disponível)")
    parser.add_argument("--sem-download", action="store_true", help="Não consulta novos downloads na B3; usa o que já está em data/raw")
    args = parser.parse_args()

    payload = run_scan_payload(target_date=args.data, do_download=not args.sem_download)
    report_txt = (ROOT / "results" / "option_patterns" / "ultimo_scan_tiro_rapido_d3.txt").read_text(encoding="utf-8")
    print(report_txt)


if __name__ == "__main__":
    main()
