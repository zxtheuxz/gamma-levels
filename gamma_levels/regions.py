from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd

from .storage import Database


@dataclass(slots=True)
class RegionConfig:
    lookback: int = 100
    tolerance_atr: float = 0.35
    touch_separation: int = 3
    move_away_atr: float = 0.75
    rsi_period: int = 14
    ema_fast: int = 20
    ema_slow: int = 50

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def adjusted_bars(
    database: Database, ticker: str, end_date: date, limit: int = 140,
    shared_cache: dict[tuple[Any, ...], Any] | None = None,
) -> pd.DataFrame:
    """Retorna preços ajustados somente por eventos efetivos até end_date.

    As colunas OHLC brutas são preservadas com prefixo raw_. A série ajustada termina
    na mesma escala do preço bruto de end_date, evitando olhar eventos futuros.
    """
    cache_key = ("adjusted_bars", ticker, end_date.isoformat(), limit)
    if shared_cache is not None and cache_key in shared_cache:
        return shared_cache[cache_key].copy()
    bars = database.bars(ticker, end_date, limit).copy()
    if bars.empty:
        return bars
    for column in ("open", "low", "high", "close", "volume"):
        bars[column] = pd.to_numeric(bars[column], errors="coerce")
        bars[f"raw_{column}"] = bars[column]
    actions = database.frame(
        """SELECT * FROM corporate_actions WHERE ticker=? AND ex_date<=?
        ORDER BY ex_date""",
        (ticker, end_date.isoformat()),
    )
    if actions.empty:
        if shared_cache is not None:
            shared_cache[cache_key] = bars.copy()
        return bars
    dates = pd.to_datetime(bars["trade_date"])
    for action in actions.itertuples(index=False):
        ex_date = pd.Timestamp(action.ex_date)
        prior_mask = dates < ex_date
        if not prior_mask.any():
            continue
        factor = float(action.quantity_factor or 1.0)
        cash = float(action.cash_amount or 0.0)
        if factor > 0 and not np.isclose(factor, 1.0):
            for column in ("open", "low", "high", "close"):
                bars.loc[prior_mask, column] = bars.loc[prior_mask, column] / factor
            bars.loc[prior_mask, "volume"] = bars.loc[prior_mask, "volume"] * factor
        if cash > 0:
            previous = bars.loc[prior_mask, "close"].dropna()
            if previous.empty:
                continue
            previous_close = float(previous.iloc[-1])
            cash_factor = max((previous_close - cash) / previous_close, 0.01)
            for column in ("open", "low", "high", "close"):
                bars.loc[prior_mask, column] = bars.loc[prior_mask, column] * cash_factor
    if shared_cache is not None:
        shared_cache[cache_key] = bars.copy()
    return bars


def _atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    previous = bars["close"].shift(1)
    ranges = pd.concat(
        [bars["high"] - bars["low"], (bars["high"] - previous).abs(), (bars["low"] - previous).abs()],
        axis=1,
    ).max(axis=1)
    return ranges.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


