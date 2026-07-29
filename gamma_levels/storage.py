from __future__ import annotations

import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np
import pandas as pd

from .b3 import B3SessionData


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS market_sessions (
    trade_date TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    loaded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS instruments (
    ticker TEXT PRIMARY KEY,
    asset_root TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    option_type TEXT,
    style TEXT,
    expiration TEXT,
    strike REAL,
    lot_size REAL,
    price_factor REAL,
    isin TEXT,
    cfi_code TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS instruments_asset_idx ON instruments(asset_root, instrument_type);

CREATE TABLE IF NOT EXISTS underlying_bars (
    trade_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    asset_root TEXT NOT NULL,
    open REAL,
    low REAL,
    high REAL,
    close REAL,
    trades REAL,
    volume REAL,
    PRIMARY KEY (trade_date, ticker)
);

CREATE INDEX IF NOT EXISTS bars_ticker_date_idx ON underlying_bars(ticker, trade_date);

CREATE TABLE IF NOT EXISTS option_quotes (
    trade_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    asset_root TEXT NOT NULL,
    option_type TEXT NOT NULL,
    style TEXT NOT NULL,
    expiration TEXT NOT NULL,
    strike REAL NOT NULL,
    open REAL,
    low REAL,
    high REAL,
    close REAL,
    reference_price REAL,
    bid REAL,
    ask REAL,
    trades REAL,
    contracts REAL,
    financial_volume REAL,
    open_interest REAL,
    implied_volatility REAL,
    PRIMARY KEY (trade_date, ticker)
);

CREATE INDEX IF NOT EXISTS option_asset_date_idx ON option_quotes(asset_root, trade_date);
CREATE INDEX IF NOT EXISTS option_expiry_idx ON option_quotes(expiration, option_type);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    message TEXT,
    config_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS asset_scores (
    run_id INTEGER NOT NULL,
    trade_date TEXT NOT NULL,
    rank INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    asset_root TEXT NOT NULL,
    status TEXT NOT NULL,
    setup TEXT,
    score REAL NOT NULL,
    liquidity_score REAL NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, ticker),
    FOREIGN KEY (run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS option_signals (
    signal_id TEXT PRIMARY KEY,
    run_id INTEGER NOT NULL,
    trade_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    option_ticker TEXT,
    status TEXT NOT NULL,
    score REAL NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS signals_date_idx ON option_signals(trade_date, status);

CREATE TABLE IF NOT EXISTS signal_outcomes (
    signal_id TEXT PRIMARY KEY,
    observed_until TEXT,
    return_3d REAL,
    return_5d REAL,
    return_10d REAL,
    max_gain REAL,
    max_loss REAL,
    hit_10 INTEGER NOT NULL DEFAULT 0,
    hit_25 INTEGER NOT NULL DEFAULT 0,
    hit_50 INTEGER NOT NULL DEFAULT 0,
    hit_100 INTEGER NOT NULL DEFAULT 0,
    invalidated INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (signal_id) REFERENCES option_signals(signal_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS interest_rates (
    trade_date TEXT PRIMARY KEY,
    annual_rate REAL NOT NULL,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS corporate_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    ex_date TEXT NOT NULL,
    action_type TEXT NOT NULL,
    cash_amount REAL NOT NULL DEFAULT 0,
    quantity_factor REAL NOT NULL DEFAULT 1,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(ticker, ex_date, action_type, cash_amount, quantity_factor)
);

CREATE INDEX IF NOT EXISTS corporate_actions_ticker_date_idx
ON corporate_actions(ticker, ex_date);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    asset_root TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    phase TEXT NOT NULL,
    message TEXT,
    first_date TEXT,
    last_date TEXT,
    evaluated_sessions INTEGER NOT NULL DEFAULT 0,
    dataset_hash TEXT,
    config_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS region_snapshots (
    run_id INTEGER NOT NULL,
    variant TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    region_type TEXT NOT NULL,
    center REAL,
    lower_bound REAL,
    upper_bound REAL,
    score REAL NOT NULL,
    touches INTEGER NOT NULL DEFAULT 0,
    pressure_penalty REAL NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(run_id, variant, trade_date, ticker, region_type),
    FOREIGN KEY(run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    trade_id TEXT PRIMARY KEY,
    run_id INTEGER NOT NULL,
    variant TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    option_ticker TEXT NOT NULL,
    expiration TEXT NOT NULL,
    strike REAL NOT NULL,
    signal_score REAL NOT NULL,
    region_score REAL,
    entry_limit REAL,
    entry_date TEXT,
    entry_price REAL,
    fill_status TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS backtest_trades_run_idx
ON backtest_trades(run_id, variant, signal_date);

CREATE TABLE IF NOT EXISTS trade_path (
    trade_id TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    dte INTEGER NOT NULL,
    option_open REAL,
    option_low REAL,
    option_high REAL,
    option_close REAL,
    underlying_open REAL,
    underlying_low REAL,
    underlying_high REAL,
    underlying_close REAL,
    return_open REAL,
    return_low REAL,
    return_high REAL,
    return_close REAL,
    mfe REAL,
    mae REAL,
    drawdown_from_peak REAL,
    asset_score REAL,
    exit_evidence_score REAL,
    exit_state TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(trade_id, trade_date),
    FOREIGN KEY(trade_id) REFERENCES backtest_trades(trade_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS strategy_results (
    trade_id TEXT NOT NULL,
    strategy TEXT NOT NULL,
    overlap_mode TEXT NOT NULL,
    included INTEGER NOT NULL DEFAULT 1,
    completed INTEGER NOT NULL DEFAULT 0,
    gross_return REAL,
    net_return REAL,
    mfe REAL,
    mae REAL,
    expiry_return REAL,
    peak_date TEXT,
    exit_date TEXT,
    holding_sessions INTEGER,
    payload_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(trade_id, strategy, overlap_mode),
    FOREIGN KEY(trade_id) REFERENCES backtest_trades(trade_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS backtest_metrics (
    run_id INTEGER NOT NULL,
    variant TEXT NOT NULL,
    strategy TEXT NOT NULL,
    overlap_mode TEXT NOT NULL,
    sample TEXT NOT NULL,
    trades INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    win_rate REAL,
    expectancy REAL,
    profit_factor REAL,
    avg_win REAL,
    avg_loss REAL,
    median_return REAL,
    max_drawdown REAL,
    mfe_capture REAL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(run_id, variant, strategy, overlap_mode, sample),
    FOREIGN KEY(run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
);
"""


def _clean_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clean_json(value: Any) -> Any:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, dict):
        return {str(key): _clean_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_json(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return _clean_number(value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    return value


def json_dumps(value: Any) -> str:
    return json.dumps(_clean_json(value), ensure_ascii=False, separators=(",", ":"))


class Database:
    def __init__(self, path: str | Path = "data/gamma_levels.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def has_instruments(self) -> bool:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM instruments").fetchone()
        return bool(row and row["total"])

    def loaded_dates(self) -> list[date]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT trade_date FROM market_sessions WHERE status='OK' ORDER BY trade_date"
            ).fetchall()
        return [date.fromisoformat(row["trade_date"]) for row in rows]

    def latest_date(self) -> date | None:
        dates = self.loaded_dates()
        return dates[-1] if dates else None

    def _instrument_maps(self, connection: sqlite3.Connection) -> tuple[dict[str, str], dict[str, str]]:
        option_roots = {
            row["ticker"]: row["asset_root"]
            for row in connection.execute(
                "SELECT ticker, asset_root FROM instruments WHERE instrument_type='option'"
            )
        }
        equity_roots = {
            row["ticker"]: row["asset_root"]
            for row in connection.execute(
                "SELECT ticker, asset_root FROM instruments WHERE instrument_type='equity'"
            )
        }
        return option_roots, equity_roots

    def store_session(self, session: B3SessionData) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        trade_date = session.trade_date.isoformat()
        with self.connect() as connection:
            if not session.instruments.empty:
                rows = []
                for item in session.instruments.to_dict("records"):
                    rows.append(
                        (
                            item.get("ticker"), item.get("asset_root") or "",
                            item.get("instrument_type") or "option", item.get("option_type"),
                            item.get("style"), _clean_json(item.get("expiration")),
                            _clean_number(item.get("strike")), _clean_number(item.get("lot_size")),
                            _clean_number(item.get("price_factor")), item.get("isin"),
                            item.get("cfi_code"), now,
                        )
                    )
                connection.executemany(
                    """INSERT INTO instruments
                    (ticker,asset_root,instrument_type,option_type,style,expiration,strike,lot_size,price_factor,isin,cfi_code,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(ticker) DO UPDATE SET
                    asset_root=excluded.asset_root,instrument_type=excluded.instrument_type,
                    option_type=excluded.option_type,style=excluded.style,expiration=excluded.expiration,
                    strike=excluded.strike,lot_size=excluded.lot_size,price_factor=excluded.price_factor,
                    isin=excluded.isin,cfi_code=excluded.cfi_code,updated_at=excluded.updated_at""",
                    rows,
                )

            option_roots, equity_roots = self._instrument_maps(connection)
            prices = session.prices.set_index("ticker", drop=False)
            bar_rows = []
            for ticker, root in equity_roots.items():
                if ticker not in prices.index:
                    continue
                item = prices.loc[ticker]
                if isinstance(item, pd.DataFrame):
                    item = item.iloc[-1]
                bar_rows.append(
                    (
                        trade_date, ticker, root, _clean_number(item.get("open")),
                        _clean_number(item.get("low")), _clean_number(item.get("high")),
                        _clean_number(item.get("close")), _clean_number(item.get("trades")),
                        _clean_number(item.get("financial_volume")),
                    )
                )
            connection.executemany(
                """INSERT OR REPLACE INTO underlying_bars
                (trade_date,ticker,asset_root,open,low,high,close,trades,volume)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                bar_rows,
            )

            merged = session.option_reference.merge(
                session.prices.drop(columns=["trade_date"], errors="ignore"), on="ticker", how="left"
            )
            merged["dte"] = (merged["expiration"] - pd.Timestamp(session.trade_date)).dt.days
            merged = merged.loc[merged["dte"].between(1, 120)].copy()
            option_rows = []
            for item in merged.to_dict("records"):
                ticker = str(item["ticker"])
                root = option_roots.get(ticker) or ticker[:4]
                option_rows.append(
                    (
                        trade_date, ticker, root, item.get("option_type"), item.get("style") or "european",
                        _clean_json(item.get("expiration")), _clean_number(item.get("strike")),
                        _clean_number(item.get("open")), _clean_number(item.get("low")),
                        _clean_number(item.get("high")), _clean_number(item.get("close")),
                        _clean_number(item.get("reference_price")), _clean_number(item.get("bid")),
                        _clean_number(item.get("ask")), _clean_number(item.get("trades")),
                        _clean_number(item.get("contracts")), _clean_number(item.get("financial_volume")),
                        _clean_number(item.get("open_interest")), _clean_number(item.get("implied_volatility")),
                    )
                )
            connection.executemany(
                """INSERT OR REPLACE INTO option_quotes
                (trade_date,ticker,asset_root,option_type,style,expiration,strike,open,low,high,close,
                 reference_price,bid,ask,trades,contracts,financial_volume,open_interest,implied_volatility)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                option_rows,
            )
            connection.execute(
                """INSERT OR REPLACE INTO market_sessions(trade_date,status,manifest_json,loaded_at)
                VALUES (?,?,?,?)""",
                (trade_date, "OK", json_dumps(session.manifest), now),
            )

    def frame(self, query: str, params: Iterable[object] = ()) -> pd.DataFrame:
        with self.connect() as connection:
            return pd.read_sql_query(query, connection, params=tuple(params))

    def bars(self, ticker: str, end_date: date, limit: int = 120) -> pd.DataFrame:
        frame = self.frame(
            """SELECT * FROM underlying_bars WHERE ticker=? AND trade_date<=?
            ORDER BY trade_date DESC LIMIT ?""",
            (ticker, end_date.isoformat(), limit),
        )
        return frame.sort_values("trade_date").reset_index(drop=True)

    def current_options(self, asset_root: str, trade_date: date) -> pd.DataFrame:
        return self.frame(
            "SELECT * FROM option_quotes WHERE asset_root=? AND trade_date=?",
            (asset_root, trade_date.isoformat()),
        )

    def start_run(self, trade_date: date, config: dict[str, object]) -> int:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO analysis_runs(trade_date,started_at,status,config_json)
                VALUES (?,?,?,?)""",
                (trade_date.isoformat(), now, "RUNNING", json_dumps(config)),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str, message: str = "") -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.connect() as connection:
            connection.execute(
                "UPDATE analysis_runs SET finished_at=?,status=?,message=? WHERE id=?",
                (now, status, message, run_id),
            )

    def save_analysis(self, run_id: int, trade_date: date, assets: list[dict[str, Any]]) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.connect() as connection:
            for item in assets:
                connection.execute(
                    """INSERT OR REPLACE INTO asset_scores
                    (run_id,trade_date,rank,ticker,asset_root,status,setup,score,liquidity_score,payload_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        run_id, trade_date.isoformat(), item["rank"], item["ticker"], item["asset_root"],
                        item["status"], item.get("setup"), item["score"], item["liquidity_score"],
                        json_dumps(item),
                    ),
                )
                signal = item.get("selected_call") or {}
                signal_id = f"{trade_date.isoformat()}|{item['ticker']}|{signal.get('ticker','NONE')}"
                connection.execute(
                    """INSERT OR REPLACE INTO option_signals
                    (signal_id,run_id,trade_date,ticker,option_ticker,status,score,payload_json,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        signal_id, run_id, trade_date.isoformat(), item["ticker"], signal.get("ticker"),
                        item["status"], item["score"], json_dumps(item), now,
                    ),
                )

    def latest_assets(self, trade_date: date | None = None) -> list[dict[str, Any]]:
        with self.connect() as connection:
            if trade_date is None:
                row = connection.execute(
                    "SELECT MAX(trade_date) AS trade_date FROM asset_scores"
                ).fetchone()
                if not row or not row["trade_date"]:
                    return []
                selected = row["trade_date"]
            else:
                selected = trade_date.isoformat()
            rows = connection.execute(
                """SELECT payload_json FROM asset_scores
                WHERE trade_date=? AND run_id=(SELECT MAX(id) FROM analysis_runs WHERE trade_date=? AND status='OK')
                ORDER BY rank""",
                (selected, selected),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def history_summary(self) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT s.trade_date,s.ticker,s.option_ticker,s.status,s.score,o.*
                FROM option_signals s LEFT JOIN signal_outcomes o ON o.signal_id=s.signal_id
                WHERE s.status='COMPRAR CALL' ORDER BY s.trade_date DESC"""
            ).fetchall()
        records = [dict(row) for row in rows]
        completed = [row for row in records if row.get("observed_until")]
        return {
            "signals": len(records),
            "completed": len(completed),
            "hit_rates": {
                label: (sum(int(row.get(column) or 0) for row in completed) / len(completed) if completed else None)
                for label, column in (("10", "hit_10"), ("25", "hit_25"), ("50", "hit_50"), ("100", "hit_100"))
            },
            "rows": records[:200],
        }

    def start_backtest_run(
        self, ticker: str, asset_root: str, config: dict[str, Any], *, phase: str = "starting"
    ) -> int:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO backtest_runs
                (ticker,asset_root,started_at,status,phase,message,config_json)
                VALUES (?,?,?,?,?,?,?)""",
                (ticker, asset_root, now, "RUNNING", phase, "Preparando estudo", json_dumps(config)),
            )
            return int(cursor.lastrowid)

    def update_backtest_run(self, run_id: int, **values: Any) -> None:
        allowed = {
            "status", "phase", "message", "first_date", "last_date",
            "evaluated_sessions", "dataset_hash", "finished_at",
        }
        payload = {key: value for key, value in values.items() if key in allowed}
        if not payload:
            return
        if payload.get("status") in {"COMPLETE", "ERROR", "INCOMPLETE"} and "finished_at" not in payload:
            payload["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        assignments = ",".join(f"{key}=?" for key in payload)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE backtest_runs SET {assignments} WHERE id=?",
                (*payload.values(), run_id),
            )

    def replace_region_snapshot(
        self, run_id: int, variant: str, trade_date: date, ticker: str, region: dict[str, Any]
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO region_snapshots
                (run_id,variant,trade_date,ticker,region_type,center,lower_bound,upper_bound,
                 score,touches,pressure_penalty,payload_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id, variant, trade_date.isoformat(), ticker, region["region_type"],
                    _clean_number(region.get("center")), _clean_number(region.get("lower_bound")),
                    _clean_number(region.get("upper_bound")), float(region.get("score") or 0),
                    int(region.get("touches") or 0), float(region.get("pressure_penalty") or 0),
                    json_dumps(region),
                ),
            )

    def replace_backtest_trade(self, trade: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO backtest_trades
                (trade_id,run_id,variant,signal_date,ticker,option_ticker,expiration,strike,
                 signal_score,region_score,entry_limit,entry_date,entry_price,fill_status,completed,payload_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    trade["trade_id"], trade["run_id"], trade["variant"], trade["signal_date"],
                    trade["ticker"], trade["option_ticker"], trade["expiration"], trade["strike"],
                    trade["signal_score"], trade.get("region_score"), trade.get("entry_limit"),
                    trade.get("entry_date"), trade.get("entry_price"), trade["fill_status"],
                    int(bool(trade.get("completed"))), json_dumps(trade.get("payload", {})),
                ),
            )

    def replace_trade_path(self, trade_id: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        columns = [
            "trade_id", "trade_date", "dte", "option_open", "option_low", "option_high",
            "option_close", "underlying_open", "underlying_low", "underlying_high",
            "underlying_close", "return_open", "return_low", "return_high", "return_close",
            "mfe", "mae", "drawdown_from_peak", "asset_score", "exit_evidence_score",
            "exit_state", "payload_json",
        ]
        values = []
        for row in rows:
            item = {**row, "trade_id": trade_id, "payload_json": json_dumps(row.get("payload", {}))}
            values.append(tuple(item.get(column) for column in columns))
        with self.connect() as connection:
            connection.executemany(
                f"INSERT OR REPLACE INTO trade_path ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                values,
            )

    def replace_strategy_results(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        with self.connect() as connection:
            connection.executemany(
                """INSERT OR REPLACE INTO strategy_results
                (trade_id,strategy,overlap_mode,included,completed,gross_return,net_return,mfe,mae,
                 expiry_return,peak_date,exit_date,holding_sessions,payload_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        row["trade_id"], row["strategy"], row["overlap_mode"],
                        int(bool(row.get("included", True))), int(bool(row.get("completed"))),
                        row.get("gross_return"), row.get("net_return"), row.get("mfe"), row.get("mae"),
                        row.get("expiry_return"), row.get("peak_date"), row.get("exit_date"),
                        row.get("holding_sessions"), json_dumps(row.get("payload", {})),
                    )
                    for row in rows
                ],
            )

    def replace_backtest_metrics(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        with self.connect() as connection:
            connection.executemany(
                """INSERT OR REPLACE INTO backtest_metrics
                (run_id,variant,strategy,overlap_mode,sample,trades,wins,win_rate,expectancy,
                 profit_factor,avg_win,avg_loss,median_return,max_drawdown,mfe_capture,payload_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        row["run_id"], row["variant"], row["strategy"], row["overlap_mode"],
                        row.get("sample", "full"), row["trades"], row["wins"], row.get("win_rate"),
                        row.get("expectancy"), row.get("profit_factor"), row.get("avg_win"),
                        row.get("avg_loss"), row.get("median_return"), row.get("max_drawdown"),
                        row.get("mfe_capture"), json_dumps(row.get("payload", {})),
                    )
                    for row in rows
                ],
            )

    def latest_backtest_summary(self) -> dict[str, Any]:
        with self.connect() as connection:
            run = connection.execute("SELECT * FROM backtest_runs ORDER BY id DESC LIMIT 1").fetchone()
            if not run:
                return {"run": None, "metrics": [], "trades": []}
            run_id = int(run["id"])
            metrics = connection.execute(
                """SELECT * FROM backtest_metrics WHERE run_id=?
                ORDER BY variant,strategy,overlap_mode,sample""", (run_id,)
            ).fetchall()
            trades = connection.execute(
                """SELECT t.*,r.strategy,r.overlap_mode,r.included,r.gross_return,r.net_return,
                r.mfe,r.mae,r.expiry_return,r.peak_date,r.exit_date,r.holding_sessions
                FROM backtest_trades t LEFT JOIN strategy_results r ON r.trade_id=t.trade_id
                WHERE t.run_id=? ORDER BY t.signal_date DESC,r.strategy,r.overlap_mode LIMIT 1000""",
                (run_id,),
            ).fetchall()
        return {
            "run": dict(run),
            "metrics": [dict(row) for row in metrics],
            "trades": [dict(row) for row in trades],
        }

    def trade_detail(self, trade_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            trade = connection.execute("SELECT * FROM backtest_trades WHERE trade_id=?", (trade_id,)).fetchone()
            if not trade:
                return None
            path = connection.execute("SELECT * FROM trade_path WHERE trade_id=? ORDER BY trade_date", (trade_id,)).fetchall()
            results = connection.execute(
                "SELECT * FROM strategy_results WHERE trade_id=? ORDER BY strategy,overlap_mode", (trade_id,)
            ).fetchall()
        return {"trade": dict(trade), "path": [dict(row) for row in path], "strategies": [dict(row) for row in results]}
