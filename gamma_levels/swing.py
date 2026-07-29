from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from .core import AnalysisConfig, analyze_chain, black_scholes_greeks
from .signals import black_scholes_price
from .storage import Database
from .market_context import rate_on
from .regions import RegionConfig, RegionEngine, adjusted_bars


@dataclass(slots=True)
class SwingConfig:
    variant: str = "baseline_v0"
    universe_size: int = 20
    max_buy_signals: int = 5
    history_sessions: int = 120
    liquidity_sessions: int = 20
    min_dte: int = 10
    max_dte: int = 60
    delta_min: float = 0.55
    delta_max: float = 0.80
    min_open_interest: float = 500.0
    min_premium: float = 0.10
    max_spread_pct: float = 0.15
    min_financial_volume: float = 50_000.0
    buy_score: float = 80.0
    wait_score: float = 65.0
    min_reward_risk: float = 1.5
    iv_shock: float = 0.03
    interest_rate: float = 0.15
    holding_sessions: tuple[int, ...] = (3, 5, 10)
    use_regions: bool = False
    ema_fast: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    rsi_entry_floor: float = 0.0
    region_lookback: int = 100
    region_tolerance_atr: float = 0.35
    breakout_volume_min: float = 1.20
    fixed_ticker: str | None = None
    fixed_asset_root: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["holding_sessions"] = list(self.holding_sessions)
        return value


def _percentile(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0)
    if len(numeric) <= 1:
        return pd.Series(100.0, index=series.index)
    return numeric.rank(method="average", pct=True) * 100.0


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def _atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    previous = frame["close"].shift(1)
    ranges = pd.concat(
        [frame["high"] - frame["low"], (frame["high"] - previous).abs(), (frame["low"] - previous).abs()],
        axis=1,
    ).max(axis=1)
    return ranges.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _crr_american_call(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    interest_rate: float,
    dividend_yield: float,
    steps: int = 150,
) -> float:
    if time_to_expiry <= 0:
        return max(spot - strike, 0.0)
    if min(spot, strike, volatility) <= 0:
        return math.nan
    steps = max(25, steps)
    dt = time_to_expiry / steps
    up = math.exp(volatility * math.sqrt(dt))
    down = 1.0 / up
    probability = (math.exp((interest_rate - dividend_yield) * dt) - down) / (up - down)
    probability = min(max(probability, 0.0), 1.0)
    discount = math.exp(-interest_rate * dt)
    indexes = np.arange(steps + 1, dtype=float)
    prices = spot * np.power(up, steps - indexes) * np.power(down, indexes)
    values = np.maximum(prices - strike, 0.0)
    for level in range(steps - 1, -1, -1):
        values = discount * (probability * values[:-1] + (1.0 - probability) * values[1:])
        prices = prices[:-1] / up
        values = np.maximum(values, prices - strike)
    return float(values[0])


def option_price(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    style: str,
    interest_rate: float,
    dividend_yield: float = 0.0,
) -> float:
    if style == "american":
        return _crr_american_call(
            spot, strike, time_to_expiry, volatility, interest_rate, dividend_yield
        )
    return black_scholes_price(
        spot, strike, time_to_expiry, volatility, "call", interest_rate, dividend_yield
    )


