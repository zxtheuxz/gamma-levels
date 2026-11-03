from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from .b3 import (
    B3Client,
    B3DataError,
    parse_index_report,
    parse_instruments,
    parse_option_reference,
    parse_price_report,
    resolve_instrument_underliers,
)
from .footprint import build_footprint, read_trade_file
from .index_futures import (
    DailyIndexMap,
    IndexCompositionClient,
    IndexFuturesConfig,
    active_win_contract,
    build_daily_map,
    prepare_option_market,
)
from .index_futures_storage import IndexFuturesDatabase, json_dumps
from .market_context import rate_on
from .storage import Database


@dataclass(slots=True)
class DailyRunResult:
    daily_map: DailyIndexMap
    footprint: pd.DataFrame
    footprint_summary: dict[str, Any]
    output_dir: Path | None = None


class IndexFuturesService:
    def __init__(
        self,
        data_dir: str | Path = "data",
        *,
        main_database: str | Path | None = None,
        index_database: str | Path | None = None,
        allow_download: bool = True,
        config: IndexFuturesConfig | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.main_database = Database(main_database or self.data_dir / "gamma_levels.db")
        self.index_database = IndexFuturesDatabase(
            index_database or self.data_dir / "index_futures" / "gamma_index.db"
        )
        self.allow_download = allow_download
        self.config = config or IndexFuturesConfig()

    def _raw_path(self, kind: str, trading_date: date) -> Path:
        return self.data_dir / "raw" / trading_date.isoformat() / B3Client.file_name(kind, trading_date)

    def _blob(self, client: B3Client, kind: str, trading_date: date) -> bytes:
        target = self._raw_path(kind, trading_date)
        if not self.allow_download and not target.exists():
            raise B3DataError(f"Modo sem download: arquivo ausente {target}")
        return client.download(kind, trading_date)

    def _cached_report(
        self,
        client: B3Client,
        kind: str,
        trading_date: date,
        roots: set[str] | None,
    ) -> pd.DataFrame:
        shard_text = "ALL" if roots is None else "|".join(sorted(roots))
        shard = hashlib.sha1(shard_text.encode()).hexdigest()[:12]
        target = self.data_dir / "parsed" / "index_futures" / trading_date.isoformat() / f"{kind}_{shard}.parquet"
        if target.exists():
            return pd.read_parquet(target)
        blob = self._blob(client, kind, trading_date)
        if kind == "PR":
            frame = parse_price_report(blob, roots)
        elif kind == "PE":
            frame = parse_option_reference(blob, roots)
        else:
            raise ValueError(f"Relatório sem parser de cache: {kind}")
        target.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(target, index=False, compression="zstd")
        return frame

    def resolve_date(self, requested: date | None, client: B3Client) -> date:
        if requested:
            return requested
        if self.allow_download:
            return client.latest_available_date()
        available = []
        for path in (self.data_dir / "raw").glob("????-??-??/PR*.zip"):
            try:
                candidate = date.fromisoformat(path.parent.name)
            except ValueError:
                continue
            if self._raw_path("PE", candidate).exists():
                available.append(candidate)
        if not available:
            raise B3DataError("Nenhum par PR/PE local disponível")
        return max(available)

    def _composition(self, trading_date: date) -> pd.DataFrame:
        if self.allow_download:
            frame = IndexCompositionClient().fetch()
            self.index_database.save_composition(frame)
        else:
            frame = self.index_database.composition_for(trading_date)
        if frame.empty:
            raise B3DataError("Carteira IBOV indisponível; execute uma vez com download")
        return frame

    def _nearest_instruments(self, trading_date: date, client: B3Client) -> tuple[pd.DataFrame, str]:
        candidates: list[tuple[date, Path]] = []
        for path in (self.data_dir / "raw").glob("????-??-??/IN*.zip"):
            try:
                candidate = date.fromisoformat(path.parent.name)
            except ValueError:
                continue
            if candidate <= trading_date:
                candidates.append((candidate, path))
        if candidates:
            instrument_date, path = max(candidates, key=lambda item: item[0])
            cache = self.data_dir / "parsed" / "index_futures" / instrument_date.isoformat() / "IN_ALL_v2.parquet"
            if cache.exists():
                return resolve_instrument_underliers(pd.read_parquet(cache)), instrument_date.isoformat()
            frame = parse_instruments(path.read_bytes())
            cache.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(cache, index=False, compression="zstd")
            return frame, instrument_date.isoformat()
        if not self.allow_download:
            raise B3DataError("Cadastro IN local não encontrado")
        blob = self._blob(client, "IN", trading_date)
        return parse_instruments(blob), trading_date.isoformat()

    def _raw_session_dates(self, end: date, count: int) -> list[date]:
        dates = []
        for path in (self.data_dir / "raw").glob("????-??-??/PR*.zip"):
            try:
                candidate = date.fromisoformat(path.parent.name)
            except ValueError:
                continue
            if candidate <= end:
                dates.append(candidate)
        return sorted(set(dates))[-count:]

    def _store_context(self, trading_date: date, prices: pd.DataFrame, index: pd.DataFrame | None) -> dict[str, Any]:
        win = active_win_contract(prices, trading_date)
        bova = prices[prices["ticker"].eq("BOVA11")]
        ibov = index[index["ticker"].eq("IBOV")].iloc[0] if index is not None and not index.empty else None
        row: dict[str, Any] = {
            "trade_date": trading_date.isoformat(),
            "win_ticker": win["ticker"],
            "win_expiration": win["expiration"].isoformat(),
            "win_open": win.get("open"),
            "win_low": win.get("low"),
            "win_high": win.get("high"),
            "win_close": win.get("close"),
            "win_contracts": win.get("contracts"),
            "win_financial_volume": win.get("financial_volume"),
            "ibov_source": "IR_B3" if ibov is not None else "UNAVAILABLE",
        }
        if not bova.empty:
            for field in ("open", "low", "high", "close"):
                row[f"bova_{field}"] = bova.iloc[0].get(field)
        if ibov is not None:
            for field in ("open", "low", "high", "close"):
                row[f"ibov_{field}"] = ibov.get(field)
            row["ibov_settlement"] = ibov.get("settlement_value")
        self.index_database.save_market_context(row)
        return row

    def _load_context_history(self, client: B3Client, trading_date: date, sessions: int) -> pd.DataFrame:
        for candidate in self._raw_session_dates(trading_date, sessions):
            existing = self.index_database.frame(
                "SELECT 1 FROM market_context WHERE trade_date=?", (candidate.isoformat(),)
            )
            if not existing.empty:
                continue
            prices = self._cached_report(client, "PR", candidate, {"WIN", "BOVA11"})
            index = None
            ir_path = self._raw_path("IR", candidate)
            if ir_path.exists():
                index = parse_index_report(ir_path.read_bytes(), {"IBOV"})
            self._store_context(candidate, prices, index)
        return self.index_database.market_history(trading_date)

    def _previous_market(
        self,
        trading_date: date,
        roots: set[str],
        instruments: pd.DataFrame,
    ) -> pd.DataFrame:
        earlier = [item for item in self._raw_session_dates(trading_date, 5) if item < trading_date]
        for candidate in reversed(earlier):
            pe = self._raw_path("PE", candidate)
            pr = self._raw_path("PR", candidate)
            if not pe.exists() or not pr.exists():
                continue
            with B3Client(self.data_dir) as client:
                prices = self._cached_report(client, "PR", candidate, roots)
                references = self._cached_report(client, "PE", candidate, roots)
            return prepare_option_market(prices, references, roots, instruments)
        return pd.DataFrame()

    def run_daily(
        self,
        trading_date: date | None = None,
        *,
        footprint_file: str | Path | None = None,
        context_sessions: int = 80,
        include_components: bool = True,
        include_ibov: bool = True,
    ) -> DailyRunResult:
        with B3Client(self.data_dir) as client:
            trading_date = self.resolve_date(trading_date, client)
            composition = (
                self._composition(trading_date)
                if include_components
                else pd.DataFrame(columns=["ticker", "asset_root", "weight", "as_of"])
            )
            instruments, instrument_as_of = self._nearest_instruments(trading_date, client)
            roots = set(composition["asset_root"].astype(str).str.upper()) | {"BOVA", "WIN"}
            if include_ibov:
                roots.add("IBOV")
            prices = self._cached_report(client, "PR", trading_date, roots)
            references = self._cached_report(client, "PE", trading_date, roots)
            official_index = (
                parse_index_report(self._blob(client, "IR", trading_date), {"IBOV"})
                if include_ibov else pd.DataFrame()
            )
            option_market = prepare_option_market(prices, references, roots, instruments)
            previous_market = self._previous_market(trading_date, roots, instruments)
            current_context = self._store_context(trading_date, prices, official_index)
            history = self._load_context_history(client, trading_date, context_sessions)

        index_history = history[["trade_date", "ibov_close", "win_close"]].copy()
        index_history["close"] = index_history["ibov_close"].combine_first(index_history["win_close"])
        index_history = index_history[["trade_date", "close"]].dropna()
        win_history = history.rename(
            columns={"win_open": "open", "win_low": "low", "win_high": "high", "win_close": "close", "win_ticker": "ticker"}
        )[["trade_date", "ticker", "open", "low", "high", "close"]].dropna(subset=["close"])
        component_histories = (
            {
                str(ticker): self.main_database.bars(
                    str(ticker), trading_date, self.config.beta_window + 5
                )
                for ticker in composition["ticker"].astype(str)
            }
            if include_components
            else {}
        )
        rate = rate_on(self.main_database, trading_date)
        index_row = (
            official_index[official_index["ticker"].eq("IBOV")].iloc[0].to_dict()
            if include_ibov and not official_index.empty else None
        )
        source_families = {"BOVA"}
        if include_ibov:
            source_families.add("IBOV")
        if include_components:
            source_families.add("COMPONENT")
        daily_map = build_daily_map(
            trade_date=trading_date,
            prices=prices,
            index_row=index_row,
            option_market=option_market,
            previous_option_market=previous_market,
            composition=composition,
            instruments=instruments,
            component_histories=component_histories,
            index_history=index_history,
            win_history=win_history,
            rate=rate,
            config=self.config,
            source_families=source_families,
        )
        daily_map.context.update(
            {
                "instrument_as_of": instrument_as_of,
                "composition_lookahead_days": (
                    date.fromisoformat(str(composition.iloc[0]["as_of"])) - trading_date
                ).days if not composition.empty else None,
                "source_families": sorted(source_families),
                "ibov_history_observations": int(history["ibov_close"].notna().sum()),
                "beta_proxy_observations": int(history["ibov_close"].isna().sum()),
                "rate": rate,
                "win_ticker": current_context["win_ticker"],
            }
        )
        footprint_bins = pd.DataFrame()
        footprint_summary = {"status": "UNAVAILABLE", "reason": "arquivo negócio a negócio não fornecido"}
        if footprint_file:
            footprint = build_footprint(
                read_trade_file(footprint_file), ticker=str(current_context["win_ticker"])
            )
            footprint_bins, footprint_summary = footprint.bins, footprint.summary
            footprint_date = footprint_summary.get("trade_date")
            if footprint_date and str(footprint_date) != trading_date.isoformat():
                raise ValueError(
                    f"Footprint é de {footprint_date}, mas o mapa solicitado é {trading_date.isoformat()}"
                )
            self.index_database.save_footprint(footprint_bins)
        daily_map.context["footprint"] = footprint_summary
        self.index_database.save_daily_map(daily_map)
        return DailyRunResult(daily_map, footprint_bins, footprint_summary)


def write_daily_package(result: DailyRunResult, output_root: str | Path) -> Path:
    trade_date = str(result.daily_map.context["trade_date"])
    target = Path(output_root) / trade_date
    target.mkdir(parents=True, exist_ok=True)
    payload = {
        "context": result.daily_map.context,
        "zones": result.daily_map.zones.to_dict("records"),
        "source_levels": result.daily_map.levels.to_dict("records"),
        "source_summary": result.daily_map.source_summary.to_dict("records"),
        "quality": result.daily_map.quality.to_dict("records"),
        "footprint_summary": result.footprint_summary,
    }
    (target / "daily_map.json").write_text(
        json.dumps(json.loads(json_dumps(payload)), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for name, frame in (
        ("zones", result.daily_map.zones),
        ("source_levels", result.daily_map.levels),
        ("source_summary", result.daily_map.source_summary),
        ("quality", result.daily_map.quality),
        ("footprint", result.footprint),
    ):
        frame.to_csv(target / f"{name}.csv", index=False, encoding="utf-8-sig")
    result.output_dir = target
    return target


def console_report(result: DailyRunResult) -> str:
    context = result.daily_map.context
    lines = [
        f"Mapa WIN D-1 — {context['trade_date']} — {context.get('win_ticker')}",
        f"IBOV {context.get('ibov_close', 0):,.2f} | WIN {context.get('win_close', 0):,.0f} | ATR20 {context.get('atr_points', 0):,.0f}",
        f"Footprint: {result.footprint_summary.get('status')} ({result.footprint_summary.get('method') or result.footprint_summary.get('reason')})",
    ]
    if result.daily_map.zones.empty:
        lines.append("Nenhuma zona válida; consulte quality.csv.")
    else:
        lines.append("Horizonte  Tipo       Região              Conf.  Famílias")
        for row in result.daily_map.zones.sort_values(["horizon", "zone_center"]).to_dict("records"):
            lines.append(
                f"{row['horizon']:<10} {row['zone_type']:<10} {row['zone_low']:>8.0f}–{row['zone_high']:<8.0f} {row['confidence']:<6} {row['source_families']}"
            )
    return "\n".join(lines)
