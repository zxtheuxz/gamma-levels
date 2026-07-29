from __future__ import annotations

import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .b3 import B3Client, B3DataError, B3FileUnavailable
from .market_context import CorporateActionClient, InterestRateClient
from .storage import Database
from .study import AnnualStudy, CostConfig, StudyConfig


class StudyService:
    def __init__(self, root: str | Path | None = None, ticker: str = "PETR4") -> None:
        self.project_root = Path(root) if root else Path(__file__).resolve().parents[1]
        self.data_root = self.project_root / "data"
        self.ticker = ticker.upper()
        self.study_dir = self.data_root / f"pilot_{self.ticker.lower()}"
        self.database = Database(self.study_dir / "gamma_levels.db")
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "running": False, "phase": "idle", "message": "Estudo anual pronto para iniciar",
            "progress": 0, "completed": len(self.database.loaded_dates()), "total": 345,
            "error": None, "missing_dates": [], "run_id": None, "ticker": self.ticker,
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            state = dict(self._state)
        state["loaded_sessions"] = len(self.database.loaded_dates())
        state["latest_market_date"] = self.database.latest_date().isoformat() if self.database.latest_date() else None
        return state

    def _set(self, **values: Any) -> None:
        with self._lock:
            self._state.update(values)

    def start(self, config: StudyConfig | None = None) -> bool:
        with self._lock:
            if self._state["running"]:
                return False
            selected = config or StudyConfig()
            if selected.ticker != self.ticker:
                raise ValueError(f"Serviço {self.ticker} não pode executar {selected.ticker}")
            self._state.update(
                running=True, phase="starting", message=f"Preparando backtest anual {selected.ticker}",
                progress=0, completed=len(self.database.loaded_dates()),
                total=selected.target_loaded_sessions, error=None, missing_dates=[], run_id=None,
            )
        threading.Thread(target=self._worker, args=(selected,), daemon=True).start()
        return True

    def _copy_instruments(self, asset_root: str) -> None:
        main_path = self.data_root / "gamma_levels.db"
        if not main_path.exists():
            raise B3DataError("Cadastro principal de instrumentos não encontrado")
        source = Database(main_path).frame("SELECT * FROM instruments WHERE asset_root=?", (asset_root,))
        if source.empty:
            raise B3DataError(f"Cadastro principal não contém {asset_root}")
        columns = [
            "ticker", "asset_root", "instrument_type", "option_type", "style", "expiration",
            "strike", "lot_size", "price_factor", "isin", "cfi_code", "updated_at",
        ]
        with self.database.connect() as connection:
            connection.executemany(
                f"INSERT OR REPLACE INTO instruments ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                [tuple(row.get(column) for column in columns) for row in source.to_dict("records")],
            )

    def _worker(self, config: StudyConfig) -> None:
        missing: list[str] = []
        try:
            self._copy_instruments(config.asset_root)
            with B3Client(self.data_root) as client:
                latest = client.latest_available_date()
                loaded = {item for item in self.database.loaded_dates() if item <= latest}
                candidate = latest
                attempts = 0
                max_attempts = config.target_loaded_sessions * 2 + 120
                while len(loaded) < config.target_loaded_sessions and attempts < max_attempts:
                    attempts += 1
                    if candidate.weekday() >= 5 or candidate in loaded:
                        candidate -= timedelta(days=1)
                        continue
                    progress = round(len(loaded) / config.target_loaded_sessions * 68)
                    self._set(
                        phase="download", message=(
                            f"{config.ticker}: pregão {len(loaded) + 1}/{config.target_loaded_sessions} — "
                            f"{candidate:%d/%m/%Y}"
                        ), completed=len(loaded), progress=progress,
                    )
                    try:
                        session = client.load_session(
                            candidate, ticker_prefixes={config.asset_root},
                            progress=lambda message: self._set(message=message),
                        )
                    except B3FileUnavailable:
                        candidate -= timedelta(days=1)
                        continue
                    except B3DataError:
                        missing.append(candidate.isoformat())
                        self._set(missing_dates=list(missing))
                        candidate -= timedelta(days=1)
                        continue
                    self.database.store_session(session)
                    loaded.add(candidate)
                    candidate -= timedelta(days=1)
                if len(loaded) < config.target_loaded_sessions:
                    raise B3DataError(
                        f"Carga encontrou {len(loaded)}/{config.target_loaded_sessions} pregões válidos"
                    )

            first, last = self.database.loaded_dates()[0], self.database.loaded_dates()[-1]
            self._set(phase="context", message="Carregando Selic e eventos corporativos", progress=69)
            try:
                rate_count = InterestRateClient().load(self.database, first, last)
                config.interest_rates_complete = rate_count > 0
            except Exception as exc:
                config.interest_rates_complete = False
                self._set(message=f"Selic indisponível; backtest usará fallback registrado: {exc}")
            try:
                action_count = CorporateActionClient().load(self.database, config.ticker, config.asset_root)
                with self.database.connect() as connection:
                    total_actions = connection.execute(
                        "SELECT COUNT(*) AS total FROM corporate_actions WHERE ticker=?",
                        (config.ticker,),
                    ).fetchone()["total"]
                config.corporate_actions_complete = action_count > 0 or int(total_actions) > 0
            except Exception as exc:
                config.corporate_actions_complete = False
                self._set(message=f"Eventos automáticos indisponíveis; valide por CSV: {exc}")

            self._set(phase="backtest", message="Executando estudo walk-forward", progress=70)
            study = AnnualStudy(self.database, config)
            run_id = study.run(
                lambda message, pct: self._set(
                    phase="backtest", message=message, progress=70 + round(pct * 0.30)
                )
            )
            summary = self.database.latest_backtest_summary()
            run_status = (summary.get("run") or {}).get("status")
            final_status = "complete" if run_status == "COMPLETE" and not missing else "incomplete"
            self._set(
                running=False, phase=final_status,
                message=(summary.get("run") or {}).get("message") or "Estudo processado",
                progress=100, completed=len(self.database.loaded_dates()), error=None,
                missing_dates=missing, run_id=run_id,
            )
        except Exception as exc:
            self._set(running=False, phase="error", message="Backtest anual interrompido", error=str(exc), missing_dates=missing)


def config_from_payload(payload: dict[str, Any] | None) -> StudyConfig:
    payload = payload or {}
    costs = payload.get("costs") or {}
    return StudyConfig(
        ticker=str(payload.get("ticker") or "PETR4").upper(),
        asset_root=str(payload.get("asset_root") or "PETR").upper(),
        target_loaded_sessions=max(int(payload.get("target_loaded_sessions") or 345), 55),
        warmup_sessions=max(int(payload.get("warmup_sessions") or 50), 50),
        evaluation_sessions=max(int(payload.get("evaluation_sessions") or 252), 1),
        costs=CostConfig(
            buy_pct=float(costs.get("buy_pct") or 0), sell_pct=float(costs.get("sell_pct") or 0),
            slippage_pct=float(costs.get("slippage_pct") or 0),
            fixed_per_order_brl=float(costs.get("fixed_per_order_brl") or 0),
            capital_per_trade_brl=float(costs.get("capital_per_trade_brl") or 1000),
        ),
        corporate_actions_complete=bool(payload.get("corporate_actions_complete", True)),
        interest_rates_complete=bool(payload.get("interest_rates_complete", True)),
    )
