"""Eleva a janela do banco diário até o número de pregões desejado.

O estudo anual calcula os indicadores com 140 pregões de contexto. O banco diário
nasceu com 120, o que produz um sinal ligeiramente diferente do backtest. Este
script baixa os pregões faltantes da B3 caminhando para trás a partir da data mais
antiga já carregada, sem tocar nas sessões existentes.

Uso:
    python scripts/extend_daily_history.py --target 150
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gamma_levels.b3 import B3Client, B3FileUnavailable  # noqa: E402
from gamma_levels.storage import Database  # noqa: E402


def extend(target: int, max_lookback_days: int) -> int:
    data_dir = ROOT / "data"
    database = Database(data_dir / "gamma_levels.db")
    loaded = set(database.loaded_dates())
    if not loaded:
        raise SystemExit("Banco diário vazio; rode a atualização normal antes de estender o histórico.")
    print(f"Sessões carregadas: {len(loaded)} ({min(loaded)} a {max(loaded)})", flush=True)
    if len(loaded) >= target:
        print(f"Nada a fazer: já existem {len(loaded)} pregões (alvo {target}).", flush=True)
        return 0

    candidate = min(loaded) - timedelta(days=1)
    limit = candidate - timedelta(days=max_lookback_days)
    added = 0
    with B3Client(data_dir) as client:
        while len(loaded) < target and candidate >= limit:
            if candidate.weekday() >= 5 or candidate in loaded:
                candidate -= timedelta(days=1)
                continue
            position = len(loaded) + 1
            print(f"[{position}/{target}] baixando {candidate:%d/%m/%Y}", flush=True)
            try:
                session = client.load_session(candidate)
            except B3FileUnavailable:
                print(f"  {candidate:%d/%m/%Y} sem pregão — avançando", flush=True)
                candidate -= timedelta(days=1)
                continue
            except Exception as exc:  # falha isolada não deve abortar a carga inteira
                print(f"  {candidate:%d/%m/%Y} falhou: {exc}", flush=True)
                candidate -= timedelta(days=1)
                continue
            database.store_session(session)
            loaded.add(candidate)
            added += 1
            candidate -= timedelta(days=1)

    final = database.loaded_dates()
    print(
        f"Concluído: +{added} pregões. Total {len(final)} ({final[0]} a {final[-1]}).",
        flush=True,
    )
    return 0 if len(final) >= target else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Estende o histórico do banco diário")
    parser.add_argument("--target", type=int, default=150, help="Quantidade desejada de pregões")
    parser.add_argument(
        "--max-lookback-days", type=int, default=180,
        help="Limite de dias corridos que o script pode recuar procurando pregões",
    )
    args = parser.parse_args()
    return extend(args.target, args.max_lookback_days)


if __name__ == "__main__":
    raise SystemExit(main())
