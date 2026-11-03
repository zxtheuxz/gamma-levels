from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .index_futures import IndexFuturesConfig, cluster_levels
from .index_futures_storage import json_dumps


WIN_BRL_PER_POINT = 0.20


@dataclass(slots=True)
class IndexBacktestResult:
    region_outcomes: pd.DataFrame
    trades: pd.DataFrame
    metrics: pd.DataFrame


def ablation_zones(
    levels: pd.DataFrame,
    contexts: pd.DataFrame,
    config: IndexFuturesConfig,
) -> pd.DataFrame:
    """Reconstrói zonas por modelo para medir a contribuição de cada família."""
    if levels.empty:
        return pd.DataFrame()
    context_atr = contexts.set_index("trade_date")["atr_points"].to_dict()
    rows: list[pd.DataFrame] = []
    for trade_date, daily in levels.groupby("trade_date", sort=True):
        components = (
            daily[daily["source_family"].eq("COMPONENT")]
            .groupby("source")["component_weight"].max().sort_values(ascending=False)
        )
        top5 = set(components.head(5).index)
        models = {
            "IBOV": daily["source_family"].eq("IBOV"),
            "BOVA": daily["source_family"].eq("BOVA"),
            "IBOV_BOVA": daily["source_family"].isin(["IBOV", "BOVA"]),
            "IBOV_TOP5": daily["source_family"].eq("IBOV") | daily["source"].isin(top5),
            "FULL": pd.Series(True, index=daily.index),
        }
        for model, mask in models.items():
            selected = daily[mask]
            if selected.empty:
                continue
            zones = cluster_levels(
                selected,
                atr_points=float(context_atr.get(str(trade_date), config.min_atr_points)),
                config=config,
            )
            if zones.empty:
                continue
            zones["model"] = model
            zones["zone_id"] = model + ":" + zones["zone_id"].astype(str)
            zones["atr_points"] = float(context_atr.get(str(trade_date), config.min_atr_points))
            rows.append(zones)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _future_bars(zone: pd.Series, bars: pd.DataFrame, days: int) -> pd.DataFrame:
    source_date = str(zone["trade_date"])
    future = bars[bars["trade_date"].astype(str).gt(source_date)].sort_values("trade_date")
    source_contract = zone.get("win_ticker")
    if source_contract and "ticker" in future:
        future = future[future["ticker"].eq(source_contract)]
    return future.head(days).reset_index(drop=True)


