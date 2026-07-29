from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import date
from statistics import median
from typing import Any, Callable

import numpy as np
import pandas as pd

from .storage import Database, json_dumps
from .swing import SwingConfig, SwingScanner


STRATEGIES = (
    "HOLD_TO_EXPIRY",
    "CALCULATED_EXIT",
    "PARTIAL_25",
    "PARTIAL_50",
    "LADDER_25_50_100",
    "PARTIAL_25_CALCULATED",
)
OVERLAP_MODES = ("INDEPENDENT", "SINGLE_POSITION")


@dataclass(slots=True)
class CostConfig:
    buy_pct: float = 0.0
    sell_pct: float = 0.0
    slippage_pct: float = 0.0
    fixed_per_order_brl: float = 0.0
    capital_per_trade_brl: float = 1_000.0


@dataclass(slots=True)
class StudyConfig:
    ticker: str = "PETR4"
    asset_root: str = "PETR"
    target_loaded_sessions: int = 345
    warmup_sessions: int = 50
    evaluation_sessions: int = 252
    costs: CostConfig | None = None
    variants: str = "standard_v1"
    corporate_actions_complete: bool = True
    interest_rates_complete: bool = True

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["costs"] = asdict(self.costs or CostConfig())
        return value


def standard_variants(history_sessions: int = 140) -> list[SwingConfig]:
    baseline = SwingConfig(
        variant="baseline_v0", universe_size=1, max_buy_signals=1,
        history_sessions=history_sessions, liquidity_sessions=20,
        use_regions=False, rsi_entry_floor=0.0,
    )
    region = replace(
        baseline, variant="region_v1", use_regions=True, rsi_entry_floor=50.0,
        region_lookback=100, region_tolerance_atr=0.35,
    )
    variants = [baseline, region]
    changes: list[tuple[str, str, Any]] = [
        ("ema_9_21", "ema", (9, 21)),
        ("ema_21_50", "ema", (21, 50)),
        ("ema_21_72", "ema", (21, 72)),
        ("rsi_period_7", "rsi_period", 7),
        ("rsi_period_21", "rsi_period", 21),
        ("rsi_floor_45", "rsi_entry_floor", 45.0),
        ("rsi_floor_55", "rsi_entry_floor", 55.0),
        ("region_atr_025", "region_tolerance_atr", 0.25),
        ("region_atr_050", "region_tolerance_atr", 0.50),
        ("region_lookback_20", "region_lookback", 20),
        ("region_lookback_50", "region_lookback", 50),
        ("volume_100", "breakout_volume_min", 1.0),
        ("volume_150", "breakout_volume_min", 1.5),
        ("score_75", "buy_score", 75.0),
        ("score_85", "buy_score", 85.0),
        ("rr_125", "min_reward_risk", 1.25),
        ("rr_200", "min_reward_risk", 2.0),
    ]
    for name, field, value in changes:
        if field == "ema":
            variants.append(replace(region, variant=name, ema_fast=value[0], ema_slow=value[1]))
        else:
            variants.append(replace(region, variant=name, **{field: value}))
    return variants