class SwingScanner:
    def __init__(
        self, database: Database, config: SwingConfig | None = None,
        shared_cache: dict[tuple[Any, ...], Any] | None = None,
    ) -> None:
        self.database = database
        self.config = config or SwingConfig()
        self.shared_cache = shared_cache

    def _universe(self, trade_date: date) -> pd.DataFrame:
        cache_key = (
            "universe", trade_date.isoformat(), self.config.universe_size,
            self.config.liquidity_sessions, self.config.fixed_ticker,
        )
        if self.shared_cache is not None and cache_key in self.shared_cache:
            return self.shared_cache[cache_key].copy()
        if self.config.fixed_ticker and self.config.fixed_asset_root:
            equity = self.database.frame(
                """SELECT ticker,asset_root,close FROM underlying_bars
                WHERE ticker=? AND trade_date=? AND close>0 LIMIT 1""",
                (self.config.fixed_ticker, trade_date.isoformat()),
            )
            if equity.empty:
                return equity
            equity["liquidity_score"] = 100.0
            result = equity[["asset_root", "ticker", "close", "liquidity_score"]]
            if self.shared_cache is not None:
                self.shared_cache[cache_key] = result.copy()
            return result
        dates = self.database.loaded_dates()
        selected_dates = [item.isoformat() for item in dates if item <= trade_date][-self.config.liquidity_sessions :]
        if not selected_dates:
            return pd.DataFrame()
        placeholders = ",".join("?" for _ in selected_dates)
        daily = self.database.frame(
            f"""SELECT trade_date,asset_root,
                SUM(COALESCE(financial_volume,0)) AS notional,
                SUM(COALESCE(trades,0)) AS trades,
                SUM(CASE WHEN COALESCE(trades,0)>0 THEN 1 ELSE 0 END) AS traded_series,
                SUM(COALESCE(open_interest,0)) AS open_interest
            FROM option_quotes
            WHERE option_type='call' AND trade_date IN ({placeholders})
            GROUP BY trade_date,asset_root""",
            selected_dates,
        )
        if daily.empty:
            return daily
        total_sessions = len(selected_dates)
        grouped = daily.groupby("asset_root", as_index=False).agg(
            median_notional=("notional", "median"),
            median_trades=("trades", "median"),
            active_sessions=("trade_date", "nunique"),
            median_oi=("open_interest", "median"),
        )
        grouped["frequency"] = grouped["active_sessions"] / total_sessions
        grouped["liquidity_score"] = (
            0.35 * _percentile(np.log1p(grouped["median_notional"]))
            + 0.25 * _percentile(np.log1p(grouped["median_trades"]))
            + 0.20 * grouped["frequency"] * 100.0
            + 0.20 * _percentile(np.log1p(grouped["median_oi"]))
        )
        equities = self.database.frame(
            """SELECT ticker,asset_root,volume,close FROM underlying_bars
            WHERE trade_date=? AND close>0 ORDER BY volume DESC""",
            (trade_date.isoformat(),),
        ).drop_duplicates("asset_root")
        grouped = grouped.merge(equities[["asset_root", "ticker", "close"]], on="asset_root", how="inner")
        result = grouped.sort_values("liquidity_score", ascending=False).head(self.config.universe_size).reset_index(drop=True)
        if self.shared_cache is not None:
            self.shared_cache[cache_key] = result.copy()
        return result

    def _chain_summary(self, options: pd.DataFrame, spot: float, trade_date: date) -> dict[str, Any]:
        source = options.loc[
            options["implied_volatility"].gt(0)
            & options["open_interest"].notna()
            & options["expiration"].notna()
        ].copy()
        if source.empty:
            return {}
        chain = pd.DataFrame(
            {
                "ticker": source["ticker"],
                "option_type": source["option_type"],
                "strike": source["strike"],
                "expiration": source["expiration"],
                "open_interest": source["open_interest"],
                "volume": source["contracts"].fillna(0.0),
                "implied_volatility": source["implied_volatility"],
                "underlying_price": spot,
                "option_price": source["reference_price"].where(
                    source["reference_price"].gt(0), source["close"]
                ),
            }
        )
        try:
            result = analyze_chain(
                chain,
                AnalysisConfig(
                    spot=spot,
                    valuation_date=trade_date,
                    interest_rate=self.config.interest_rate,
                    use_vendor_greeks=False,
                ),
            )
        except ValueError:
            return {}
        return result.summary

    def _select_call(self, options: pd.DataFrame, spot: float, trade_date: date) -> dict[str, Any] | None:
        calls = options.loc[options["option_type"].eq("call")].copy()
        if calls.empty:
            return None
        calls["expiration"] = pd.to_datetime(calls["expiration"])
        calls["dte"] = (calls["expiration"] - pd.Timestamp(trade_date)).dt.days
        puts = options.loc[options["option_type"].eq("put"), ["expiration", "strike", "reference_price"]].copy()
        puts["expiration"] = pd.to_datetime(puts["expiration"])
        puts = puts.rename(columns={"reference_price": "put_reference"}).drop_duplicates(["expiration", "strike"])
        calls = calls.merge(puts, on=["expiration", "strike"], how="left")
        time_to_expiry = calls["dte"].clip(lower=1) / 365.0
        prepaid_forward = (
            calls["reference_price"] - calls["put_reference"]
            + calls["strike"] * np.exp(-self.config.interest_rate * time_to_expiry)
        )
        valid_forward = calls["put_reference"].gt(0) & prepaid_forward.gt(0) & prepaid_forward.le(spot * 1.05)
        implied_carry = (-np.log((prepaid_forward / spot).where(valid_forward)) / time_to_expiry).clip(0.0, 0.30)
        calls["dividend_yield"] = implied_carry.where(valid_forward, 0.0).fillna(0.0)
        calls["carry_source"] = np.where(valid_forward, "paridade call-put B3", "sem paridade")
        greeks = black_scholes_greeks(
            spot,
            calls["strike"].to_numpy(float),
            (calls["dte"].clip(lower=0) / 365.0).to_numpy(float),
            calls["implied_volatility"].fillna(0.0).to_numpy(float),
            np.array(["call"] * len(calls)),
            np.full(len(calls), self.config.interest_rate),
            calls["dividend_yield"].to_numpy(float),
        )
        calls["delta"] = greeks["delta"]
        calls["gamma"] = greeks["gamma"]
        calls["market_price"] = calls["reference_price"].where(calls["reference_price"].gt(0), calls["close"])
        calls["mid"] = (calls["bid"] + calls["ask"]) / 2.0
        calls["spread_pct"] = (calls["ask"] - calls["bid"]) / calls["mid"]
        eligible = calls.loc[
            calls["dte"].between(self.config.min_dte, self.config.max_dte)
            & calls["delta"].between(self.config.delta_min, self.config.delta_max)
            & calls["open_interest"].ge(self.config.min_open_interest)
            & calls["market_price"].ge(self.config.min_premium)
            & calls["spread_pct"].between(0.0, self.config.max_spread_pct)
            & calls["financial_volume"].ge(self.config.min_financial_volume)
            & calls["implied_volatility"].gt(0)
        ].copy()
        if eligible.empty:
            return None
        delta_center = (self.config.delta_min + self.config.delta_max) / 2.0
        delta_half = (self.config.delta_max - self.config.delta_min) / 2.0
        eligible["delta_component"] = (100.0 * (1.0 - (eligible["delta"] - delta_center).abs() / delta_half)).clip(0, 100)
        eligible["liquidity_component"] = (
            0.45 * _percentile(np.log1p(eligible["financial_volume"]))
            + 0.30 * _percentile(np.log1p(eligible["open_interest"]))
            + 0.25 * _percentile(np.log1p(eligible["trades"]))
        )
        eligible["spread_component"] = (100.0 * (1.0 - eligible["spread_pct"] / self.config.max_spread_pct)).clip(0, 100)
        eligible["dte_component"] = (100.0 - (eligible["dte"] - 30).abs() / 20.0 * 100.0).clip(0, 100)
        iv_median = float(eligible["implied_volatility"].median())
        eligible["iv_component"] = (100.0 - (eligible["implied_volatility"] - iv_median).abs() / max(iv_median, 0.01) * 100.0).clip(0, 100)
        eligible["option_score"] = (
            0.30 * eligible["liquidity_component"]
            + 0.25 * eligible["delta_component"]
            + 0.20 * eligible["spread_component"]
            + 0.15 * eligible["dte_component"]
            + 0.10 * eligible["iv_component"]
        )
        selected = eligible.sort_values(["option_score", "financial_volume"], ascending=False).iloc[0]
        return {
            "ticker": selected["ticker"],
            "strike": float(selected["strike"]),
            "expiration": selected["expiration"].date().isoformat(),
            "dte": int(selected["dte"]),
            "delta": float(selected["delta"]),
            "gamma": float(selected["gamma"]),
            "iv": float(selected["implied_volatility"]),
            "style": selected["style"],
            "dividend_yield": float(selected["dividend_yield"]),
            "carry_source": selected["carry_source"],
            "reference_price": float(selected["market_price"]),
            "bid": float(selected["bid"]),
            "ask": float(selected["ask"]),
            "spread_pct": float(selected["spread_pct"]),
            "open_interest": float(selected["open_interest"]),
            "financial_volume": float(selected["financial_volume"]),
            "score": float(selected["option_score"]),
        }

    def _project_call(self, call: dict[str, Any], spot: float, target: float) -> dict[str, Any]:
        projections: dict[str, Any] = {}
        for sessions in self.config.holding_sessions:
            remaining = max((call["dte"] - sessions) / 365.0, 0.0)
            values: dict[str, float] = {}
            for label, iv in (
                ("conservative", max(call["iv"] - self.config.iv_shock, 0.0001)),
                ("base", call["iv"]),
                ("optimistic", call["iv"] + self.config.iv_shock),
            ):
                projected = option_price(
                    target, call["strike"], remaining, iv, call["style"], self.config.interest_rate,
                    call.get("dividend_yield", 0.0),
                )
                values[label] = projected / call["reference_price"] - 1.0
            projections[str(sessions)] = values
        required: dict[str, float | None] = {}
        remaining = max((call["dte"] - 5) / 365.0, 0.0)
        for gain in (0.10, 0.25, 0.50, 1.00):
            wanted = call["reference_price"] * (1.0 + gain)
            low, high = spot * 0.70, spot * 1.60
            if option_price(high, call["strike"], remaining, call["iv"], call["style"], self.config.interest_rate, call.get("dividend_yield", 0.0)) < wanted:
                required[str(int(gain * 100))] = None
                continue
            # 32 iterações já deixam o preço-objetivo abaixo de um milionésimo de real
            # na faixa pesquisada; 60 apenas repetia árvores binomiais sem ganho prático.
            for _ in range(32):
                middle = (low + high) / 2.0
                value = option_price(middle, call["strike"], remaining, call["iv"], call["style"], self.config.interest_rate, call.get("dividend_yield", 0.0))
                if value >= wanted:
                    high = middle
                else:
                    low = middle
            required[str(int(gain * 100))] = high
        conservative_target = option_price(
            target,
            call["strike"],
            max((call["dte"] - 5) / 365.0, 0.0),
            max(call["iv"] - self.config.iv_shock, 0.0001),
            call["style"],
            self.config.interest_rate,
            call.get("dividend_yield", 0.0),
        )
        max_entry = min(conservative_target / 1.10, call["reference_price"] * 1.15)
        expected_move = spot * call["iv"] * math.sqrt(10.0 / 252.0)
        return {
            "horizons": projections,
            "required_underlying": required,
            "expected_move_10d": expected_move,
            "expected_range_10d": [spot - expected_move, spot + expected_move],
            "max_entry_premium": max(max_entry, 0.0),
        }

    def _analyze_asset(self, row: pd.Series, trade_date: date) -> dict[str, Any]:
        ticker, root = str(row["ticker"]), str(row["asset_root"])
        raw_key = ("raw_bars", ticker, trade_date.isoformat(), self.config.history_sessions)
        if self.config.use_regions:
            bars = adjusted_bars(
                self.database, ticker, trade_date, self.config.history_sessions, self.shared_cache
            )
        elif self.shared_cache is not None and raw_key in self.shared_cache:
            bars = self.shared_cache[raw_key].copy()
        else:
            bars = self.database.bars(ticker, trade_date, self.config.history_sessions)
            if self.shared_cache is not None:
                self.shared_cache[raw_key] = bars.copy()
        base: dict[str, Any] = {
            "ticker": ticker,
            "asset_root": root,
            "liquidity_score": float(row["liquidity_score"]),
            "status": "AGUARDAR",
            "setup": None,
            "score": 0.0,
            "reasons": [],
            "data_quality": "OK",
        }
        if len(bars) < 50:
            base.update(data_quality="INCOMPLETO", reasons=[f"Histórico insuficiente: {len(bars)}/50 pregões"])
            return base
        technical_key = (
            "technical_bars", ticker, trade_date.isoformat(), self.config.history_sessions,
            self.config.use_regions, self.config.ema_fast, self.config.ema_slow, self.config.rsi_period,
        )
        cached_technical = self.shared_cache.get(technical_key) if self.shared_cache is not None else None
        if cached_technical is not None:
            bars = cached_technical.copy()
        else:
            for column in ("open", "low", "high", "close", "volume"):
                bars[column] = pd.to_numeric(bars[column], errors="coerce")
            bars = bars.dropna(subset=["open", "low", "high", "close"])
            if len(bars) >= 50:
                close = bars["close"]
                bars["ema20"] = close.ewm(span=self.config.ema_fast, adjust=False).mean()
                bars["ema50"] = close.ewm(span=self.config.ema_slow, adjust=False).mean()
                bars["rsi"] = _rsi(close, self.config.rsi_period)
                bars["atr"] = _atr(bars)
                bars["roc20"] = close.pct_change(20)
                if self.shared_cache is not None:
                    self.shared_cache[technical_key] = bars.copy()
        if len(bars) < 50:
            base.update(data_quality="INCOMPLETO", reasons=["Preços históricos incompletos"])
            return base
        close = bars["close"]
        current = bars.iloc[-1]
        previous = bars.iloc[-2]
        spot = float(current["close"])
        atr = float(current["atr"])
        support = float(bars.iloc[-21:-1]["low"].min())
        resistance = float(bars.iloc[-21:-1]["high"].max())
        volume_median = float(bars.iloc[-21:-1]["volume"].fillna(0).median())
        volume_ratio = float(current["volume"] / volume_median) if volume_median > 0 else 0.0
        reversal = (
            float(current["low"]) <= support + 0.35 * atr
            and float(current["close"]) > float(current["open"])
            and float(current["rsi"]) > float(previous["rsi"])
        )
        breakout = spot >= resistance + 0.10 * atr and volume_ratio >= self.config.breakout_volume_min
        prior_breakout = float(bars.iloc[-6:-1]["close"].max()) > resistance
        retest = prior_breakout and float(current["low"]) <= resistance + 0.25 * atr and spot > resistance
        setup = "REVERSÃO EM SUPORTE" if reversal else ("ROMPIMENTO/RETESTE" if breakout or retest else None)

        trend = (
            (40 if spot > current["ema20"] else 0)
            + (30 if current["ema20"] > current["ema50"] else 0)
            + (15 if current["ema20"] > bars.iloc[-6]["ema20"] else 0)
            + (15 if spot > bars.iloc[-6]["close"] else 0)
        )
        rsi_value = float(current["rsi"])
        momentum = (
            (60 if 50 <= rsi_value <= 70 else 30 if 45 <= rsi_value < 75 else 0)
            + (25 if current["roc20"] > 0 else 0)
            + (15 if rsi_value > previous["rsi"] else 0)
        )
        structure = 100.0 if setup else max(0.0, 100.0 - min(abs(spot - support), abs(resistance - spot)) / max(atr, 0.01) * 35.0)
        volume_score = min(100.0, volume_ratio / 1.5 * 100.0)

        market_key = ("option_market", root, trade_date.isoformat(), round(spot, 6), round(self.config.interest_rate, 6))
        cached_market = self.shared_cache.get(market_key) if self.shared_cache is not None else None
        if cached_market is None:
            options = self.database.current_options(root, trade_date)
            chain_summary = self._chain_summary(options, spot, trade_date)
            selected_call = self._select_call(options, spot, trade_date)
            cached_market = (options, chain_summary, selected_call)
            if self.shared_cache is not None:
                self.shared_cache[market_key] = cached_market
        else:
            options, chain_summary, selected_call = cached_market
        region_payload: dict[str, Any] | None = None
        if self.config.use_regions:
            region_payload = RegionEngine(
                self.database,
                RegionConfig(
                    lookback=self.config.region_lookback,
                    tolerance_atr=self.config.region_tolerance_atr,
                    rsi_period=self.config.rsi_period,
                    ema_fast=self.config.ema_fast,
                    ema_slow=self.config.ema_slow,
                ),
                self.shared_cache,
            ).features(ticker, trade_date, chain_summary)
            support_region = region_payload.get("support") or {}
            resistance_region = region_payload.get("resistance") or {}
            if support_region.get("center") is not None:
                support = float(support_region["center"])
            if resistance_region.get("center") is not None:
                resistance = float(resistance_region["center"])
            structure = float(region_payload.get("region_score") or structure)
            reversal = (
                float(current["low"]) <= support + 0.35 * atr
                and float(current["close"]) > float(current["open"])
                and float(current["rsi"]) > float(previous["rsi"])
            )
            breakout = spot >= resistance + 0.10 * atr and volume_ratio >= self.config.breakout_volume_min
            prior_breakout = float(bars.iloc[-6:-1]["close"].max()) > resistance
            retest = prior_breakout and float(current["low"]) <= resistance + 0.25 * atr and spot > resistance
            setup = "REVERSÃO EM SUPORTE" if reversal else ("ROMPIMENTO/RETESTE" if breakout or retest else None)
        derivatives = 0.0
        if chain_summary:
            call_wall = chain_summary.get("call_wall")
            gamma_flip = chain_summary.get("gamma_flip")
            derivatives += 40.0 if call_wall and float(call_wall) > spot else 10.0
            derivatives += 30.0 if gamma_flip is None or spot >= float(gamma_flip) else 0.0
            derivatives += 30.0 if float(chain_summary.get("gex_total") or 0.0) >= 0 else 15.0
        score = 0.25 * trend + 0.15 * momentum + 0.25 * structure + 0.15 * volume_score + 0.20 * derivatives
        invalidation = (support if reversal else resistance) - 0.25 * atr if setup else support - 0.25 * atr
        risk = max(spot - invalidation, 0.01)
        target_candidates = [resistance, spot + atr, spot + 2 * atr]
        if chain_summary.get("call_wall"):
            target_candidates.append(float(chain_summary["call_wall"]))
        target_candidates = sorted({value for value in target_candidates if value > spot})
        targets = [value for value in target_candidates if (value - spot) / risk >= self.config.min_reward_risk]
        if not targets:
            targets = target_candidates[-1:] if target_candidates else [spot + 2 * atr]
        targets = targets[:3]
        reward_risk = (targets[0] - spot) / risk if targets else 0.0
        projection_key = (
            "projection", trade_date.isoformat(), selected_call.get("ticker") if selected_call else None,
            round(spot, 6), round(targets[0], 6), round(self.config.interest_rate, 6),
        )
        projections = self.shared_cache.get(projection_key) if self.shared_cache is not None else None
        if projections is None and selected_call:
            projections = self._project_call(selected_call, spot, targets[0])
            if self.shared_cache is not None:
                self.shared_cache[projection_key] = projections
        conservative_return = (
            projections["horizons"]["5"]["conservative"] if projections else None
        )

        reasons = [
            f"Tendência {trend:.0f}/100",
            f"Momentum {momentum:.0f}/100 (RSI {rsi_value:.1f})",
            f"Estrutura {structure:.0f}/100",
            f"Volume {volume_ratio:.2f}x da mediana",
            f"Derivativos {derivatives:.0f}/100",
        ]
        if selected_call is None:
            reasons.append("Nenhuma CALL passou todos os filtros de liquidez")
        qualifies = (
            score >= self.config.buy_score
            and rsi_value >= self.config.rsi_entry_floor
            and setup is not None
            and selected_call is not None
            and reward_risk >= self.config.min_reward_risk
            and conservative_return is not None
            and conservative_return >= 0.10
        )
        status = "COMPRAR CALL" if qualifies else ("AGUARDAR" if score >= self.config.wait_score or setup else "DESCARTAR")
        base.update(
            status=status,
            setup=setup,
            score=round(float(score), 2),
            spot=spot,
            atr=atr,
            support=support,
            resistance=resistance,
            entry_zone=[max(invalidation, spot - 0.25 * atr), spot + 0.25 * atr],
            invalidation=invalidation,
            targets=targets,
            reward_risk=reward_risk,
            selected_call=selected_call,
            projections=projections,
            components={
                "trend": trend,
                "momentum": momentum,
                "structure": structure,
                "volume": volume_score,
                "derivatives": derivatives,
            },
            levels={
                "gamma_flip": chain_summary.get("gamma_flip"),
                "call_wall": chain_summary.get("call_wall"),
                "put_wall": chain_summary.get("put_wall"),
                "max_pain": chain_summary.get("max_pain"),
                "gex_total": chain_summary.get("gex_total"),
            },
            region=region_payload,
            reasons=reasons,
        )
        return base

    def run(self, trade_date: date) -> list[dict[str, Any]]:
        rate_key = ("interest_rate", trade_date.isoformat())
        cached_rate = self.shared_cache.get(rate_key) if self.shared_cache is not None else None
        if cached_rate is None:
            cached_rate = rate_on(self.database, trade_date, self.config.interest_rate)
            if self.shared_cache is not None:
                self.shared_cache[rate_key] = cached_rate
        self.config.interest_rate = float(cached_rate)
        universe = self._universe(trade_date)
        if universe.empty:
            raise RuntimeError("Não há dados suficientes para montar o universo de CALLs")
        assets = [self._analyze_asset(row, trade_date) for _, row in universe.iterrows()]
        assets.sort(key=lambda item: (item["status"] == "COMPRAR CALL", item["score"], item["liquidity_score"]), reverse=True)
        buys = 0
        for rank, item in enumerate(assets, 1):
            item["rank"] = rank
            if item["status"] == "COMPRAR CALL":
                buys += 1
                if buys > self.config.max_buy_signals:
                    item["status"] = "AGUARDAR"
                    item["reasons"].append("Limite diário de cinco sinais de alta convicção")
        return assets
