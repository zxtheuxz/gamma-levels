from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from .b3 import B3Client, B3DataError, B3FileUnavailable
from .backtest import Backtester
from .storage import Database, json_dumps
from .swing import SwingConfig, SwingScanner


class PilotRunner:
    def __init__(
        self,
        project_root: str | Path,
        *,
        asset_root: str = "PETR",
        ticker: str = "PETR4",
        sessions: int = 60,
    ) -> None:
        self.project_root = Path(project_root)
        self.asset_root = asset_root.upper()
        self.ticker = ticker.upper()
        self.sessions = max(55, sessions)
        self.data_root = self.project_root / "data"
        self.pilot_dir = self.data_root / f"pilot_{self.ticker.lower()}"
        self.pilot_dir.mkdir(parents=True, exist_ok=True)
        self.status_path = self.pilot_dir / "status.json"
        self.database = Database(self.pilot_dir / "gamma_levels.db")
        self.config = SwingConfig(
            universe_size=1,
            max_buy_signals=1,
            history_sessions=self.sessions,
            liquidity_sessions=min(20, self.sessions),
        )

    def _status(self, **values: Any) -> None:
        current: dict[str, Any] = {}
        if self.status_path.exists():
            try:
                current = json.loads(self.status_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                current = {}
        current.update(values)
        current["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        temporary = self.status_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.status_path)

    def _copy_instruments(self) -> None:
        main_path = self.data_root / "gamma_levels.db"
        if not main_path.exists():
            raise B3DataError("O cadastro inicial de instrumentos ainda não foi carregado")
        source = Database(main_path).frame(
            "SELECT * FROM instruments WHERE asset_root=?",
            (self.asset_root,),
        )
        if source.empty:
            raise B3DataError(f"Cadastro de instrumentos não contém {self.asset_root}")
        columns = [
            "ticker", "asset_root", "instrument_type", "option_type", "style", "expiration",
            "strike", "lot_size", "price_factor", "isin", "cfi_code", "updated_at",
        ]
        with self.database.connect() as connection:
            connection.executemany(
                f"INSERT OR REPLACE INTO instruments ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                [tuple(row.get(column) for column in columns) for row in source.to_dict("records")],
            )

    def _export(self, assets: list[dict[str, Any]], trade_date: date) -> Path:
        output = self.pilot_dir / f"piloto_{self.ticker}_{trade_date.isoformat()}.xlsx"
        history = self.database.history_summary()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.json_normalize(assets, sep="_").to_excel(writer, sheet_name="Analise", index=False)
            pd.DataFrame(history["rows"]).to_excel(writer, sheet_name="Backtest", index=False)
            pd.DataFrame(
                [
                    {"campo": "Ativo", "valor": self.ticker},
                    {"campo": "Pregões", "valor": self.sessions},
                    {"campo": "Data-base", "valor": trade_date.isoformat()},
                    {"campo": "Fonte", "valor": "B3 D-1"},
                    {"campo": "Entrada histórica", "valor": "Primeiro negócio de D0"},
                ]
            ).to_excel(writer, sheet_name="Metodologia", index=False)
        return output

    def run(self) -> Path:
        self._status(
            running=True,
            phase="starting",
            message=f"Preparando piloto de {self.ticker}",
            completed=0,
            total=self.sessions,
            error=None,
        )
        try:
            self._copy_instruments()
            with B3Client(self.data_root) as client:
                latest = client.latest_available_date()
                loaded = {item for item in self.database.loaded_dates() if item <= latest}
                candidate = latest
                attempts = 0
                max_attempts = self.sessions * 2 + 60
                while len(loaded) < self.sessions and attempts < max_attempts:
                    attempts += 1
                    if candidate.weekday() >= 5 or candidate in loaded:
                        candidate -= timedelta(days=1)
                        continue
                    self._status(
                        phase="download",
                        message=f"{self.ticker}: pregão {len(loaded) + 1}/{self.sessions} — {candidate:%d/%m/%Y}",
                        completed=len(loaded),
                        progress=round(len(loaded) / self.sessions * 75),
                    )
                    try:
                        session = client.load_session(
                            candidate,
                            ticker_prefixes={self.asset_root},
                            progress=lambda message: self._status(message=message),
                        )
                    except B3FileUnavailable:
                        self._status(message=f"{candidate:%d/%m/%Y} sem pregão — ignorado")
                        candidate -= timedelta(days=1)
                        continue
                    self.database.store_session(session)
                    loaded.add(candidate)
                    candidate -= timedelta(days=1)
                if len(loaded) < self.sessions:
                    raise B3DataError(f"Somente {len(loaded)} pregões válidos foram encontrados")

            self._status(phase="analysis", message="Calculando sinal e projeções de PETR4", progress=80)
            run_id = self.database.start_run(latest, self.config.to_dict())
            assets = SwingScanner(self.database, self.config).run(latest)
            assets = [item for item in assets if item["ticker"] == self.ticker] or assets
            self.database.save_analysis(run_id, latest, assets)
            self.database.finish_run(run_id, "OK", f"Piloto {self.ticker}")

            self._status(phase="backtest", message="Executando backtest walk-forward", progress=88)
            Backtester(self.database, self.config).build_historical_signals(
                progress=lambda message: self._status(message=message),
                max_sessions=max(self.sessions - 51, 1),
            )
            output = self._export(assets, latest)
            summary = self.pilot_dir / "resultado.json"
            summary.write_text(
                json.dumps(
                    json.loads(
                        json_dumps(
                            {"trade_date": latest.isoformat(), "assets": assets, "history": self.database.history_summary()}
                        )
                    ),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            self._status(
                running=False,
                phase="complete",
                message=f"Piloto {self.ticker} concluído",
                progress=100,
                completed=self.sessions,
                output=str(output),
                summary=str(summary),
            )
            return output
        except Exception as exc:
            self._status(running=False, phase="error", message="Piloto interrompido", error=str(exc))
            raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Executa o piloto isolado de uma ação")
    parser.add_argument("--asset", default="PETR")
    parser.add_argument("--ticker", default="PETR4")
    parser.add_argument("--sessions", type=int, default=60)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    output = PilotRunner(
        args.root, asset_root=args.asset, ticker=args.ticker, sessions=args.sessions
    ).run()
    print(f"Piloto concluído: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
