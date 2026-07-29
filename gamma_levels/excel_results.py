from __future__ import annotations

import argparse
import json
import math
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .core import AnalysisConfig, AnalysisResult, analyze_chain
from .signals import SignalConfig, build_signals


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _dates(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    parsed = pd.to_datetime(text, errors="coerce", format="%Y-%m-%d")
    unresolved = parsed.isna()
    if unresolved.any():
        parsed.loc[unresolved] = pd.to_datetime(
            text.loc[unresolved], errors="coerce", dayfirst=True
        )
    return parsed


def read_b3_reference(path: str | Path) -> pd.DataFrame:
    """Lê ticker, strike e vencimento da lista de séries autorizadas da B3."""
    rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".txt")]
        if not names:
            raise ValueError("O catálogo ZIP da B3 não contém um arquivo TXT")
        with archive.open(names[0]) as source:
            for raw_line in source:
                line = raw_line.decode("cp1252", errors="replace").rstrip("\r\n")
                if not line.startswith("02|"):
                    continue
                fields = line.split("|")
                if len(fields) < 18:
                    continue
                kind_text = fields[3].upper()
                kind = "call" if "COMPRA" in kind_text else "put" if "VENDA" in kind_text else None
                if kind is None:
                    continue
                try:
                    strike = float(fields[16])
                    expiration = pd.to_datetime(fields[17].strip(), format="%Y%m%d")
                except (TypeError, ValueError):
                    continue
                rows.append({
                    "ticker": fields[13].strip().upper(),
                    "option_type_b3": kind,
                    "strike_b3": strike,
                    "expiration_b3": expiration,
                })
    return pd.DataFrame(rows).drop_duplicates("ticker", keep="first").set_index("ticker")


