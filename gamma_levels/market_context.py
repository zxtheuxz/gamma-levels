from __future__ import annotations

import base64
import csv
import io
import json
from datetime import date, datetime, timedelta
from typing import Any, Iterable

import httpx

from .storage import Database, json_dumps


BCB_SELIC_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1178/dados"
B3_LISTED_PROXY = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall"


def _number(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return default


def _date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()[:10]
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


class InterestRateClient:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def load(self, database: Database, start: date, end: date) -> int:
        params = {
            "formato": "json",
            "dataInicial": start.strftime("%d/%m/%Y"),
            "dataFinal": end.strftime("%d/%m/%Y"),
        }
        response = httpx.get(BCB_SELIC_URL, params=params, timeout=self.timeout)
        response.raise_for_status()
        rows = []
        for item in response.json():
            trade_date = _date(item.get("data"))
            value = _number(item.get("valor"), -1.0)
            if trade_date and value >= 0:
                rows.append((trade_date.isoformat(), value / 100.0, "BCB SGS 1178", json_dumps(item)))
        with database.connect() as connection:
            connection.executemany(
                """INSERT OR REPLACE INTO interest_rates(trade_date,annual_rate,source,payload_json)
                VALUES (?,?,?,?)""",
                rows,
            )
        return len(rows)


class CorporateActionClient:
    """Importa eventos públicos da página de companhias listadas da B3."""

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    @staticmethod
    def _encode(payload: dict[str, Any]) -> str:
        return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()

    @classmethod
    def _token(cls, asset_root: str) -> str:
        payload = json.dumps(
            {"issuingCompany": asset_root.upper(), "language": "pt-br"},
            separators=(",", ":"),
        ).encode()
        return base64.b64encode(payload).decode()

    def _trading_name(self, asset_root: str) -> str:
        payload = {
            "language": "pt", "pageNumber": 1, "pageSize": 100,
            "company": asset_root.upper(),
        }
        url = f"{B3_LISTED_PROXY}/GetInitialCompanies/{self._encode(payload)}"
        response = httpx.get(url, timeout=self.timeout, headers={"User-Agent": "GammaLevelsSwing/0.3"})
        response.raise_for_status()
        for row in response.json().get("results", []):
            if str(row.get("issuingCompany") or "").upper() == asset_root.upper():
                return str(row.get("tradingName") or "").upper().replace(" ", "").replace("-", "").replace("_", "").replace("/", "")
        raise ValueError(f"Companhia {asset_root} não encontrada na B3")

    def _fetch(self, method: str, asset_root: str) -> list[dict[str, Any]]:
        trading_name = self._trading_name(asset_root)
        rows: list[dict[str, Any]] = []
        page_number, total_pages = 1, 1
        while page_number <= total_pages:
            token = self._encode(
                {"language": "pt", "pageNumber": page_number, "pageSize": 100, "tradingName": trading_name}
            )
            url = f"{B3_LISTED_PROXY}/{method}/{token}"
            response = httpx.get(url, timeout=self.timeout, headers={"User-Agent": "GammaLevelsSwing/0.3"})
            response.raise_for_status()
            payload = response.json()
            current = payload if isinstance(payload, list) else payload.get("results") or payload.get("result") or payload.get("data") or []
            rows.extend(current)
            page = payload.get("page") or {} if isinstance(payload, dict) else {}
            total_pages = int(page.get("totalPages") or 1)
            page_number += 1
        return rows

    def load(self, database: Database, ticker: str, asset_root: str) -> int:
        events: list[dict[str, Any]] = []
        for method, kind in (
            ("GetListedCashDividends", "CASH"),
            ("GetListedStockDividends", "STOCK"),
        ):
            try:
                rows = self._fetch(method, asset_root)
            except (httpx.HTTPError, ValueError):
                continue
            for row in rows:
                stock_type = str(row.get("typeStock") or "").upper()
                if stock_type and not self._matches_ticker_class(ticker, stock_type):
                    continue
                ex_date = self._event_ex_date(database, row)
                if not ex_date:
                    continue
                cash = _number(
                    row.get("valueCash") or row.get("cashValue") or row.get("value")
                ) if kind == "CASH" else 0.0
                quoted = max(_number(row.get("quotedPerShares"), 1.0), 1.0)
                cash /= quoted
                factor = _number(
                    row.get("factor") or row.get("ratio") or row.get("percentage"), 1.0
                ) if kind == "STOCK" else 1.0
                if kind == "STOCK" and factor > 10:
                    factor = 1.0 + factor / 100.0
                events.append(
                    {
                        "ticker": ticker.upper(), "ex_date": ex_date,
                        "action_type": f"{kind}:{row.get('corporateAction') or stock_type or 'EVENT'}",
                        "cash_amount": cash, "quantity_factor": max(factor, 0.01),
                        "source": "B3 Companhias Listadas", "payload": row,
                    }
                )
        return self.store(database, events)

    @staticmethod
    def _matches_ticker_class(ticker: str, stock_type: str) -> bool:
        suffix = ticker[-1:] if ticker else ""
        if suffix == "3":
            return stock_type.startswith("ON")
        if suffix in {"4", "5", "6", "7", "8"}:
            return stock_type.startswith("PN")
        return True

    @staticmethod
    def _event_ex_date(database: Database, row: dict[str, Any]) -> date | None:
        direct = _date(row.get("exDate") or row.get("dateEx") or row.get("dateExRight"))
        if direct:
            return direct
        prior = _date(
            row.get("lastDatePrior") or row.get("lastDatePriorEx")
            or row.get("dateClosingPricePriorExDate")
        )
        if not prior:
            return None
        for loaded in database.loaded_dates():
            if loaded > prior:
                if (loaded - prior).days <= 7:
                    return loaded
                break
        current = prior + timedelta(days=1)
        while current.weekday() >= 5:
            current += timedelta(days=1)
        return current

    @staticmethod
    def store(database: Database, events: Iterable[dict[str, Any]]) -> int:
        rows = [
            (
                event["ticker"], event["ex_date"].isoformat() if isinstance(event["ex_date"], date) else event["ex_date"],
                event["action_type"], float(event.get("cash_amount") or 0),
                float(event.get("quantity_factor") or 1), event.get("source", "IMPORT"),
                json_dumps(event.get("payload", {})),
            )
            for event in events
        ]
        with database.connect() as connection:
            connection.executemany(
                """INSERT OR IGNORE INTO corporate_actions
                (ticker,ex_date,action_type,cash_amount,quantity_factor,source,payload_json)
                VALUES (?,?,?,?,?,?,?)""",
                rows,
            )
        return len(rows)

    @classmethod
    def import_csv(cls, database: Database, ticker: str, content: str) -> int:
        events = []
        for row in csv.DictReader(io.StringIO(content)):
            ex_date = _date(row.get("ex_date") or row.get("data_ex"))
            if not ex_date:
                continue
            events.append(
                {
                    "ticker": ticker.upper(), "ex_date": ex_date,
                    "action_type": row.get("action_type") or row.get("tipo") or "CASH",
                    "cash_amount": _number(row.get("cash_amount") or row.get("valor")),
                    "quantity_factor": _number(row.get("quantity_factor") or row.get("fator"), 1.0),
                    "source": "CSV auditável", "payload": row,
                }
            )
        return cls.store(database, events)


def rate_on(database: Database, trade_date: date, fallback: float = 0.15) -> float:
    with database.connect() as connection:
        row = connection.execute(
            """SELECT annual_rate FROM interest_rates WHERE trade_date<=?
            ORDER BY trade_date DESC LIMIT 1""",
            (trade_date.isoformat(),),
        ).fetchone()
    return float(row["annual_rate"]) if row else fallback
