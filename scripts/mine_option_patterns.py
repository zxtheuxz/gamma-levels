from __future__ import annotations

import json
import math
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Os 25 ativos com maior liquidez e atividade histórica em opções nos nossos 75 bancos
LIQUID_TICKERS = [
    "VALE3", "PETR4", "BBDC4", "ITUB4", "BBAS3", "B3SA3", "PRIO3", "PETR3",
    "CMIG4", "USIM5", "ITSA4", "SUZB3", "WEGE3", "GGBR4", "CSNA3", "MGLU3",
    "RENT3", "VBBR3", "RADL3", "LREN3", "CSAN3", "BRAV3", "EMBR3", "JBSS3", "EQTL3",
]


def _bsm_call_price(spot: np.ndarray | float, strike: np.ndarray, t: np.ndarray, vol: np.ndarray, r: float = 0.13) -> np.ndarray:
    spot_arr = np.asarray(spot, dtype=float)
    strike_arr = np.asarray(strike, dtype=float)
    t_arr = np.maximum(np.asarray(t, dtype=float), 1.0 / 365.0)
    vol_arr = np.maximum(np.asarray(vol, dtype=float), 0.05)
    sqrt_t = np.sqrt(t_arr)
    d1 = (np.log(np.maximum(spot_arr, 1e-4) / np.maximum(strike_arr, 1e-4)) + (r + 0.5 * vol_arr ** 2) * t_arr) / (vol_arr * sqrt_t)
    d2 = d1 - vol_arr * sqrt_t
    # Aproximação vetorizada rápida da CDF normal (precisão < 1e-7)
    def norm_cdf(x: np.ndarray) -> np.ndarray:
        return 0.5 * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * np.power(x, 3))))
    return spot_arr * norm_cdf(d1) - strike_arr * np.exp(-r * t_arr) * norm_cdf(d2)


def _bsm_delta_gamma(spot: np.ndarray | float, strike: np.ndarray, t: np.ndarray, vol: np.ndarray, is_call: np.ndarray, r: float = 0.13) -> tuple[np.ndarray, np.ndarray]:
    spot_arr = np.asarray(spot, dtype=float)
    strike_arr = np.asarray(strike, dtype=float)
    t_arr = np.maximum(np.asarray(t, dtype=float), 1.0 / 365.0)
    vol_arr = np.maximum(np.asarray(vol, dtype=float), 0.05)
    sqrt_t = np.sqrt(t_arr)
    d1 = (np.log(np.maximum(spot_arr, 1e-4) / np.maximum(strike_arr, 1e-4)) + (r + 0.5 * vol_arr ** 2) * t_arr) / (vol_arr * sqrt_t)
    cdf_d1 = 0.5 * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (d1 + 0.044715 * np.power(d1, 3))))
    pdf_d1 = np.exp(-0.5 * d1 * d1) / np.sqrt(2.0 * np.pi)
    delta = np.where(is_call, cdf_d1, cdf_d1 - 1.0)
    gamma = pdf_d1 / (spot_arr * vol_arr * sqrt_t)
    return delta, gamma


