from __future__ import annotations

import base64
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import httpx
import numpy as np
import pandas as pd

from .core import AnalysisConfig, AnalysisResult, analyze_chain


WIN_PATTERN = re.compile(r"^WIN([FGHJKMNQUVXZ])(\d{2})$")
FUTURE_MONTHS = {
    "F": 1,
    "G": 2,
    "H": 3,
    "J": 4,
    "K": 5,
    "M": 6,
    "N": 7,
    "Q": 8,
    "U": 9,
    "V": 10,
    "X": 11,
    "Z": 12,
}


def _number_pt(value: Any) -> float:
    text = str(value or "").strip().replace(".", "").replace(",", ".")
    return float(text) if text else math.nan


def asset_root(ticker: str) -> str:
    return re.sub(r"\d+$", "", str(ticker).strip().upper())


def future_expiration(ticker: str) -> date | None:
    match = WIN_PATTERN.fullmatch(str(ticker).upper())
    if not match:
        return None
    month = FUTURE_MONTHS[match.group(1)]
    year = 2000 + int(match.group(2))
    candidates = [date(year, month, 15) + timedelta(days=offset) for offset in range(-3, 4)]
    return min((day for day in candidates if day.weekday() == 2), key=lambda day: abs(day.day - 15))


def active_win_contract(prices: pd.DataFrame, trade_date: date) -> dict[str, Any]:
    """Escolhe o WIN líquido do dia sem confundir séries sem negociação."""
    candidates: list[dict[str, Any]] = []
    for row in prices.to_dict("records"):
        ticker = str(row.get("ticker") or "").upper()
        expiration = future_expiration(ticker)
        close = pd.to_numeric(pd.Series([row.get("close")]), errors="coerce").iloc[0]
        if expiration is None or expiration < trade_date or not np.isfinite(close) or close <= 0:
            continue
        item = dict(row)
        item["ticker"] = ticker
        item["expiration"] = expiration
        item["days_to_expiry"] = (expiration - trade_date).days
        candidates.append(item)
    if not candidates:
        raise ValueError(f"Nenhum contrato WIN negociado em {trade_date}")
    candidates.sort(
        key=lambda row: (
            float(row.get("financial_volume") or 0.0),
            float(row.get("contracts") or 0.0),
            -int(row["days_to_expiry"]),
        ),
        reverse=True,
    )
    return candidates[0]


def true_range(frame: pd.DataFrame) -> pd.Series:
    previous = pd.to_numeric(frame["close"], errors="coerce").shift(1)
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    return pd.concat([(high - low), (high - previous).abs(), (low - previous).abs()], axis=1).max(axis=1)


def atr(frame: pd.DataFrame, window: int = 20) -> float | None:
    if frame.empty:
        return None
    values = true_range(frame.sort_values("trade_date")).dropna()
    if values.empty:
        return None
    return float(values.tail(window).mean())


@dataclass(slots=True)
class IndexFuturesConfig:
    short_dte_min: int = 2
    short_dte_max: int = 9
    swing_dte_min: int = 10
    swing_dte_max: int = 45
    beta_window: int = 60
    beta_min_observations: int = 40
    zone_merge_atr: float = 0.20
    zone_padding_atr: float = 0.05
    battle_min_share: float = 0.30
    breakout_atr: float = 0.10
    stop_padding_atr: float = 0.25
    short_time_stop: int = 5
    swing_time_stop: int = 10
    min_distinct_strikes: int = 5
    min_iv_coverage: float = 0.60
    ibov_source_weight: float = 1.00
    bova_source_weight: float = 0.75
    component_source_weight: float = 1.00
    min_atr_points: float = 100.0
    max_level_distance_atr: float = 4.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DailyIndexMap:
    context: dict[str, Any]
    levels: pd.DataFrame
    zones: pd.DataFrame
    source_summary: pd.DataFrame
    quality: pd.DataFrame