def evaluate_regions(zones: pd.DataFrame, bars: pd.DataFrame, config: IndexFuturesConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, zone in zones.iterrows():
        days = config.short_time_stop if zone["horizon"] == "SHORT" else config.swing_time_stop
        future = _future_bars(zone, bars, days)
        if future.empty:
            continue
        atr_points = max(float(zone.get("atr_points") or config.min_atr_points), config.min_atr_points)
        low, high = float(zone["zone_low"]), float(zone["zone_high"])
        touched = future[(future["low"] <= high) & (future["high"] >= low)]
        touch_index = int(touched.index[0]) if not touched.empty else None
        reaction = breakout = false_breakout = False
        mfe = mae = None
        event_index = touch_index
        direction = 1 if zone["zone_type"] == "BUYER" else -1 if zone["zone_type"] == "SELLER" else 0
        breakout_direction = 0
        if touch_index is not None:
            path = future.iloc[touch_index:]
            center = float(zone["zone_center"])
            if direction == 1:
                mfe = float(path["high"].max() - center)
                mae = float(center - path["low"].min())
                break_mask = path["close"] < low - config.breakout_atr * atr_points
                breakout_direction = -1
            elif direction == -1:
                mfe = float(center - path["low"].min())
                mae = float(path["high"].max() - center)
                break_mask = path["close"] > high + config.breakout_atr * atr_points
                breakout_direction = 1
            else:
                mfe = float(max(path["high"].max() - center, center - path["low"].min()))
                mae = float(min(path["high"].max() - center, center - path["low"].min()))
                up = path["close"] > high + config.breakout_atr * atr_points
                down = path["close"] < low - config.breakout_atr * atr_points
                break_mask = up | down
                if break_mask.any():
                    first = break_mask[break_mask].index[0]
                    breakout_direction = 1 if bool(up.loc[first]) else -1
            if break_mask.any():
                breakout = True
                break_index = int(break_mask[break_mask].index[0])
                event_index = break_index
                after = future.loc[break_index + 1: break_index + 2]
                if breakout_direction == 1:
                    false_breakout = bool((after["close"] <= high).any())
                else:
                    false_breakout = bool((after["close"] >= low).any())
            reaction_path = path.loc[:break_index] if breakout else path
            if direction == 1:
                reaction = float(reaction_path["high"].max() - center) >= 0.5 * atr_points
            elif direction == -1:
                reaction = float(center - reaction_path["low"].min()) >= 0.5 * atr_points
            else:
                reaction = max(
                    float(reaction_path["high"].max() - center),
                    float(center - reaction_path["low"].min()),
                ) >= 0.5 * atr_points
        rows.append(
            {
                "zone_id": zone["zone_id"],
                "source_trade_date": str(zone["trade_date"]),
                "horizon": zone["horizon"],
                "evaluation_start": str(future.iloc[0]["trade_date"]) if not future.empty else str(zone["trade_date"]),
                "touched": int(touch_index is not None),
                "touch_date": str(future.iloc[touch_index]["trade_date"]) if touch_index is not None else None,
                "reaction": int(reaction),
                "breakout": int(breakout),
                "false_breakout": int(false_breakout),
                "mfe_points": mfe,
                "mae_points": mae,
                "days_to_event": event_index + 1 if event_index is not None else None,
                "payload_json": json_dumps({"model": zone.get("model"), "zone_type": zone["zone_type"], "atr_points": atr_points}),
            }
        )
    return pd.DataFrame(rows)


def _signal_rejection(zone: pd.Series, future: pd.DataFrame) -> tuple[int, int] | None:
    for index, row in future.iterrows():
        touched = float(row["low"]) <= float(zone["zone_high"]) and float(row["high"]) >= float(zone["zone_low"])
        if zone["zone_type"] == "BUYER" and touched and float(row["close"]) > float(zone["zone_high"]):
            return int(index), 1
        if zone["zone_type"] == "SELLER" and touched and float(row["close"]) < float(zone["zone_low"]):
            return int(index), -1
    return None


def _signal_breakout(zone: pd.Series, future: pd.DataFrame, threshold: float) -> tuple[int, int] | None:
    low, high = float(zone["zone_low"]), float(zone["zone_high"])
    for index in range(len(future)):
        close = float(future.iloc[index]["close"])
        direction = 1 if close > high + threshold else -1 if close < low - threshold else 0
        if not direction:
            continue
        for retest_index in range(index + 1, min(index + 3, len(future))):
            row = future.iloc[retest_index]
            if direction == 1 and float(row["low"]) <= high and float(row["close"]) > high:
                return retest_index, direction
            if direction == -1 and float(row["high"]) >= low and float(row["close"]) < low:
                return retest_index, direction
    return None


def _simulate_exit(
    entry_index: int,
    entry: float,
    direction: int,
    zone: pd.Series,
    future: pd.DataFrame,
    peer_zones: pd.DataFrame,
    config: IndexFuturesConfig,
) -> dict[str, Any]:
    atr_points = max(float(zone.get("atr_points") or config.min_atr_points), config.min_atr_points)
    stop = (
        float(zone["zone_low"]) - config.stop_padding_atr * atr_points
        if direction == 1 else float(zone["zone_high"]) + config.stop_padding_atr * atr_points
    )
    risk = direction * (entry - stop)
    if risk <= 0:
        stop = entry - direction * config.stop_padding_atr * atr_points
        risk = config.stop_padding_atr * atr_points
    target1 = entry + direction * risk
    candidates = peer_zones[
        peer_zones["zone_center"].gt(entry) if direction == 1 else peer_zones["zone_center"].lt(entry)
    ]["zone_center"]
    if direction == 1:
        candidates = candidates[candidates >= target1].sort_values()
    else:
        candidates = candidates[candidates <= target1].sort_values(ascending=False)
    target2 = float(candidates.iloc[0]) if not candidates.empty else entry + direction * 2 * risk
    path = future.iloc[entry_index:].copy()
    mfe = mae = 0.0
    first_filled = False
    realized = 0.0
    exit_price = entry
    exit_reason = "TIME"
    exit_date = str(path.iloc[-1]["trade_date"])
    for _, bar in path.iterrows():
        favorable = float(bar["high"] - entry) if direction == 1 else float(entry - bar["low"])
        adverse = float(entry - bar["low"]) if direction == 1 else float(bar["high"] - entry)
        mfe, mae = max(mfe, favorable), max(mae, adverse)
        stop_hit = float(bar["low"]) <= stop if direction == 1 else float(bar["high"]) >= stop
        if stop_hit:
            weight = 0.5 if first_filled else 1.0
            realized += weight * direction * (stop - entry)
            exit_price = stop
            exit_reason = "STOP_AFTER_PARTIAL" if first_filled else "STOP"
            exit_date = str(bar["trade_date"])
            break
        if not first_filled:
            hit1 = float(bar["high"]) >= target1 if direction == 1 else float(bar["low"]) <= target1
            if hit1:
                realized += 0.5 * risk
                first_filled = True
        hit2 = float(bar["high"]) >= target2 if direction == 1 else float(bar["low"]) <= target2
        if hit2:
            realized += (0.5 if first_filled else 1.0) * direction * (target2 - entry)
            exit_price = target2
            exit_reason = "TARGET2"
            exit_date = str(bar["trade_date"])
            break
    else:
        last = path.iloc[-1]
        exit_price = float(last["close"])
        realized += (0.5 if first_filled else 1.0) * direction * (exit_price - entry)
    return {
        "exit_date": exit_date,
        "exit_price": exit_price,
        "return_points": float(realized),
        "return_brl": float(realized * WIN_BRL_PER_POINT),
        "mfe_points": float(mfe),
        "mae_points": float(mae),
        "exit_reason": exit_reason,
        "stop": stop,
        "target1": target1,
        "target2": target2,
    }


def strategy_trades(zones: pd.DataFrame, bars: pd.DataFrame, config: IndexFuturesConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, zone in zones.iterrows():
        days = config.short_time_stop if zone["horizon"] == "SHORT" else config.swing_time_stop
        future = _future_bars(zone, bars, days + 3)
        if len(future) < 2:
            continue
        atr_points = max(float(zone.get("atr_points") or config.min_atr_points), config.min_atr_points)
        peers = zones[(zones["trade_date"].eq(zone["trade_date"])) & (zones["horizon"].eq(zone["horizon"])) & (zones["model"].eq(zone["model"]))]
        signals = {
            "REJECTION": _signal_rejection(zone, future),
            "BREAKOUT_RETEST": _signal_breakout(zone, future, config.breakout_atr * atr_points),
        }
        for playbook, signal in signals.items():
            if signal is None:
                continue
            signal_index, direction = signal
            entry_index = signal_index + 1
            if entry_index >= len(future):
                continue
            entry_bar = future.iloc[entry_index]
            entry = float(entry_bar["open"])
            exit_data = _simulate_exit(entry_index, entry, direction, zone, future, peers, config)
            raw_id = f"{zone['zone_id']}|{playbook}|{entry_bar['trade_date']}|{direction}"
            rows.append(
                {
                    "trade_id": hashlib.sha1(raw_id.encode()).hexdigest()[:20],
                    "zone_id": zone["zone_id"],
                    "source_trade_date": str(zone["trade_date"]),
                    "horizon": zone["horizon"],
                    "playbook": playbook,
                    "direction": "LONG" if direction == 1 else "SHORT",
                    "entry_date": str(entry_bar["trade_date"]),
                    "entry_price": entry,
                    "exit_date": exit_data["exit_date"],
                    "exit_price": exit_data["exit_price"],
                    "return_points": exit_data["return_points"],
                    "return_brl": exit_data["return_brl"],
                    "mfe_points": exit_data["mfe_points"],
                    "mae_points": exit_data["mae_points"],
                    "exit_reason": exit_data["exit_reason"],
                    "payload_json": json_dumps({"model": zone["model"], "stop": exit_data["stop"], "target1": exit_data["target1"], "target2": exit_data["target2"], "zone_type": zone["zone_type"]}),
                }
            )
    return pd.DataFrame(rows)


def _sample_masks(frame: pd.DataFrame, all_dates: list[str]) -> dict[str, pd.Series]:
    rank = {value: index for index, value in enumerate(sorted(all_dates))}
    positions = frame["source_trade_date"].map(rank)
    return {
        "ALL": pd.Series(True, index=frame.index),
        "TRAIN_126": positions.lt(126),
        "VALIDATION_1": positions.between(126, 188),
        "VALIDATION_2": positions.between(189, 251),
        "OUT_OF_SAMPLE": positions.between(126, 251),
    }


def metric_table(trades: pd.DataFrame, all_dates: list[str] | None = None) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    sample_masks = _sample_masks(
        trades, all_dates or sorted(trades["source_trade_date"].unique())
    )
    rows: list[dict[str, Any]] = []
    for sample, mask in sample_masks.items():
        selected = trades[mask]
        model = selected["payload_json"].map(lambda item: json.loads(item).get("model", "FULL"))
        for keys, group in selected.assign(model=model).groupby(["model", "horizon", "playbook", "direction"], sort=True):
            model_name, horizon, playbook, direction = keys
            points = group["return_points"].astype(float)
            wins = points[points > 0]
            losses = points[points < 0]
            equity = points.cumsum()
            drawdown = equity - equity.cummax().clip(lower=0)
            rows.append(
                {
                    "sample": sample,
                    "model": model_name,
                    "horizon": horizon,
                    "playbook": playbook,
                    "direction": direction,
                    "trades": int(len(group)),
                    "wins": int((points > 0).sum()),
                    "win_rate": float((points > 0).mean()),
                    "expectancy_points": float(points.mean()),
                    "profit_factor": float(wins.sum() / abs(losses.sum())) if not losses.empty else None,
                    "total_points": float(points.sum()),
                    "max_drawdown_points": float(abs(drawdown.min())) if not drawdown.empty else 0.0,
                    "payload_json": json_dumps({
                        "total_brl": float(group["return_brl"].sum()),
                        "minimum_sample_ok": len(group) >= 10,
                        "slippage_scenarios_brl": {
                            str(points_cost): float((points.sum() - points_cost * len(group)) * WIN_BRL_PER_POINT)
                            for points_cost in (0, 25, 50)
                        },
                    }),
                }
            )
    return pd.DataFrame(rows)


def region_metric_table(outcomes: pd.DataFrame, all_dates: list[str]) -> pd.DataFrame:
    if outcomes.empty:
        return pd.DataFrame()
    decoded = outcomes["payload_json"].map(json.loads)
    enriched = outcomes.assign(
        model=decoded.map(lambda item: item.get("model", "FULL")),
        zone_type=decoded.map(lambda item: item.get("zone_type", "NEUTRAL")),
    )
    rows: list[dict[str, Any]] = []
    for sample, mask in _sample_masks(enriched, all_dates).items():
        for keys, group in enriched[mask].groupby(["model", "horizon", "zone_type"], sort=True):
            model, horizon, zone_type = keys
            mfe = pd.to_numeric(group["mfe_points"], errors="coerce").fillna(0.0)
            mae = pd.to_numeric(group["mae_points"], errors="coerce").fillna(0.0)
            edge = mfe - mae
            rows.append(
                {
                    "sample": sample,
                    "model": model,
                    "horizon": horizon,
                    "playbook": "ZONE_QUALITY",
                    "direction": zone_type,
                    "trades": int(len(group)),
                    "wins": int(group["reaction"].sum()),
                    "win_rate": float(group["reaction"].mean()),
                    "expectancy_points": float(edge.mean()),
                    "profit_factor": float(mfe.sum() / mae.sum()) if mae.sum() > 0 else None,
                    "total_points": float(edge.sum()),
                    "max_drawdown_points": None,
                    "payload_json": json_dumps({
                        "touch_rate": float(group["touched"].mean()),
                        "breakout_rate": float(group["breakout"].mean()),
                        "false_breakout_rate": float(group["false_breakout"].mean()),
                        "minimum_sample_ok": len(group) >= 10,
                    }),
                }
            )
    return pd.DataFrame(rows)


def run_backtest(
    levels: pd.DataFrame,
    contexts: pd.DataFrame,
    bars: pd.DataFrame,
    config: IndexFuturesConfig | None = None,
) -> IndexBacktestResult:
    config = config or IndexFuturesConfig()
    zones = ablation_zones(levels, contexts, config)
    if zones.empty:
        return IndexBacktestResult(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    if "win_ticker" in contexts:
        zones = zones.merge(contexts[["trade_date", "win_ticker"]], on="trade_date", how="left")
    outcomes = evaluate_regions(zones, bars, config)
    trades = strategy_trades(zones, bars, config)
    all_dates = sorted(zones["trade_date"].astype(str).unique())
    metrics = pd.concat(
        [region_metric_table(outcomes, all_dates), metric_table(trades, all_dates)],
        ignore_index=True,
    )
    return IndexBacktestResult(outcomes, trades, metrics)
