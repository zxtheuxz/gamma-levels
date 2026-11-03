from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ALIASES = {
    "datareferencia": "report_date",
    "reportdate": "report_date",
    "codigoinstrumento": "ticker",
    "tickersymbol": "ticker",
    "acaoatualizacao": "update_action",
    "updateaction": "update_action",
    "preconegocio": "price",
    "grosstradeamount": "price",
    "quantidadenegociada": "quantity",
    "tradequantity": "quantity",
    "horafechamento": "entry_time",
    "entrytime": "entry_time",
    "codigoidentificadornegocio": "trade_id",
    "tradeidentification": "trade_id",
    "tiposessaopregao": "session",
    "tradingsessionidentification": "session",
    "datanegocio": "trade_date",
    "tradedate": "trade_date",
    "codigoparticipantecomprador": "buyer_participant",
    "buyerparticipantcode": "buyer_participant",
    "codigoparticipantevendedor": "seller_participant",
    "sellerparticipantcode": "seller_participant",
}


def _key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]", "", text).lower()


def normalize_trade_columns(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = {column: ALIASES.get(_key(column), _key(column)) for column in frame.columns}
    out = frame.rename(columns=renamed).copy()
    required = {"ticker", "update_action", "price", "quantity", "entry_time", "trade_id", "trade_date"}
    missing = sorted(required - set(out.columns))
    if missing:
        raise ValueError(f"Arquivo negócio a negócio sem colunas: {', '.join(missing)}")
    for optional in ("buyer_participant", "seller_participant", "session"):
        if optional not in out:
            out[optional] = None
    return out


def read_trade_file(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path)
    else:
        try:
            frame = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
        except UnicodeDecodeError:
            frame = pd.read_csv(path, sep=None, engine="python", encoding="latin-1")
    return normalize_trade_columns(frame)


def apply_trade_updates(frame: pd.DataFrame) -> pd.DataFrame:
    """Aplica registros new/delete do arquivo público antes do footprint."""
    out = normalize_trade_columns(frame)
    out["update_action"] = pd.to_numeric(out["update_action"], errors="coerce").fillna(0).astype(int)
    out["trade_id"] = out["trade_id"].astype(str)
    active: dict[str, dict[str, Any]] = {}
    for item in out.to_dict("records"):
        trade_id = str(item["trade_id"])
        if int(item["update_action"]) == 2:
            active.pop(trade_id, None)
        else:
            active[trade_id] = item
    return pd.DataFrame(active.values()) if active else out.iloc[0:0].copy()


def estimate_aggressor(frame: pd.DataFrame) -> pd.DataFrame:
    """Tick rule: +1 comprador, -1 vendedor e 0 desconhecido.

    O layout público não contém o agressor. A classificação é deliberadamente
    chamada de estimativa e nunca deve ser exibida como fluxo observado.
    """
    out = apply_trade_updates(frame)
    if out.empty:
        out["aggressor_estimate"] = pd.Series(dtype=int)
        return out
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce")
    out = out.dropna(subset=["price", "quantity"])
    out = out[out["quantity"] > 0].copy()
    out["entry_time"] = out["entry_time"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(9)
    out = out.sort_values(["trade_date", "ticker", "entry_time", "trade_id"]).reset_index(drop=True)
    sides = np.zeros(len(out), dtype=int)
    for _, indexes in out.groupby(["trade_date", "ticker"], sort=False).groups.items():
        previous_price: float | None = None
        previous_side = 0
        for index in indexes:
            price = float(out.at[index, "price"])
            if previous_price is None:
                side = 0
            elif price > previous_price:
                side = 1
            elif price < previous_price:
                side = -1
            else:
                side = previous_side
            sides[index] = side
            previous_price = price
            if side:
                previous_side = side
    out["aggressor_estimate"] = sides
    return out


@dataclass(slots=True)
class FootprintResult:
    bins: pd.DataFrame
    summary: dict[str, Any]


def build_footprint(frame: pd.DataFrame, *, ticker: str, bin_points: int = 25) -> FootprintResult:
    if bin_points <= 0 or bin_points % 5:
        raise ValueError("bin_points deve ser múltiplo de 5")
    trades = estimate_aggressor(frame)
    trades = trades[trades["ticker"].astype(str).str.upper().eq(ticker.upper())].copy()
    if trades.empty:
        return FootprintResult(pd.DataFrame(), {"ticker": ticker, "status": "SEM_NEGOCIOS"})
    trades["price_bin"] = (trades["price"] / bin_points).round() * bin_points
    trades["buy_volume_est"] = trades["quantity"].where(trades["aggressor_estimate"].eq(1), 0.0)
    trades["sell_volume_est"] = trades["quantity"].where(trades["aggressor_estimate"].eq(-1), 0.0)
    grouped = trades.groupby("price_bin", as_index=False).agg(
        volume=("quantity", "sum"),
        trades=("trade_id", "count"),
        buy_volume_est=("buy_volume_est", "sum"),
        sell_volume_est=("sell_volume_est", "sum"),
        buyer_participants=("buyer_participant", lambda values: int(pd.Series(values).dropna().nunique())),
        seller_participants=("seller_participant", lambda values: int(pd.Series(values).dropna().nunique())),
    )
    grouped["delta_est"] = grouped["buy_volume_est"] - grouped["sell_volume_est"]
    grouped["delta_share"] = grouped["delta_est"] / grouped["volume"].replace(0, np.nan)
    grouped = grouped.sort_values("price_bin").reset_index(drop=True)
    total = float(grouped["volume"].sum())
    poc = float(grouped.loc[grouped["volume"].idxmax(), "price_bin"])
    ordered = grouped.sort_values("volume", ascending=False)
    ordered["cum_share"] = ordered["volume"].cumsum() / total
    value_area = ordered[ordered["cum_share"].shift(fill_value=0) < 0.70]
    value_area = pd.concat([value_area, ordered[ordered["cum_share"] >= 0.70].head(1)]).drop_duplicates("price_bin")
    trade_date = str(trades["trade_date"].iloc[0])
    grouped.insert(0, "ticker", ticker.upper())
    grouped.insert(0, "trade_date", trade_date)
    unknown = float(trades.loc[trades["aggressor_estimate"].eq(0), "quantity"].sum())
    summary = {
        "trade_date": trade_date,
        "ticker": ticker.upper(),
        "status": "ESTIMATED",
        "bin_points": bin_points,
        "volume": total,
        "trades": int(len(trades)),
        "poc": poc,
        "value_area_low": float(value_area["price_bin"].min()),
        "value_area_high": float(value_area["price_bin"].max()),
        "delta_est": float(grouped["delta_est"].sum()),
        "unknown_volume": unknown,
        "method": "tick_rule; agressor não fornecido pela B3",
    }
    return FootprintResult(grouped, summary)
