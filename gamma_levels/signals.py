from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from .core import AnalysisResult, _normal_cdf


@dataclass(slots=True)
class SignalConfig:
    strength_min: float = 65.0
    reward_risk_min: float = 1.5
    horizon_days: int = 5
    delta_min: float = 0.50
    delta_max: float = 0.70
    iv_shock: float = 0.03
    buffer_step_fraction: float = 0.25
    monitor_interval_seconds: int = 60
    candidate_levels_per_setup: int = 3
    targets_count: int = 3
    trading_days: int = 252
    call_override: str | None = None
    put_override: str | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.strength_min <= 100:
            raise ValueError("strength_min deve estar entre 0 e 100")
        if self.reward_risk_min <= 0 or self.horizon_days < 0:
            raise ValueError("reward_risk_min deve ser positivo e horizon_days não negativo")
        if not 0 < self.delta_min < self.delta_max <= 1:
            raise ValueError("Faixa de delta inválida")
        if self.iv_shock < 0 or self.buffer_step_fraction < 0:
            raise ValueError("iv_shock e buffer_step_fraction devem ser não negativos")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SignalResult:
    score_by_strike: pd.DataFrame
    signals: pd.DataFrame
    option_candidates: pd.DataFrame
    config: SignalConfig


def _percentile(series: pd.Series, *, reverse: bool = False) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    valid = values.notna()
    out = pd.Series(0.0, index=series.index)
    if valid.any():
        ranked = values.loc[valid].rank(method="average", pct=True) * 100.0
        out.loc[valid] = 100.0 - ranked + (100.0 / max(int(valid.sum()), 1)) if reverse else ranked
    return out.clip(0.0, 100.0)


def _strength_label(value: float) -> str:
    if value >= 80:
        return "MUITO FORTE"
    if value >= 65:
        return "FORTE"
    if value >= 50:
        return "MODERADO"
    return "FRACO"


def _expiry_confirmation(options: pd.DataFrame, strikes: pd.Series, side: str) -> pd.Series:
    rows: list[dict[str, float]] = []
    selected = options.loc[options["option_type"].eq(side)].copy()
    for expiration, group in selected.groupby("expiration", sort=True):
        grouped = group.groupby("strike", as_index=False).agg(
            side_gex=("gex", lambda values: float(np.abs(values).sum())),
            expiry_weight=("expiry_weight", "median"),
        )
        if grouped.empty:
            continue
        threshold = float(grouped["side_gex"].quantile(0.75))
        for row in grouped.itertuples(index=False):
            rows.append({
                "strike": float(row.strike),
                "weight": float(row.expiry_weight),
                "confirmed": float(row.expiry_weight) if float(row.side_gex) >= threshold and float(row.side_gex) > 0 else 0.0,
            })
    if not rows:
        return pd.Series(0.0, index=strikes.index)
    frame = pd.DataFrame(rows)
    agg = frame.groupby("strike").agg(weight=("weight", "sum"), confirmed=("confirmed", "sum"))
    ratio = (agg["confirmed"] / agg["weight"].replace(0, np.nan) * 100.0).fillna(0.0)
    return strikes.map(ratio).fillna(0.0)


