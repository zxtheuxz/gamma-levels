from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


LOCAL_ORIGINALS = {"PETR4", "VALE3", "ITUB4", "BBDC4"}
SPLITS = ("train_126", "validation_1", "validation_2")


def clean(value: Any) -> Any:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def pct(value: float | None) -> float | None:
    return None if value is None else value * 100


def flatten_combo(ticker: str, rows: dict[str, sqlite3.Row]) -> dict[str, Any]:
    full = rows["full"]
    output: dict[str, Any] = {
        "ticker": ticker,
        "source": "LOCAL_ORIGINAL" if ticker in LOCAL_ORIGINALS else "VPS_BATCH",
        "variant": full["variant"],
        "strategy": full["strategy"],
        "full_trades": full["trades"],
        "full_wins": full["wins"],
        "full_win_rate_pct": pct(full["win_rate"]),
        "full_expectancy_pct": pct(full["expectancy"]),
        "full_profit_factor": full["profit_factor"],
        "full_avg_win_pct": pct(full["avg_win"]),
        "full_avg_loss_pct": pct(full["avg_loss"]),
        "full_max_drawdown_pct": pct(full["max_drawdown"]),
    }
    for sample in (*SPLITS, "out_of_sample"):
        row = rows[sample]
        prefix = {"train_126": "train", "validation_1": "val1", "validation_2": "val2", "out_of_sample": "oos"}[sample]
        output[f"{prefix}_trades"] = row["trades"]
        output[f"{prefix}_wins"] = row["wins"]
        output[f"{prefix}_win_rate_pct"] = pct(row["win_rate"])
        output[f"{prefix}_expectancy_pct"] = pct(row["expectancy"])
        output[f"{prefix}_profit_factor"] = row["profit_factor"]

    split_expectancies = [output[f"{prefix}_expectancy_pct"] for prefix in ("train", "val1", "val2")]
    output["positive_full"] = bool(output["full_expectancy_pct"] is not None and output["full_expectancy_pct"] > 0)
    output["consistent_oos"] = bool(
        output["full_trades"] >= 10
        and output["train_trades"] >= 3
        and output["oos_trades"] >= 4
        and output["full_expectancy_pct"] is not None
        and output["full_expectancy_pct"] > 0
        and output["train_expectancy_pct"] is not None
        and output["train_expectancy_pct"] > 0
        and output["oos_expectancy_pct"] is not None
        and output["oos_expectancy_pct"] > 0
        and (output["full_profit_factor"] is None or output["full_profit_factor"] > 1)
    )
    output["strictly_stable"] = bool(
        output["consistent_oos"]
        and output["val1_trades"] >= 2
        and output["val2_trades"] >= 2
        and all(value is not None and value > 0 for value in split_expectancies)
    )
    output["stability_floor_pct"] = min(split_expectancies) if output["strictly_stable"] else None
    return {key: clean(value) for key, value in output.items()}


