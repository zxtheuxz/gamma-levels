from __future__ import annotations

import json
from datetime import date
from typing import Callable

from .storage import Database, json_dumps
from .swing import SwingConfig, SwingScanner


class Backtester:
    def __init__(self, database: Database, config: SwingConfig | None = None) -> None:
        self.database = database
        self.config = config or SwingConfig()

    def build_historical_signals(
        self,
        *,
        progress: Callable[[str], None] | None = None,
        max_sessions: int | None = None,
    ) -> int:
        tell = progress or (lambda _: None)
        dates = self.database.loaded_dates()
        eligible = dates[50:-1]
        if max_sessions:
            eligible = eligible[-max_sessions:]
        completed = 0
        scanner = SwingScanner(self.database, self.config)
        for index, trading_date in enumerate(eligible, 1):
            with self.database.connect() as connection:
                exists = connection.execute(
                    "SELECT 1 FROM analysis_runs WHERE trade_date=? AND status='OK' LIMIT 1",
                    (trading_date.isoformat(),),
                ).fetchone()
            if exists:
                continue
            tell(f"Backtest {index}/{len(eligible)} — {trading_date:%d/%m/%Y}")
            run_id = self.database.start_run(trading_date, self.config.to_dict())
            try:
                assets = scanner.run(trading_date)
                self.database.save_analysis(run_id, trading_date, assets)
                self.database.finish_run(run_id, "OK", "Backtest walk-forward")
                completed += 1
            except Exception as exc:  # o erro fica registrado sem perder os demais dias
                self.database.finish_run(run_id, "ERROR", str(exc))
        self.update_outcomes(progress=tell)
        return completed

    def update_outcomes(self, *, progress: Callable[[str], None] | None = None) -> int:
        tell = progress or (lambda _: None)
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT s.signal_id,s.trade_date,s.ticker,s.option_ticker,s.payload_json
                FROM option_signals s LEFT JOIN signal_outcomes o ON o.signal_id=s.signal_id
                WHERE s.status='COMPRAR CALL' AND o.signal_id IS NULL
                ORDER BY s.trade_date"""
            ).fetchall()
        updated = 0
        for index, row in enumerate(rows, 1):
            payload = json.loads(row["payload_json"])
            option_ticker = row["option_ticker"]
            if not option_ticker:
                continue
            signal_date = date.fromisoformat(row["trade_date"])
            quotes = self.database.frame(
                """SELECT * FROM option_quotes WHERE ticker=? AND trade_date>?
                ORDER BY trade_date LIMIT 10""",
                (option_ticker, signal_date.isoformat()),
            )
            if quotes.empty:
                continue
            entry_row = quotes.iloc[0]
            entry = entry_row["open"] if entry_row["open"] and entry_row["open"] > 0 else entry_row["reference_price"]
            if not entry or entry <= 0:
                continue
            bars = self.database.frame(
                """SELECT trade_date,close FROM underlying_bars
                WHERE ticker=? AND trade_date>? ORDER BY trade_date LIMIT 10""",
                (row["ticker"], signal_date.isoformat()),
            ).set_index("trade_date")
            returns: dict[int, float | None] = {3: None, 5: None, 10: None}
            hit = {10: False, 25: False, 50: False, 100: False}
            max_gain, max_loss = -1.0, 0.0
            invalidated = False
            observed_until = None
            used = 0
            for quote in quotes.itertuples(index=False):
                used += 1
                observed_until = quote.trade_date
                underlying_close = bars.loc[quote.trade_date, "close"] if quote.trade_date in bars.index else None
                if underlying_close is not None and float(underlying_close) <= float(payload["invalidation"]):
                    invalidated = True
                    break
                high = quote.high if quote.high and quote.high > 0 else quote.reference_price
                low = quote.low if quote.low and quote.low > 0 else quote.reference_price
                close = quote.close if quote.close and quote.close > 0 else quote.reference_price
                if high and high > 0:
                    max_gain = max(max_gain, float(high) / float(entry) - 1.0)
                if low and low > 0:
                    max_loss = min(max_loss, float(low) / float(entry) - 1.0)
                for level in hit:
                    hit[level] = hit[level] or max_gain >= level / 100.0
                if used in returns and close and close > 0:
                    returns[used] = float(close) / float(entry) - 1.0
            if used < 3:
                continue
            tell(f"Atualizando resultado {index}/{len(rows)}")
            with self.database.connect() as connection:
                connection.execute(
                    """INSERT OR REPLACE INTO signal_outcomes
                    (signal_id,observed_until,return_3d,return_5d,return_10d,max_gain,max_loss,
                     hit_10,hit_25,hit_50,hit_100,invalidated,payload_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        row["signal_id"], observed_until, returns[3], returns[5], returns[10],
                        max_gain, max_loss, int(hit[10]), int(hit[25]), int(hit[50]), int(hit[100]),
                        int(invalidated), json_dumps({"entry_price": entry, "entry_rule": "primeiro negócio de D0"}),
                    ),
                )
            updated += 1
        return updated