def build_strength_scores(result: AnalysisResult) -> pd.DataFrame:
    out = result.by_strike.copy()
    for label, side in (("support", "put"), ("resistance", "call")):
        composite_col = f"{label}_composite"
        wall_col = "put_wall_score" if side == "put" else "call_wall_score"
        out[f"{label}_component_composite"] = _percentile(out[composite_col])
        out[f"{label}_component_wall"] = _percentile(out[wall_col])
        out[f"{label}_component_expiry"] = _expiry_confirmation(result.options, out["strike"], side)
        greek_parts = pd.concat([
            _percentile(out[f"dex_{side}"].abs()),
            _percentile(out[f"vanna_exposure_{side}"].abs()),
            _percentile(out[f"charm_exposure_{side}"].abs()),
        ], axis=1)
        out[f"{label}_component_greeks"] = greek_parts.mean(axis=1)
        out[f"{label}_component_cluster"] = np.where(out["is_gamma_level"].fillna(False), 100.0, 0.0)
        liquidity = pd.concat([
            _percentile(out[f"oi_{side}"]),
            _percentile(out[f"volume_{side}"]),
        ], axis=1).mean(axis=1)
        out[f"{label}_component_liquidity"] = liquidity
        score = (
            0.30 * out[f"{label}_component_composite"]
            + 0.25 * out[f"{label}_component_wall"]
            + 0.20 * out[f"{label}_component_expiry"]
            + 0.10 * out[f"{label}_component_greeks"]
            + 0.10 * out[f"{label}_component_cluster"]
            + 0.05 * out[f"{label}_component_liquidity"]
        )
        side_is_valid = out[f"oi_{side}"].fillna(0).gt(0)
        out[f"{label}_strength"] = score.where(side_is_valid, 0.0).clip(0.0, 100.0)
        out[f"{label}_strength_label"] = out[f"{label}_strength"].map(_strength_label)
    return out


def _market_price(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    bid = pd.to_numeric(frame.get("bid"), errors="coerce")
    ask = pd.to_numeric(frame.get("ask"), errors="coerce")
    last = pd.to_numeric(frame.get("option_price"), errors="coerce")
    good_mid = bid.gt(0) & ask.gt(0) & ask.ge(bid)
    price = ((bid + ask) / 2.0).where(good_mid, last.where(last.gt(0)))
    source = pd.Series(np.where(good_mid, "MID", np.where(last.gt(0), "LAST", "SEM COTACAO")), index=frame.index)
    return price, source


def rank_option_candidates(options: pd.DataFrame, config: SignalConfig) -> pd.DataFrame:
    frame = options.copy()
    for column in ("delta", "bid", "ask", "option_price", "open_interest", "volume", "days_to_expiry", "implied_volatility"):
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    frame["abs_delta"] = frame["delta"].abs()
    frame["market_price"], frame["market_price_source"] = _market_price(frame)
    good_quote = frame["bid"].gt(0) & frame["ask"].gt(0) & frame["ask"].ge(frame["bid"])
    frame["spread_pct"] = ((frame["ask"] - frame["bid"]) / ((frame["ask"] + frame["bid"]) / 2.0)).where(good_quote)
    min_dte = config.horizon_days + 2
    output: list[pd.DataFrame] = []
    for side in ("call", "put"):
        side_frame = frame.loc[
            frame["option_type"].eq(side)
            & frame["days_to_expiry"].ge(min_dte)
            & frame["market_price"].gt(0)
        ].copy()
        if side_frame.empty:
            continue
        expirations = sorted(side_frame["days_to_expiry"].dropna().unique().tolist())
        selected = pd.DataFrame()
        delta_fallback = False
        for dte in expirations:
            bucket = side_frame.loc[side_frame["days_to_expiry"].eq(dte)].copy()
            selected = bucket.loc[bucket["abs_delta"].between(config.delta_min, config.delta_max)].copy()
            if not selected.empty:
                break
        if selected.empty:
            delta_fallback = True
            for dte in expirations:
                bucket = side_frame.loc[side_frame["days_to_expiry"].eq(dte)].copy()
                selected = bucket.loc[bucket["abs_delta"].between(max(0.05, config.delta_min - 0.10), min(0.95, config.delta_max + 0.10))].copy()
                if not selected.empty:
                    break
        if selected.empty:
            continue
        center = (config.delta_min + config.delta_max) / 2.0
        half = max((config.delta_max - config.delta_min) / 2.0, 0.01)
        selected["option_component_delta"] = (100.0 * (1.0 - (selected["abs_delta"] - center).abs() / half)).clip(0.0, 100.0)
        selected["option_component_spread"] = _percentile(selected["spread_pct"], reverse=True)
        selected["option_component_oi"] = _percentile(selected["open_interest"])
        selected["option_component_volume"] = _percentile(selected["volume"])
        iv_source = selected["iv_source"] if "iv_source" in selected else pd.Series("Profit", index=selected.index)
        selected["option_component_iv"] = np.where(iv_source.eq("Profit"), 100.0, 60.0)
        selected["option_score"] = (
            0.30 * selected["option_component_delta"]
            + 0.25 * selected["option_component_spread"]
            + 0.20 * selected["option_component_oi"]
            + 0.10 * selected["option_component_volume"]
            + 0.15 * selected["option_component_iv"]
        )
        selected["option_selection_flag"] = np.where(delta_fallback, "DELTA AMPLIADO", "OK")
        output.append(selected.sort_values("option_score", ascending=False).head(10))
    if not output:
        return pd.DataFrame()
    keep = [
        "ticker", "option_type", "strike", "expiration", "days_to_expiry", "abs_delta",
        "gamma", "implied_volatility", "iv_source", "open_interest", "volume", "bid", "ask",
        "market_price", "market_price_source", "spread_pct", "interest_rate", "dividend_yield",
        "time_to_expiry", "option_score", "option_selection_flag",
    ]
    return pd.concat(output, ignore_index=True)[[column for column in keep if column in output[0].columns]]


def black_scholes_price(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    option_type: str,
    interest_rate: float,
    dividend_yield: float,
) -> float:
    if spot <= 0 or strike <= 0 or volatility <= 0:
        return math.nan
    if time_to_expiry <= 0:
        return max(spot - strike, 0.0) if option_type == "call" else max(strike - spot, 0.0)
    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(spot / strike) + (interest_rate - dividend_yield + 0.5 * volatility**2) * time_to_expiry) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t
    cdf_d1 = float(_normal_cdf(np.array([d1]))[0])
    cdf_d2 = float(_normal_cdf(np.array([d2]))[0])
    if option_type == "call":
        return spot * math.exp(-dividend_yield * time_to_expiry) * cdf_d1 - strike * math.exp(-interest_rate * time_to_expiry) * cdf_d2
    return strike * math.exp(-interest_rate * time_to_expiry) * (1.0 - cdf_d2) - spot * math.exp(-dividend_yield * time_to_expiry) * (1.0 - cdf_d1)


