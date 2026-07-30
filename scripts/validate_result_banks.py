from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scalar(connection: sqlite3.Connection, query: str, parameters: tuple[Any, ...] = ()) -> Any:
    row = connection.execute(query, parameters).fetchone()
    return row[0] if row else None


def inspect_database(path: Path, batch_item: dict[str, Any] | None) -> dict[str, Any]:
    ticker = path.parent.name.removeprefix("pilot_").upper()
    result: dict[str, Any] = {
        "ticker": ticker,
        "batch_status": (batch_item or {}).get("status", "not_listed"),
        "database": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }
    try:
        connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        integrity = scalar(connection, "PRAGMA quick_check")
        result["integrity"] = integrity
        run = connection.execute("SELECT * FROM backtest_runs ORDER BY id DESC LIMIT 1").fetchone()
        if run is None:
            result["valid_complete"] = False
            result["error"] = "no backtest run"
            return result
        run_data = dict(run)
        run_id = int(run_data["id"])
        result["run"] = {
            key: run_data.get(key)
            for key in (
                "id",
                "ticker",
                "asset_root",
                "started_at",
                "finished_at",
                "status",
                "phase",
                "message",
                "first_date",
                "last_date",
                "evaluated_sessions",
                "dataset_hash",
            )
        }
        result["metrics_count"] = scalar(
            connection, "SELECT COUNT(*) FROM backtest_metrics WHERE run_id=?", (run_id,)
        )
        result["trades_count"] = scalar(
            connection, "SELECT COUNT(*) FROM backtest_trades WHERE run_id=?", (run_id,)
        )
        result["filled_trades_count"] = scalar(
            connection,
            "SELECT COUNT(*) FROM backtest_trades WHERE run_id=? AND fill_status LIKE 'FILLED%'",
            (run_id,),
        )
        result["valid_complete"] = (
            integrity == "ok"
            and run_data.get("status") == "COMPLETE"
        )
    except Exception as exc:  # keep a complete manifest even when one bank is damaged
        result["valid_complete"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if "connection" in locals():
            connection.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Gamma Levels batch SQLite results.")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--batch-status", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--file-list", type=Path)
    args = parser.parse_args()

    batch: dict[str, Any] = {}
    if args.batch_status and args.batch_status.exists():
        batch = json.loads(args.batch_status.read_text(encoding="utf-8"))
    items = batch.get("items", {})
    databases = sorted(args.data_dir.glob("pilot_*/gamma_levels.db"))
    results = [
        inspect_database(database, items.get(database.parent.name.removeprefix("pilot_").upper()))
        for database in databases
    ]
    valid = [item for item in results if item.get("valid_complete")]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(args.data_dir),
        "batch_updated_at": batch.get("updated_at"),
        "batch_counts": batch.get("counts"),
        "database_count": len(results),
        "valid_complete_count": len(valid),
        "invalid_or_incomplete_count": len(results) - len(valid),
        "valid_complete_bytes": sum(int(item["size_bytes"]) for item in valid),
        "results": results,
    }
    rendered = json.dumps(manifest, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if args.file_list:
        project_root = args.data_dir.parent
        export_paths = [str(Path("data") / Path(item["database"]).parent.name) for item in valid]
        export_paths.extend(
            str(path)
            for path in (
                Path("data/logs"),
                Path("data/batch_status.json"),
                Path("data/result_manifest_vps.json"),
                Path("data/result_export_files.txt"),
                Path("lista.md"),
                Path("PROJECT_MEMORY.md"),
            )
            if (project_root / path).exists() or path == Path("data/result_export_files.txt")
        )
        args.file_list.parent.mkdir(parents=True, exist_ok=True)
        args.file_list.write_text("\n".join(export_paths) + "\n", encoding="utf-8")
    print(rendered)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
