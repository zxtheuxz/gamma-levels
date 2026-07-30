from __future__ import annotations

import sqlite3

from gamma_levels.api import available_backtests


def create_study(data_root, ticker: str, status: str) -> None:
    directory = data_root / f"pilot_{ticker.lower()}"
    directory.mkdir(parents=True)
    connection = sqlite3.connect(directory / "gamma_levels.db")
    connection.execute(
        """CREATE TABLE backtest_runs (
            id INTEGER PRIMARY KEY, ticker TEXT, status TEXT, first_date TEXT,
            last_date TEXT, evaluated_sessions INTEGER
        )"""
    )
    connection.execute(
        "INSERT INTO backtest_runs VALUES (1,?,?,?,?,?)",
        (ticker, status, "2025-03-11", "2026-07-28", 254),
    )
    connection.commit()
    connection.close()


def test_available_backtests_lists_only_complete_and_keeps_originals_first(tmp_path) -> None:
    create_study(tmp_path, "WEGE3", "COMPLETE")
    create_study(tmp_path, "PETR4", "COMPLETE")
    create_study(tmp_path, "POMO4", "INCOMPLETE")

    studies = available_backtests(tmp_path)

    assert [item["ticker"] for item in studies] == ["PETR4", "WEGE3"]
    assert studies[0]["evaluated_sessions"] == 254
