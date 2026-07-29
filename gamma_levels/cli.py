from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .core import AnalysisConfig, analyze_chain, load_chain


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gamma-levels",
        description="Calcula exposições e níveis derivados de uma cadeia de opções.",
    )
    parser.add_argument("input", help="Cadeia em CSV, TSV ou XLSX")
    parser.add_argument("--output-dir", "-o", default="resultado", help="Pasta dos arquivos de saída")
    parser.add_argument("--spot", type=float, help="Preço atual; substitui underlying_price do arquivo")
    parser.add_argument("--valuation-date", help="Data-base YYYY-MM-DD (padrão: hoje)")
    parser.add_argument("--rate", type=float, default=0.0, help="Taxa livre de risco anual decimal")
    parser.add_argument("--dividend", type=float, default=0.0, help="Dividend yield anual decimal")
    parser.add_argument("--multiplier", type=float, default=100.0, help="Ativos por contrato")
    parser.add_argument("--sep", help="Separador de entrada; padrão: detecção automática")
    parser.add_argument("--decimal", choices=[".", ","], default=".", help="Separador decimal da entrada")
    parser.add_argument("--thousands", choices=[".", ","], help="Separador de milhares da entrada")
    parser.add_argument("--encoding", default="utf-8-sig", help="Codificação da entrada")
    parser.add_argument("--output-sep", default=",", help="Separador dos CSVs de saída")
    parser.add_argument("--output-decimal", choices=[".", ","], default=".")
    parser.add_argument(
        "--sign-convention",
        choices=["call_positive_put_negative", "all_positive", "all_negative"],
        default="call_positive_put_negative",
    )
    parser.add_argument(
        "--iv-percent",
        choices=["auto", "yes", "no"],
        default="auto",
        help="Se a IV de entrada está em percentual (25 em vez de 0.25)",
    )
    parser.add_argument(
        "--recompute-greeks",
        action="store_true",
        help="Ignora gregas fornecidas e recalcula tudo por Black-Scholes-Merton",
    )
    parser.add_argument(
        "--vendor-vol-greeks-per-1pct",
        action="store_true",
        help="Vega/vanna fornecidos são por 1 ponto percentual de IV",
    )
    parser.add_argument(
        "--vendor-charm-per-day",
        action="store_true",
        help="Charm fornecido já representa a mudança de delta por dia",
    )
    parser.add_argument("--gamma-percentile", type=float, default=0.90)
    parser.add_argument("--distance-decay", type=float, default=10.0)
    parser.add_argument("--expiry-decay", type=float, default=2.0)
    parser.add_argument("--min-oi-volume-ratio", type=float, default=10.0)
    parser.add_argument("--flip-low", type=float)
    parser.add_argument("--flip-high", type=float)
    parser.add_argument("--flip-grid-points", type=int, default=501)
    parser.add_argument(
        "--same-day-hours",
        type=float,
        help="Horas restantes para opções que vencem na data-base (0DTE)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    iv_mode = {"auto": None, "yes": True, "no": False}[args.iv_percent]
    config = AnalysisConfig(
        spot=args.spot,
        valuation_date=args.valuation_date,
        interest_rate=args.rate,
        dividend_yield=args.dividend,
        multiplier=args.multiplier,
        sign_convention=args.sign_convention,
        use_vendor_greeks=not args.recompute_greeks,
        vendor_vega_vanna_per_1pct=args.vendor_vol_greeks_per_1pct,
        vendor_charm_per_day=args.vendor_charm_per_day,
        iv_in_percent=iv_mode,
        gamma_percentile=args.gamma_percentile,
        distance_decay=args.distance_decay,
        expiry_decay=args.expiry_decay,
        min_oi_for_volume_ratio=args.min_oi_volume_ratio,
        flip_low=args.flip_low,
        flip_high=args.flip_high,
        flip_grid_points=args.flip_grid_points,
        same_day_hours=args.same_day_hours,
    )
    chain = load_chain(
        args.input,
        sep=args.sep,
        decimal=args.decimal,
        thousands=args.thousands,
        encoding=args.encoding,
    )
    result = analyze_chain(chain, config)

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    safe_summary = _json_safe(result.summary)
    (output / "resumo.json").write_text(
        json.dumps(safe_summary, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    csv_options = {"index": False, "sep": args.output_sep, "decimal": args.output_decimal, "encoding": "utf-8-sig"}
    result.by_strike.to_csv(output / "por_strike.csv", **csv_options)
    result.by_expiration.to_csv(output / "por_vencimento.csv", **csv_options)
    result.options.to_csv(output / "opcoes_calculadas.csv", **csv_options)

    print(f"Análise concluída: {len(result.options)} opções, {len(result.by_strike)} strikes")
    print(f"Spot: {result.summary['spot']:.4f}")
    print(f"GEX total: {result.summary['gex_total']:.2f}")
    print(f"Gamma Flip: {result.summary['gamma_flip']}")
    print(f"Call Wall: {result.summary['call_wall']} | Put Wall: {result.summary['put_wall']}")
    print(f"Arquivos: {output.resolve()}")
    return 0
