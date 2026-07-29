from __future__ import annotations

import hashlib
import io
import json
import math
import os
import threading
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Callable, Iterable
from xml.etree.ElementTree import iterparse

import httpx
import pandas as pd


B3_DOWNLOAD_URL = "https://www.b3.com.br/pesquisapregao/download"


class B3DataError(RuntimeError):
    """Falha explícita ao obter ou interpretar um arquivo público da B3."""


class B3FileUnavailable(B3DataError):
    """A B3 não publicou o arquivo para a data solicitada (feriado ou ausência de pregão)."""


@dataclass(slots=True)
class B3SessionData:
    trade_date: date
    prices: pd.DataFrame
    option_reference: pd.DataFrame
    instruments: pd.DataFrame
    manifest: dict[str, object]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _as_float(value: object) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return math.nan
    return number if math.isfinite(number) else math.nan


def _record_values(element: object) -> dict[str, str]:
    values: dict[str, str] = {}
    for child in element.iter():
        if child.text and child.text.strip():
            values[_local_name(child.tag)] = child.text.strip()
    return values


def _zip_member(blob: bytes, suffix: str) -> tuple[str, bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            names = [name for name in archive.namelist() if name.upper().endswith(suffix.upper())]
            if not names:
                raise B3DataError(f"Pacote B3 não contém {suffix}")
            name = sorted(names)[-1]
            return name, archive.read(name)
    except zipfile.BadZipFile as exc:
        raise B3DataError("Pacote B3 inválido ou incompleto") from exc


@contextmanager
def _xml_stream(package: bytes) -> Iterable[BinaryIO]:
    """Abre o XML da revisão mais recente sem extraí-lo para o disco."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(package))
    except zipfile.BadZipFile as exc:
        raise B3DataError("Arquivo interno da B3 não é um ZIP válido") from exc
    xml_names = sorted(name for name in archive.namelist() if name.lower().endswith(".xml"))
    if not xml_names:
        archive.close()
        raise B3DataError("Arquivo interno da B3 não contém XML")
    try:
        with archive.open(xml_names[-1]) as stream:
            yield stream
    finally:
        archive.close()


def parse_price_report(outer_blob: bytes, ticker_prefixes: set[str] | None = None) -> pd.DataFrame:
    _, inner = _zip_member(outer_blob, ".zip")
    rows: list[dict[str, object]] = []
    with _xml_stream(inner) as stream:
        for _, element in iterparse(stream, events=("end",)):
            if _local_name(element.tag) != "PricRpt":
                continue
            raw = _record_values(element)
            ticker = raw.get("TckrSymb")
            if ticker and (not ticker_prefixes or any(ticker.upper().startswith(prefix.upper()) for prefix in ticker_prefixes)):
                rows.append(
                    {
                        "trade_date": raw.get("Dt"),
                        "ticker": ticker.upper(),
                        "open": _as_float(raw.get("FrstPric")),
                        "low": _as_float(raw.get("MinPric")),
                        "high": _as_float(raw.get("MaxPric")),
                        "average": _as_float(raw.get("TradAvrgPric")),
                        "close": _as_float(raw.get("LastPric")),
                        "bid": _as_float(raw.get("BestBidPric")),
                        "ask": _as_float(raw.get("BestAskPric")),
                        "trades": _as_float(raw.get("RglrTxsQty") or raw.get("TradQty")),
                        "contracts": _as_float(raw.get("RglrTraddCtrcts") or raw.get("FinInstrmQty")),
                        "financial_volume": _as_float(raw.get("NtlRglrVol") or raw.get("NtlFinVol")),
                        "open_interest": _as_float(raw.get("OpnIntrst")),
                    }
                )
            element.clear()
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise B3DataError("Relatório de preços da B3 não contém instrumentos")
    return frame


def parse_option_reference(outer_blob: bytes, ticker_prefixes: set[str] | None = None) -> pd.DataFrame:
    _, executable = _zip_member(outer_blob, ".ex_")
    # O .ex_ é um arquivo autoextraível. ZipFile lê seu conteúdo sem executá-lo.
    _, text_blob = _zip_member(executable, ".txt")
    text = text_blob.decode("latin-1", errors="replace").splitlines()
    if not text:
        raise B3DataError("Arquivo de prêmios de referência vazio")
    rows: list[dict[str, object]] = []
    for line in text[1:]:
        parts = line.strip().split(";")
        if len(parts) < 7:
            continue
        ticker, option_type, style, expiration, strike, reference, iv = parts[:7]
        if ticker_prefixes and not any(ticker.upper().startswith(prefix.upper()) for prefix in ticker_prefixes):
            continue
        rows.append(
            {
                "ticker": ticker.upper(),
                "option_type": "call" if option_type.upper() == "C" else "put",
                "style": "european" if style.upper() == "E" else "american",
                "expiration": pd.to_datetime(expiration, format="%Y%m%d", errors="coerce"),
                "strike": _as_float(strike),
                "reference_price": _as_float(reference),
                "implied_volatility": _as_float(iv) / 100.0,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise B3DataError("Arquivo de prêmios não contém opções")
    return frame


def parse_instruments(outer_blob: bytes) -> pd.DataFrame:
    _, inner = _zip_member(outer_blob, ".zip")
    rows: list[dict[str, object]] = []
    with _xml_stream(inner) as stream:
        for _, element in iterparse(stream, events=("end",)):
            if _local_name(element.tag) != "Instrm":
                continue
            raw = _record_values(element)
            ticker = raw.get("TckrSymb", "").upper()
            is_option = raw.get("OptnTp") in {"CALL", "PUT"}
            is_equity = raw.get("SctyCtgy") == "11" and raw.get("CFICd", "").startswith("E")
            if not ticker or not (is_option or is_equity):
                element.clear()
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "asset_root": raw.get("Asst", "").upper(),
                    "instrument_type": "option" if is_option else "equity",
                    "option_type": raw.get("OptnTp", "").lower() if is_option else None,
                    "style": ("european" if raw.get("OptnStyle") == "EURO" else "american") if is_option else None,
                    "expiration": pd.to_datetime(raw.get("XprtnDt"), errors="coerce"),
                    "strike": _as_float(raw.get("ExrcPric")),
                    "lot_size": _as_float(raw.get("AllcnRndLot")),
                    "price_factor": _as_float(raw.get("PricFctr")),
                    "isin": raw.get("ISIN"),
                    "cfi_code": raw.get("CFICd"),
                }
            )
            element.clear()
    return pd.DataFrame(rows)


class B3Client:
    def __init__(self, data_dir: str | Path = "data", timeout: float = 90.0) -> None:
        self.data_dir = Path(data_dir)
        self.raw_dir = self.data_dir / "raw"
        self.parsed_dir = self.data_dir / "parsed"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.parsed_dir.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=20.0),
            follow_redirects=True,
            headers={"User-Agent": "GammaLevelsSwing/0.3 (+local dashboard)"},
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "B3Client":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def file_name(kind: str, trading_date: date) -> str:
        stamp = trading_date.strftime("%y%m%d")
        return f"{kind}{stamp}.ex_" if kind == "PE" else f"{kind}{stamp}.zip"

    def _path(self, kind: str, trading_date: date) -> Path:
        return self.raw_dir / trading_date.isoformat() / self.file_name(kind, trading_date)

    def _parsed_path(
        self, kind: str, trading_date: date, ticker_prefixes: set[str] | None = None
    ) -> Path:
        shard = "ALL" if not ticker_prefixes else "_".join(sorted(prefix.upper() for prefix in ticker_prefixes))
        return self.parsed_dir / trading_date.isoformat() / f"{kind}_{shard}.parquet"

    def _load_parsed_report(
        self, kind: str, trading_date: date, parser: Callable[[bytes], pd.DataFrame],
        ticker_prefixes: set[str] | None = None,
    ) -> tuple[bytes, pd.DataFrame]:
        """Interpreta cada relatório uma vez por grupo de ativos e reutiliza o recorte."""
        target = self._parsed_path(kind, trading_date, ticker_prefixes)
        if target.exists():
            blob = self.download(kind, trading_date)
            try:
                return blob, pd.read_parquet(target)
            except (OSError, ValueError):
                self._quarantine(target)
        blob, frame = self._load_with_retry(kind, trading_date, parser)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(
            f"{target.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        frame.to_parquet(temporary, index=False, compression="zstd")
        os.replace(temporary, target)
        return blob, frame

    def is_available(self, trading_date: date) -> bool:
        name = self.file_name("PR", trading_date)
        try:
            response = self.client.head(B3_DOWNLOAD_URL, params={"filelist": name})
            return response.status_code == 200 and int(response.headers.get("content-length", "1")) > 0
        except httpx.HTTPError:
            return False

    def latest_available_date(self, before: date | None = None, lookback: int = 10) -> date:
        candidate = (before or date.today()) - timedelta(days=1)
        for offset in range(lookback + 1):
            current = candidate - timedelta(days=offset)
            if current.weekday() < 5 and self.is_available(current):
                return current
        raise B3DataError("Nenhum pregão B3 publicado foi encontrado nos últimos dias")

    def download(self, kind: str, trading_date: date, *, force: bool = False) -> bytes:
        target = self._path(kind, trading_date)
        if target.exists() and not force:
            blob = target.read_bytes()
            try:
                self._validate(kind, blob)
                return blob
            except B3DataError:
                self._quarantine(target)
        name = self.file_name(kind, trading_date)
        try:
            response = self.client.get(B3_DOWNLOAD_URL, params={"filelist": name})
            if response.status_code in {404, 410}:
                raise B3FileUnavailable(f"Arquivo não publicado pela B3: {name}")
            response.raise_for_status()
        except B3FileUnavailable:
            raise
        except httpx.HTTPError as exc:
            raise B3DataError(f"Falha ao baixar {name}: {exc}") from exc
        blob = response.content
        if len(blob) < 100 or not zipfile.is_zipfile(io.BytesIO(blob)):
            raise B3FileUnavailable(f"Arquivo não publicado pela B3: {name}")
        self._validate(kind, blob)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(blob)
        os.replace(temporary, target)
        return blob

    @staticmethod
    def _validate(kind: str, blob: bytes) -> None:
        if not zipfile.is_zipfile(io.BytesIO(blob)):
            raise B3DataError(f"Pacote {kind} inválido ou incompleto")
        if kind == "PR":
            _, inner = _zip_member(blob, ".zip")
            with _xml_stream(inner) as stream:
                stream.read(128)
        elif kind == "PE":
            _, executable = _zip_member(blob, ".ex_")
            _zip_member(executable, ".txt")
        elif kind == "IN":
            _, inner = _zip_member(blob, ".zip")
            with _xml_stream(inner) as stream:
                stream.read(128)

    @staticmethod
    def _quarantine(target: Path) -> None:
        if not target.exists():
            return
        quarantine = target.parent / "quarantine"
        quarantine.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        os.replace(target, quarantine / f"{target.name}.{stamp}.bad")

    def _load_with_retry(
        self, kind: str, trading_date: date, parser: Callable[[bytes], pd.DataFrame],
        attempts: int = 3,
    ) -> tuple[bytes, pd.DataFrame]:
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                blob = self.download(kind, trading_date, force=attempt > 0)
                return blob, parser(blob)
            except B3FileUnavailable:
                raise
            except (B3DataError, OSError, zipfile.BadZipFile) as exc:
                last_error = exc
                self._quarantine(self._path(kind, trading_date))
        raise B3DataError(
            f"{kind}{trading_date:%y%m%d} falhou após {attempts} tentativas: {last_error}"
        )

    def load_session(
        self,
        trading_date: date,
        *,
        include_instruments: bool = False,
        ticker_prefixes: set[str] | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> B3SessionData:
        tell = progress or (lambda _: None)
        tell(f"Baixando relatório de preços de {trading_date:%d/%m/%Y}")
        tell("Lendo preços, negócios e posições em aberto")
        price_blob, prices = self._load_parsed_report(
            "PR", trading_date, lambda blob: parse_price_report(blob, ticker_prefixes), ticker_prefixes
        )
        if prices.empty:
            raise B3DataError("Relatório de preços da B3 não contém os ativos solicitados")
        tell("Baixando prêmios e volatilidades de referência")
        reference_blob, option_reference = self._load_parsed_report(
            "PE", trading_date, lambda blob: parse_option_reference(blob, ticker_prefixes), ticker_prefixes
        )
        if option_reference.empty:
            raise B3DataError("Arquivo de prêmios não contém as opções solicitadas")
        instruments = pd.DataFrame()
        hashes = {
            "PR": hashlib.sha256(price_blob).hexdigest(),
            "PE": hashlib.sha256(reference_blob).hexdigest(),
        }
        if include_instruments:
            tell("Atualizando o cadastro de instrumentos")
            instrument_blob = self.download("IN", trading_date)
            instruments = parse_instruments(instrument_blob)
            hashes["IN"] = hashlib.sha256(instrument_blob).hexdigest()
        manifest: dict[str, object] = {
            "trade_date": trading_date.isoformat(),
            "source": "B3 Pesquisa por Pregão",
            "files": hashes,
            "price_rows": len(prices),
            "option_rows": len(option_reference),
            "instrument_rows": len(instruments),
        }
        manifest_path = self.raw_dir / trading_date.isoformat() / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return B3SessionData(trading_date, prices, option_reference, instruments, manifest)


def previous_weekdays(end: date, count: int) -> Iterable[date]:
    current = end
    emitted = 0
    while emitted < count:
        if current.weekday() < 5:
            yield current
            emitted += 1
        current -= timedelta(days=1)
