from __future__ import annotations

from datetime import date, timedelta

import pytest

from gamma_levels.regions import adjusted_bars
from gamma_levels.storage import Database
from gamma_levels.study import AnnualStudy, CostConfig, StudyConfig, STRATEGIES


def _session(database: Database, trading_date: date, close: float) -> None:
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO market_sessions VALUES (?,?,?,?)",
            (trading_date.isoformat(), "OK", "{}", trading_date.isoformat()),
        )
        connection.execute(
            """INSERT INTO underlying_bars
            (trade_date,ticker,asset_root,open,low,high,close,trades,volume)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (trading_date.isoformat(), "PETR4", "PETR", close, close - 1, close + 1, close, 1000, 1_000_000),
        )


def test_schema_contains_full_study_tables(tmp_path) -> None:
    database = Database(tmp_path / "study.db")
    with database.connect() as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"backtest_runs", "backtest_trades", "trade_path", "strategy_results", "region_snapshots"} <= names


def test_adjusted_bars_preserve_raw_execution_prices(tmp_path) -> None:
    database = Database(tmp_path / "adjusted.db")
    dates = [date(2026, 1, 2) + timedelta(days=index) for index in range(3)]
    for index, trading_date in enumerate(dates):
        _session(database, trading_date, 10.0 + index)
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO corporate_actions
            (ticker,ex_date,action_type,cash_amount,quantity_factor,source,payload_json)
            VALUES (?,?,?,?,?,?,?)""",
            ("PETR4", dates[-1].isoformat(), "CASH", 1.0, 1.0, "TEST", "{}"),
        )
    bars = adjusted_bars(database, "PETR4", dates[-1], 10)
    assert bars.iloc[-1]["close"] == pytest.approx(12.0)
    assert bars.iloc[-1]["raw_close"] == pytest.approx(12.0)
    assert bars.iloc[0]["close"] < bars.iloc[0]["raw_close"]


def test_six_exit_strategies_use_partial_targets_and_expiry(tmp_path) -> None:
    study = AnnualStudy(Database(tmp_path / "exit.db"), StudyConfig(costs=CostConfig()))
    trade = {
        "trade_id": "T1", "variant": "region_v1", "signal_date": "2026-01-02",
        "expiration": "2026-02-20", "fill_status": "FILLED_OPEN", "completed": True,
        "payload": {"expiry_return": -1.0, "late_fill": False},
        "path": [
            {"trade_date": "2026-01-05", "return_high": 0.30, "return_open": 0.0, "mfe": 0.30, "mae": 0.0, "exit_evidence_score": 20},
            {"trade_date": "2026-01-06", "return_high": 0.55, "return_open": 0.20, "mfe": 0.55, "mae": -0.05, "exit_evidence_score": 75},
            {"trade_date": "2026-01-07", "return_high": 0.10, "return_open": 0.10, "mfe": 0.55, "mae": -0.10, "exit_evidence_score": 80},
        ],
    }
    results = {strategy: study._simulate_strategy(trade, strategy) for strategy in STRATEGIES}
    assert len(results) == 6
    assert results["HOLD_TO_EXPIRY"]["gross_return"] == pytest.approx(-1.0)
    assert results["PARTIAL_25"]["gross_return"] == pytest.approx(-0.375)
    assert results["CALCULATED_EXIT"]["gross_return"] == pytest.approx(0.10)
    assert results["PARTIAL_25_CALCULATED"]["gross_return"] == pytest.approx(0.175)


def test_late_limit_fill_does_not_take_same_day_target(tmp_path) -> None:
    study = AnnualStudy(Database(tmp_path / "late.db"), StudyConfig())
    trade = {
        "trade_id": "T2", "variant": "region_v1", "signal_date": "2026-01-02",
        "expiration": "2026-02-20", "fill_status": "FILLED_LIMIT", "completed": True,
        "payload": {"expiry_return": -1.0, "late_fill": True},
        "path": [
            {"trade_date": "2026-01-05", "return_high": 0.60, "return_open": 0.30, "mfe": 0.60, "mae": 0.0, "exit_evidence_score": 0},
            {"trade_date": "2026-01-06", "return_high": 0.10, "return_open": 0.05, "mfe": 0.60, "mae": -0.10, "exit_evidence_score": 0},
        ],
    }
    result = study._simulate_strategy(trade, "PARTIAL_50")
    assert result["gross_return"] == pytest.approx(-1.0)


def test_unfilled_signal_keeps_reference_mfe_outside_metrics(tmp_path) -> None:
    study = AnnualStudy(Database(tmp_path / "shadow.db"), StudyConfig())
    trade = {
        "trade_id": "T3", "variant": "baseline_v0", "signal_date": "2026-01-02",
        "expiration": "2026-02-20", "fill_status": "UNFILLED", "completed": False,
        "payload": {"path_basis": "FIRST_TRADE_REFERENCE"},
        "path": [
            {"trade_date": "2026-01-05", "return_high": 0.50, "mfe": 0.50, "mae": -0.10},
        ],
    }
    result = study._simulate_strategy(trade, "HOLD_TO_EXPIRY")
    assert result["completed"] is False
    assert result["net_return"] is None
    assert result["mfe"] == pytest.approx(0.50)
