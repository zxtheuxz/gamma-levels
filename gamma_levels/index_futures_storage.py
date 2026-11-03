from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd

from .index_futures import DailyIndexMap


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS composition_snapshots (
    as_of TEXT NOT NULL,
    ticker TEXT NOT NULL,
    asset_root TEXT NOT NULL,
    weight REAL NOT NULL,
    theoretical_quantity REAL,
    asset TEXT,
    type TEXT,
    source_url TEXT,
    PRIMARY KEY (as_of, ticker)
);

CREATE TABLE IF NOT EXISTS market_context (
    trade_date TEXT PRIMARY KEY,
    ibov_open REAL,
    ibov_low REAL,
    ibov_high REAL,
    ibov_close REAL,
    ibov_settlement REAL,
    bova_open REAL,
    bova_low REAL,
    bova_high REAL,
    bova_close REAL,
    win_ticker TEXT,
    win_expiration TEXT,
    win_open REAL,
    win_low REAL,
    win_high REAL,
    win_close REAL,
    win_contracts REAL,
    win_financial_volume REAL,
    source_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS daily_maps (
    trade_date TEXT PRIMARY KEY,
    context_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_levels (
    trade_date TEXT NOT NULL,
    horizon TEXT NOT NULL,
    source TEXT NOT NULL,
    source_family TEXT NOT NULL,
    component_ticker TEXT,
    level_kind TEXT NOT NULL,
    side TEXT NOT NULL,
    source_level REAL NOT NULL,
    win_level REAL NOT NULL,
    strength REAL NOT NULL,
    quality_score REAL NOT NULL,
    component_weight REAL,
    beta REAL
);
CREATE INDEX IF NOT EXISTS source_levels_date_idx ON source_levels(trade_date, horizon);

CREATE TABLE IF NOT EXISTS index_zones (
    trade_date TEXT NOT NULL,
    horizon TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    zone_low REAL NOT NULL,
    zone_high REAL NOT NULL,
    zone_center REAL NOT NULL,
    zone_type TEXT NOT NULL,
    strength REAL NOT NULL,
    buyer_score REAL NOT NULL,
    seller_score REAL NOT NULL,
    buyer_share REAL NOT NULL,
    seller_share REAL NOT NULL,
    source_families TEXT NOT NULL,
    sources TEXT NOT NULL,
    family_count INTEGER NOT NULL,
    level_count INTEGER NOT NULL,
    confidence TEXT NOT NULL,
    PRIMARY KEY (trade_date, zone_id)
);

CREATE TABLE IF NOT EXISTS source_summaries (
    trade_date TEXT NOT NULL,
    horizon TEXT NOT NULL,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (trade_date, horizon, source)
);

CREATE TABLE IF NOT EXISTS data_quality (
    trade_date TEXT NOT NULL,
    horizon TEXT NOT NULL,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (trade_date, horizon, source)
);

CREATE TABLE IF NOT EXISTS footprint_bins (
    trade_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    price_bin REAL NOT NULL,
    volume REAL NOT NULL,
    trades INTEGER NOT NULL,
    buy_volume_est REAL NOT NULL,
    sell_volume_est REAL NOT NULL,
    delta_est REAL NOT NULL,
    delta_share REAL,
    buyer_participants INTEGER,
    seller_participants INTEGER,
    PRIMARY KEY (trade_date, ticker, price_bin)
);

CREATE TABLE IF NOT EXISTS region_outcomes (
    zone_id TEXT NOT NULL,
    source_trade_date TEXT NOT NULL,
    horizon TEXT NOT NULL,
    evaluation_start TEXT NOT NULL,
    touched INTEGER NOT NULL,
    touch_date TEXT,
    reaction INTEGER NOT NULL,
    breakout INTEGER NOT NULL,
    false_breakout INTEGER NOT NULL,
    mfe_points REAL,
    mae_points REAL,
    days_to_event INTEGER,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (zone_id, evaluation_start)
);

CREATE TABLE IF NOT EXISTS strategy_trades (
    trade_id TEXT PRIMARY KEY,
    zone_id TEXT NOT NULL,
    source_trade_date TEXT NOT NULL,
    horizon TEXT NOT NULL,
    playbook TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_date TEXT NOT NULL,
    exit_price REAL NOT NULL,
    return_points REAL NOT NULL,
    return_brl REAL NOT NULL,
    mfe_points REAL,
    mae_points REAL,
    exit_reason TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_metrics (
    sample TEXT NOT NULL,
    model TEXT NOT NULL,
    horizon TEXT NOT NULL,
    playbook TEXT NOT NULL,
    direction TEXT NOT NULL,
    trades INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    win_rate REAL,
    expectancy_points REAL,
    profit_factor REAL,
    total_points REAL,
    max_drawdown_points REAL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (sample, model, horizon, playbook, direction)
);
"""


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if value is pd.NA:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (pd.Timestamp, date)):
        return value.isoformat()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _json_clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_clean(item) for item in value]
    return _clean(value)


def json_dumps(value: Any) -> str:
    return json.dumps(
        _json_clean(value),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


class IndexFuturesDatabase:
    def __init__(self, path: str | Path = "data/index_futures/gamma_index.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._migrate_schema(connection)

    @staticmethod
    def _migrate_schema(connection: sqlite3.Connection) -> None:
        metric_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(backtest_metrics)").fetchall()
        }
        if metric_columns and "model" not in metric_columns:
            connection.executescript(
                """
                ALTER TABLE backtest_metrics RENAME TO backtest_metrics_legacy;
                CREATE TABLE backtest_metrics (
                    sample TEXT NOT NULL,
                    model TEXT NOT NULL,
                    horizon TEXT NOT NULL,
                    playbook TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    trades INTEGER NOT NULL,
                    wins INTEGER NOT NULL,
                    win_rate REAL,
                    expectancy_points REAL,
                    profit_factor REAL,
                    total_points REAL,
                    max_drawdown_points REAL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (sample, model, horizon, playbook, direction)
                );
                INSERT INTO backtest_metrics
                SELECT sample,'FULL',horizon,playbook,direction,trades,wins,win_rate,
                       expectancy_points,profit_factor,total_points,max_drawdown_points,payload_json
                FROM backtest_metrics_legacy;
                DROP TABLE backtest_metrics_legacy;
                """
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def frame(self, query: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
        with self.connect() as connection:
            return pd.read_sql_query(query, connection, params=params)

    def save_composition(self, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        columns = [
            "as_of", "ticker", "asset_root", "weight", "theoretical_quantity",
            "asset", "type", "source_url",
        ]
        rows = [tuple(_clean(item.get(column)) for column in columns) for item in frame.to_dict("records")]
        with self.connect() as connection:
            connection.executemany(
                """INSERT OR REPLACE INTO composition_snapshots
                (as_of,ticker,asset_root,weight,theoretical_quantity,asset,type,source_url)
                VALUES (?,?,?,?,?,?,?,?)""",
                rows,
            )

    def composition_for(self, trade_date: date, *, allow_next_day: bool = True) -> pd.DataFrame:
        limit = trade_date + timedelta(days=1) if allow_next_day else trade_date
        with self.connect() as connection:
            row = connection.execute(
                "SELECT MAX(as_of) AS as_of FROM composition_snapshots WHERE as_of<=?",
                (limit.isoformat(),),
            ).fetchone()
            if not row or not row["as_of"]:
                return pd.DataFrame()
            return pd.read_sql_query(
                "SELECT * FROM composition_snapshots WHERE as_of=? ORDER BY weight DESC",
                connection,
                params=(row["as_of"],),
            )

    def save_market_context(self, row: dict[str, Any]) -> None:
        columns = [
            "trade_date", "ibov_open", "ibov_low", "ibov_high", "ibov_close",
            "ibov_settlement", "bova_open", "bova_low", "bova_high", "bova_close",
            "win_ticker", "win_expiration", "win_open", "win_low", "win_high",
            "win_close", "win_contracts", "win_financial_volume",
        ]
        values = [_clean(row.get(column)) for column in columns]
        values.append(json_dumps(row))
        placeholders = ",".join("?" for _ in values)
        with self.connect() as connection:
            connection.execute(
                f"""INSERT OR REPLACE INTO market_context
                ({','.join(columns)},source_json) VALUES ({placeholders})""",
                values,
            )

    def market_history(self, end: date | None = None) -> pd.DataFrame:
        query = "SELECT * FROM market_context"
        params: tuple[Any, ...] = ()
        if end is not None:
            query += " WHERE trade_date<=?"
            params = (end.isoformat(),)
        return self.frame(query + " ORDER BY trade_date", params)

    def save_daily_map(self, result: DailyIndexMap) -> None:
        trade_date = str(result.context["trade_date"])
        with self.connect() as connection:
            connection.execute("DELETE FROM source_levels WHERE trade_date=?", (trade_date,))
            connection.execute("DELETE FROM index_zones WHERE trade_date=?", (trade_date,))
            connection.execute("DELETE FROM source_summaries WHERE trade_date=?", (trade_date,))
            connection.execute("DELETE FROM data_quality WHERE trade_date=?", (trade_date,))
            connection.execute(
                "INSERT OR REPLACE INTO daily_maps(trade_date,context_json,created_at) VALUES (?,?,?)",
                (trade_date, json_dumps(result.context), datetime_now()),
            )
            if not result.levels.empty:
                columns = list(result.levels.columns)
                connection.executemany(
                    f"INSERT INTO source_levels({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                    [tuple(_clean(item.get(column)) for column in columns) for item in result.levels.to_dict("records")],
                )
            if not result.zones.empty:
                columns = list(result.zones.columns)
                connection.executemany(
                    f"INSERT INTO index_zones({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                    [tuple(_clean(item.get(column)) for column in columns) for item in result.zones.to_dict("records")],
                )
            for table, frame in (("source_summaries", result.source_summary), ("data_quality", result.quality)):
                if frame.empty:
                    continue
                connection.executemany(
                    f"INSERT INTO {table}(trade_date,horizon,source,payload_json) VALUES (?,?,?,?)",
                    [
                        (
                            trade_date,
                            str(item.get("horizon")),
                            str(item.get("source")),
                            json_dumps(item),
                        )
                        for item in frame.to_dict("records")
                    ],
                )

    def save_footprint(self, bins: pd.DataFrame) -> None:
        if bins.empty:
            return
        required = [
            "trade_date", "ticker", "price_bin", "volume", "trades",
            "buy_volume_est", "sell_volume_est", "delta_est", "delta_share",
            "buyer_participants", "seller_participants",
        ]
        with self.connect() as connection:
            for (trade_date, ticker), group in bins.groupby(["trade_date", "ticker"]):
                connection.execute(
                    "DELETE FROM footprint_bins WHERE trade_date=? AND ticker=?",
                    (str(trade_date), str(ticker)),
                )
                connection.executemany(
                    f"INSERT INTO footprint_bins({','.join(required)}) VALUES ({','.join('?' for _ in required)})",
                    [tuple(_clean(item.get(column)) for column in required) for item in group.to_dict("records")],
                )

    def save_backtest(
        self,
        region_outcomes: pd.DataFrame,
        trades: pd.DataFrame,
        metrics: pd.DataFrame,
    ) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM region_outcomes")
            connection.execute("DELETE FROM strategy_trades")
            connection.execute("DELETE FROM backtest_metrics")
            if not region_outcomes.empty:
                columns = list(region_outcomes.columns)
                connection.executemany(
                    f"INSERT INTO region_outcomes({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                    [tuple(_clean(item.get(column)) for column in columns) for item in region_outcomes.to_dict("records")],
                )
            if not trades.empty:
                columns = list(trades.columns)
                connection.executemany(
                    f"INSERT INTO strategy_trades({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                    [tuple(_clean(item.get(column)) for column in columns) for item in trades.to_dict("records")],
                )
            if not metrics.empty:
                columns = list(metrics.columns)
                connection.executemany(
                    f"INSERT INTO backtest_metrics({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                    [tuple(_clean(item.get(column)) for column in columns) for item in metrics.to_dict("records")],
                )


def datetime_now() -> str:
    return pd.Timestamp.now(tz="America/Sao_Paulo").isoformat()