def load_ticker_panel(ticker: str) -> pd.DataFrame | None:
    cache_path = Path(f"results/option_patterns/cache/{ticker}.parquet")
    if cache_path.exists():
        try:
            return pd.read_parquet(cache_path)
        except Exception:
            pass
    db_path = Path(f"data/pilot_{ticker.lower()}/gamma_levels.db")
    if not db_path.exists():
        return None
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        bars = pd.read_sql_query(
            "SELECT trade_date, ticker, open, low, high, close, volume FROM underlying_bars ORDER BY trade_date",
            con,
        )
        if bars.empty:
            return None
        # Separar o ticker principal de outra classe (ex: PETR3 vs PETR4) se existir na mesma raiz
        main_bars = bars.loc[bars["ticker"] == ticker].drop_duplicates("trade_date").sort_values("trade_date").reset_index(drop=True)
        if len(main_bars) < 100:
            return None

        # Verificar se há outra classe importante (ON vs PN) para desambiguação matemática de opções
        other_tickers = [
            t for t in bars["ticker"].unique()
            if t != ticker and len(t) == 5 and t[:4] == ticker[:4] and t[-1] in ("3", "4", "5", "6")
        ]
        other_spot_map: dict[str, float] = {}
        if other_tickers:
            other_df = bars.loc[bars["ticker"] == other_tickers[0]].drop_duplicates("trade_date")
            other_spot_map = dict(zip(other_df["trade_date"], pd.to_numeric(other_df["close"], errors="coerce")))

        inst = pd.read_sql_query(
            "SELECT ticker, isin FROM instruments WHERE instrument_type='option' AND isin IS NOT NULL",
            con,
        )
        inst_map = dict(zip(inst["ticker"], inst["isin"]))

        opts = pd.read_sql_query(
            """SELECT trade_date, ticker, option_type, expiration, strike,
                      open, low, high, close, reference_price, bid, ask,
                      trades, contracts, financial_volume, open_interest, implied_volatility
               FROM option_quotes
               WHERE open_interest > 0 OR financial_volume > 0 OR trades > 0""",
            con,
        )
    finally:
        con.close()

    if opts.empty:
        return None

    for col in ("open", "low", "high", "close", "volume"):
        main_bars[col] = pd.to_numeric(main_bars[col], errors="coerce")
    main_bars = main_bars.dropna(subset=["open", "low", "high", "close"]).reset_index(drop=True)

    # Ajustar corporate actions básicas se houver salto abrupto? Melhor: checar corporate_actions
    spot_map = dict(zip(main_bars["trade_date"], main_bars["close"]))
    opts["spot"] = opts["trade_date"].map(spot_map)
    opts = opts.dropna(subset=["spot", "strike", "expiration"]).copy()

    # Filtro 1: ISIN quando disponível em instruments
    opts["isin"] = opts["ticker"].map(inst_map)
    expected_prefix = f"BR{ticker}"
    has_other_isin = opts["isin"].notna() & ~opts["isin"].str.startswith(expected_prefix)
    opts = opts.loc[~has_other_isin].copy()

    # Converter colunas numéricas
    num_cols = ["strike", "open", "low", "high", "close", "reference_price", "bid", "ask", "trades", "contracts", "financial_volume", "open_interest", "implied_volatility"]
    for col in num_cols:
        opts[col] = pd.to_numeric(opts[col], errors="coerce")

    opts["mkt_price"] = opts["reference_price"].where(opts["reference_price"] > 0, opts["close"])
    opts["dte"] = (pd.to_datetime(opts["expiration"]) - pd.to_datetime(opts["trade_date"])).dt.days
    opts = opts.loc[opts["dte"].between(1, 120) & (opts["strike"] > 0)].copy()

    # Filtro 2: Desambiguação matemática ON/PN (ex.: PETR3 vs PETR4, BBDC3 vs BBDC4, ITUB3 vs ITUB4)
    if other_spot_map:
        opts["other_spot"] = opts["trade_date"].map(other_spot_map)
        both_valid = opts["other_spot"].notna() & (opts["other_spot"] > 0) & (opts["mkt_price"] > 0) & (opts["implied_volatility"] > 0)
        if both_valid.any():
            sub = opts.loc[both_valid]
            iv_scaled = np.where(sub["implied_volatility"] > 3.0, sub["implied_volatility"] / 100.0, sub["implied_volatility"])
            t_yr = sub["dte"] / 365.0
            is_c = sub["option_type"] == "call"
            # Preço BSM com spot principal vs spot da outra classe
            c_main = _bsm_call_price(sub["spot"].to_numpy(), sub["strike"].to_numpy(), t_yr.to_numpy(), iv_scaled)
            p_main = c_main - sub["spot"].to_numpy() + sub["strike"].to_numpy() * np.exp(-0.13 * t_yr.to_numpy())
            theo_main = np.where(is_c, c_main, np.maximum(p_main, 0.0))

            c_other = _bsm_call_price(sub["other_spot"].to_numpy(), sub["strike"].to_numpy(), t_yr.to_numpy(), iv_scaled)
            p_other = c_other - sub["other_spot"].to_numpy() + sub["strike"].to_numpy() * np.exp(-0.13 * t_yr.to_numpy())
            theo_other = np.where(is_c, c_other, np.maximum(p_other, 0.0))

            err_main = np.abs(theo_main - sub["mkt_price"].to_numpy())
            err_other = np.abs(theo_other - sub["mkt_price"].to_numpy())
            # Se o erro no spot da outra classe for muito menor e a diferença entre spots for relevante (>2%), descartar
            spot_diff_pct = np.abs(sub["spot"].to_numpy() - sub["other_spot"].to_numpy()) / sub["spot"].to_numpy()
            belongs_to_other = (spot_diff_pct > 0.02) & (err_other + 0.15 < err_main) & (err_main > 0.35)
            bad_idx = sub.index[belongs_to_other]
            opts = opts.drop(index=bad_idx)

    # Filtro 3: No-arbitrage em CALLs (evitar cotação podre/invertida)
    is_call_pre = opts["option_type"] == "call"
    intrinsic_call = np.maximum(opts["spot"] - opts["strike"] * np.exp(-0.13 * opts["dte"] / 365.0), 0.0)
    violates_no_arb = is_call_pre & (opts["mkt_price"] > 0) & (opts["mkt_price"] < intrinsic_call * 0.82 - 0.15)
    opts = opts.loc[~violates_no_arb].copy()
    is_call = opts["option_type"] == "call"

    # Normalizar IV
    opts["iv"] = np.where(opts["implied_volatility"] > 3.0, opts["implied_volatility"] / 100.0, opts["implied_volatility"])
    opts["iv"] = opts["iv"].clip(0.05, 2.50)

    # Calcular Delta, Gamma e GEX vetorizados para todas as opções
    delta, gamma = _bsm_delta_gamma(
        opts["spot"].to_numpy(),
        opts["strike"].to_numpy(),
        (opts["dte"] / 365.0).to_numpy(),
        opts["iv"].to_numpy(),
        is_call.to_numpy(),
    )
    opts["delta"] = delta
    opts["gamma"] = gamma
    oi_filled = opts["open_interest"].fillna(0.0)
    vol_fin = opts["financial_volume"].fillna(0.0)
    trades_cnt = opts["trades"].fillna(0.0)
    opts["gex"] = opts["gamma"] * oi_filled * 100.0 * (opts["spot"] ** 2) * 0.01 * np.where(is_call, 1.0, -1.0)

    # Calcular Delta OI por opção de um dia para o outro
    opts = opts.sort_values(["ticker", "trade_date"]).reset_index(drop=True)
    opts["prev_oi"] = opts.groupby("ticker")["open_interest"].shift(1)
    opts["delta_oi"] = (opts["open_interest"] - opts["prev_oi"]).fillna(0.0)

    # Indexar cotações futuras por (option_ticker, trade_date) para simular a CALL selecionada
    # Para rapidez, guardar um dicionário {option_ticker: DataFrame ou dict por trade_date}
    call_quotes = opts.loc[
        (opts["option_type"] == "call") & (opts["mkt_price"] > 0),
        ["trade_date", "ticker", "strike", "dte", "open", "low", "high", "close", "mkt_price", "bid", "ask", "financial_volume", "open_interest", "trades", "delta", "gamma", "iv"],
    ].copy()

    # Mapear (ticker_opcao, trade_date) -> (open, high, low, close, mkt_price)
    opt_daily_map: dict[tuple[str, str], tuple[float, float, float, float]] = {}
    for row in call_quotes.itertuples(index=False):
        c_val = float(row.close) if pd.notna(row.close) and row.close > 0 else float(row.mkt_price)
        o_val = float(row.open) if pd.notna(row.open) and row.open > 0 else c_val
        h_val = float(row.high) if pd.notna(row.high) and row.high > 0 else max(o_val, c_val)
        l_val = float(row.low) if pd.notna(row.low) and row.low > 0 else min(o_val, c_val)
        opt_daily_map[(str(row.ticker), str(row.trade_date))] = (o_val, h_val, l_val, c_val)

    # Agregar features diárias da grade de opções (10 a 60 DTE como foco operacional e 2 a 60 DTE geral)
    swing_opts = opts.loc[opts["dte"].between(5, 65)].copy()
    if swing_opts.empty:
        return None

    daily_records: list[dict[str, Any]] = []
    opts_by_date = {d: g for d, g in swing_opts.groupby("trade_date")}

    dates = main_bars["trade_date"].tolist()
    closes = main_bars["close"].to_numpy(float)
    opens = main_bars["open"].to_numpy(float)
    highs = main_bars["high"].to_numpy(float)
    lows = main_bars["low"].to_numpy(float)
    vols = main_bars["volume"].fillna(0.0).to_numpy(float)

    for idx, d in enumerate(dates):
        spot = closes[idx]
        g = opts_by_date.get(d)
        if g is None or g.empty or spot <= 0:
            continue

        calls = g.loc[g["option_type"] == "call"]
        puts = g.loc[g["option_type"] == "put"]
        if calls.empty:
            continue

        call_vol = float(calls["financial_volume"].fillna(0).sum())
        put_vol = float(puts["financial_volume"].fillna(0).sum())
        call_trades = float(calls["trades"].fillna(0).sum())
        put_trades = float(puts["trades"].fillna(0).sum())
        call_oi = float(calls["open_interest"].fillna(0).sum())
        put_oi = float(puts["open_interest"].fillna(0).sum())

        # Calls OTM (strikes de +0.5% a +10% acima do spot)
        otm_calls = calls.loc[calls["strike"].between(spot * 1.005, spot * 1.10)]
        otm_call_vol = float(otm_calls["financial_volume"].fillna(0).sum())
        otm_call_trades = float(otm_calls["trades"].fillna(0).sum())
        otm_call_doi = float(otm_calls["delta_oi"].sum())
        total_call_doi = float(calls["delta_oi"].sum())
        total_put_doi = float(puts["delta_oi"].sum())

        # Call Wall (strike com maior GEX/OI de Call acima ou perto do spot)
        calls_above = calls.loc[calls["strike"] >= spot * 0.98]
        if not calls_above.empty and calls_above["open_interest"].fillna(0).sum() > 0:
            wall_by_strike = calls_above.groupby("strike").agg(
                oi=("open_interest", "sum"),
                gex=("gex", "sum"),
                vol=("financial_volume", "sum"),
                doi=("delta_oi", "sum"),
            )
            call_wall_strike = float(wall_by_strike["oi"].idxmax())
            call_wall_doi = float(wall_by_strike.loc[call_wall_strike, "doi"])
            call_wall_oi = float(wall_by_strike.loc[call_wall_strike, "oi"])
            # Strike imã do dia (strike com maior volume financeiro de Call no dia)
            vol_wall_strike = float(wall_by_strike["vol"].idxmax()) if wall_by_strike["vol"].sum() > 0 else call_wall_strike
        else:
            call_wall_strike = spot * 1.05
            call_wall_doi = 0.0
            call_wall_oi = 0.0
            vol_wall_strike = spot * 1.02

        # Put Wall (strike com maior OI de Put abaixo ou perto do spot)
        puts_below = puts.loc[puts["strike"] <= spot * 1.02]
        if not puts_below.empty and puts_below["open_interest"].fillna(0).sum() > 0:
            pwall_by_strike = puts_below.groupby("strike")["open_interest"].sum()
            put_wall_strike = float(pwall_by_strike.idxmax())
        else:
            put_wall_strike = spot * 0.95

        # Strike médio ponderado pelo volume financeiro de Calls do dia
        if call_vol > 0:
            vwap_call_strike = float(np.average(calls["strike"], weights=calls["financial_volume"].fillna(0)))
        else:
            vwap_call_strike = spot

        # GEX líquido
        gex_net = float(g["gex"].sum())
        gex_call = float(calls["gex"].sum())
        gex_put = float(puts["gex"].abs().sum())
        gex_imbalance = (gex_call - gex_put) / max(gex_call + gex_put, 1.0)

        # IV ATM e Skew Call vs Put
        atm_calls = calls.loc[calls["delta"].between(0.35, 0.65) & (calls["iv"] > 0.05)]
        atm_puts = puts.loc[puts["delta"].between(-0.65, -0.35) & (puts["iv"] > 0.05)]
        atm_iv = float(atm_calls["iv"].median()) if not atm_calls.empty else np.nan
        otm_c_iv = float(calls.loc[calls["delta"].between(0.20, 0.40) & (calls["iv"] > 0.05), "iv"].median())
        otm_p_iv = float(puts.loc[puts["delta"].between(-0.40, -0.20) & (puts["iv"] > 0.05), "iv"].median())
        call_put_iv_skew = (otm_c_iv - otm_p_iv) if pd.notna(otm_c_iv) and pd.notna(otm_p_iv) else 0.0

        # Seleção Matemática da Melhor CALL Líquida do Dia (10 a 45 DTE, Delta 0.35 a 0.70)
        elig_calls = calls.loc[
            calls["dte"].between(10, 48)
            & calls["delta"].between(0.35, 0.72)
            & (calls["mkt_price"] >= 0.12)
            & ((calls["financial_volume"] >= 10_000) | (calls["trades"] >= 5))
        ].copy()

        selected_opt_ticker = None
        selected_opt_price = np.nan
        selected_opt_delta = np.nan
        selected_opt_dte = np.nan
        req_move_for_30pct = np.nan
        req_move_for_50pct = np.nan

        if not elig_calls.empty:
            # Escolher a CALL mais líquida e com melhor relação Delta/preço (alavancagem efetiva)
            elig_calls["leverage"] = elig_calls["delta"] * spot / elig_calls["mkt_price"]
            elig_calls["liq_rank"] = elig_calls["financial_volume"].fillna(0).rank(pct=True) * 0.6 + elig_calls["trades"].fillna(0).rank(pct=True) * 0.4
            # Preferir delta próximo a 0.50 e alta liquidez
            elig_calls["delta_pref"] = 1.0 - (elig_calls["delta"] - 0.52).abs() / 0.25
            elig_calls["pick_score"] = 0.65 * elig_calls["liq_rank"] + 0.35 * elig_calls["delta_pref"]
            best_c = elig_calls.sort_values(["pick_score", "financial_volume"], ascending=False).iloc[0]
            selected_opt_ticker = str(best_c["ticker"])
            selected_opt_price = float(best_c["mkt_price"])
            selected_opt_delta = float(best_c["delta"])
            selected_opt_gamma = float(best_c["gamma"])
            selected_opt_dte = int(best_c["dte"])
            # Estimativa analítica de segunda ordem (Delta-Gamma) do movimento percentual da ação necessário para +30% e +50% na CALL
            # dC = delta * dS + 0.5 * gamma * dS^2
            for target_gain, attr_name in ((0.30, "req30"), (0.50, "req50")):
                dc = selected_opt_price * target_gain
                a_coef = 0.5 * max(selected_opt_gamma, 1e-6)
                b_coef = max(selected_opt_delta, 0.05)
                ds = (-b_coef + math.sqrt(max(b_coef ** 2 + 4 * a_coef * dc, 0.0))) / (2 * a_coef)
                if attr_name == "req30":
                    req_move_for_30pct = ds / spot
                else:
                    req_move_for_50pct = ds / spot

        # Calcular desfechos futuros (D+1, D+3, D+5) no papel e na CALL selecionada
        if idx + 5 >= len(dates):
            continue

        # Desfechos do papel (Ação)
        d1_open = opens[idx + 1]
        d1_high = highs[idx + 1]
        d1_low = lows[idx + 1]
        d1_close = closes[idx + 1]

        # Retornos da ação a partir do fechamento D-1 e a partir da abertura D+1
        stock_d1_high_from_close = d1_high / spot - 1.0
        stock_d1_high_from_open = d1_high / d1_open - 1.0 if d1_open > 0 else 0.0
        stock_d1_close_from_close = d1_close / spot - 1.0
        stock_d1_close_from_open = d1_close / d1_open - 1.0 if d1_open > 0 else 0.0

        stock_d3_max_high = float(np.max(highs[idx + 1 : idx + 4]) / spot - 1.0)
        stock_d5_max_high = float(np.max(highs[idx + 1 : idx + 6]) / spot - 1.0)
        stock_d5_close = float(closes[idx + 5] / spot - 1.0)

        # Desfechos reais da CALL selecionada (entrando na abertura de D+1)
        opt_d1_max_ret = np.nan
        opt_d1_close_ret = np.nan
        opt_d3_max_ret = np.nan
        opt_d5_max_ret = np.nan
        opt_d5_close_ret = np.nan

        if selected_opt_ticker is not None:
            d1_date = dates[idx + 1]
            d1_quote = opt_daily_map.get((selected_opt_ticker, d1_date))
            if d1_quote is not None and d1_quote[0] >= 0.08:
                entry_opt = d1_quote[0]  # open de D+1
                # Verificar sanidade da abertura vs referência D-1 (evitar dado espúrio sem liquidez)
                if 0.35 * selected_opt_price <= entry_opt <= 2.50 * selected_opt_price:
                    opt_d1_max_ret = d1_quote[1] / entry_opt - 1.0
                    opt_d1_close_ret = d1_quote[3] / entry_opt - 1.0

                    max_h_3 = d1_quote[1]
                    max_h_5 = d1_quote[1]
                    last_c_5 = d1_quote[3]
                    for f_step in range(1, 6):
                        f_date = dates[idx + f_step]
                        fq = opt_daily_map.get((selected_opt_ticker, f_date))
                        if fq is not None:
                            if f_step <= 3:
                                max_h_3 = max(max_h_3, fq[1])
                            max_h_5 = max(max_h_5, fq[1])
                            last_c_5 = fq[3]
                    opt_d3_max_ret = max_h_3 / entry_opt - 1.0
                    opt_d5_max_ret = max_h_5 / entry_opt - 1.0
                    opt_d5_close_ret = last_c_5 / entry_opt - 1.0

        daily_records.append({
            "ticker": ticker,
            "trade_date": d,
            "spot": spot,
            "stock_open": opens[idx],
            "stock_high": highs[idx],
            "stock_low": lows[idx],
            "stock_vol": vols[idx],
            "call_vol": call_vol,
            "put_vol": put_vol,
            "otm_call_vol": otm_call_vol,
            "call_trades": call_trades,
            "put_trades": put_trades,
            "otm_call_trades": otm_call_trades,
            "call_oi": call_oi,
            "put_oi": put_oi,
            "otm_call_doi": otm_call_doi,
            "total_call_doi": total_call_doi,
            "total_put_doi": total_put_doi,
            "call_wall_strike": call_wall_strike,
            "call_wall_doi": call_wall_doi,
            "call_wall_oi": call_wall_oi,
            "vol_wall_strike": vol_wall_strike,
            "put_wall_strike": put_wall_strike,
            "vwap_call_strike": vwap_call_strike,
            "gex_net": gex_net,
            "gex_imbalance": gex_imbalance,
            "atm_iv": atm_iv,
            "call_put_iv_skew": call_put_iv_skew,
            "req_move_for_30pct": req_move_for_30pct,
            "req_move_for_50pct": req_move_for_50pct,
            "stock_d1_high_from_close": stock_d1_high_from_close,
            "stock_d1_high_from_open": stock_d1_high_from_open,
            "stock_d1_close_from_close": stock_d1_close_from_close,
            "stock_d1_close_from_open": stock_d1_close_from_open,
            "stock_d3_max_high": stock_d3_max_high,
            "stock_d5_max_high": stock_d5_max_high,
            "stock_d5_close": stock_d5_close,
            "opt_d1_max_ret": opt_d1_max_ret,
            "opt_d1_close_ret": opt_d1_close_ret,
            "opt_d3_max_ret": opt_d3_max_ret,
            "opt_d5_max_ret": opt_d5_max_ret,
            "opt_d5_close_ret": opt_d5_close_ret,
        })

    if not daily_records:
        return None

    df = pd.DataFrame(daily_records).sort_values("trade_date").reset_index(drop=True)

    # Calcular variáveis matemáticas de série temporal do ativo (sem médias móveis subjetivas: apenas estatística de retorno, vol e ratios de opções)
    df["ret_1d"] = df["spot"].pct_change(1)
    df["ret_3d"] = df["spot"].pct_change(3)
    df["ret_5d"] = df["spot"].pct_change(5)
    df["hv20"] = df["ret_1d"].rolling(20, min_periods=10).std() * np.sqrt(252)
    df["ret_1d_z"] = df["ret_1d"] / df["ret_1d"].rolling(20, min_periods=10).std().replace(0, np.nan)
    df["ret_3d_z"] = df["ret_3d"] / (df["ret_1d"].rolling(20, min_periods=10).std() * np.sqrt(3)).replace(0, np.nan)

    # Posição do fechamento no range do dia (0 = fechou na mínima, 1 = fechou na máxima)
    day_range = (df["stock_high"] - df["stock_low"]).replace(0, np.nan)
    df["close_in_range"] = (df["spot"] - df["stock_low"]) / day_range

    # Ratios de volume e negócios de opções contra a própria mediana de 20 dias do ativo
    df["call_vol_med20"] = df["call_vol"].rolling(20, min_periods=10).median().replace(0, np.nan)
    df["call_vol_ratio"] = df["call_vol"] / df["call_vol_med20"]

    df["otm_call_vol_med20"] = df["otm_call_vol"].rolling(20, min_periods=10).median().replace(0, np.nan)
    df["otm_call_vol_ratio"] = df["otm_call_vol"] / df["otm_call_vol_med20"]

    df["call_trades_med20"] = df["call_trades"].rolling(20, min_periods=10).median().replace(0, np.nan)
    df["call_trades_ratio"] = df["call_trades"] / df["call_trades_med20"]

    df["call_put_vol_ratio"] = df["call_vol"] / df["put_vol"].replace(0, np.nan)
    df["call_put_oi_ratio"] = df["call_oi"] / df["put_oi"].replace(0, np.nan)

    # Dinâmica de Parede ("Parede que vai subir" / deslocamento de strike dominante)
    df["call_wall_dist_pct"] = df["call_wall_strike"] / df["spot"] - 1.0
    df["vol_wall_dist_pct"] = df["vol_wall_strike"] / df["spot"] - 1.0
    df["vwap_strike_dist_pct"] = df["vwap_call_strike"] / df["spot"] - 1.0
    df["put_wall_dist_pct"] = df["spot"] / df["put_wall_strike"] - 1.0

    # Parede de Call subiu em relação a 1, 3 ou 5 dias atrás
    df["call_wall_change_1d"] = df["call_wall_strike"] / df["call_wall_strike"].shift(1) - 1.0
    df["call_wall_change_3d"] = df["call_wall_strike"] / df["call_wall_strike"].shift(3) - 1.0
    df["vwap_strike_change_1d"] = df["vwap_call_strike"] / df["vwap_call_strike"].shift(1) - 1.0

    # Fluxo de abertura de contratos (Delta OI normalizado pelo OI total de calls)
    df["otm_doi_pct"] = df["otm_call_doi"] / df["call_oi"].replace(0, np.nan)
    df["total_call_doi_pct"] = df["total_call_doi"] / df["call_oi"].replace(0, np.nan)
    df["wall_unwind_pct"] = df["call_wall_doi"] / df["call_wall_oi"].replace(0, np.nan)

    # Dinâmica de GEX e IV
    df["gex_rising_3d"] = (df["gex_net"] > df["gex_net"].shift(1)) & (df["gex_net"] > df["gex_net"].shift(3))
    df["iv_vs_hv20"] = df["atm_iv"] / df["hv20"].replace(0, np.nan)
    df["iv_change_1d"] = df["atm_iv"] - df["atm_iv"].shift(1)
    df["skew_change_1d"] = df["call_put_iv_skew"] - df["call_put_iv_skew"].shift(1)

    # Razão entre movimento necessário na ação para +30% na CALL e a volatilidade realizada de 5 dias da ação
    hv_5d_move = (df["hv20"] / np.sqrt(252 / 5.0)).replace(0, np.nan)
    df["convexity_ratio_30"] = df["req_move_for_30pct"] / hv_5d_move

    out_df = df.iloc[20:].reset_index(drop=True)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        out_df.to_parquet(cache_path, index=False)
    except Exception:
        pass
    return out_df