def inspect_asset(database: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ticker = database.parent.name.removeprefix("pilot_").upper()
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        run = connection.execute("SELECT * FROM backtest_runs ORDER BY id DESC LIMIT 1").fetchone()
        if run is None or run["status"] != "COMPLETE":
            raise RuntimeError(f"{ticker}: latest run is not COMPLETE")
        rows = connection.execute(
            """SELECT * FROM backtest_metrics
               WHERE run_id=? AND overlap_mode='INDEPENDENT'
               ORDER BY variant,strategy,sample""",
            (run["id"],),
        ).fetchall()
        grouped: dict[tuple[str, str], dict[str, sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault((row["variant"], row["strategy"]), {})[row["sample"]] = row
        combinations = [
            flatten_combo(ticker, samples)
            for samples in grouped.values()
            if {"full", "train_126", "validation_1", "validation_2", "out_of_sample"} <= samples.keys()
        ]
        filled = connection.execute(
            "SELECT COUNT(*) FROM backtest_trades WHERE run_id=? AND fill_status LIKE 'FILLED%'",
            (run["id"],),
        ).fetchone()[0]
        candidates = [item for item in combinations if item["full_trades"] >= 10]
        raw_best = max(candidates, key=lambda item: item["full_expectancy_pct"] or -math.inf, default=None)
        oos_best = max(
            (item for item in candidates if item["consistent_oos"]),
            key=lambda item: (item["oos_expectancy_pct"] or -math.inf, item["full_expectancy_pct"] or -math.inf),
            default=None,
        )
        stable_best = max(
            (item for item in candidates if item["strictly_stable"]),
            key=lambda item: (item["stability_floor_pct"] or -math.inf, item["full_expectancy_pct"] or -math.inf),
            default=None,
        )
        maximum_trades = max((item["full_trades"] for item in combinations), default=0)
        if filled == 0:
            classification = "NO_TRADES"
        elif maximum_trades < 10:
            classification = "LOW_SAMPLE"
        elif stable_best:
            classification = "STRICTLY_STABLE"
        elif oos_best:
            classification = "POSITIVE_TRAIN_AND_OOS"
        elif raw_best and (raw_best["full_expectancy_pct"] or 0) > 0:
            classification = "POSITIVE_FULL_ONLY"
        else:
            classification = "NO_POSITIVE_10_TRADE_COMBO"

        chosen = stable_best or oos_best or raw_best
        summary = {
            "ticker": ticker,
            "source": "LOCAL_ORIGINAL" if ticker in LOCAL_ORIGINALS else "VPS_BATCH",
            "classification": classification,
            "run_id": run["id"],
            "first_date": run["first_date"],
            "last_date": run["last_date"],
            "evaluated_sessions": run["evaluated_sessions"],
            "filled_variant_trades": filled,
            "max_full_trades": maximum_trades,
            "eligible_combinations": len(candidates),
        }
        for label, item in (("best_raw", raw_best), ("best_oos", oos_best), ("best_stable", stable_best), ("selected", chosen)):
            summary[f"{label}_variant"] = item["variant"] if item else None
            summary[f"{label}_strategy"] = item["strategy"] if item else None
            summary[f"{label}_trades"] = item["full_trades"] if item else None
            summary[f"{label}_win_rate_pct"] = item["full_win_rate_pct"] if item else None
            summary[f"{label}_expectancy_pct"] = item["full_expectancy_pct"] if item else None
            summary[f"{label}_profit_factor"] = item["full_profit_factor"] if item else None
            summary[f"{label}_oos_trades"] = item["oos_trades"] if item else None
            summary[f"{label}_oos_expectancy_pct"] = item["oos_expectancy_pct"] if item else None
            summary[f"{label}_stability_floor_pct"] = item["stability_floor_pct"] if item else None
        return summary, combinations
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a consolidated multi-asset result ranking.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("resultado_excel"))
    args = parser.parse_args()

    summaries: list[dict[str, Any]] = []
    combinations: list[dict[str, Any]] = []
    for database in sorted(args.data_dir.glob("pilot_*/gamma_levels.db")):
        summary, asset_combinations = inspect_asset(database)
        summaries.append(summary)
        combinations.extend(asset_combinations)

    summary_frame = pd.DataFrame(summaries)
    combination_frame = pd.DataFrame(combinations)
    stable_frame = combination_frame.loc[combination_frame["strictly_stable"]].copy()
    stable_frame.sort_values(
        ["stability_floor_pct", "full_expectancy_pct", "full_trades"], ascending=[False, False, False], inplace=True
    )
    oos_frame = combination_frame.loc[combination_frame["consistent_oos"]].copy()
    oos_frame.sort_values(["oos_expectancy_pct", "full_expectancy_pct"], ascending=[False, False], inplace=True)
    class_order = {
        "STRICTLY_STABLE": 0,
        "POSITIVE_TRAIN_AND_OOS": 1,
        "POSITIVE_FULL_ONLY": 2,
        "NO_POSITIVE_10_TRADE_COMBO": 3,
        "LOW_SAMPLE": 4,
        "NO_TRADES": 5,
    }
    summary_frame["class_order"] = summary_frame["classification"].map(class_order)
    summary_frame.sort_values(
        ["class_order", "selected_stability_floor_pct", "selected_oos_expectancy_pct", "selected_expectancy_pct"],
        ascending=[True, False, False, False],
        na_position="last",
        inplace=True,
    )
    summary_frame.drop(columns=["class_order"], inplace=True)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    workbook = args.output_dir / "ranking_consolidado_75_ativos.xlsx"
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        summary_frame.to_excel(writer, sheet_name="Resumo_Ativos", index=False)
        stable_frame.to_excel(writer, sheet_name="Ranking_Estavel", index=False)
        oos_frame.to_excel(writer, sheet_name="Treino_e_OOS", index=False)
        combination_frame.to_excel(writer, sheet_name="Todas_Combinacoes", index=False)
        pd.DataFrame(
            [
                {"campo": "Gerado em (UTC)", "valor": datetime.now(timezone.utc).isoformat()},
                {"campo": "Universo", "valor": f"{len(summary_frame)} bancos COMPLETE e íntegros"},
                {"campo": "Sobreposição", "valor": "INDEPENDENT"},
                {"campo": "Amostra mínima principal", "valor": "10 operações no período completo"},
                {"campo": "Estável estrito", "valor": "treino >=3, validação 1 >=2, validação 2 >=2 e expectativa positiva em todos"},
                {"campo": "Treino e OOS", "valor": "treino >=3, OOS >=4 e expectativa positiva no completo, treino e OOS"},
                {"campo": "Ordenação estável", "valor": "pior expectativa entre treino/validação 1/validação 2; depois expectativa completa"},
                {"campo": "Observação", "valor": "Classificação comparativa; não é recomendação de investimento"},
            ]
        ).to_excel(writer, sheet_name="Metodologia", index=False)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asset_count": len(summary_frame),
        "classification_counts": summary_frame["classification"].value_counts().to_dict(),
        "summary": [
            {key: clean(value) for key, value in row.items()}
            for row in summary_frame.to_dict("records")
        ],
        "strictly_stable": [
            {key: clean(value) for key, value in row.items()}
            for row in stable_frame.to_dict("records")
        ],
    }
    json_path = args.output_dir / "ranking_consolidado_75_ativos.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"workbook": str(workbook), "json": str(json_path), **payload["classification_counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