def _target_pool(result: AnalysisResult, scores: pd.DataFrame) -> list[dict[str, Any]]:
    pool: list[dict[str, Any]] = []
    for row in scores.itertuples(index=False):
        if max(float(row.support_strength), float(row.resistance_strength)) >= 50 or bool(row.is_gamma_level):
            pool.append({"price": float(row.strike), "source": "Nivel estrutural"})
    summary = result.summary
    scalar_sources = {
        "max_pain": "Max Pain", "gamma_magnet": "Gamma Magnet", "gamma_flip": "Gamma Flip",
        "call_wall": "Call Wall", "put_wall": "Put Wall", "gamma_center": "Centro Gamma",
        "expected_move_iv_upper": "Expected Move superior", "expected_move_iv_lower": "Expected Move inferior",
    }
    for key, source in scalar_sources.items():
        value = summary.get(key)
        if value is not None and np.isfinite(value):
            pool.append({"price": float(value), "source": source})
    for key, source in (("support_levels", "Suporte composto"), ("resistance_levels", "Resistencia composta")):
        for value in summary.get(key) or []:
            if value is not None and np.isfinite(value):
                pool.append({"price": float(value), "source": source})
    return pool


def _pick_targets(pool: list[dict[str, Any]], entry: float, direction: str, spacing: float, count: int) -> list[dict[str, Any]]:
    candidates = [item for item in pool if item["price"] > entry + 1e-9] if direction == "ALTA" else [item for item in pool if item["price"] < entry - 1e-9]
    candidates.sort(key=lambda item: item["price"], reverse=direction == "BAIXA")
    tolerance = max(spacing / 2.0, 1e-6)
    selected: list[dict[str, Any]] = []
    for item in candidates:
        if any(abs(item["price"] - existing["price"]) <= tolerance for existing in selected):
            continue
        selected.append(item)
        if len(selected) == count:
            break
    return selected