class AnnualStudy:
    def __init__(self, database: Database, config: StudyConfig | None = None) -> None:
        self.database = database
        self.config = config or StudyConfig()
        self.costs = self.config.costs or CostConfig()

    def run(self, progress: Callable[[str, int], None] | None = None) -> int:
        tell = progress or (lambda _message, _progress: None)
        dates = self.database.loaded_dates()
        if len(dates) < self.config.warmup_sessions + 2:
            raise RuntimeError(
                f"Histórico insuficiente: {len(dates)} pregões; mínimo {self.config.warmup_sessions + 2}"
            )
        dataset_hash = hashlib.sha256("|".join(item.isoformat() for item in dates).encode()).hexdigest()
        run_id = self.database.start_backtest_run(
            self.config.ticker, self.config.asset_root, self.config.to_dict(), phase="features"
        )
        try:
            eligible = dates[self.config.warmup_sessions : -1]
            variants = standard_variants(max(140, self.config.warmup_sessions + 20))
            for variant in variants:
                variant.fixed_ticker = self.config.ticker
                variant.fixed_asset_root = self.config.asset_root
            total_steps = max(len(eligible) * len(variants), 1)
            step = 0
            all_trades: list[dict[str, Any]] = []
            shared_market_cache: dict[tuple[Any, ...], Any] = {}
            self._run_cache = shared_market_cache
            for variant in variants:
                tell(f"Calculando {variant.variant}", round(step / total_steps * 65))
                assets_by_date: dict[str, dict[str, Any]] = {}
                scanner = SwingScanner(self.database, variant, shared_market_cache)
                for trading_date in eligible:
                    step += 1
                    if step == 1 or step % 5 == 0:
                        tell(
                            f"{variant.variant}: {trading_date:%d/%m/%Y} ({step}/{total_steps})",
                            round(step / total_steps * 65),
                        )
                    try:
                        assets = scanner.run(trading_date)
                    except RuntimeError:
                        continue
                    asset = next(
                        (item for item in assets if item["ticker"] == self.config.ticker),
                        assets[0] if assets else None,
                    )
                    if not asset:
                        continue
                    assets_by_date[trading_date.isoformat()] = asset
                    region = asset.get("region") or {}
                    for key in ("support", "resistance"):
                        if region.get(key):
                            self.database.replace_region_snapshot(
                                run_id, variant.variant, trading_date, self.config.ticker, region[key]
                            )
                for trading_date in eligible:
                    asset = assets_by_date.get(trading_date.isoformat())
                    if not asset or asset.get("status") != "COMPRAR CALL":
                        continue
                    trade = self._build_trade(run_id, variant.variant, trading_date, asset, assets_by_date, dates)
                    self.database.replace_backtest_trade(trade)
                    self.database.replace_trade_path(trade["trade_id"], trade.get("path", []))
                    all_trades.append(trade)

            tell("Simulando seis estratégias de saída", 72)
            independent: list[dict[str, Any]] = []
            for trade in all_trades:
                for strategy in STRATEGIES:
                    independent.append(self._simulate_strategy(trade, strategy))
            portfolio = self._apply_single_position(independent, all_trades)
            results = independent + portfolio
            self.database.replace_strategy_results(results)

            tell("Calculando métricas e validação walk-forward", 86)
            metrics = self._metrics(run_id, results, all_trades, eligible)
            self.database.replace_backtest_metrics(metrics)
            enough = (
                len(dates) >= self.config.target_loaded_sessions
                and self.config.corporate_actions_complete
                and self.config.interest_rates_complete
            )
            completed_candidates = sum(
                1 for trading_date in eligible
                if (dates[-1] - trading_date).days >= 60
            )
            status = "COMPLETE" if enough and completed_candidates >= self.config.evaluation_sessions else "INCOMPLETE"
            message = (
                f"Estudo anual concluído com {completed_candidates} datas avaliáveis"
                if status == "COMPLETE" else
                f"Resultado parcial: {len(dates)}/{self.config.target_loaded_sessions} pregões e "
                f"{completed_candidates}/{self.config.evaluation_sessions} datas encerráveis"
            )
            self.database.update_backtest_run(
                run_id, status=status, phase="complete", message=message,
                first_date=dates[0].isoformat(), last_date=dates[-1].isoformat(),
                evaluated_sessions=completed_candidates, dataset_hash=dataset_hash,
            )
            tell(message, 100)
            return run_id
        except Exception as exc:
            self.database.update_backtest_run(
                run_id, status="ERROR", phase="error", message=str(exc), dataset_hash=dataset_hash
            )
            raise

    def _build_trade(
        self, run_id: int, variant: str, signal_date: date, asset: dict[str, Any],
        assets_by_date: dict[str, dict[str, Any]], loaded_dates: list[date],
    ) -> dict[str, Any]:
        call = asset["selected_call"]
        option_ticker = call["ticker"]
        expiration = date.fromisoformat(call["expiration"])
        entry_limit = float(asset["projections"]["max_entry_premium"])
        future_key = ("future_option_path", option_ticker, signal_date.isoformat())
        future = getattr(self, "_run_cache", {}).get(future_key)
        if future is None:
            future = self.database.frame(
                """SELECT * FROM option_quotes WHERE ticker=? AND trade_date>?
                ORDER BY trade_date""",
                (option_ticker, signal_date.isoformat()),
            )
            getattr(self, "_run_cache", {})[future_key] = future.copy()
        else:
            future = future.copy()
        future = future.loc[pd.to_datetime(future["trade_date"]).dt.date <= expiration] if not future.empty else future
        fill_status = "UNFILLED"
        entry_date = None
        entry_price = None
        late_fill = False
        reference_entry_date = None
        reference_entry_price = None
        if not future.empty:
            first = future.iloc[0]
            opening = float(first["open"]) if pd.notna(first["open"]) and float(first["open"]) > 0 else None
            low = float(first["low"]) if pd.notna(first["low"]) and float(first["low"]) > 0 else None
            reference_entry_date = str(first["trade_date"])
            reference_entry_price = opening
            if opening is None or low is None:
                fill_status = "DATA_INSUFFICIENT"
            elif opening <= entry_limit:
                fill_status, entry_date, entry_price = "FILLED_OPEN", str(first["trade_date"]), opening
            elif low <= entry_limit:
                fill_status, entry_date, entry_price, late_fill = "FILLED_LIMIT", str(first["trade_date"]), entry_limit, True
        trade_id = f"{run_id}|{variant}|{signal_date.isoformat()}|{self.config.ticker}|{option_ticker}"
        trade: dict[str, Any] = {
            "trade_id": trade_id, "run_id": run_id, "variant": variant,
            "signal_date": signal_date.isoformat(), "ticker": self.config.ticker,
            "option_ticker": option_ticker, "expiration": expiration.isoformat(),
            "strike": float(call["strike"]), "signal_score": float(asset["score"]),
            "region_score": float((asset.get("region") or {}).get("region_score") or 0),
            "entry_limit": entry_limit, "entry_date": entry_date, "entry_price": entry_price,
            "fill_status": fill_status, "completed": False,
            "payload": {"signal": asset, "late_fill": late_fill}, "path": [],
        }
        if not fill_status.startswith("FILLED") or entry_price is None or entry_date is None:
            if reference_entry_price is not None and reference_entry_date is not None:
                shadow = {
                    **trade, "entry_price": reference_entry_price, "entry_date": reference_entry_date,
                    "payload": {**trade["payload"], "late_fill": False},
                }
                path, observation_complete, expiry_return = self._build_path(
                    shadow, future, assets_by_date, asset, loaded_dates[-1]
                )
                trade["path"] = path
                trade["payload"].update(
                    {
                        "path_basis": "FIRST_TRADE_REFERENCE", "reference_entry_price": reference_entry_price,
                        "signal_observation_complete": observation_complete,
                        "reference_expiry_return": expiry_return,
                    }
                )
            return trade
        path, completed, expiry_return = self._build_path(
            trade, future, assets_by_date, asset, loaded_dates[-1]
        )
        trade["path"] = path
        trade["completed"] = completed
        trade["payload"].update({"expiry_return": expiry_return, "path_basis": "OFFICIAL_LIMIT_ENTRY"})
        return trade

    def _build_path(
        self, trade: dict[str, Any], quotes: pd.DataFrame, assets_by_date: dict[str, dict[str, Any]],
        signal_asset: dict[str, Any], latest_date: date,
    ) -> tuple[list[dict[str, Any]], bool, float | None]:
        entry = float(trade["entry_price"])
        entry_date = date.fromisoformat(trade["entry_date"])
        expiration = date.fromisoformat(trade["expiration"])
        bars_key = (
            "underlying_trade_path", trade["ticker"], entry_date.isoformat(), expiration.isoformat()
        )
        bars = getattr(self, "_run_cache", {}).get(bars_key)
        if bars is None:
            bars = self.database.frame(
                """SELECT * FROM underlying_bars WHERE ticker=? AND trade_date>=? AND trade_date<=?
                ORDER BY trade_date""",
                (trade["ticker"], entry_date.isoformat(), expiration.isoformat()),
            )
            getattr(self, "_run_cache", {})[bars_key] = bars.copy()
        else:
            bars = bars.copy()
        quote_map = {str(row.trade_date): row for row in quotes.itertuples(index=False)}
        path: list[dict[str, Any]] = []
        mfe, mae = -1.0, 0.0
        peak_date = None
        maximum_asset_score = float(signal_asset["score"])
        targets = [float(value) for value in signal_asset.get("targets") or []]
        invalidation = float(signal_asset.get("invalidation") or 0)
        atr = float(signal_asset.get("atr") or 0.01)
        call_wall = (signal_asset.get("levels") or {}).get("call_wall")
        completed = expiration <= latest_date and not bars.empty and pd.to_datetime(bars["trade_date"]).dt.date.max() >= expiration
        late_fill = bool(trade.get("payload", {}).get("late_fill"))
        for _, bar in bars.iterrows():
            day = str(bar["trade_date"])
            quote = quote_map.get(day)
            if quote is None:
                continue
            values: dict[str, float | None] = {}
            for column in ("open", "low", "high", "close"):
                raw = getattr(quote, column)
                fallback = getattr(quote, "reference_price")
                value = float(raw) if raw is not None and pd.notna(raw) and float(raw) > 0 else (
                    float(fallback) if fallback is not None and pd.notna(fallback) and float(fallback) > 0 else None
                )
                values[column] = value
            if late_fill and day == trade["entry_date"]:
                # A mínima tocou a ordem, mas o OHLC não informa se a máxima veio antes.
                # O fechamento é posterior ao preenchimento; usamos apenas ele para o MFE do dia.
                values["open"] = entry
                values["high"] = max(entry, float(values["close"] or entry))
            returns = {key: (value / entry - 1.0 if value is not None else None) for key, value in values.items()}
            if returns["high"] is not None and returns["high"] > mfe:
                mfe, peak_date = float(returns["high"]), day
            if returns["low"] is not None:
                mae = min(mae, float(returns["low"]))
            drawdown = (float(returns["close"]) - mfe) if returns["close"] is not None and mfe >= 0 else 0.0
            daily_asset = assets_by_date.get(day) or {}
            daily_score = float(daily_asset.get("score") or signal_asset["score"])
            maximum_asset_score = max(maximum_asset_score, daily_score)
            rr = float(daily_asset.get("reward_risk") or 99.0)
            setup_missing = not daily_asset.get("setup")
            volume_component = float((daily_asset.get("components") or {}).get("volume") or 100.0)
            high_underlying = float(bar["high"] or 0)
            low_underlying = float(bar["low"] or 0)
            close_underlying = float(bar["close"] or 0)
            daily_range = max(high_underlying - low_underlying, 0.01)
            obstacles = targets + ([float(call_wall)] if call_wall else [])
            rejection = any(
                high_underlying >= obstacle - 0.25 * atr
                and (high_underlying - close_underlying >= 0.5 * atr or (close_underlying - low_underlying) / daily_range <= 0.40)
                for obstacle in obstacles
            )
            dte = max((expiration - date.fromisoformat(day)).days, 0)
            evidence = (
                (25 if setup_missing else 0)
                + (20 if rr < 0.75 else 0)
                + (20 if rejection else 0)
                + (15 if maximum_asset_score - daily_score >= 10 else 0)
                + (10 if mfe >= 0.10 and volume_component < (100 / 1.5) else 0)
                + (15 if mfe >= 0.25 and drawdown <= -0.15 else 0)
                + (15 if dte <= 10 and daily_score < 80 else 0)
            )
            evidence = min(evidence, 100)
            state = "MANTER" if evidence < 25 else "ATENÇÃO" if evidence < 50 else "PARCIAL" if evidence < 70 else "SAIR/PROTEGER"
            path.append(
                {
                    "trade_date": day, "dte": dte,
                    "option_open": values["open"], "option_low": values["low"],
                    "option_high": values["high"], "option_close": values["close"],
                    "underlying_open": float(bar["open"]), "underlying_low": low_underlying,
                    "underlying_high": high_underlying, "underlying_close": close_underlying,
                    "return_open": returns["open"], "return_low": returns["low"],
                    "return_high": returns["high"], "return_close": returns["close"],
                    "mfe": mfe, "mae": mae, "drawdown_from_peak": drawdown,
                    "asset_score": daily_score, "exit_evidence_score": evidence, "exit_state": state,
                    "payload": {
                        "invalidated": close_underlying <= invalidation,
                        "setup_missing": setup_missing, "reward_risk": rr,
                        "rejection": rejection, "peak_date": peak_date,
                        "implied_volatility": float(quote.implied_volatility) if quote.implied_volatility is not None else None,
                    },
                }
            )
        expiry_return = None
        if completed:
            expiry_bar = bars.iloc[-1]
            intrinsic = max(float(expiry_bar["close"]) - float(trade["strike"]), 0.0)
            expiry_return = intrinsic / entry - 1.0
        return path, completed, expiry_return

    def _simulate_strategy(self, trade: dict[str, Any], strategy: str) -> dict[str, Any]:
        base = {
            "trade_id": trade["trade_id"], "strategy": strategy, "overlap_mode": "INDEPENDENT",
            "included": True, "completed": bool(trade.get("completed")), "gross_return": None,
            "net_return": None, "mfe": None, "mae": None, "expiry_return": trade.get("payload", {}).get("expiry_return"),
            "peak_date": None, "exit_date": None, "holding_sessions": None, "payload": {},
        }
        path = trade.get("path") or []
        if path:
            base["mfe"] = max(float(row["mfe"]) for row in path)
            base["mae"] = min(float(row["mae"]) for row in path)
            peak = max(path, key=lambda row: float(row.get("return_high") or -999))
            base["peak_date"] = peak["trade_date"]
        if not trade["fill_status"].startswith("FILLED") or not path:
            base["completed"] = False
            base["payload"] = {"observation_only": True, "path_basis": trade.get("payload", {}).get("path_basis")}
            return base
        if not trade.get("completed"):
            return base
        expiry_return = float(trade["payload"]["expiry_return"])
        late_fill = bool(trade["payload"].get("late_fill"))
        sales: list[tuple[float, float, str]] = []

        def target_hit(level: float) -> tuple[int, float, str] | None:
            for index, row in enumerate(path):
                if index == 0 and late_fill:
                    continue
                if row.get("return_high") is not None and float(row["return_high"]) >= level:
                    return index, level, row["trade_date"]
            return None

        def calculated_hit() -> tuple[int, float, str] | None:
            for index, row in enumerate(path[:-1]):
                if float(row.get("exit_evidence_score") or 0) >= 70:
                    next_row = path[index + 1]
                    value = next_row.get("return_open")
                    if value is not None:
                        return index + 1, float(value), next_row["trade_date"]
            return None

        if strategy == "HOLD_TO_EXPIRY":
            sales.append((1.0, expiry_return, trade["expiration"]))
        elif strategy == "CALCULATED_EXIT":
            calculated = calculated_hit()
            if calculated:
                sales.append((1.0, calculated[1], calculated[2]))
            else:
                sales.append((1.0, expiry_return, trade["expiration"]))
        elif strategy == "PARTIAL_25":
            hit = target_hit(0.25)
            if hit:
                sales.append((0.5, hit[1], hit[2]))
            filled = hit is not None
            sales.append((0.5 if filled else 1.0, expiry_return, trade["expiration"]))
        elif strategy == "PARTIAL_50":
            hit = target_hit(0.50)
            if hit:
                sales.append((0.5, hit[1], hit[2]))
            filled = hit is not None
            sales.append((0.5 if filled else 1.0, expiry_return, trade["expiration"]))
        elif strategy == "LADDER_25_50_100":
            remaining = 1.0
            for level in (0.25, 0.50, 1.00):
                hit = target_hit(level)
                if hit:
                    sales.append((1 / 3, hit[1], hit[2]))
                    remaining -= 1 / 3
            if remaining > 1e-8:
                sales.append((remaining, expiry_return, trade["expiration"]))
        elif strategy == "PARTIAL_25_CALCULATED":
            target_25 = target_hit(0.25)
            calculated = calculated_hit()
            if calculated and (not target_25 or calculated[0] <= target_25[0]):
                sales.append((1.0, calculated[1], calculated[2]))
            else:
                remaining = 1.0
                if target_25:
                    sales.append((0.5, target_25[1], target_25[2]))
                    remaining = 0.5
                if calculated and (not target_25 or calculated[0] > target_25[0]):
                    sales.append((remaining, calculated[1], calculated[2]))
                else:
                    sales.append((remaining, expiry_return, trade["expiration"]))
        gross = sum(quantity * return_value for quantity, return_value, _ in sales)
        sell_multiplier = 1.0 - self.costs.sell_pct - self.costs.slippage_pct
        proceeds_multiple = sum(quantity * (1.0 + return_value) * sell_multiplier for quantity, return_value, _ in sales)
        buy_cost = 1.0 + self.costs.buy_pct + self.costs.slippage_pct
        order_cost = self.costs.fixed_per_order_brl * (1 + len(sales)) / max(self.costs.capital_per_trade_brl, 0.01)
        net = (proceeds_multiple - buy_cost - order_cost) / buy_cost
        base.update(
            gross_return=gross, net_return=net, exit_date=max(day for _, _, day in sales),
            holding_sessions=len(path), payload={"sales": sales},
        )
        return base

    @staticmethod
    def _apply_single_position(
        independent: list[dict[str, Any]], trades: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        trade_map = {trade["trade_id"]: trade for trade in trades}
        rows: list[dict[str, Any]] = []
        for variant in sorted({trade["variant"] for trade in trades}):
            for strategy in STRATEGIES:
                source = [
                    row for row in independent
                    if row["strategy"] == strategy and trade_map[row["trade_id"]]["variant"] == variant
                ]
                source.sort(key=lambda row: trade_map[row["trade_id"]]["signal_date"])
                blocked_until = ""
                for row in source:
                    copied = {**row, "overlap_mode": "SINGLE_POSITION"}
                    signal_date = trade_map[row["trade_id"]]["signal_date"]
                    included = signal_date > blocked_until
                    copied["included"] = included
                    if included:
                        blocked_until = str(row.get("exit_date") or trade_map[row["trade_id"]]["expiration"])
                    rows.append(copied)
        return rows

    def _metrics(
        self, run_id: int, results: list[dict[str, Any]], trades: list[dict[str, Any]], eligible: list[date]
    ) -> list[dict[str, Any]]:
        trade_map = {trade["trade_id"]: trade for trade in trades}
        date_rank = {day.isoformat(): index for index, day in enumerate(eligible[: self.config.evaluation_sessions])}
        output = []
        variants = sorted({trade["variant"] for trade in trades})
        for variant in variants:
            for strategy in STRATEGIES:
                for overlap in OVERLAP_MODES:
                    source = [
                        row for row in results
                        if row["strategy"] == strategy and row["overlap_mode"] == overlap
                        and row.get("included") and row.get("completed")
                        and row.get("net_return") is not None
                        and trade_map[row["trade_id"]]["variant"] == variant
                    ]
                    samples = {
                        "full": source,
                        "train_126": [row for row in source if date_rank.get(trade_map[row["trade_id"]]["signal_date"], 9999) < 126],
                        "validation_1": [row for row in source if 126 <= date_rank.get(trade_map[row["trade_id"]]["signal_date"], -1) < 189],
                        "validation_2": [row for row in source if 189 <= date_rank.get(trade_map[row["trade_id"]]["signal_date"], -1) < 252],
                    }
                    samples["out_of_sample"] = samples["validation_1"] + samples["validation_2"]
                    for sample, rows in samples.items():
                        output.append(self._metric_row(run_id, variant, strategy, overlap, sample, rows))
        return output

    @staticmethod
    def _metric_row(
        run_id: int, variant: str, strategy: str, overlap: str, sample: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        returns = [float(row["net_return"]) for row in rows]
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        cumulative, peak, max_drawdown = 0.0, 0.0, 0.0
        for value in returns:
            cumulative += value
            peak = max(peak, cumulative)
            max_drawdown = min(max_drawdown, cumulative - peak)
        captures = [
            float(row["net_return"]) / float(row["mfe"])
            for row in rows if row.get("mfe") is not None and float(row["mfe"]) > 0
        ]
        hits = {
            str(level): sum(1 for row in rows if row.get("mfe") is not None and float(row["mfe"]) >= level / 100)
            for level in (10, 25, 50, 100)
        }
        return {
            "run_id": run_id, "variant": variant, "strategy": strategy,
            "overlap_mode": overlap, "sample": sample, "trades": len(rows),
            "wins": len(wins), "win_rate": len(wins) / len(rows) if rows else None,
            "expectancy": float(np.mean(returns)) if returns else None,
            "profit_factor": gross_profit / gross_loss if gross_loss else None,
            "avg_win": float(np.mean(wins)) if wins else None,
            "avg_loss": float(np.mean(losses)) if losses else None,
            "median_return": median(returns) if returns else None,
            "max_drawdown": max_drawdown if rows else None,
            "mfe_capture": float(np.mean(captures)) if captures else None,
            "payload": {"hits": hits, "minimum_sample_ok": len(rows) >= 10, "no_losing_trades": bool(rows and not losses)},
        }