class IndexCompositionClient:
    URL = "https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/"
    SOURCE_URL = "https://sistemaswebb3-listados.b3.com.br/indexPage/day/IBOV?language=pt-br"

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def fetch(self) -> pd.DataFrame:
        payload = {
            "language": "pt-br",
            "pageNumber": 1,
            "pageSize": 120,
            "index": "IBOV",
            "segment": "1",
        }
        token = base64.b64encode(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        ).decode()
        response = httpx.get(
            self.URL + token,
            timeout=self.timeout,
            headers={"User-Agent": "GammaLevelsIndex/0.1"},
        )
        response.raise_for_status()
        body = response.json()
        as_of = datetime.strptime(body["header"]["date"], "%d/%m/%y").date()
        rows = []
        for item in body.get("results") or []:
            ticker = str(item.get("cod") or "").strip().upper()
            if not ticker:
                continue
            rows.append(
                {
                    "as_of": as_of.isoformat(),
                    "ticker": ticker,
                    "asset_root": asset_root(ticker),
                    "weight": _number_pt(item.get("part")) / 100.0,
                    "theoretical_quantity": _number_pt(item.get("theoricalQty")),
                    "asset": item.get("asset"),
                    "type": item.get("type"),
                    "source_url": self.SOURCE_URL,
                }
            )
        frame = pd.DataFrame(rows)
        if frame.empty or not math.isclose(float(frame["weight"].sum()), 1.0, abs_tol=0.02):
            raise ValueError("Carteira IBOV vazia ou pesos não reconciliados")
        return frame.sort_values("weight", ascending=False).reset_index(drop=True)


def infer_preferred_underliers(instruments: pd.DataFrame) -> dict[str, str]:
    if instruments.empty or "instrument_type" not in instruments:
        return {}
    options = instruments[
        instruments["instrument_type"].eq("option")
        & instruments.get("underlying_ticker", pd.Series(index=instruments.index, dtype=object)).notna()
    ]
    preferred: dict[str, str] = {}
    for root, group in options.groupby("asset_root"):
        counts = group["underlying_ticker"].astype(str).value_counts()
        if not counts.empty:
            preferred[str(root)] = str(counts.index[0])
    return preferred