def _option_projection(option: pd.Series | None, trigger: float, target: float, config: SignalConfig) -> dict[str, float | None]:
    empty = {"low": None, "base": None, "high": None, "entry_theoretical": None}
    if option is None:
        return empty
    try:
        strike = float(option["strike"])
        t = float(option["time_to_expiry"])
        iv = float(option["implied_volatility"])
        r = float(option.get("interest_rate", 0.0))
        q = float(option.get("dividend_yield", 0.0))
        side = str(option["option_type"])
    except (TypeError, ValueError, KeyError):
        return empty
    entry = black_scholes_price(trigger, strike, t, iv, side, r, q)
    if not np.isfinite(entry) or entry <= 0:
        return empty
    target_t = max(t - config.horizon_days / config.trading_days, 0.0)
    values: dict[str, float | None] = {"entry_theoretical": entry}
    for label, target_iv in (("low", max(0.0001, iv - config.iv_shock)), ("base", iv), ("high", iv + config.iv_shock)):
        price = black_scholes_price(target, strike, target_t, target_iv, side, r, q)
        values[label] = price / entry - 1.0 if np.isfinite(price) else None
    return values


def build_signals(result: AnalysisResult, config: SignalConfig | None = None) -> SignalResult:
    config = config or SignalConfig()
    scores = build_strength_scores(result)
    option_candidates = rank_option_candidates(result.options, config)
    selected_options: dict[str, pd.Series | None] = {"call": None, "put": None}
    if not option_candidates.empty:
        for side in selected_options:
            rows = option_candidates.loc[option_candidates["option_type"].eq(side)].sort_values("option_score", ascending=False)
            if not rows.empty:
                selected_options[side] = rows.iloc[0]
    for side, ticker in (("call", config.call_override), ("put", config.put_override)):
        if not ticker:
            continue
        source = result.options.loc[
            result.options.get("ticker", pd.Series("", index=result.options.index)).astype(str).str.upper().eq(str(ticker).strip().upper())
            & result.options["option_type"].eq(side)
            & result.options["days_to_expiry"].ge(config.horizon_days + 2)
        ].copy()
        if source.empty:
            continue
        source["abs_delta"] = pd.to_numeric(source["delta"], errors="coerce").abs()
        source["market_price"], source["market_price_source"] = _market_price(source)
        source = source.loc[source["market_price"].gt(0)]
        if source.empty:
            continue
        selected = source.iloc[0].copy()
        selected["option_score"] = 100.0
        selected["option_selection_flag"] = "OVERRIDE MANUAL"
        selected_options[side] = selected

    strikes = scores["strike"].sort_values()
    spacing = float(strikes.diff().dropna().median()) if len(strikes) > 1 else 0.0
    buffer_value = spacing * config.buffer_step_fraction
    pool = _target_pool(result, scores)
    spot = float(result.summary["spot"])
    setups = [
        ("CALL_REVERSAO", "ALTA", "support", "call", scores["strike"].le(spot)),
        ("CALL_ROMPIMENTO", "ALTA", "resistance", "call", scores["strike"].gt(spot)),
        ("PUT_REVERSAO", "BAIXA", "resistance", "put", scores["strike"].ge(spot)),
        ("PUT_ROMPIMENTO", "BAIXA", "support", "put", scores["strike"].lt(spot)),
    ]
    signal_rows: list[dict[str, Any]] = []
    for setup, direction, level_type, option_type, mask in setups:
        strength_col = f"{level_type}_strength"
        candidates = scores.loc[mask & scores[strength_col].gt(0)].copy()
        candidates["_distance"] = (candidates["strike"] - spot).abs()
        candidates = candidates.sort_values([strength_col, "_distance"], ascending=[False, True]).head(config.candidate_levels_per_setup)
        for level in candidates.itertuples(index=False):
            zone_low = float(level.zone_low)
            zone_high = float(level.zone_high)
            if direction == "ALTA":
                trigger = zone_high + buffer_value
                invalidation = zone_low - buffer_value
            else:
                trigger = zone_low - buffer_value
                invalidation = zone_high + buffer_value
            targets = _pick_targets(pool, trigger, direction, spacing, config.targets_count)
            risk = abs(trigger - invalidation)
            option = selected_options[option_type]
            row: dict[str, Any] = {
                "signal_id": f"{result.summary['valuation_date']}|{setup}|{float(level.strike):.4f}",
                "direction": direction,
                "setup": setup,
                "level_type": level_type,
                "level": float(level.strike),
                "zone_low": zone_low,
                "zone_high": zone_high,
                "buffer": buffer_value,
                "trigger": trigger,
                "invalidation": invalidation,
                "strength": float(getattr(level, strength_col)),
                "strength_label": _strength_label(float(getattr(level, strength_col))),
                "initial_state": "OBSERVAR",
                "has_viable_target": False,
                "selected_ticker": None if option is None else option.get("ticker"),
                "option_type": option_type,
                "option_strike": None if option is None else float(option["strike"]),
                "option_delta": None if option is None else float(option["abs_delta"]),
                "option_dte": None if option is None else float(option["days_to_expiry"]),
                "option_market_price": None if option is None else float(option["market_price"]),
                "option_price_source": None if option is None else option.get("market_price_source"),
                "option_iv_source": None if option is None else option.get("iv_source"),
                "option_score": None if option is None else float(option["option_score"]),
                "option_selection_flag": None if option is None else option.get("option_selection_flag"),
            }
            for target_index in range(1, config.targets_count + 1):
                if target_index <= len(targets):
                    target = targets[target_index - 1]
                    move = target["price"] / trigger - 1.0
                    rr = abs(target["price"] - trigger) / risk if risk > 0 else None
                    projection = _option_projection(option, trigger, target["price"], config)
                    row.update({
                        f"target_{target_index}": target["price"],
                        f"target_{target_index}_source": target["source"],
                        f"target_{target_index}_asset_pct": move,
                        f"target_{target_index}_rr": rr,
                        f"target_{target_index}_option_low_pct": projection["low"],
                        f"target_{target_index}_option_base_pct": projection["base"],
                        f"target_{target_index}_option_high_pct": projection["high"],
                    })
                    if rr is not None and rr >= config.reward_risk_min:
                        row["has_viable_target"] = True
                else:
                    for suffix in ("", "_source", "_asset_pct", "_rr", "_option_low_pct", "_option_base_pct", "_option_high_pct"):
                        row[f"target_{target_index}{suffix}"] = None
            if row["strength"] < config.strength_min:
                row["initial_state"] = "FORCA INSUFICIENTE"
            elif option is None:
                row["initial_state"] = "SEM OPCAO"
            elif not row["has_viable_target"]:
                row["initial_state"] = "SEM ESPACO"
            signal_rows.append(row)
    signals = pd.DataFrame(signal_rows)
    if not signals.empty:
        state_order = {"OBSERVAR": 0, "SEM ESPACO": 1, "SEM OPCAO": 2, "FORCA INSUFICIENTE": 3}
        signals["_state_order"] = signals["initial_state"].map(state_order).fillna(9)
        signals = signals.sort_values(["_state_order", "strength", "level"], ascending=[True, False, True]).drop(columns="_state_order").reset_index(drop=True)
    return SignalResult(score_by_strike=scores, signals=signals, option_candidates=option_candidates, config=config)
