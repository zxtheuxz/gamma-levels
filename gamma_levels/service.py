from __future__ import annotations

import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .b3 import B3Client, B3DataError, B3FileUnavailable
from .backtest import Backtester
from .storage import Database
from .swing import SwingConfig, SwingScanner


class RefreshService:
    def __init__(self, root: str | Path | None = None) -> None:
        project_root = Path(root) if root else Path(__file__).resolve().parents[1]
        self.data_dir = project_root / "data"
        self.database = Database(self.data_dir / "gamma_levels.db")
        self.config = SwingConfig()
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "running": False,
            "phase": "idle",
            "message": "Pronto para atualizar",
            "progress": 0,
            "completed": 0,
            "total": 0,
            "error": None,
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            value = dict(self._state)
        value["latest_market_date"] = self.database.latest_date().isoformat() if self.database.latest_date() else None
        value["loaded_sessions"] = len(self.database.loaded_dates())
        return value

    def _set(self, **values: Any) -> None:
        with self._lock:
            self._state.update(values)

    def start_refresh(self, full_history: bool | None = None) -> bool:
        with self._lock:
            if self._state["running"]:
                return False
            self._state.update(
                running=True, phase="starting", message="Localizando o último pregão da B3",
                progress=0, completed=0, total=0, error=None,
            )
        bootstrap = (
            len(self.database.loaded_dates()) < self.config.history_sessions
            if full_history is None
            else full_history
        )
        thread = threading.Thread(target=self._refresh_worker, args=(bootstrap,), daemon=True)
        thread.start()
        return True

    def start_backtest(self) -> bool:
        with self._lock:
            if self._state["running"]:
                return False
            self._state.update(
                running=True, phase="backtest", message="Iniciando backtest walk-forward",
                progress=0, completed=0, total=0, error=None,
            )
        threading.Thread(target=self._backtest_worker, daemon=True).start()
        return True

    def _progress_message(self, message: str) -> None:
        self._set(message=message)

    def _refresh_worker(self, bootstrap: bool) -> None:
        try:
            with B3Client(self.data_dir) as client:
                latest = client.latest_available_date()
                include_instruments = not self.database.has_instruments()
                latest_session = client.load_session(
                    latest, include_instruments=include_instruments, progress=self._progress_message
                )
                self.database.store_session(latest_session)
                if bootstrap:
                    self._set(phase="download", message="Montando a carga inicial de 120 pregões")
                    target_sessions = self.config.history_sessions
                    loaded = {item for item in self.database.loaded_dates() if item <= latest}
                    candidate = latest - timedelta(days=1)
                    attempts = 0
                    max_attempts = target_sessions * 2 + 60
                    self._set(total=target_sessions, completed=len(loaded))
                    while len(loaded) < target_sessions and attempts < max_attempts:
                        attempts += 1
                        if candidate.weekday() >= 5 or candidate in loaded:
                            candidate -= timedelta(days=1)
                            continue
                        self._set(
                            phase="download",
                            message=(
                                f"Carregando pregão {len(loaded) + 1}/{target_sessions} — "
                                f"{candidate:%d/%m/%Y}"
                            ),
                            completed=len(loaded),
                            progress=round(len(loaded) / target_sessions * 70),
                        )
                        try:
                            session = client.load_session(candidate, progress=self._progress_message)
                        except B3FileUnavailable:
                            self._set(message=f"{candidate:%d/%m/%Y} sem pregão — avançando")
                            candidate -= timedelta(days=1)
                            continue
                        self.database.store_session(session)
                        loaded.add(candidate)
                        self._set(completed=len(loaded))
                        candidate -= timedelta(days=1)
                    if len(loaded) < target_sessions:
                        raise B3DataError(
                            f"A carga encontrou somente {len(loaded)} dos {target_sessions} pregões necessários"
                        )
                else:
                    self._set(total=1, completed=1, progress=70)

            self._set(phase="analysis", message="Calculando ranking e sinais", progress=75)
            run_id = self.database.start_run(latest, self.config.to_dict())
            try:
                assets = SwingScanner(self.database, self.config).run(latest)
                self.database.save_analysis(run_id, latest, assets)
                self.database.finish_run(run_id, "OK", "Atualização D-1 concluída")
            except Exception as exc:
                self.database.finish_run(run_id, "ERROR", str(exc))
                raise

            if bootstrap:
                self._set(phase="backtest", message="Validando sinais no histórico", progress=82)
                Backtester(self.database, self.config).build_historical_signals(
                    progress=self._progress_message
                )
            else:
                Backtester(self.database, self.config).update_outcomes(progress=self._progress_message)
            self._set(
                running=False, phase="complete", message="Dados D-1 e sinais atualizados",
                progress=100, error=None,
            )
        except Exception as exc:
            self._set(running=False, phase="error", message="A atualização não foi concluída", error=str(exc))

    def _backtest_worker(self) -> None:
        try:
            Backtester(self.database, self.config).build_historical_signals(
                progress=self._progress_message
            )
            self._set(running=False, phase="complete", message="Backtest atualizado", progress=100)
        except Exception as exc:
            self._set(running=False, phase="error", message="Backtest não concluído", error=str(exc))