def evaluate_patterns(panel: pd.DataFrame) -> dict[str, Any]:
    # Dividir cronologicamente por data em Treino (primeiros 60%) e OOS (últimos 40%)
    all_dates = sorted(panel["trade_date"].unique())
    split_idx = int(len(all_dates) * 0.60)
    cutoff_date = all_dates[split_idx]
    panel = panel.copy()
    panel["is_oos"] = panel["trade_date"] >= cutoff_date

    # Retorno na opção com saída em alvo (+30%, +50%, +100%) em até 5 dias ou saída no fechamento do 5º dia
    panel["opt_ev_target30_5d"] = np.where(
        panel["opt_d5_max_ret"] >= 0.30, 0.30, panel["opt_d5_close_ret"]
    )
    panel["opt_ev_target50_5d"] = np.where(
        panel["opt_d5_max_ret"] >= 0.50, 0.50, panel["opt_d5_close_ret"]
    )
    panel["opt_ev_target100_5d"] = np.where(
        panel["opt_d5_max_ret"] >= 1.00, 1.00, panel["opt_d5_close_ret"]
    )
    panel["opt_ev_target20_1d"] = np.where(
        panel["opt_d1_max_ret"] >= 0.20, 0.20, panel["opt_d1_close_ret"]
    )

    # Médias de base (Baseline incondicional de todo o universo para comparação justa)
    valid_opt = panel.dropna(subset=["opt_d5_max_ret", "opt_d5_close_ret"])
    base_stats = {
        "total_stock_days": int(len(panel)),
        "total_option_days": int(len(valid_opt)),
        "cutoff_date": cutoff_date,
        "base_d1_high_1pct_rate": float((panel["stock_d1_high_from_close"] >= 0.01).mean()),
        "base_d1_high_15pct_rate": float((panel["stock_d1_high_from_close"] >= 0.015).mean()),
        "base_d1_close_pos_rate": float((panel["stock_d1_close_from_close"] > 0).mean()),
        "base_d5_stock_up_2pct_rate": float((panel["stock_d5_max_high"] >= 0.02).mean()),
        "base_d5_stock_up_3pct_rate": float((panel["stock_d5_max_high"] >= 0.03).mean()),
        "base_opt_d1_hit20_rate": float((valid_opt["opt_d1_max_ret"] >= 0.20).mean()),
        "base_opt_d5_hit30_rate": float((valid_opt["opt_d5_max_ret"] >= 0.30).mean()),
        "base_opt_d5_hit50_rate": float((valid_opt["opt_d5_max_ret"] >= 0.50).mean()),
        "base_opt_d5_hit100_rate": float((valid_opt["opt_d5_max_ret"] >= 1.00).mean()),
        "base_opt_ev30_5d": float(valid_opt["opt_ev_target30_5d"].mean()),
        "base_opt_ev50_5d": float(valid_opt["opt_ev_target50_5d"].mean()),
        "base_opt_ev100_5d": float(valid_opt["opt_ev_target100_5d"].mean()),
    }

    # Construir dicionário de blocos matemáticos elementares (condições atômicas)
    c: dict[str, tuple[str, pd.Series]] = {
        # Bloco 1: Explosão de Volume / Giro em Calls
        "VOL_CALL_1.5X": ("Volume em Calls >= 1.5x mediana 20d", panel["call_vol_ratio"] >= 1.5),
        "VOL_CALL_2.0X": ("Volume em Calls >= 2.0x mediana 20d", panel["call_vol_ratio"] >= 2.0),
        "VOL_CALL_3.0X": ("Volume em Calls >= 3.0x mediana 20d", panel["call_vol_ratio"] >= 3.0),
        "VOL_OTM_CALL_2.0X": ("Volume em Calls OTM (+0.5% a +10%) >= 2.0x mediana", panel["otm_call_vol_ratio"] >= 2.0),
        "VOL_OTM_CALL_3.0X": ("Volume em Calls OTM (+0.5% a +10%) >= 3.0x mediana", panel["otm_call_vol_ratio"] >= 3.0),
        "TRADES_CALL_2.0X": ("Negócios em Calls >= 2.0x mediana 20d", panel["call_trades_ratio"] >= 2.0),
        "CALL_PUT_VOL_3X": ("Volume Calls >= 3x Volume Puts", panel["call_put_vol_ratio"] >= 3.0),
        "CALL_PUT_VOL_5X": ("Volume Calls >= 5x Volume Puts", panel["call_put_vol_ratio"] >= 5.0),

        # Bloco 2: "Parede que vai subir" / Deslocamento de Strike e OI
        "WALL_SUBIU_1D": ("Call Wall subiu de strike hoje (rolagem para cima)", panel["call_wall_change_1d"] >= 0.01),
        "WALL_SUBIU_3D": ("Call Wall subiu de strike nos últimos 3 pregões", panel["call_wall_change_3d"] >= 0.015),
        "FLUXO_STRIKE_ACIMA_2PCT": ("Strike médio do volume de Calls >= +2% acima do spot", panel["vwap_strike_dist_pct"].between(0.02, 0.10)),
        "FLUXO_STRIKE_ACIMA_3PCT": ("Strike médio do volume de Calls >= +3% acima do spot", panel["vwap_strike_dist_pct"].between(0.03, 0.12)),
        "VWAP_STRIKE_SUBINDO": ("Strike médio negociado em Calls subiu >= +1.5% hoje", panel["vwap_strike_change_1d"] >= 0.015),
        "CORREDOR_LIVRE_WALL_3PCT": ("Call Wall com corredor livre >= +3% acima do preço", panel["call_wall_dist_pct"].between(0.03, 0.15)),
        "WALL_UNWIND": ("Desmonte de parede (OI na Call Wall caiu >= -3% no dia)", panel["wall_unwind_pct"] <= -0.03),
        "OI_NOVO_OTM_FORTE": ("Abertura líquida de novos contratos (Delta OI >= +3%) em Calls OTM", panel["otm_doi_pct"] >= 0.03),
        "OI_NOVO_TOTAL_FORTE": ("Aumento de contratos abertos totais de Call >= +4% no dia", panel["total_call_doi_pct"] >= 0.04),
        "SUPORTE_PUT_WALL_PERTO": ("Preço próximo à Put Wall (até 2.5% de distância)", panel["put_wall_dist_pct"].between(-0.01, 0.025)),

        # Bloco 3: GEX, IV e Convexidade Matemática
        "GEX_POSITIVO": ("GEX líquido positivo", panel["gex_net"] > 0),
        "GEX_NEGATIVO": ("GEX líquido negativo (gamma short / aceleração)", panel["gex_net"] < 0),
        "GEX_SUBINDO_3D": ("GEX líquido subindo há 3 pregões", panel["gex_rising_3d"].fillna(False)),
        "IV_BARATA_VS_HV": ("IV ATM barata (<= 1.05x Volatilidade Realizada HV20)", panel["iv_vs_hv20"] <= 1.05),
        "IV_MUITO_BARATA": ("IV ATM muito descontada (<= 0.92x HV20)", panel["iv_vs_hv20"] <= 0.92),
        "CALL_SKEW_SUBINDO": ("Skew de IV puxando para Calls (IV Call subindo vs Put)", panel["skew_change_1d"] >= 0.01),
        "ALTA_CONVEXIDADE": ("Alta convexidade: CALL precisa de <= 0.75x do movimento de 5d para dar +30%", panel["convexity_ratio_30"] <= 0.75),

        # Bloco 4: Ação em "V" (Queda estatística + Fluxo em Opções) e Força de Fechamento
        "ACAO_CAIU_HOJE_1PCT": ("Ação caiu hoje (<= -1.0%)", panel["ret_1d"] <= -0.01),
        "ACAO_CAIU_HOJE_1.5PCT": ("Ação caiu forte hoje (<= -1.5%)", panel["ret_1d"] <= -0.015),
        "ACAO_ESTI_QUEDA_Z1.5": ("Ação esticada na queda em 3 dias (Z-score <= -1.5)", panel["ret_3d_z"] <= -1.5),
        "ACAO_ESTI_QUEDA_Z2.0": ("Ação muito esticada na queda em 3 dias (Z-score <= -2.0)", panel["ret_3d_z"] <= -2.0),
        "ACAO_SUBIU_FORTE_HOJE": ("Ação subiu hoje (>= +1.5% e fechou no terço superior)", (panel["ret_1d"] >= 0.015) & (panel["close_in_range"] >= 0.65)),
        "FECHOU_MAXIMA_DIA": ("Ação fechou nos 25% superiores do range do dia", panel["close_in_range"] >= 0.75),
        "FECHOU_MINIMA_DIA": ("Ação fechou nos 25% inferiores do range do dia (exaustão intradiária)", panel["close_in_range"] <= 0.25),
    }

    # Gerar todos os cenários individuais + combinações de 2 condições (de blocos complementares)
    keys = list(c.keys())
    scenarios: list[tuple[str, str, pd.Series]] = []
    for k1 in keys:
        desc1, mask1 = c[k1]
        scenarios.append((k1, desc1, mask1.fillna(False)))

    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            k1, k2 = keys[i], keys[j]
            # Evitar combinar duas versões da mesma variável
            if k1[:8] == k2[:8]:
                continue
            desc1, m1 = c[k1]
            desc2, m2 = c[k2]
            comb_mask = (m1 & m2).fillna(False)
            if int(comb_mask.sum()) >= 20:
                scenarios.append((f"{k1} + {k2}", f"{desc1} E {desc2}", comb_mask))

    # Também testar algumas combinações triplas clássicas da tese do usuário
    triples = [
        ("V_REVERSAL_CALL_FLOW", "Ação caiu (Z <= -1.5 em 3d) + Volume Calls >= 1.5x + CALL alta convexidade",
         c["ACAO_ESTI_QUEDA_Z1.5"][1] & c["VOL_CALL_1.5X"][1] & c["ALTA_CONVEXIDADE"][1]),
        ("V_QUEDA_Z1.5 + VOL_OTM_2X + STRIKE_ACIMA_2PCT", "Ação em V (Z <= -1.5) + Volume Calls OTM >= 2x + Strike médio >= +2% acima",
         c["ACAO_ESTI_QUEDA_Z1.5"][1] & c["VOL_OTM_CALL_2.0X"][1] & c["FLUXO_STRIKE_ACIMA_2PCT"][1]),
        ("V_QUEDA_Z2.0 + VOL_CALL_1.5X + STRIKE_ACIMA_2PCT", "Ação em V forte (Z <= -2.0) + Volume Calls >= 1.5x + Strike médio >= +2% acima",
         c["ACAO_ESTI_QUEDA_Z2.0"][1] & c["VOL_CALL_1.5X"][1] & c["FLUXO_STRIKE_ACIMA_2PCT"][1]),
        ("WALL_SUBIU_1D + CALL_PUT_3X + GEX_SUBINDO", "Call Wall subiu hoje + Volume Calls >= 3x Puts + GEX subindo 3d",
         c["WALL_SUBIU_1D"][1] & c["CALL_PUT_VOL_3X"][1] & c["GEX_SUBINDO_3D"][1]),
        ("WALL_SUBIU_1D + CALL_PUT_3X + ALTA_CONVEX", "Call Wall subiu hoje + Volume Calls >= 3x Puts + Alta Convexidade",
         c["WALL_SUBIU_1D"][1] & c["CALL_PUT_VOL_3X"][1] & c["ALTA_CONVEXIDADE"][1]),
        ("WALL_SUBIU_3D + CALL_PUT_3X + TRADES_2X", "Call Wall subiu 3d + Volume Calls >= 3x Puts + Negócios Calls >= 2x",
         c["WALL_SUBIU_3D"][1] & c["CALL_PUT_VOL_3X"][1] & c["TRADES_CALL_2.0X"][1]),
        ("WALL_SUBIU_3D + CALL_PUT_3X + FECHOU_MAXIMA", "Call Wall subiu 3d + Volume Calls >= 3x Puts + Fechou no topo do dia",
         c["WALL_SUBIU_3D"][1] & c["CALL_PUT_VOL_3X"][1] & c["FECHOU_MAXIMA_DIA"][1]),
        ("TRADES_2X + GEX_SUBINDO + WALL_SUBIU_3D", "Negócios Calls >= 2x + GEX subindo 3d + Call Wall subiu 3d",
         c["TRADES_CALL_2.0X"][1] & c["GEX_SUBINDO_3D"][1] & c["WALL_SUBIU_3D"][1]),
        ("PAREDE_SUBINDO_COM_FLUXO", "Call Wall subiu + Volume Calls >= 1.5x + Strike médio >= +2% acima do spot",
         c["WALL_SUBIU_3D"][1] & c["VOL_CALL_1.5X"][1] & c["FLUXO_STRIKE_ACIMA_2PCT"][1]),
        ("EXPLOSAO_OTM_COM_IV_BARATA", "Volume Calls OTM >= 2.0x + IV barata vs HV20 + Corredor livre >= 3%",
         c["VOL_OTM_CALL_2.0X"][1] & c["IV_BARATA_VS_HV"][1] & c["CORREDOR_LIVRE_WALL_3PCT"][1]),
        ("UNWIND_PAREDE_COM_VOLUME", "Desmonte de OI na Call Wall + Volume Calls >= 1.5x + Fechou na máxima",
         c["WALL_UNWIND"][1] & c["VOL_CALL_1.5X"][1] & c["FECHOU_MAXIMA_DIA"][1]),
        ("QUEDA_COM_COMPRA_PESADA_CALL", "Ação caiu hoje <= -1% + Volume Calls >= 2x + Strike médio >= +2% acima",
         c["ACAO_CAIU_HOJE_1PCT"][1] & c["VOL_CALL_2.0X"][1] & c["FLUXO_STRIKE_ACIMA_2PCT"][1]),
        ("SUPORTE_PUT_WALL_COM_FLUXO_CALL", "Perto da Put Wall + Volume Calls >= 1.5x + IV barata vs HV20",
         c["SUPORTE_PUT_WALL_PERTO"][1] & c["VOL_CALL_1.5X"][1] & c["IV_BARATA_VS_HV"][1]),
    ]
    for code, desc, m in triples:
        mask = m.fillna(False)
        if int(mask.sum()) >= 15:
            scenarios.append((code, desc, mask))

    results: list[dict[str, Any]] = []
    for code, desc, mask in scenarios:
        sub = panel.loc[mask]
        n_total = len(sub)
        if n_total < 20:
            continue
        sub_tr = sub.loc[~sub["is_oos"]]
        sub_oos = sub.loc[sub["is_oos"]]
        if len(sub_tr) < 8 or len(sub_oos) < 8:
            continue

        sub_opt = sub.dropna(subset=["opt_d5_max_ret", "opt_d5_close_ret"])
        sub_opt_tr = sub_opt.loc[~sub_opt["is_oos"]]
        sub_opt_oos = sub_opt.loc[sub_opt["is_oos"]]
        if len(sub_opt_tr) < 6 or len(sub_opt_oos) < 6:
            continue

        # Métricas D+1 (Tiro no dia seguinte)
        d1_h10_tr = float((sub_tr["stock_d1_high_from_close"] >= 0.01).mean())
        d1_h10_oos = float((sub_oos["stock_d1_high_from_close"] >= 0.01).mean())
        d1_h10_all = float((sub["stock_d1_high_from_close"] >= 0.01).mean())

        d1_h15_all = float((sub["stock_d1_high_from_close"] >= 0.015).mean())
        d1_pos_all = float((sub["stock_d1_close_from_close"] > 0).mean())

        opt_d1_hit20_tr = float((sub_opt_tr["opt_d1_max_ret"] >= 0.20).mean())
        opt_d1_hit20_oos = float((sub_opt_oos["opt_d1_max_ret"] >= 0.20).mean())
        opt_d1_hit20_all = float((sub_opt["opt_d1_max_ret"] >= 0.20).mean())
        opt_ev20_1d_all = float(sub_opt["opt_ev_target20_1d"].mean())

        # Métricas D+5 (Explosão em até 5 dias na ação e na CALL)
        d5_s20_all = float((sub["stock_d5_max_high"] >= 0.02).mean())
        d5_s30_all = float((sub["stock_d5_max_high"] >= 0.03).mean())

        opt_hit30_tr = float((sub_opt_tr["opt_d5_max_ret"] >= 0.30).mean())
        opt_hit30_oos = float((sub_opt_oos["opt_d5_max_ret"] >= 0.30).mean())
        opt_hit30_all = float((sub_opt["opt_d5_max_ret"] >= 0.30).mean())

        opt_hit50_tr = float((sub_opt_tr["opt_d5_max_ret"] >= 0.50).mean())
        opt_hit50_oos = float((sub_opt_oos["opt_d5_max_ret"] >= 0.50).mean())
        opt_hit50_all = float((sub_opt["opt_d5_max_ret"] >= 0.50).mean())

        opt_hit100_all = float((sub_opt["opt_d5_max_ret"] >= 1.00).mean())

        ev30_tr = float(sub_opt_tr["opt_ev_target30_5d"].mean())
        ev30_oos = float(sub_opt_oos["opt_ev_target30_5d"].mean())
        ev30_all = float(sub_opt["opt_ev_target30_5d"].mean())

        ev50_tr = float(sub_opt_tr["opt_ev_target50_5d"].mean())
        ev50_oos = float(sub_opt_oos["opt_ev_target50_5d"].mean())
        ev50_all = float(sub_opt["opt_ev_target50_5d"].mean())

        ev100_tr = float(sub_opt_tr["opt_ev_target100_5d"].mean())
        ev100_oos = float(sub_opt_oos["opt_ev_target100_5d"].mean())
        ev100_all = float(sub_opt["opt_ev_target100_5d"].mean())

        results.append({
            "code": code,
            "description": desc,
            "n_stock": n_total,
            "n_opt": len(sub_opt),
            "n_opt_train": len(sub_opt_tr),
            "n_opt_oos": len(sub_opt_oos),
            "tickers_count": int(sub_opt["ticker"].nunique()),
            "d1_high_1pct_all": d1_h10_all,
            "d1_high_1pct_train": d1_h10_tr,
            "d1_high_1pct_oos": d1_h10_oos,
            "d1_high_15pct_all": d1_h15_all,
            "d1_close_pos_all": d1_pos_all,
            "opt_d1_hit20_all": opt_d1_hit20_all,
            "opt_d1_hit20_train": opt_d1_hit20_tr,
            "opt_d1_hit20_oos": opt_d1_hit20_oos,
            "opt_ev20_1d_all": opt_ev20_1d_all,
            "d5_stock_up_2pct_all": d5_s20_all,
            "d5_stock_up_3pct_all": d5_s30_all,
            "opt_d5_hit30_all": opt_hit30_all,
            "opt_d5_hit30_train": opt_hit30_tr,
            "opt_d5_hit30_oos": opt_hit30_oos,
            "opt_d5_hit50_all": opt_hit50_all,
            "opt_d5_hit50_train": opt_hit50_tr,
            "opt_d5_hit50_oos": opt_hit50_oos,
            "opt_d5_hit100_all": opt_hit100_all,
            "ev30_all": ev30_all,
            "ev30_train": ev30_tr,
            "ev30_oos": ev30_oos,
            "ev30_min_split": min(ev30_tr, ev30_oos),
            "ev50_all": ev50_all,
            "ev50_train": ev50_tr,
            "ev50_oos": ev50_oos,
            "ev50_min_split": min(ev50_tr, ev50_oos),
            "ev100_all": ev100_all,
            "ev100_train": ev100_tr,
            "ev100_oos": ev100_oos,
            "ev100_min_split": min(ev100_tr, ev100_oos),
        })

    return {
        "baseline": base_stats,
        "scenarios_tested": len(scenarios),
        "scenarios_qualified": len(results),
        "results": results,
    }


