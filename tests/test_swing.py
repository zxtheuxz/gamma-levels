from __future__ import annotations

from datetime import date, timedelta

import pytest

from gamma_levels.backtest import Backtester
from gamma_levels.storage import Database
from gamma_levels.swing import SwingConfig, SwingScanner, option_price


def _business_dates(start: date, count: int) -> list[date]:
    values = []
    current = start
    while len(values) < count:
        if current.weekday() < 5:
            values.append(current)
        current += timedelta(days=1)
    return values


def test_scanner_selects_only_liquid_call_in_configured_delta(tmp_path) -> None:
    database = Database(tmp_path / "scanner.db")
    dates = _business_dates(date(2026, 4, 1), 60)
    expiration = dates[-1] + timedelta(days=30)
    with database.connect() as connection:
        for index, trading_date in enumerate(dates):
            close = 80.0 + index * 0.34
            volume = 300_000_000 if index == len(dates) - 1 else 100_000_000
            connection.execute(
                "INSERT INTO market_sessions VALUES (?,?,?,?)",
                (trading_date.isoformat(), "OK", "{}", trading_date.isoformat()),
            )
            connection.execute(
                """INSERT INTO underlying_bars
                (trade_date,ticker,asset_root,open,low,high,close,trades,volume)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    trading_date.isoformat(), "TEST3", "TEST", close - 0.4,
                    close - 0.8, close + 0.4, close, 5000, volume,
                ),
            )
            for ticker, side in (("TESTH100", "call"), ("TESTT100", "put")):
                option_value = 4.1 if side == "call" else 2.87
                connection.execute(
                    """INSERT INTO option_quotes
                    (trade_date,ticker,asset_root,option_type,style,expiration,strike,open,low,high,close,
                     reference_price,bid,ask,trades,contracts,financial_volume,open_interest,implied_volatility)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        trading_date.isoformat(), ticker, "TEST", side, "european",
                        expiration.isoformat(), close, option_value, option_value - 0.2,
                        option_value + 0.3, option_value, option_value,
                        option_value - 0.1, option_value + 0.1, 50, 25_000, 102_500, 2_000, 0.30,
                    ),
                )
    assets = SwingScanner(database, SwingConfig()).run(dates[-1])
    assert len(assets) == 1
    assert assets[0]["selected_call"]["ticker"] == "TESTH100"
    assert 0.55 <= assets[0]["selected_call"]["delta"] <= 0.80
    assert assets[0]["selected_call"]["dte"] == 30
    assert assets[0]["status"] in {"COMPRAR CALL", "AGUARDAR", "DESCARTAR"}


def test_american_call_model_respects_intrinsic_value() -> None:
    price = option_price(110, 100, 30 / 365, 0.30, "american", 0.15)
    assert price >= 9.99


def test_backtest_enters_on_first_trade_of_next_session(tmp_path) -> None:
    database = Database(tmp_path / "backtest.db")
    signal_date = date(2026, 7, 20)
    run_id = database.start_run(signal_date, SwingConfig().to_dict())
    database.save_analysis(
        run_id,
        signal_date,
        [
            {
                "rank": 1,
                "ticker": "TEST3",
                "asset_root": "TEST",
                "status": "COMPRAR CALL",
                "setup": "ROMPIMENTO/RETESTE",
                "score": 91.0,
                "liquidity_score": 99.0,
                "invalidation": 95.0,
                "selected_call": {"ticker": "TESTH100"},
            }
        ],
    )
    database.finish_run(run_id, "OK")
    future_dates = _business_dates(signal_date + timedelta(days=1), 3)
    with database.connect() as connection:
        for index, trading_date in enumerate(future_dates):
            close = 4.0 + index * 0.6
            connection.execute(
                """INSERT INTO underlying_bars
                (trade_date,ticker,asset_root,open,low,high,close,trades,volume)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (trading_date.isoformat(), "TEST3", "TEST", 100, 99, 102, 101, 1000, 1_000_000),
            )
            connection.execute(
                """INSERT INTO option_quotes
                (trade_date,ticker,asset_root,option_type,style,expiration,strike,open,low,high,close,
                 reference_price,bid,ask,trades,contracts,financial_volume,open_interest,implied_volatility)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    trading_date.isoformat(), "TESTH100", "TEST", "call", "european",
                    "2026-08-21", 100, 4.0 if index == 0 else close, close - 0.2,
                    close + 0.4, close, close, close - 0.1, close + 0.1, 20, 1000,
                    100_000, 2000, 0.3,
                ),
            )
    assert Backtester(database).update_outcomes() == 1
    outcome = database.frame("SELECT * FROM signal_outcomes").iloc[0]
    assert outcome["hit_25"] == 1
    assert outcome["return_3d"] == pytest.approx(5.2 / 4.0 - 1.0)