class RegionEngine:
    def __init__(
        self, database: Database, config: RegionConfig | None = None,
        shared_cache: dict[tuple[Any, ...], Any] | None = None,
    ) -> None:
        self.database = database
        self.config = config or RegionConfig()
        self.shared_cache = shared_cache

    def features(self, ticker: str, trade_date: date, levels: dict[str, Any] | None = None) -> dict[str, Any]:
        level_values = levels or {}
        cache_key = (
            "region_features", ticker, trade_date.isoformat(), self.config.lookback,
            self.config.tolerance_atr, self.config.touch_separation, self.config.move_away_atr,
            self.config.rsi_period, self.config.ema_fast, self.config.ema_slow,
            *(level_values.get(name) for name in ("put_wall", "call_wall", "gamma_flip", "max_pain")),
        )
        if self.shared_cache is not None and cache_key in self.shared_cache:
            return deepcopy(self.shared_cache[cache_key])
        bars = adjusted_bars(
            self.database, ticker, trade_date, max(140, self.config.lookback + 20), self.shared_cache
        )
        if len(bars) < 50:
            return {"data_quality": "INCOMPLETO", "region_score": 0.0, "support": None, "resistance": None}
        bars = bars.dropna(subset=["open", "low", "high", "close"]).reset_index(drop=True)
        bars["atr"] = _atr(bars)
        bars["rsi"] = _rsi(bars["close"], self.config.rsi_period)
        bars["ema_fast"] = bars["close"].ewm(span=self.config.ema_fast, adjust=False).mean()
        bars["ema_slow"] = bars["close"].ewm(span=self.config.ema_slow, adjust=False).mean()
        current = bars.iloc[-1]
        atr = float(current["atr"])
        if not np.isfinite(atr) or atr <= 0:
            return {"data_quality": "INCOMPLETO", "region_score": 0.0, "support": None, "resistance": None}
        window = bars.iloc[-self.config.lookback :].copy()
        pivots: list[dict[str, Any]] = []
        # Um pivô usa dois candles à direita; o último pivô elegível termina em D-3.
        for index in range(2, len(window) - 2):
            row = window.iloc[index]
            neighborhood = window.iloc[index - 2 : index + 3]
            if float(row["low"]) <= float(neighborhood["low"].min()):
                pivots.append({"kind": "support", "price": float(row["low"]), "index": index})
            if float(row["high"]) >= float(neighborhood["high"].max()):
                pivots.append({"kind": "resistance", "price": float(row["high"]), "index": index})
        for lookback in (20, 50, min(100, len(window))):
            sample = window.iloc[-lookback:]
            pivots.append({"kind": "support", "price": float(sample["low"].min()), "index": len(window) - 1})
            pivots.append({"kind": "resistance", "price": float(sample["high"].max()), "index": len(window) - 1})

        spot = float(current["close"])
        derivative_levels = level_values
        for name in ("put_wall", "gamma_flip", "max_pain"):
            value = derivative_levels.get(name)
            if value is not None and float(value) <= spot + atr:
                pivots.append({"kind": "support", "price": float(value), "index": len(window) - 1, "source": name})
        call_wall = derivative_levels.get("call_wall")
        if call_wall is not None and float(call_wall) >= spot - atr:
            pivots.append({"kind": "resistance", "price": float(call_wall), "index": len(window) - 1, "source": "call_wall"})
        for name in ("ema_fast", "ema_slow"):
            pivots.append({"kind": "support" if float(current[name]) <= spot else "resistance", "price": float(current[name]), "index": len(window) - 1, "source": name})

        support = self._best_region(window, [item for item in pivots if item["kind"] == "support"], spot, atr, "support")
        resistance = self._best_region(window, [item for item in pivots if item["kind"] == "resistance"], spot, atr, "resistance")
        chosen = support if support and abs(spot - support["center"]) <= (abs((resistance or {}).get("center", spot + 99 * atr) - spot)) else resistance
        region_score = float((chosen or {}).get("score", 0.0))
        result = {
            "data_quality": "OK",
            "spot_adjusted": spot,
            "atr_adjusted": atr,
            "rsi": float(current["rsi"]),
            "ema_fast": float(current["ema_fast"]),
            "ema_slow": float(current["ema_slow"]),
            "support": support,
            "resistance": resistance,
            "region_score": region_score,
            "config": self.config.to_dict(),
        }
        if self.shared_cache is not None:
            self.shared_cache[cache_key] = deepcopy(result)
        return result

    def _best_region(
        self, bars: pd.DataFrame, candidates: list[dict[str, Any]], spot: float, atr: float, kind: str
    ) -> dict[str, Any] | None:
        if not candidates:
            return None
        tolerance = self.config.tolerance_atr * atr
        clusters: list[list[dict[str, Any]]] = []
        for candidate in sorted(candidates, key=lambda item: item["price"]):
            if clusters and abs(candidate["price"] - np.mean([item["price"] for item in clusters[-1]])) <= tolerance:
                clusters[-1].append(candidate)
            else:
                clusters.append([candidate])
        regions = []
        for cluster in clusters:
            center = float(np.mean([item["price"] for item in cluster]))
            touch_indexes: list[int] = []
            reactions: list[float] = []
            rejection_scores: list[float] = []
            for index, row in bars.iterrows():
                touched = float(row["low"]) <= center + tolerance if kind == "support" else float(row["high"]) >= center - tolerance
                if not touched:
                    continue
                if touch_indexes and index - touch_indexes[-1] < self.config.touch_separation:
                    continue
                prior = bars.iloc[max(0, index - self.config.touch_separation) : index]
                if touch_indexes and not prior.empty:
                    moved = float(prior["high"].max() - center) if kind == "support" else float(center - prior["low"].min())
                    if moved < self.config.move_away_atr * atr:
                        continue
                touch_indexes.append(int(index))
                future = bars.iloc[index + 1 : min(index + 6, len(bars))]
                if not future.empty:
                    move = float(future["high"].max() - center) if kind == "support" else float(center - future["low"].min())
                    reactions.append(max(0.0, move / atr))
                daily_range = max(float(row["high"] - row["low"]), 0.01)
                rejection = (float(row["close"] - row["low"]) / daily_range) if kind == "support" else (float(row["high"] - row["close"]) / daily_range)
                rejection_scores.append(rejection)
            touches = len(touch_indexes)
            touch_score = min(touches / 4.0, 1.0) * 25.0
            reaction_score = min((float(np.mean(reactions)) if reactions else 0.0) / 1.5, 1.0) * 25.0
            freshness = max(0.0, 1.0 - ((len(bars) - 1 - max(touch_indexes, default=0)) / 30.0))
            spacing_score = min((np.mean(np.diff(touch_indexes)) if len(touch_indexes) > 1 else 0.0) / 10.0, 1.0) * 10.0 + freshness * 5.0
            rejection_score = min(float(np.mean(rejection_scores)) if rejection_scores else 0.0, 1.0) * 15.0
            sources = {str(item.get("source")) for item in cluster if item.get("source")}
            confluence_score = min((len(cluster) + len(sources)) / 5.0, 1.0) * 20.0
            recent = bars.iloc[-5:]
            pressure = sum(
                1 for _, row in recent.iterrows()
                if (abs(float(row["low"] if kind == "support" else row["high"]) - center) <= tolerance)
            )
            favorable_move = float(recent["high"].max() - center) if kind == "support" else float(center - recent["low"].min())
            pressure_penalty = min(25.0, pressure * 5.0) if pressure >= 2 and favorable_move < self.config.move_away_atr * atr else 0.0
            score = max(0.0, min(100.0, touch_score + reaction_score + spacing_score + rejection_score + confluence_score - pressure_penalty))
            regions.append(
                {
                    "region_type": kind,
                    "center": center,
                    "lower_bound": center - tolerance,
                    "upper_bound": center + tolerance,
                    "score": score,
                    "touches": touches,
                    "pressure_penalty": pressure_penalty,
                    "sources": sorted(sources),
                    "distance_atr": abs(spot - center) / atr,
                }
            )
        valid = [region for region in regions if region["center"] <= spot + tolerance] if kind == "support" else [region for region in regions if region["center"] >= spot - tolerance]
        if not valid:
            valid = regions
        return max(valid, key=lambda region: (region["score"] - min(region["distance_atr"], 3.0) * 8.0, region["touches"]))
