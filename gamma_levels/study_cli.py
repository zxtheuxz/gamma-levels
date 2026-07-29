from __future__ import annotations

import argparse
import time
from pathlib import Path

from .study import CostConfig, StudyConfig
from .study_service import StudyService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carrega e executa backtest anual de uma ação B3")
    parser.add_argument("--ticker", default="PETR4")
    parser.add_argument("--asset-root", default="PETR")
    parser.add_argument("--sessions", type=int, default=345)
    parser.add_argument("--evaluation", type=int, default=252)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    ticker = args.ticker.upper()
    service = StudyService(args.root, ticker=ticker)
    config = StudyConfig(
        ticker=ticker,
        asset_root=args.asset_root.upper(),
        target_loaded_sessions=args.sessions,
        evaluation_sessions=args.evaluation,
        costs=CostConfig(),
    )
    if not service.start(config):
        print("Já existe um estudo em andamento.")
        return 1
    previous = None
    while True:
        state = service.status()
        message = f"{state.get('progress', 0):3}% | {state.get('message')}"
        if message != previous:
            print(message, flush=True)
            previous = message
        if not state.get("running"):
            if state.get("error"):
                print(f"Erro: {state['error']}")
                return 1
            print("Estudo finalizado. Abra o dashboard para consultar os resultados.")
            return 0 if state.get("phase") == "complete" else 2
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
