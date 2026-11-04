"""Consulta SOMENTE LEITURA ao MetaTrader 5 aberto (cotacao, abertura real e OHLC do dia).

Uso (ambiente dedicado, sem tocar no Python global):
    .venv_mt5\\Scripts\\python.exe scripts\\mt5_consulta.py SUZB3 SUZBL521

Nunca envia ordens. Os timestamps do MT5 sao epoch do relogio do servidor, que ja
corresponde ao horario de Brasilia; por isso usa-se utcfromtimestamp (sem somar fuso).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

import MetaTrader5 as mt5

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def brt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


def consultar(sym: str) -> None:
    info = mt5.symbol_info(sym)
    if info is None:
        print(f"\n== {sym} == NAO ENCONTRADO no MT5 ({mt5.last_error()})")
        return
    mt5.symbol_select(sym, True)
    tick = mt5.symbol_info_tick(sym)
    print(f"\n== {sym} ==")
    if tick is not None and (tick.bid or tick.ask or tick.last):
        print(f"   bid={tick.bid} ask={tick.ask} last={tick.last} hora={brt(tick.time):%H:%M:%S}")
    else:
        print("   sem tick ao vivo (ativo fora do Market Watch ou sem negocio ainda)")

    d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 2)
    if d1 is not None and len(d1) >= 1:
        for r in d1:
            print(f"   D1 {brt(r['time']):%Y-%m-%d} O={r['open']} H={r['high']} L={r['low']} C={r['close']}")

    m5 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 120)
    if m5 is not None and len(m5):
        hoje = brt(m5[-1]["time"]).date()
        barras = [r for r in m5 if brt(r["time"]).date() == hoje]
        if barras:
            print(
                f"   M5 {hoje}: 1a barra {brt(barras[0]['time']):%H:%M} abertura={barras[0]['open']} "
                f"max={max(r['high'] for r in barras)} min={min(r['low'] for r in barras)} "
                f"ultimo={barras[-1]['close']}"
            )


def main() -> int:
    simbolos = sys.argv[1:] or ["SUZB3"]
    if not mt5.initialize():
        print("MT5 indisponivel (abrir/logar o terminal):", mt5.last_error())
        return 1
    try:
        for s in simbolos:
            consultar(s.upper())
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