def main() -> None:
    t0 = time.time()
    print(f"Carregando histórico de {len(LIQUID_TICKERS)} ativos líquidos em paralelo...")
    frames: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for ticker, df in zip(LIQUID_TICKERS, pool.map(load_ticker_panel, LIQUID_TICKERS)):
            if df is not None and not df.empty:
                frames.append(df)
                print(f"  [OK] {ticker}: {len(df)} pregões úteis com cadeia limpa")

    panel = pd.concat(frames, ignore_index=True)
    print(f"\nPainel consolidado: {len(panel)} ativo-pregões carregados em {time.time() - t0:.1f}s.")

    report = evaluate_patterns(panel)
    out_dir = Path("results/option_patterns")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "pattern_discovery_report.json"
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    res_df = pd.DataFrame(report["results"])
    res_df.to_csv(out_dir / "pattern_discovery_all.csv", index=False, encoding="utf-8-sig")

    base = report["baseline"]
    print("\n=== BASELINE INCONDICIONAL (QUALQUER DIA / SEM FILTRO) ===")
    print(f"Total Ativo-Pregões: {base['total_stock_days']} | Com CALL líquida: {base['total_option_days']} | Corte OOS: {base['cutoff_date']}")
    print(f"D+1 Ação bate >= +1.0% na máxima: {base['base_d1_high_1pct_rate']*100:.1f}% | >= +1.5%: {base['base_d1_high_15pct_rate']*100:.1f}%")
    print(f"D+1 CALL bate >= +20% na máxima:  {base['base_opt_d1_hit20_rate']*100:.1f}%")
    print(f"D+5 CALL bate >= +30%: {base['base_opt_d5_hit30_rate']*100:.1f}% | >= +50%: {base['base_opt_d5_hit50_rate']*100:.1f}% | >= +100%: {base['base_opt_d5_hit100_rate']*100:.1f}%")
    print(f"Expectativa 5d sem filtro: Alvo +30% = {base['base_opt_ev30_5d']*100:+.2f}% | Alvo +50% = {base['base_opt_ev50_5d']*100:+.2f}% | Alvo +100% = {base['base_opt_ev100_5d']*100:+.2f}%")

    # Top 1: Padrões consistentes para Tiro de D+1 (Máxima >= +1% na ação e +20% na CALL já no dia seguinte)
    d1_cons = res_df.loc[
        (res_df["d1_high_1pct_train"] >= base["base_d1_high_1pct_rate"] + 0.08)
        & (res_df["d1_high_1pct_oos"] >= base["base_d1_high_1pct_rate"] + 0.08)
        & (res_df["n_opt"] >= 35)
    ].sort_values("d1_high_1pct_all", ascending=False).head(10)

    print("\n=== TOP 10 PADRÕES: TIRO NO DIA SEGUINTE (D+1 MÁXIMA >= +1% NA AÇÃO / +20% NA CALL) ===")
    for r in d1_cons.itertuples(index=False):
        print(
            f"- [{r.code}] (n={r.n_opt}, {r.tickers_count} ativos) | "
            f"D+1 Máx >=+1%: {r.d1_high_1pct_all*100:.1f}% (Tr {r.d1_high_1pct_train*100:.1f}% / OOS {r.d1_high_1pct_oos*100:.1f}%) | "
            f"CALL >=+20% em D+1: {r.opt_d1_hit20_all*100:.1f}% | EV D+1: {r.opt_ev20_1d_all*100:+.2f}%"
        )

    # Top 2: Padrões consistentes para +30% e +50% na CALL em até 5 dias (positivos e fortes no Treino E no OOS)
    d5_cons = res_df.loc[
        (res_df["ev50_train"] > 0.06)
        & (res_df["ev50_oos"] > 0.06)
        & (res_df["opt_d5_hit30_train"] >= 0.50)
        & (res_df["opt_d5_hit30_oos"] >= 0.50)
        & (res_df["n_opt"] >= 30)
    ].sort_values("ev50_min_split", ascending=False).head(15)

    print("\n=== TOP 15 PADRÕES ESTÁVEIS (TREINO E OOS) PARA BUSCAR +30% / +50% / +100% EM 5 DIAS ===")
    for r in d5_cons.itertuples(index=False):
        print(
            f"- [{r.code}] (n={r.n_opt}: Tr {r.n_opt_train}/OOS {r.n_opt_oos}, {r.tickers_count} ativos)\n"
            f"    {r.description}\n"
            f"    Hit 5d CALL: >=+30%: {r.opt_d5_hit30_all*100:.1f}% (Tr {r.opt_d5_hit30_train*100:.1f}%/OOS {r.opt_d5_hit30_oos*100:.1f}%) | "
            f">=+50%: {r.opt_d5_hit50_all*100:.1f}% | >=+100%: {r.opt_d5_hit100_all*100:.1f}%\n"
            f"    EV 5d (Alvo +30%): {r.ev30_all*100:+.2f}% | EV 5d (Alvo +50%): {r.ev50_all*100:+.2f}% (Tr {r.ev50_train*100:+.2f}% / OOS {r.ev50_oos*100:+.2f}%) | "
            f"EV 5d (Alvo +100%): {r.ev100_all*100:+.2f}%"
        )


if __name__ == "__main__":
    main()