def prepare_profit_chain(
    raw: pd.DataFrame,
    b3_reference: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Prepara a cadeia do Profit e preenche IVs inválidas de forma auditável."""
    chain = raw.copy()
    chain.columns = [str(column).strip() for column in chain.columns]

    input_rows = len(chain)
    if "ticker" in chain:
        ticker = chain["ticker"].fillna("").astype(str).str.strip()
        chain = chain.loc[ticker.ne("")].copy()
    nonblank_rows = len(chain)

    required = ["option_type", "strike", "expiration", "open_interest"]
    missing = [column for column in required if column not in chain]
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes na aba Cadeia: {', '.join(missing)}")

    chain["source_row"] = chain.index + 2
    chain["strike_original"] = _numeric(chain["strike"])
    chain["expiration_original"] = _dates(chain["expiration"])
    chain["strike"] = chain["strike_original"]
    chain["open_interest"] = _numeric(chain["open_interest"])
    chain["expiration"] = chain["expiration_original"]
    chain["option_type"] = chain["option_type"].fillna("").astype(str).str.strip().str.lower()
    chain["option_type"] = chain["option_type"].replace({"c": "call", "p": "put"})

    chain["strike_source"] = "Profit"
    chain["expiration_source"] = "Profit"
    strike_recovered = 0
    expiration_recovered = 0
    if b3_reference is not None and not b3_reference.empty and "ticker" in chain:
        ticker_key = chain["ticker"].fillna("").astype(str).str.strip().str.upper()
        strike_b3 = ticker_key.map(b3_reference["strike_b3"])
        expiration_b3 = ticker_key.map(b3_reference["expiration_b3"])
        strike_diff = strike_b3.notna() & (
            chain["strike"].isna() | ~np.isclose(chain["strike"], strike_b3, atol=0.0001)
        )
        expiration_diff = expiration_b3.notna() & (
            chain["expiration"].isna()
            | chain["expiration"].dt.normalize().ne(expiration_b3.dt.normalize())
        )
        strike_recovered = int(strike_diff.sum())
        expiration_recovered = int(expiration_diff.sum())
        chain.loc[strike_b3.notna(), "strike"] = strike_b3[strike_b3.notna()]
        chain.loc[expiration_b3.notna(), "expiration"] = expiration_b3[expiration_b3.notna()]
        chain.loc[strike_b3.notna(), "strike_source"] = np.where(
            strike_diff[strike_b3.notna()], "B3_CORRIGIDO", "Profit/B3"
        )
        chain.loc[expiration_b3.notna(), "expiration_source"] = np.where(
            expiration_diff[expiration_b3.notna()], "B3_CORRIGIDO", "Profit/B3"
        )

    valid_required = (
        chain["option_type"].isin(["call", "put"])
        & chain["strike"].gt(0)
        & chain["expiration"].notna()
        & chain["open_interest"].ge(0)
    )
    excluded_required = int((~valid_required).sum())
    chain = chain.loc[valid_required].copy()

    for profit_name, standard_name in (
        ("delta_profit", "delta"),
        ("gamma_profit", "gamma"),
        ("vega_profit", "vega"),
    ):
        if profit_name in chain:
            chain[profit_name] = _numeric(chain[profit_name])
            chain[standard_name] = chain[profit_name]

    if "implied_volatility" not in chain:
        chain["implied_volatility"] = np.nan
    chain["iv_original"] = _numeric(chain["implied_volatility"])
    chain["iv_used"] = chain["iv_original"].where(chain["iv_original"].gt(0))
    valid_iv = chain["iv_used"].notna()
    valid_iv_count = int(valid_iv.sum())

    # Interpolação linear por vencimento e tipo. Nas bordas, usa o vizinho
    # válido mais próximo. Isso evita misturar smiles de calls e puts.
    for (_, _), group in chain.groupby([chain["expiration"].dt.normalize(), "option_type"]):
        missing_mask = group["iv_used"].isna()
        if not missing_mask.any():
            continue
        anchors = (
            group.loc[~missing_mask, ["strike", "iv_used"]]
            .groupby("strike", as_index=False)["iv_used"]
            .median()
            .sort_values("strike")
        )
        if anchors.empty:
            continue
        target_index = group.index[missing_mask]
        chain.loc[target_index, "iv_used"] = np.interp(
            chain.loc[target_index, "strike"].to_numpy(dtype=float),
            anchors["strike"].to_numpy(dtype=float),
            anchors["iv_used"].to_numpy(dtype=float),
        )

    # Fallbacks somente quando não existe qualquer âncora no mesmo smile.
    still_missing = chain["iv_used"].isna()
    if still_missing.any():
        expiry_median = chain.loc[chain["iv_used"].notna()].groupby(
            chain.loc[chain["iv_used"].notna(), "expiration"].dt.normalize()
        )["iv_used"].median()
        for index in chain.index[still_missing]:
            expiry = chain.at[index, "expiration"].normalize()
            if expiry in expiry_median.index:
                chain.at[index, "iv_used"] = float(expiry_median.loc[expiry])

    still_missing = chain["iv_used"].isna()
    global_median = chain.loc[chain["iv_used"].notna(), "iv_used"].median()
    if still_missing.any() and pd.notna(global_median):
        chain.loc[still_missing, "iv_used"] = float(global_median)

    usable = chain["iv_used"].notna() & chain["iv_used"].gt(0)
    excluded_iv = int((~usable).sum())
    chain = chain.loc[usable].copy()
    chain["iv_source"] = np.where(chain["iv_original"].gt(0), "Profit", "Interpolada")
    chain["data_quality_flag"] = np.where(
        chain["iv_source"].eq("Profit"), "OK", "IV_INTERPOLADA"
    )
    chain["implied_volatility"] = chain["iv_used"]

    quality = {
        "input_rows": int(input_rows),
        "nonblank_rows": int(nonblank_rows),
        "valid_iv_count": valid_iv_count,
        "imputed_iv_count": int(chain["iv_source"].eq("Interpolada").sum()),
        "excluded_required_count": excluded_required,
        "excluded_iv_count": excluded_iv,
        "calculated_rows": int(len(chain)),
        "strike_recovered_count": strike_recovered,
        "expiration_recovered_count": expiration_recovered,
    }
    return chain.reset_index(drop=True), quality


def build_results(
    raw: pd.DataFrame,
    *,
    valuation_date: date | str | None = None,
    b3_reference: pd.DataFrame | None = None,
) -> tuple[AnalysisResult, dict[str, int]]:
    chain, quality = prepare_profit_chain(raw, b3_reference=b3_reference)
    config = AnalysisConfig(
        valuation_date=valuation_date,
        use_vendor_greeks=True,
        # O Profit apresenta vega por ponto percentual; o núcleo trabalha por
        # variação de 1,00 da volatilidade.
        vendor_vega_vanna_per_1pct=True,
        same_day_hours=4.0,
    )
    return analyze_chain(chain, config), quality


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_json_value(item) for item in value]
    if pd.isna(value):
        return None
    return value


def _frame_payload(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "columns": [str(column) for column in frame.columns],
        "rows": [
            [_json_value(value) for value in row]
            for row in frame.itertuples(index=False, name=None)
        ],
    }


def make_payload(
    result: AnalysisResult,
    quality: dict[str, int],
    signal_config: SignalConfig | None = None,
) -> dict[str, Any]:
    signal_result = build_signals(result, signal_config)
    top = result.by_strike.copy()
    if "is_gamma_level" in top:
        selected = top.loc[top["is_gamma_level"].fillna(False)].copy()
        if selected.empty:
            selected = top.copy()
    else:
        selected = top.copy()
    selected["_rank"] = selected["gex_net"].abs()
    top_columns = [
        "strike", "distance_percent", "gex_call", "gex_put", "gex_net",
        "zone_low", "zone_high", "gamma_cluster_id",
    ]
    top_levels = selected.sort_values("_rank", ascending=False).head(10)[top_columns]

    summary = _json_value(result.summary)
    gex_total = summary.get("gex_total") or 0.0
    quality_status = "OK" if not quality["excluded_required_count"] and not quality["excluded_iv_count"] else "ATENCAO"
    checks = [
        {"check": "Linhas calculadas", "status": "OK", "detail": quality["calculated_rows"]},
        {"check": "IV recebida do Profit", "status": "OK", "detail": quality["valid_iv_count"]},
        {
            "check": "IV interpolada e sinalizada",
            "status": "AVISO" if quality["imputed_iv_count"] else "OK",
            "detail": quality["imputed_iv_count"],
        },
        {
            "check": "Linhas excluídas",
            "status": "OK" if not quality["excluded_required_count"] and not quality["excluded_iv_count"] else "ATENCAO",
            "detail": quality["excluded_required_count"] + quality["excluded_iv_count"],
        },
        {
            "check": "Strikes corrigidos pela B3",
            "status": "AVISO" if quality["strike_recovered_count"] else "OK",
            "detail": quality["strike_recovered_count"],
        },
        {
            "check": "Vencimentos corrigidos pela B3",
            "status": "AVISO" if quality["expiration_recovered_count"] else "OK",
            "detail": quality["expiration_recovered_count"],
        },
        {"check": "Cálculos e tabelas", "status": "OK", "detail": "Concluídos"},
    ]
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "quality_status": quality_status,
        "regime": "GEX POSITIVO" if gex_total >= 0 else "GEX NEGATIVO",
        "quality": quality,
        "checks": checks,
        "summary": summary,
        "by_expiration": _frame_payload(result.by_expiration),
        "by_strike": _frame_payload(signal_result.score_by_strike),
        "options": _frame_payload(result.options),
        "top_levels": _frame_payload(top_levels),
        "signal_config": signal_result.config.to_dict(),
        "signals": _frame_payload(signal_result.signals),
        "option_candidates": _frame_payload(signal_result.option_candidates),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera o payload das abas de resultado do Excel")
    parser.add_argument("--workbook", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--valuation-date")
    parser.add_argument("--b3-catalog")
    parser.add_argument("--signal-strength-min", type=float, default=65.0)
    parser.add_argument("--signal-rr-min", type=float, default=1.5)
    parser.add_argument("--signal-horizon-days", type=int, default=5)
    parser.add_argument("--signal-delta-min", type=float, default=0.50)
    parser.add_argument("--signal-delta-max", type=float, default=0.70)
    parser.add_argument("--signal-iv-shock", type=float, default=0.03)
    parser.add_argument("--signal-buffer-step", type=float, default=0.25)
    parser.add_argument("--monitor-interval", type=int, default=60)
    parser.add_argument("--signal-call-override")
    parser.add_argument("--signal-put-override")
    args = parser.parse_args(argv)

    workbook = Path(args.workbook)
    raw = pd.read_excel(workbook, sheet_name="Cadeia")
    catalog_path = Path(args.b3_catalog) if args.b3_catalog else workbook.with_name("series_autorizadas_b3.zip")
    b3_reference = read_b3_reference(catalog_path) if catalog_path.exists() else None
    result, quality = build_results(
        raw,
        valuation_date=args.valuation_date,
        b3_reference=b3_reference,
    )
    signal_config = SignalConfig(
        strength_min=args.signal_strength_min,
        reward_risk_min=args.signal_rr_min,
        horizon_days=args.signal_horizon_days,
        delta_min=args.signal_delta_min,
        delta_max=args.signal_delta_max,
        iv_shock=args.signal_iv_shock,
        buffer_step_fraction=args.signal_buffer_step,
        monitor_interval_seconds=args.monitor_interval,
        call_override=args.signal_call_override,
        put_override=args.signal_put_override,
    )
    payload = make_payload(result, quality, signal_config)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(
        f"Payload criado: {quality['calculated_rows']} opções, "
        f"{len(result.by_strike)} strikes, {len(result.by_expiration)} vencimentos, "
        f"{quality['imputed_iv_count']} IVs interpoladas"
    )
    print(f"Sinais criados: {len(payload['signals']['rows'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
