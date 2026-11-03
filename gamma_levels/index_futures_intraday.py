from __future__ import annotations

import json
import math
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .index_futures import IndexFuturesConfig
from .index_futures_backtest import ablation_zones


@dataclass(slots=True)
class IntradayBacktestResult:
    events: pd.DataFrame
    exclusions: pd.DataFrame
    metrics: pd.DataFrame
    coverage: dict[str, Any]


@dataclass(slots=True)
class FixedPointsResult:
    trades: pd.DataFrame
    metrics: pd.DataFrame


@dataclass(slots=True)
class MultiSessionResult:
    trades: pd.DataFrame
    metrics: pd.DataFrame


def _header_key(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    return "".join(char for char in normalized if not unicodedata.combining(char)).strip().lower()


def _number_pt(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.strip().str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
        errors="coerce",
    )


def read_profit_5min(path: str | Path) -> pd.DataFrame:
    """Lê o CSV do Profit sem confundir separador decimal e milhar brasileiro."""
    source = Path(path)
    frame = pd.read_csv(source, sep=";", encoding="cp1252", dtype=str)
    renamed = {_header_key(column): column for column in frame.columns}
    required = {
        "ativo", "data", "hora", "abertura", "maximo", "minimo",
        "fechamento", "volume", "quantidade",
    }
    missing = sorted(required - set(renamed))
    if missing:
        raise ValueError(f"{source.name}: colunas ausentes: {', '.join(missing)}")
    frame = frame.rename(columns={original: key for key, original in renamed.items()})
    frame["timestamp"] = pd.to_datetime(
        frame["data"].str.strip() + " " + frame["hora"].str.strip(),
        format="%d/%m/%Y %H:%M:%S",
        errors="coerce",
    )
    for column in ("abertura", "maximo", "minimo", "fechamento", "volume", "quantidade"):
        frame[column] = _number_pt(frame[column])
    frame = frame.rename(
        columns={
            "ativo": "ticker",
            "abertura": "open",
            "maximo": "high",
            "minimo": "low",
            "fechamento": "close",
            "quantidade": "trades",
        }
    )
    invalid_timestamp = int(frame["timestamp"].isna().sum())
    numeric_columns = ["open", "high", "low", "close", "volume", "trades"]
    invalid_numeric = int(frame[numeric_columns].isna().any(axis=1).sum())
    if invalid_timestamp or invalid_numeric:
        raise ValueError(
            f"{source.name}: {invalid_timestamp} timestamps e "
            f"{invalid_numeric} linhas numéricas inválidas"
        )
    bad_ohlc = (
        frame["low"].gt(frame[["open", "close"]].min(axis=1))
        | frame["high"].lt(frame[["open", "close"]].max(axis=1))
        | frame["low"].gt(frame["high"])
    )
    if bad_ohlc.any():
        raise ValueError(f"{source.name}: {int(bad_ohlc.sum())} linhas com OHLC inconsistente")
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["trade_date"] = frame["timestamp"].dt.strftime("%Y-%m-%d")
    frame["source_file"] = source.name
    keep = [
        "ticker", "timestamp", "trade_date", "open", "high", "low", "close",
        "volume", "trades", "source_file",
    ]
    return frame[keep].sort_values(["timestamp", "ticker"]).reset_index(drop=True)


def load_profit_5min(paths: Iterable[str | Path]) -> pd.DataFrame:
    frames = [read_profit_5min(path) for path in paths]
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    duplicate = combined.duplicated(["ticker", "timestamp"], keep=False)
    if duplicate.any():
        conflicting = (
            combined[duplicate]
            .groupby(["ticker", "timestamp"])[["open", "high", "low", "close"]]
            .nunique()
            .gt(1)
            .any(axis=1)
        )
        if conflicting.any():
            raise ValueError(f"{int(conflicting.sum())} timestamps duplicados têm OHLC divergente")
        combined = combined.drop_duplicates(["ticker", "timestamp"], keep="first")
    return combined.sort_values(["timestamp", "ticker"]).reset_index(drop=True)


def intraday_coverage(bars: pd.DataFrame) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame()
    grouped = bars.groupby(["ticker", "trade_date"], sort=True)
    return grouped.agg(
        first_timestamp=("timestamp", "min"),
        last_timestamp=("timestamp", "max"),
        bars=("timestamp", "size"),
        volume=("volume", "sum"),
        trades=("trades", "sum"),
    ).reset_index()


def _excursions(
    path: pd.DataFrame,
    *,
    direction: int,
    center: float,
) -> tuple[float | None, float | None, float | None, float | None]:
    if path.empty:
        return None, None, None, None
    up = float(path["high"].max() - center)
    down = float(center - path["low"].min())
    if direction == 1:
        return up, down, up, down
    if direction == -1:
        return down, up, up, down
    return max(up, down), min(up, down), up, down


def _visit_count(session: pd.DataFrame, low: float, high: float) -> tuple[int, int]:
    inside = session["low"].le(high) & session["high"].ge(low)
    visits = int((inside & ~inside.shift(fill_value=False)).sum())
    return visits, int(inside.sum())


def _evaluate_zone(
    zone: pd.Series,
    session: pd.DataFrame,
    application_date: str,
    config: IndexFuturesConfig,
    windows: tuple[int, ...],
) -> dict[str, Any]:
    low = float(zone["zone_low"])
    high = float(zone["zone_high"])
    center = float(zone["zone_center"])
    atr_points = max(float(zone.get("atr_points") or config.min_atr_points), config.min_atr_points)
    direction = 1 if zone["zone_type"] == "BUYER" else -1 if zone["zone_type"] == "SELLER" else 0
    intersects = session["low"].le(high) & session["high"].ge(low)
    visits, bars_in_zone = _visit_count(session, low, high)
    base = {
        "zone_id": str(zone["zone_id"]),
        "source_trade_date": str(zone["trade_date"]),
        "application_date": application_date,
        "ticker": str(session.iloc[0]["ticker"]),
        "model": str(zone.get("model") or "FULL"),
        "horizon": str(zone["horizon"]),
        "zone_type": str(zone["zone_type"]),
        "confidence": str(zone.get("confidence") or ""),
        "strength": float(zone.get("strength") or 0.0),
        "zone_low": low,
        "zone_high": high,
        "zone_center": center,
        "atr_points": atr_points,
        "session_bars": int(len(session)),
        "touched": int(intersects.any()),
        "visits": visits,
        "bars_in_zone": bars_in_zone,
        "first_touch": None,
        "last_touch": None,
        "touch_open": None,
        "touch_high": None,
        "touch_low": None,
        "touch_close": None,
        "breakout": 0,
        "breakout_direction": None,
        "breakout_time": None,
        "false_breakout": 0,
        "mfe_eod": None,
        "mae_eod": None,
        "up_excursion_eod": None,
        "down_excursion_eod": None,
        "reaction_025atr": 0,
        "reaction_050atr": 0,
        "reaction_100atr": 0,
    }
    for minutes in windows:
        base[f"mfe_{minutes}m"] = None
        base[f"mae_{minutes}m"] = None
    if not intersects.any():
        return base
    touch_index = int(np.flatnonzero(intersects.to_numpy())[0])
    last_touch_index = int(np.flatnonzero(intersects.to_numpy())[-1])
    touch_bar = session.iloc[touch_index]
    base.update(
        {
            "first_touch": touch_bar["timestamp"].isoformat(),
            "last_touch": session.iloc[last_touch_index]["timestamp"].isoformat(),
            "touch_open": float(touch_bar["open"]),
            "touch_high": float(touch_bar["high"]),
            "touch_low": float(touch_bar["low"]),
            "touch_close": float(touch_bar["close"]),
        }
    )
    path = session.iloc[touch_index:].reset_index(drop=True)
    threshold = config.breakout_atr * atr_points
    if direction == 1:
        break_mask = path["close"].lt(low - threshold)
    elif direction == -1:
        break_mask = path["close"].gt(high + threshold)
    else:
        down_break = path["close"].lt(low - threshold)
        up_break = path["close"].gt(high + threshold)
        break_mask = down_break | up_break
    break_position: int | None = None
    breakout_direction: int | None = None
    if break_mask.any():
        break_position = int(np.flatnonzero(break_mask.to_numpy())[0])
        break_row = path.iloc[break_position]
        breakout_direction = 1 if float(break_row["close"]) > high else -1
        after = path.iloc[break_position + 1: break_position + 4]
        returned = (
            after["close"].le(high).any()
            if breakout_direction == 1
            else after["close"].ge(low).any()
        )
        base.update(
            {
                "breakout": 1,
                "breakout_direction": "UP" if breakout_direction == 1 else "DOWN",
                "breakout_time": break_row["timestamp"].isoformat(),
                "false_breakout": int(returned),
            }
        )
    reaction_path = path.iloc[:break_position] if break_position is not None else path
    reaction_mfe, _, _, _ = _excursions(reaction_path, direction=direction, center=center)
    if reaction_mfe is not None:
        base["reaction_025atr"] = int(reaction_mfe >= 0.25 * atr_points)
        base["reaction_050atr"] = int(reaction_mfe >= 0.50 * atr_points)
        base["reaction_100atr"] = int(reaction_mfe >= 1.00 * atr_points)
    mfe, mae, up, down = _excursions(path, direction=direction, center=center)
    base.update(
        {
            "mfe_eod": mfe,
            "mae_eod": mae,
            "up_excursion_eod": up,
            "down_excursion_eod": down,
        }
    )
    for minutes in windows:
        count = max(int(math.ceil(minutes / 5)), 1)
        window_path = path.iloc[:count]
        window_mfe, window_mae, _, _ = _excursions(
            window_path, direction=direction, center=center
        )
        base[f"mfe_{minutes}m"] = window_mfe
        base[f"mae_{minutes}m"] = window_mae
    return base


def _metric_table(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    keys = ["model", "horizon", "zone_type", "confidence"]
    for group_keys, group in events.groupby(keys, dropna=False, sort=True):
        model, horizon, zone_type, confidence = group_keys
        touched = group[group["touched"].eq(1)]
        rows.append(
            {
                "model": model,
                "horizon": horizon,
                "zone_type": zone_type,
                "confidence": confidence,
                "zones": int(len(group)),
                "touches": int(len(touched)),
                "touch_rate": float(group["touched"].mean()),
                "reaction_025atr_rate": (
                    float(touched["reaction_025atr"].mean()) if not touched.empty else None
                ),
                "reaction_050atr_rate": (
                    float(touched["reaction_050atr"].mean()) if not touched.empty else None
                ),
                "reaction_100atr_rate": (
                    float(touched["reaction_100atr"].mean()) if not touched.empty else None
                ),
                "breakout_rate": (
                    float(touched["breakout"].mean()) if not touched.empty else None
                ),
                "false_breakout_rate": (
                    float(touched.loc[touched["breakout"].eq(1), "false_breakout"].mean())
                    if touched["breakout"].eq(1).any() else None
                ),
                "median_mfe_eod": (
                    float(touched["mfe_eod"].median()) if not touched.empty else None
                ),
                "median_mae_eod": (
                    float(touched["mae_eod"].median()) if not touched.empty else None
                ),
                "median_visits": (
                    float(touched["visits"].median()) if not touched.empty else None
                ),
            }
        )
    return pd.DataFrame(rows)


def _fixed_exit(
    session: pd.DataFrame,
    *,
    entry_index: int,
    entry_price: float,
    direction: int,
    stop_points: float,
    target_points: float,
    entry_inside_bar: bool,
) -> dict[str, Any]:
    stop = entry_price - direction * stop_points
    target = entry_price + direction * target_points
    path = session.iloc[entry_index:].reset_index(drop=True)
    exit_price = float(path.iloc[-1]["close"])
    exit_time = path.iloc[-1]["timestamp"].isoformat()
    exit_reason = "SESSION_CLOSE"
    mfe = 0.0
    mae = 0.0
    for offset, bar in path.iterrows():
        high = float(bar["high"])
        low = float(bar["low"])
        favorable = high - entry_price if direction == 1 else entry_price - low
        adverse = entry_price - low if direction == 1 else high - entry_price
        mfe = max(mfe, favorable)
        mae = max(mae, adverse)
        stop_hit = low <= stop if direction == 1 else high >= stop
        target_hit = high >= target if direction == 1 else low <= target
        if stop_hit:
            exit_price = stop
            exit_time = bar["timestamp"].isoformat()
            exit_reason = "STOP"
            break
        if target_hit and not (entry_inside_bar and offset == 0):
            exit_price = target
            exit_time = bar["timestamp"].isoformat()
            exit_reason = "TARGET"
            break
    return {
        "stop_price": stop,
        "target_price": target,
        "exit_price": float(exit_price),
        "exit_time": exit_time,
        "exit_reason": exit_reason,
        "return_points": float(direction * (exit_price - entry_price)),
        "mfe_points": float(mfe),
        "mae_points": float(mae),
    }


def _fixed_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    selections = {"INDEPENDENT": trades}
    ordered = trades.assign(
        _confidence=trades["confidence"].map({"HIGH": 2, "MEDIUM": 1, "LOW": 0}).fillna(0)
    ).sort_values(
        ["playbook", "horizon", "application_date", "entry_time", "_confidence", "strength"],
        ascending=[True, True, True, True, False, False],
    )
    selections["FIRST_PER_DAY"] = ordered.drop_duplicates(
        ["playbook", "horizon", "application_date"],
        keep="first",
    )
    for selection, selected in selections.items():
        grouped: list[tuple[tuple[str, str, str], pd.DataFrame]] = []
        grouped.extend(
            (
                (str(playbook), str(horizon), str(zone_type)),
                group,
            )
            for (playbook, horizon, zone_type), group in selected.groupby(
                ["playbook", "horizon", "zone_type"], sort=True
            )
        )
        grouped.extend(
            (
                (str(playbook), str(horizon), "ALL_DIRECTIONAL"),
                group,
            )
            for (playbook, horizon), group in selected.groupby(
                ["playbook", "horizon"], sort=True
            )
        )
        for (playbook, horizon, zone_type), group in grouped:
            points = group["return_points"].astype(float)
            wins = points[points > 0]
            losses = points[points < 0]
            equity = points.cumsum()
            drawdown = equity - equity.cummax().clip(lower=0)
            rows.append(
                {
                    "selection": selection,
                    "playbook": playbook,
                    "horizon": horizon,
                    "zone_type": zone_type,
                    "trades": int(len(group)),
                    "targets": int(group["exit_reason"].eq("TARGET").sum()),
                    "stops": int(group["exit_reason"].eq("STOP").sum()),
                    "session_closes": int(group["exit_reason"].eq("SESSION_CLOSE").sum()),
                    "win_rate": float((points > 0).mean()),
                    "expectancy_points": float(points.mean()),
                    "profit_factor": (
                        float(wins.sum() / abs(losses.sum())) if not losses.empty else None
                    ),
                    "total_points": float(points.sum()),
                    "max_drawdown_points": (
                        float(abs(drawdown.min())) if not drawdown.empty else 0.0
                    ),
                    "total_after_25pt_cost": float(points.sum() - 25 * len(group)),
                    "total_after_50pt_cost": float(points.sum() - 50 * len(group)),
                }
            )
    return pd.DataFrame(rows)


def summarize_fixed_points(trades: pd.DataFrame) -> pd.DataFrame:
    """Resume operações fixas preservando as regras de seleção do backtest."""
    return _fixed_metrics(trades)


def run_fixed_points_strategy(
    events: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    stop_points: float = 300.0,
    target_points: float = 300.0,
) -> FixedPointsResult:
    """Simula 300/300 no primeiro toque e após rejeição confirmada em 5 minutos."""
    sessions = {
        (str(trade_date), str(ticker)): group.sort_values("timestamp").reset_index(drop=True)
        for (trade_date, ticker), group in bars.groupby(["trade_date", "ticker"], sort=False)
    }
    rows: list[dict[str, Any]] = []
    directional = events[
        events["touched"].eq(1) & events["zone_type"].isin(["BUYER", "SELLER"])
    ]
    for _, event in directional.iterrows():
        key = (str(event["application_date"]), str(event["ticker"]))
        session = sessions.get(key)
        if session is None or session.empty:
            continue
        direction = 1 if event["zone_type"] == "BUYER" else -1
        low = float(event["zone_low"])
        high = float(event["zone_high"])
        touched = session["low"].le(high) & session["high"].ge(low)
        touch_positions = np.flatnonzero(touched.to_numpy())
        if not len(touch_positions):
            continue
        touch_index = int(touch_positions[0])
        touch_open = float(session.iloc[touch_index]["open"])
        if low <= touch_open <= high:
            touch_entry = touch_open
        elif touch_open > high:
            touch_entry = high
        else:
            touch_entry = low
        candidates: list[tuple[str, int, float, bool, str]] = [
            (
                "FIRST_TOUCH",
                touch_index,
                touch_entry,
                True,
                session.iloc[touch_index]["timestamp"].isoformat(),
            )
        ]
        rejection_index: int | None = None
        for index in touch_positions:
            bar = session.iloc[int(index)]
            confirmed = (
                float(bar["close"]) > high
                if direction == 1 else float(bar["close"]) < low
            )
            if confirmed:
                rejection_index = int(index)
                break
        if rejection_index is not None and rejection_index + 1 < len(session):
            entry_index = rejection_index + 1
            candidates.append(
                (
                    "REJECTION_5M",
                    entry_index,
                    float(session.iloc[entry_index]["open"]),
                    False,
                    session.iloc[entry_index]["timestamp"].isoformat(),
                )
            )
        for playbook, entry_index, entry_price, inside_bar, entry_time in candidates:
            outcome = _fixed_exit(
                session,
                entry_index=entry_index,
                entry_price=entry_price,
                direction=direction,
                stop_points=stop_points,
                target_points=target_points,
                entry_inside_bar=inside_bar,
            )
            rows.append(
                {
                    "zone_id": event["zone_id"],
                    "source_trade_date": event["source_trade_date"],
                    "application_date": event["application_date"],
                    "ticker": event["ticker"],
                    "model": event["model"],
                    "horizon": event["horizon"],
                    "zone_type": event["zone_type"],
                    "confidence": event["confidence"],
                    "strength": event["strength"],
                    "playbook": playbook,
                    "entry_time": entry_time,
                    "entry_price": float(entry_price),
                    **outcome,
                }
            )
    trades = pd.DataFrame(rows)
    return FixedPointsResult(trades, summarize_fixed_points(trades))


def _multisession_exit(
    ticker_bars: pd.DataFrame,
    *,
    entry_time: pd.Timestamp,
    entry_price: float,
    direction: int,
    stop_points: float,
    target_points: float,
    max_sessions: int,
) -> dict[str, Any]:
    future = ticker_bars[ticker_bars["timestamp"].ge(entry_time)].copy()
    dates = future["trade_date"].drop_duplicates().tolist()
    holding_dates = dates[:max_sessions]
    path = future[future["trade_date"].isin(holding_dates)].reset_index(drop=True)
    stop = entry_price - direction * stop_points
    target = entry_price + direction * target_points
    exit_price: float | None = None
    exit_time: str | None = None
    exit_reason = "CENSORED"
    mfe = 0.0
    mae = 0.0
    for _, bar in path.iterrows():
        open_price = float(bar["open"])
        high = float(bar["high"])
        low = float(bar["low"])
        favorable = high - entry_price if direction == 1 else entry_price - low
        adverse = entry_price - low if direction == 1 else high - entry_price
        mfe = max(mfe, favorable)
        mae = max(mae, adverse)
        stop_gap = open_price <= stop if direction == 1 else open_price >= stop
        target_gap = open_price >= target if direction == 1 else open_price <= target
        if stop_gap:
            exit_price = open_price
            exit_time = bar["timestamp"].isoformat()
            exit_reason = "STOP_GAP"
            break
        if target_gap:
            exit_price = open_price
            exit_time = bar["timestamp"].isoformat()
            exit_reason = "TARGET_GAP"
            break
        stop_hit = low <= stop if direction == 1 else high >= stop
        target_hit = high >= target if direction == 1 else low <= target
        if stop_hit:
            exit_price = stop
            exit_time = bar["timestamp"].isoformat()
            exit_reason = "STOP"
            break
        if target_hit:
            exit_price = target
            exit_time = bar["timestamp"].isoformat()
            exit_reason = "TARGET"
            break
    if exit_price is None and len(dates) >= max_sessions and not path.empty:
        exit_price = float(path.iloc[-1]["close"])
        exit_time = path.iloc[-1]["timestamp"].isoformat()
        exit_reason = "TIME_STOP"
    return_points = (
        float(direction * (exit_price - entry_price))
        if exit_price is not None
        else None
    )
    return {
        "stop_price": float(stop),
        "target_price": float(target),
        "exit_price": exit_price,
        "exit_time": exit_time,
        "exit_reason": exit_reason,
        "return_points": return_points,
        "mfe_points": float(mfe),
        "mae_points": float(mae),
        "sessions_available": int(len(dates)),
        "sessions_in_path": int(len(holding_dates)),
        "path_end_time": (
            path.iloc[-1]["timestamp"].isoformat() if not path.empty else None
        ),
    }


def _multisession_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    selections = {
        "INDEPENDENT": trades,
        "ONE_POSITION": trades[trades["selected_one_position"].eq(1)],
    }
    for selection, selected in selections.items():
        censored = selected[selected["exit_reason"].eq("CENSORED")]
        valid = selected[~selected["exit_reason"].eq("CENSORED")].copy()
        if valid.empty:
            continue
        points = valid["return_points"].astype(float)
        wins = points[points > 0]
        losses = points[points < 0]
        equity = points.cumsum()
        drawdown = equity - equity.cummax().clip(lower=0)
        rows.append(
            {
                "selection": selection,
                "signals": int(len(selected)),
                "trades": int(len(valid)),
                "censored": int(len(censored)),
                "targets": int(valid["exit_reason"].str.startswith("TARGET").sum()),
                "stops": int(valid["exit_reason"].str.startswith("STOP").sum()),
                "time_stops": int(valid["exit_reason"].eq("TIME_STOP").sum()),
                "win_rate": float((points > 0).mean()),
                "expectancy_points": float(points.mean()),
                "expectancy_after_25pt_cost": float(points.mean() - 25.0),
                "expectancy_after_50pt_cost": float(points.mean() - 50.0),
                "profit_factor": (
                    float(wins.sum() / abs(losses.sum())) if not losses.empty else None
                ),
                "total_points": float(points.sum()),
                "total_after_25pt_cost": float(points.sum() - 25 * len(valid)),
                "total_after_50pt_cost": float(points.sum() - 50 * len(valid)),
                "max_drawdown_points": (
                    float(abs(drawdown.min())) if not drawdown.empty else 0.0
                ),
            }
        )
    return pd.DataFrame(rows)


def summarize_multisession(trades: pd.DataFrame) -> pd.DataFrame:
    """Resume trades multi-pregão sem recalcular sinais ou saídas."""
    return _multisession_metrics(trades)


def run_multisession_fixed_strategy(
    events: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    stop_points: float,
    target_points: float,
    max_sessions: int,
    horizon: str = "SWING",
    zone_type: str = "BUYER",
) -> MultiSessionResult:
    """Simula rejeição em 5 min com permanência de até vários pregões."""
    if max_sessions < 1:
        raise ValueError("max_sessions deve ser positivo")
    sessions = {
        (str(trade_date), str(ticker)): group.sort_values("timestamp").reset_index(drop=True)
        for (trade_date, ticker), group in bars.groupby(["trade_date", "ticker"], sort=False)
    }
    ticker_paths = {
        str(ticker): group.sort_values("timestamp").reset_index(drop=True)
        for ticker, group in bars.groupby("ticker", sort=False)
    }
    candidates = events[
        events["touched"].eq(1)
        & events["horizon"].eq(horizon)
        & events["zone_type"].eq(zone_type)
    ]
    signal_rows: list[dict[str, Any]] = []
    for _, event in candidates.iterrows():
        key = (str(event["application_date"]), str(event["ticker"]))
        session = sessions.get(key)
        if session is None or session.empty:
            continue
        direction = 1 if zone_type == "BUYER" else -1
        low = float(event["zone_low"])
        high = float(event["zone_high"])
        touched = session["low"].le(high) & session["high"].ge(low)
        rejection_index: int | None = None
        for index in np.flatnonzero(touched.to_numpy()):
            bar = session.iloc[int(index)]
            confirmed = (
                float(bar["close"]) > high
                if direction == 1
                else float(bar["close"]) < low
            )
            if confirmed:
                rejection_index = int(index)
                break
        if rejection_index is None or rejection_index + 1 >= len(session):
            continue
        entry_index = rejection_index + 1
        signal_rows.append(
            {
                "zone_id": event["zone_id"],
                "source_trade_date": event["source_trade_date"],
                "application_date": event["application_date"],
                "ticker": event["ticker"],
                "model": event["model"],
                "horizon": event["horizon"],
                "zone_type": event["zone_type"],
                "confidence": event["confidence"],
                "strength": event["strength"],
                "playbook": "REJECTION_5M",
                "entry_time": session.iloc[entry_index]["timestamp"].isoformat(),
                "entry_price": float(session.iloc[entry_index]["open"]),
                "direction": direction,
            }
        )
    signals = pd.DataFrame(signal_rows)
    if signals.empty:
        return MultiSessionResult(pd.DataFrame(), pd.DataFrame())
    signals["_confidence"] = signals["confidence"].map(
        {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
    ).fillna(0)
    signals = (
        signals.sort_values(
            ["application_date", "entry_time", "_confidence", "strength"],
            ascending=[True, True, False, False],
        )
        .drop_duplicates("application_date", keep="first")
        .drop(columns="_confidence")
        .reset_index(drop=True)
    )
    rows: list[dict[str, Any]] = []
    for _, signal in signals.iterrows():
        ticker_bars = ticker_paths[str(signal["ticker"])]
        outcome = _multisession_exit(
            ticker_bars,
            entry_time=pd.Timestamp(signal["entry_time"]),
            entry_price=float(signal["entry_price"]),
            direction=int(signal["direction"]),
            stop_points=stop_points,
            target_points=target_points,
            max_sessions=max_sessions,
        )
        rows.append(
            {
                **signal.to_dict(),
                "stop_points": float(stop_points),
                "target_points": float(target_points),
                "max_sessions": int(max_sessions),
                **outcome,
            }
        )
    trades = pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)
    selected: list[int] = []
    last_exit: pd.Timestamp | None = None
    for index, trade in trades.iterrows():
        entry_time = pd.Timestamp(trade["entry_time"])
        if last_exit is None or entry_time > last_exit:
            selected.append(index)
            end_time = (
                trade["exit_time"]
                if pd.notna(trade["exit_time"])
                else trade["path_end_time"]
            )
            last_exit = pd.Timestamp(end_time)
    trades["selected_one_position"] = 0
    trades.loc[selected, "selected_one_position"] = 1
    return MultiSessionResult(trades, summarize_multisession(trades))


def run_intraday_backtest(
    levels: pd.DataFrame,
    map_contexts: pd.DataFrame,
    market_calendar: pd.DataFrame,
    bars: pd.DataFrame,
    config: IndexFuturesConfig | None = None,
    *,
    model: str = "IBOV_BOVA",
    windows: tuple[int, ...] = (5, 15, 30, 60),
) -> IntradayBacktestResult:
    config = config or IndexFuturesConfig()
    zones = ablation_zones(levels, map_contexts, config)
    if not zones.empty:
        zones = zones[zones["model"].eq(model)].copy()
        zones = zones.merge(
            map_contexts[["trade_date", "win_ticker"]],
            on="trade_date",
            how="left",
            suffixes=("", "_source"),
        )
    calendar = market_calendar[["trade_date", "win_ticker"]].copy()
    calendar["trade_date"] = calendar["trade_date"].astype(str)
    calendar["_priority"] = 0
    if not bars.empty:
        bar_calendar = (
            bars.groupby(["trade_date", "ticker"], as_index=False)
            .size()
            .sort_values(["trade_date", "size"], ascending=[True, False])
            .drop_duplicates("trade_date")
            .rename(columns={"ticker": "win_ticker"})
        )[["trade_date", "win_ticker"]]
        bar_calendar["_priority"] = 1
        calendar = pd.concat([calendar, bar_calendar], ignore_index=True)
    calendar = (
        calendar.sort_values(["trade_date", "_priority"])
        .drop_duplicates("trade_date")
        .drop(columns="_priority")
    )
    calendar["application_date"] = calendar["trade_date"].shift(-1)
    calendar["application_ticker"] = calendar["win_ticker"].shift(-1)
    next_day = calendar.set_index("trade_date")[["application_date", "application_ticker"]].to_dict("index")
    sessions = {
        (str(trade_date), str(ticker)): group.sort_values("timestamp").reset_index(drop=True)
        for (trade_date, ticker), group in bars.groupby(["trade_date", "ticker"], sort=False)
    }
    event_rows: list[dict[str, Any]] = []
    exclusion_rows: list[dict[str, Any]] = []
    for _, zone in zones.iterrows() if not zones.empty else []:
        source_date = str(zone["trade_date"])
        application = next_day.get(source_date)
        reason = None
        application_date = None
        application_ticker = None
        if not application or pd.isna(application["application_date"]):
            reason = "NO_NEXT_SESSION"
        else:
            application_date = str(application["application_date"])
            application_ticker = str(application["application_ticker"])
            if str(zone.get("win_ticker") or "") != application_ticker:
                reason = "CONTRACT_ROLL"
            elif (application_date, application_ticker) not in sessions:
                reason = "INTRADAY_FILE_MISSING"
        if reason:
            exclusion_rows.append(
                {
                    "zone_id": str(zone["zone_id"]),
                    "source_trade_date": source_date,
                    "application_date": application_date,
                    "source_ticker": zone.get("win_ticker"),
                    "application_ticker": application_ticker,
                    "reason": reason,
                }
            )
            continue
        event_rows.append(
            _evaluate_zone(
                zone,
                sessions[(application_date, application_ticker)],
                application_date,
                config,
                windows,
            )
        )
    events = pd.DataFrame(event_rows)
    exclusions = pd.DataFrame(exclusion_rows)
    coverage_frame = intraday_coverage(bars)
    coverage = {
        "model": model,
        "bar_minutes": 5,
        "bars": int(len(bars)),
        "contracts": sorted(bars["ticker"].astype(str).unique()) if not bars.empty else [],
        "raw_sessions": int(len(coverage_frame)),
        "first_bar": bars["timestamp"].min().isoformat() if not bars.empty else None,
        "last_bar": bars["timestamp"].max().isoformat() if not bars.empty else None,
        "zones_rebuilt": int(len(zones)),
        "zones_evaluated": int(len(events)),
        "zones_excluded": int(len(exclusions)),
        "application_sessions": (
            int(events["application_date"].nunique()) if not events.empty else 0
        ),
        "exclusion_reasons": (
            exclusions["reason"].value_counts().to_dict() if not exclusions.empty else {}
        ),
    }
    return IntradayBacktestResult(events, exclusions, _metric_table(events), coverage)


def contexts_from_daily_maps(maps: pd.DataFrame) -> pd.DataFrame:
    if maps.empty:
        return pd.DataFrame()
    rows = [json.loads(value) for value in maps["context_json"].astype(str)]
    frame = pd.DataFrame(rows)
    frame["trade_date"] = frame["trade_date"].astype(str)
    return frame