def prepare_option_market(
    prices: pd.DataFrame,
    references: pd.DataFrame,
    known_roots: Iterable[str],
    instruments: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Une PR e PE uma única vez e atribui raiz/subjacente de forma auditável."""
    if prices.empty or references.empty:
        return pd.DataFrame()
    price_columns = [
        column
        for column in (
            "ticker", "open", "low", "high", "close", "bid", "ask", "trades",
            "contracts", "financial_volume", "open_interest",
        )
        if column in prices
    ]
    frame = references.merge(prices[price_columns], on="ticker", how="left")
    roots = sorted({str(root).upper() for root in known_roots if root}, key=len, reverse=True)
    instrument_map: dict[str, tuple[str, str | None]] = {}
    if instruments is not None and not instruments.empty:
        for item in instruments.to_dict("records"):
            if item.get("instrument_type") != "option":
                continue
            instrument_map[str(item.get("ticker"))] = (
                str(item.get("asset_root") or ""),
                str(item.get("underlying_ticker")) if item.get("underlying_ticker") else None,
            )

    def identify(ticker: str) -> tuple[str | None, str | None, str]:
        if ticker in instrument_map:
            root, underlier = instrument_map[ticker]
            return root, underlier, "instrument"
        root = next((candidate for candidate in roots if ticker.startswith(candidate)), None)
        return root, None, "prefix" if root else "unknown"

    identified = [identify(str(ticker).upper()) for ticker in frame["ticker"]]
    frame["asset_root"] = [item[0] for item in identified]
    frame["underlying_ticker"] = [item[1] for item in identified]
    frame["root_source"] = [item[2] for item in identified]
    return frame[frame["asset_root"].notna()].reset_index(drop=True)


def _mid_price(frame: pd.DataFrame) -> pd.Series:
    bid = pd.to_numeric(frame.get("bid"), errors="coerce")
    ask = pd.to_numeric(frame.get("ask"), errors="coerce")
    midpoint = (bid + ask) / 2.0
    valid_mid = bid.gt(0) & ask.gt(0) & ask.ge(bid)
    reference = pd.to_numeric(frame.get("reference_price"), errors="coerce")
    close = pd.to_numeric(frame.get("close"), errors="coerce")
    return midpoint.where(valid_mid, reference.where(reference.gt(0), close))


def build_chain(
    market: pd.DataFrame,
    previous_market: pd.DataFrame,
    *,
    root: str,
    spot: float,
    multiplier: float,
    rate: float,
    dividend_yield: float,
    valuation_date: date,
    dte_min: int,
    dte_max: int,
    underlier: str | None = None,
) -> pd.DataFrame:
    current = market[market["asset_root"].eq(root)].copy()
    if underlier and current["underlying_ticker"].notna().any():
        current = current[current["underlying_ticker"].eq(underlier)]
    if current.empty:
        return current
    current["expiration"] = pd.to_datetime(current["expiration"], errors="coerce").dt.normalize()
    current["days_to_expiry"] = (current["expiration"] - pd.Timestamp(valuation_date)).dt.days
    current = current[current["days_to_expiry"].between(dte_min, dte_max)]
    if current.empty:
        return current
    previous = previous_market[["ticker", "open_interest"]].rename(
        columns={"open_interest": "previous_open_interest"}
    ) if not previous_market.empty else pd.DataFrame(columns=["ticker", "previous_open_interest"])
    current = current.merge(previous, on="ticker", how="left")
    current["volume"] = pd.to_numeric(current.get("contracts"), errors="coerce").fillna(0.0)
    current["option_price"] = _mid_price(current)
    current["underlying_price"] = spot
    current["multiplier"] = multiplier
    current["interest_rate"] = rate
    current["dividend_yield"] = dividend_yield
    keep = [
        "ticker", "option_type", "strike", "expiration", "open_interest",
        "previous_open_interest", "volume", "implied_volatility", "option_price",
        "underlying_price", "multiplier", "interest_rate", "dividend_yield",
    ]
    for column in keep:
        if column not in current:
            current[column] = np.nan
    return current[keep].reset_index(drop=True)


def chain_quality(chain: pd.DataFrame, config: IndexFuturesConfig) -> dict[str, Any]:
    if chain.empty:
        return {"valid": False, "reason": "sem opções", "score": 0.0}
    oi = pd.to_numeric(chain["open_interest"], errors="coerce").fillna(0.0)
    active = chain[oi.gt(0)]
    calls = active[active["option_type"].eq("call")]
    puts = active[active["option_type"].eq("put")]
    iv_coverage = float(pd.to_numeric(active["implied_volatility"], errors="coerce").gt(0).mean()) if not active.empty else 0.0
    strikes = int(active["strike"].nunique())
    valid = not calls.empty and not puts.empty and strikes >= config.min_distinct_strikes and iv_coverage >= config.min_iv_coverage
    reasons = []
    if calls.empty or puts.empty:
        reasons.append("cadeia sem os dois lados")
    if strikes < config.min_distinct_strikes:
        reasons.append(f"{strikes} strikes < {config.min_distinct_strikes}")
    if iv_coverage < config.min_iv_coverage:
        reasons.append(f"IV válida {iv_coverage:.0%}")
    score = min(strikes / max(config.min_distinct_strikes * 3, 1), 1.0) * 0.4 + min(iv_coverage, 1.0) * 0.3
    score += 0.3 if not calls.empty and not puts.empty else 0.0
    return {
        "valid": valid,
        "reason": "; ".join(reasons) if reasons else "OK",
        "score": float(score),
        "options": int(len(chain)),
        "active_options": int(len(active)),
        "strikes": strikes,
        "iv_coverage": iv_coverage,
        "open_interest": float(oi.sum()),
        "financial_volume": float(pd.to_numeric(chain.get("financial_volume"), errors="coerce").fillna(0).sum()) if "financial_volume" in chain else None,
    }


def analyze_horizon_chain(
    chain: pd.DataFrame, valuation_date: date, spot: float
) -> AnalysisResult:
    usable = chain[
        pd.to_numeric(chain["implied_volatility"], errors="coerce").gt(0)
        & pd.to_numeric(chain["open_interest"], errors="coerce").ge(0)
    ].copy()
    if usable.empty:
        raise ValueError("Cadeia sem opções com IV válida")
    return analyze_chain(
        usable,
        AnalysisConfig(
            valuation_date=valuation_date,
            spot=spot,
            multiplier=float(pd.to_numeric(usable["multiplier"], errors="coerce").median()),
            interest_rate=float(pd.to_numeric(usable["interest_rate"], errors="coerce").median()),
            dividend_yield=float(pd.to_numeric(usable["dividend_yield"], errors="coerce").median()),
            use_vendor_greeks=False,
            flip_grid_points=151,
        ),
    )


def _strike_score(result: AnalysisResult, strike: float, score_column: str) -> float:
    if result.by_strike.empty or score_column not in result.by_strike:
        return 0.0
    index = (result.by_strike["strike"] - strike).abs().idxmin()
    value = result.by_strike.loc[index, score_column]
    column = pd.to_numeric(result.by_strike[score_column], errors="coerce").abs()
    maximum = float(column.max()) if column.notna().any() else 0.0
    return float(abs(value) / maximum) if maximum > 0 and pd.notna(value) else 0.0


def source_levels(
    result: AnalysisResult,
    *,
    trade_date: date,
    horizon: str,
    source: str,
    source_family: str,
    source_weight: float,
    quality_score: float,
    map_level,
    component_ticker: str | None = None,
    component_weight: float | None = None,
    beta: float | None = None,
) -> list[dict[str, Any]]:
    summary = result.summary
    definitions = [
        ("put_wall", "BUYER", "put_wall_score"),
        ("put_support_level", "BUYER", "put_support_score"),
        ("call_wall", "SELLER", "call_wall_score"),
        ("call_resistance_level", "SELLER", "call_resistance_score"),
        ("gamma_flip", "NEUTRAL", "gex_net"),
        ("gamma_magnet", "NEUTRAL", "magnet_score"),
    ]
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()
    for kind, side, score_column in definitions:
        value = summary.get(kind)
        if value is None or not np.isfinite(float(value)):
            continue
        level = float(value)
        key = (side, round(level, 8))
        if key in seen:
            continue
        seen.add(key)
        normalized = _strike_score(result, level, score_column)
        strength = source_weight * quality_score * max(normalized, 0.05)
        if component_weight is not None:
            strength *= max(component_weight, 0.0)
        mapped = map_level(level)
        if mapped is None or not np.isfinite(float(mapped)) or float(mapped) <= 0:
            continue
        rows.append(
            {
                "trade_date": trade_date.isoformat(),
                "horizon": horizon,
                "source": source,
                "source_family": source_family,
                "component_ticker": component_ticker,
                "level_kind": kind,
                "side": side,
                "source_level": level,
                "win_level": float(mapped),
                "strength": float(strength),
                "quality_score": float(quality_score),
                "component_weight": component_weight,
                "beta": beta,
            }
        )
    return rows


def estimate_beta(
    component: pd.DataFrame,
    index: pd.DataFrame,
    *,
    window: int = 60,
    min_observations: int = 40,
) -> tuple[float, int, bool]:
    left = component[["trade_date", "close"]].copy()
    right = index[["trade_date", "close"]].copy()
    merged = left.merge(right, on="trade_date", suffixes=("_asset", "_index")).sort_values("trade_date")
    returns = merged[["close_asset", "close_index"]].pct_change().dropna().tail(window)
    if len(returns) < min_observations or float(returns["close_index"].var(ddof=1)) <= 0:
        return 1.0, int(len(returns)), True
    beta = float(returns["close_asset"].cov(returns["close_index"]) / returns["close_index"].var(ddof=1))
    if not np.isfinite(beta) or beta <= 0.2 or beta > 3.0:
        return 1.0, int(len(returns)), True
    return beta, int(len(returns)), False


def cluster_levels(
    levels: pd.DataFrame,
    *,
    atr_points: float,
    config: IndexFuturesConfig,
) -> pd.DataFrame:
    if levels.empty:
        return pd.DataFrame()
    merge_distance = max(float(atr_points) * config.zone_merge_atr, 5.0)
    padding = max(float(atr_points) * config.zone_padding_atr, 5.0)
    rows: list[dict[str, Any]] = []
    for horizon, horizon_levels in levels.groupby("horizon", sort=False):
        ordered = horizon_levels.sort_values("win_level").reset_index(drop=True)
        clusters: list[list[dict[str, Any]]] = []
        for item in ordered.to_dict("records"):
            current_center = (
                float(np.mean([float(member["win_level"]) for member in clusters[-1]]))
                if clusters else None
            )
            if not clusters or abs(float(item["win_level"]) - float(current_center)) > merge_distance:
                clusters.append([item])
            else:
                clusters[-1].append(item)
        for number, items in enumerate(clusters, 1):
            strength = np.array([max(float(item["strength"]), 0.0) for item in items])
            points = np.array([float(item["win_level"]) for item in items])
            total = float(strength.sum())
            center = float(np.average(points, weights=strength)) if total > 0 else float(points.mean())
            buyer = float(sum(item["strength"] for item in items if item["side"] == "BUYER"))
            seller = float(sum(item["strength"] for item in items if item["side"] == "SELLER"))
            buyer_share = buyer / total if total else 0.0
            seller_share = seller / total if total else 0.0
            if buyer_share >= config.battle_min_share and seller_share >= config.battle_min_share:
                zone_type = "BATTLE"
            elif buyer > seller:
                zone_type = "BUYER"
            elif seller > buyer:
                zone_type = "SELLER"
            else:
                zone_type = "NEUTRAL"
            families = sorted({str(item["source_family"]) for item in items})
            sources = sorted({str(item["source"]) for item in items})
            rows.append(
                {
                    "trade_date": items[0]["trade_date"],
                    "horizon": horizon,
                    "zone_id": f"{items[0]['trade_date']}:{horizon}:{number}",
                    "zone_low": float(points.min() - padding),
                    "zone_high": float(points.max() + padding),
                    "zone_center": center,
                    "zone_type": zone_type,
                    "strength": total,
                    "buyer_score": buyer,
                    "seller_score": seller,
                    "buyer_share": buyer_share,
                    "seller_share": seller_share,
                    "source_families": ";".join(families),
                    "sources": ";".join(sources),
                    "family_count": len(families),
                    "level_count": len(items),
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    percentile = out.groupby("horizon")["strength"].rank(pct=True)
    out["confidence"] = np.select(
        [(out["family_count"] >= 2) & (percentile >= 0.60), (out["family_count"] >= 2) | (percentile >= 0.40)],
        ["HIGH", "MEDIUM"],
        default="LOW",
    )
    return out.sort_values(["horizon", "zone_center"]).reset_index(drop=True)


def implied_dividend_yield(
    spot: float, future: float, rate: float, days_to_expiry: int
) -> float:
    if spot <= 0 or future <= 0 or days_to_expiry <= 0:
        return 0.0
    years = days_to_expiry / 365.0
    value = rate - math.log(future / spot) / years
    return float(min(max(value, -0.10), 0.50))


def build_daily_map(
    *,
    trade_date: date,
    prices: pd.DataFrame,
    index_row: dict[str, Any] | None,
    option_market: pd.DataFrame,
    previous_option_market: pd.DataFrame,
    composition: pd.DataFrame,
    instruments: pd.DataFrame,
    component_histories: dict[str, pd.DataFrame] | None = None,
    index_history: pd.DataFrame | None = None,
    win_history: pd.DataFrame | None = None,
    rate: float = 0.15,
    config: IndexFuturesConfig | None = None,
    source_families: set[str] | None = None,
) -> DailyIndexMap:
    config = config or IndexFuturesConfig()
    enabled_families = source_families or {"IBOV", "BOVA", "COMPONENT"}
    ibov_close = (
        float(index_row["close"])
        if index_row is not None and pd.notna(index_row.get("close"))
        else math.nan
    )
    win = active_win_contract(prices, trade_date)
    win_close = float(win["close"])
    bova_rows = prices[prices["ticker"].eq("BOVA11")]
    bova_close = float(bova_rows.iloc[0]["close"]) if not bova_rows.empty else math.nan
    atr_points = atr(win_history if win_history is not None else pd.DataFrame())
    atr_points = max(float(atr_points or 0.0), config.min_atr_points)
    dividend_yield = (
        implied_dividend_yield(ibov_close, win_close, rate, int(win["days_to_expiry"]))
        if np.isfinite(ibov_close) and ibov_close > 0
        else 0.0
    )
    horizons = {
        "SHORT": (config.short_dte_min, config.short_dte_max),
        "SWING": (config.swing_dte_min, config.swing_dte_max),
    }
    price_map = {
        str(row.ticker): float(row.close)
        for row in prices.dropna(subset=["close"]).itertuples()
    }
    level_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []

    def analyze_source(
        root: str,
        spot: float,
        multiplier: float,
        source: str,
        family: str,
        source_weight: float,
        underlier: str | None,
        mapper,
        component_weight: float | None = None,
        beta_value: float | None = None,
    ) -> None:
        for horizon, (dte_min, dte_max) in horizons.items():
            chain = build_chain(
                option_market,
                previous_option_market,
                root=root,
                spot=spot,
                multiplier=multiplier,
                rate=rate,
                dividend_yield=dividend_yield if family in {"IBOV", "BOVA"} else 0.0,
                valuation_date=trade_date,
                dte_min=dte_min,
                dte_max=dte_max,
                underlier=underlier,
            )
            quality = chain_quality(chain, config)
            quality_rows.append(
                {
                    "trade_date": trade_date.isoformat(),
                    "horizon": horizon,
                    "source": source,
                    "source_family": family,
                    "underlier": underlier,
                    **quality,
                }
            )
            if not quality["valid"]:
                continue
            try:
                result = analyze_horizon_chain(chain, trade_date, spot)
            except ValueError as exc:
                quality_rows[-1]["valid"] = False
                quality_rows[-1]["reason"] = str(exc)
                continue
            summaries.append(
                {
                    "trade_date": trade_date.isoformat(),
                    "horizon": horizon,
                    "source": source,
                    "source_family": family,
                    "underlier": underlier,
                    "spot": spot,
                    "gex_total": result.summary.get("gex_total"),
                    "gamma_flip": result.summary.get("gamma_flip"),
                    "gamma_magnet": result.summary.get("gamma_magnet"),
                    "call_wall": result.summary.get("call_wall"),
                    "put_wall": result.summary.get("put_wall"),
                    "expected_move": result.summary.get("expected_move_iv"),
                    "quality_score": quality["score"],
                }
            )
            level_rows.extend(
                source_levels(
                    result,
                    trade_date=trade_date,
                    horizon=horizon,
                    source=source,
                    source_family=family,
                    source_weight=source_weight,
                    quality_score=float(quality["score"]),
                    map_level=mapper,
                    component_ticker=underlier if family == "COMPONENT" else None,
                    component_weight=component_weight,
                    beta=beta_value,
                )
            )

    if "IBOV" in enabled_families and np.isfinite(ibov_close) and ibov_close > 0:
        analyze_source(
            "IBOV", ibov_close, 0.01, "IBOV", "IBOV", config.ibov_source_weight,
            None, lambda level: level * win_close / ibov_close,
        )
    if "BOVA" in enabled_families and np.isfinite(bova_close) and bova_close > 0:
        analyze_source(
            "BOVA", bova_close, 100.0, "BOVA11", "BOVA", config.bova_source_weight,
            "BOVA11", lambda level: level * win_close / bova_close,
        )

    component_histories = component_histories or {}
    index_history = index_history if index_history is not None else pd.DataFrame()
    for item in (
        composition.to_dict("records")
        if "COMPONENT" in enabled_families and not composition.empty
        else []
    ):
        ticker = str(item["ticker"])
        root = str(item.get("asset_root") or asset_root(ticker))
        spot = price_map.get(ticker)
        if spot is None or spot <= 0:
            continue
        beta_value, observations, fallback = estimate_beta(
            component_histories.get(ticker, pd.DataFrame(columns=["trade_date", "close"])),
            index_history if not index_history.empty else pd.DataFrame(columns=["trade_date", "close"]),
            window=config.beta_window,
            min_observations=config.beta_min_observations,
        )

        def component_mapper(level: float, s: float = spot, beta: float = beta_value) -> float:
            return win_close * (1.0 + ((level / s) - 1.0) / beta)

        analyze_source(
            root,
            spot,
            100.0,
            ticker,
            "COMPONENT",
            config.component_source_weight,
            ticker,
            component_mapper,
            component_weight=float(item.get("weight") or 0.0),
            beta_value=beta_value,
        )
        if fallback:
            for row in quality_rows:
                if row.get("source") == ticker:
                    row["reason"] = f"{row['reason']}; beta=1 fallback ({observations} obs.)"

    levels = pd.DataFrame(level_rows)
    raw_level_count = len(levels)
    if not levels.empty:
        levels = levels[
            levels["win_level"].sub(win_close).abs().le(config.max_level_distance_atr * atr_points)
        ].reset_index(drop=True)
    zones = cluster_levels(levels, atr_points=atr_points, config=config)
    context = {
        "trade_date": trade_date.isoformat(),
        "ibov_close": ibov_close if np.isfinite(ibov_close) else None,
        "ibov_settlement": index_row.get("settlement_value") if index_row else None,
        "bova_close": bova_close if np.isfinite(bova_close) else None,
        "win_ticker": win["ticker"],
        "win_close": win_close,
        "win_expiration": win["expiration"].isoformat(),
        "win_dte": int(win["days_to_expiry"]),
        "basis_points": (
            win_close - ibov_close if np.isfinite(ibov_close) else None
        ),
        "scale_win_ibov": (
            win_close / ibov_close
            if np.isfinite(ibov_close) and ibov_close > 0 else None
        ),
        "atr20": atr_points,
        "atr_points": atr_points,
        "interest_rate": rate,
        "implied_dividend_yield": dividend_yield,
        "source_families": sorted(enabled_families),
        "composition_as_of": str(composition["as_of"].max()) if not composition.empty else None,
        "raw_level_count": raw_level_count,
        "operational_level_count": len(levels),
        "excluded_far_level_count": raw_level_count - len(levels),
        "config": config.to_dict(),
    }
    return DailyIndexMap(
        context=context,
        levels=levels,
        zones=zones,
        source_summary=pd.DataFrame(summaries),
        quality=pd.DataFrame(quality_rows),
    )
