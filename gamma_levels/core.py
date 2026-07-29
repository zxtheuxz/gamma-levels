from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


_ALIASES = {
    "type": "option_type",
    "tipo": "option_type",
    "optiontype": "option_type",
    "right": "option_type",
    "cp": "option_type",
    "exercise_price": "strike",
    "preco_exercicio": "strike",
    "preco_de_exercicio": "strike",
    "k": "strike",
    "expiry": "expiration",
    "expiration_date": "expiration",
    "data_vencimento": "expiration",
    "vencimento": "expiration",
    "oi": "open_interest",
    "openinterest": "open_interest",
    "contratos_abertos": "open_interest",
    "interesse_aberto": "open_interest",
    "vol": "volume",
    "quantidade_negociada": "volume",
    "iv": "implied_volatility",
    "impliedvolatility": "implied_volatility",
    "volatilidade_implicita": "implied_volatility",
    "volatilidade": "implied_volatility",
    "underlying": "underlying_price",
    "underlyingprice": "underlying_price",
    "spot": "underlying_price",
    "preco_ativo": "underlying_price",
    "preco_do_ativo": "underlying_price",
    "contract_multiplier": "multiplier",
    "multiplicador": "multiplier",
    "multiplicador_do_contrato": "multiplier",
    "option_price": "option_price",
    "preco_opcao": "option_price",
    "preco_da_opcao": "option_price",
    "last": "option_price",
    "close": "option_price",
    "interest_rate": "interest_rate",
    "risk_free_rate": "interest_rate",
    "taxa_juros": "interest_rate",
    "taxa_de_juros": "interest_rate",
    "dividend_yield": "dividend_yield",
    "dividend_rate": "dividend_yield",
    "taxa_dividendos": "dividend_yield",
    "previous_oi": "previous_open_interest",
    "oi_anterior": "previous_open_interest",
    "open_interest_anterior": "previous_open_interest",
}

_NUMERIC_COLUMNS = {
    "strike",
    "open_interest",
    "previous_open_interest",
    "volume",
    "delta",
    "gamma",
    "vega",
    "vanna",
    "charm",
    "implied_volatility",
    "underlying_price",
    "multiplier",
    "option_price",
    "interest_rate",
    "dividend_yield",
}


@dataclass(slots=True)
class AnalysisConfig:
    spot: float | None = None
    valuation_date: date | str | None = None
    interest_rate: float = 0.0
    dividend_yield: float = 0.0
    multiplier: float = 100.0
    sign_convention: str = "call_positive_put_negative"
    use_vendor_greeks: bool = True
    vendor_vega_vanna_per_1pct: bool = False
    vendor_charm_per_day: bool = False
    iv_in_percent: bool | None = None
    gamma_percentile: float = 0.90
    distance_decay: float = 10.0
    expiry_decay: float = 2.0
    cluster_gap_multiplier: float = 1.5
    min_oi_for_volume_ratio: float = 10.0
    trading_days: int = 252
    same_day_hours: float | None = None
    flip_grid_points: int = 501
    flip_low: float | None = None
    flip_high: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.valuation_date, str):
            self.valuation_date = pd.Timestamp(self.valuation_date).date()
        if self.valuation_date is None:
            self.valuation_date = date.today()
        if not 0 < self.gamma_percentile < 1:
            raise ValueError("gamma_percentile deve estar entre 0 e 1")
        if self.sign_convention not in {
            "call_positive_put_negative",
            "all_positive",
            "all_negative",
        }:
            raise ValueError("Convenção de sinal desconhecida")
        if self.multiplier <= 0 or self.trading_days <= 0:
            raise ValueError("multiplier e trading_days devem ser positivos")
        if self.same_day_hours is not None and not 0 < self.same_day_hours <= 24:
            raise ValueError("same_day_hours deve estar entre 0 (exclusivo) e 24")


@dataclass(slots=True)
class AnalysisResult:
    summary: dict[str, Any]
    by_strike: pd.DataFrame
    by_expiration: pd.DataFrame
    options: pd.DataFrame


def _clean_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return _ALIASES.get(text, text)


def _localized_number(value: Any) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return math.nan
    if isinstance(value, (int, float, np.number)):
        return float(value)
    text = str(value).strip().replace("%", "").replace("R$", "").replace(" ", "")
    if not text:
        return math.nan
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return math.nan


def load_chain(
    path: str | Path,
    *,
    sep: str | None = None,
    decimal: str = ".",
    thousands: str | None = None,
    encoding: str = "utf-8-sig",
) -> pd.DataFrame:
    """Lê CSV/TSV ou Excel. Em CSV, o separador pode ser detectado automaticamente."""
    path = Path(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        frame = pd.read_excel(path, decimal=decimal, thousands=thousands)
    else:
        effective_sep = sep if sep is not None else None
        frame = pd.read_csv(
            path,
            sep=effective_sep,
            engine="python" if effective_sep is None else "c",
            decimal=decimal,
            thousands=thousands,
            encoding=encoding,
        )
    frame.columns = [_clean_name(c) for c in frame.columns]
    if frame.columns.duplicated().any():
        duplicates = frame.columns[frame.columns.duplicated()].tolist()
        raise ValueError(f"Colunas duplicadas após normalização: {duplicates}")
    return frame


def _normal_cdf(x: np.ndarray) -> np.ndarray:
    # math.erf evita uma dependência obrigatória de scipy.
    return np.fromiter(
        (0.5 * (1.0 + math.erf(float(v) / math.sqrt(2.0))) for v in x),
        dtype=float,
        count=x.size,
    ).reshape(x.shape)


def _normal_pdf(x: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def black_scholes_greeks(
    spot: float | np.ndarray,
    strike: np.ndarray,
    time_to_expiry: np.ndarray,
    volatility: np.ndarray,
    option_type: np.ndarray,
    interest_rate: np.ndarray,
    dividend_yield: np.ndarray,
) -> dict[str, np.ndarray]:
    """Gregas BSM europeias; vega/vanna são por 1,00 de volatilidade e charm por ano."""
    strike = np.asarray(strike, dtype=float)
    t = np.asarray(time_to_expiry, dtype=float)
    vol = np.asarray(volatility, dtype=float)
    types = np.asarray(option_type)
    r = np.asarray(interest_rate, dtype=float)
    q = np.asarray(dividend_yield, dtype=float)
    s = np.broadcast_to(np.asarray(spot, dtype=float), strike.shape)

    valid = (s > 0) & (strike > 0) & (t > 0) & (vol > 0)
    safe_t = np.where(valid, t, 1.0)
    safe_vol = np.where(valid, vol, 1.0)
    sqrt_t = np.sqrt(safe_t)
    d1 = (
        np.log(np.where(valid, s / strike, 1.0))
        + (r - q + 0.5 * safe_vol**2) * safe_t
    ) / (safe_vol * sqrt_t)
    d2 = d1 - safe_vol * sqrt_t
    pdf = _normal_pdf(d1)
    cdf_d1 = _normal_cdf(d1)
    discount_q = np.exp(-q * safe_t)
    is_call = np.char.startswith(np.char.lower(types.astype(str)), "c")

    delta_call = discount_q * cdf_d1
    delta_put = discount_q * (cdf_d1 - 1.0)
    delta = np.where(is_call, delta_call, delta_put)
    gamma = discount_q * pdf / (s * safe_vol * sqrt_t)
    vega = s * discount_q * pdf * sqrt_t
    vanna = -discount_q * pdf * d2 / safe_vol

    common = discount_q * pdf * (
        2.0 * (r - q) * safe_t - d2 * safe_vol * sqrt_t
    ) / (2.0 * safe_t * safe_vol * sqrt_t)
    charm_call = q * discount_q * cdf_d1 - common
    charm_put = -q * discount_q * _normal_cdf(-d1) - common
    charm = np.where(is_call, charm_call, charm_put)

    intrinsic_delta = np.where(
        is_call,
        np.where(s > strike, 1.0, np.where(s < strike, 0.0, 0.5)),
        np.where(s < strike, -1.0, np.where(s > strike, 0.0, -0.5)),
    )
    return {
        "delta": np.where(valid, delta, intrinsic_delta),
        "gamma": np.where(valid, gamma, 0.0),
        "vega": np.where(valid, vega, 0.0),
        "vanna": np.where(valid, vanna, 0.0),
        "charm": np.where(valid, charm, 0.0),
    }


def _black_scholes_gamma(
    spot: float,
    strike: np.ndarray,
    time_to_expiry: np.ndarray,
    volatility: np.ndarray,
    interest_rate: np.ndarray,
    dividend_yield: np.ndarray,
) -> np.ndarray:
    """Caminho vetorizado usado na grade do Gamma Flip."""
    valid = (spot > 0) & (strike > 0) & (time_to_expiry > 0) & (volatility > 0)
    safe_t = np.where(valid, time_to_expiry, 1.0)
    safe_vol = np.where(valid, volatility, 1.0)
    sqrt_t = np.sqrt(safe_t)
    d1 = (
        np.log(np.where(valid, spot / strike, 1.0))
        + (interest_rate - dividend_yield + 0.5 * safe_vol**2) * safe_t
    ) / (safe_vol * sqrt_t)
    gamma = np.exp(-dividend_yield * safe_t) * _normal_pdf(d1) / (spot * safe_vol * sqrt_t)
    return np.where(valid, gamma, 0.0)


def _prepare_chain(raw: pd.DataFrame, config: AnalysisConfig) -> tuple[pd.DataFrame, float]:
    df = raw.copy()
    df.columns = [_clean_name(c) for c in df.columns]
    required = {"option_type", "strike", "expiration", "open_interest"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes: {', '.join(missing)}")

    for column in _NUMERIC_COLUMNS & set(df.columns):
        if not pd.api.types.is_numeric_dtype(df[column]):
            df[column] = df[column].map(_localized_number)
        else:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    type_map = {
        "c": "call", "call": "call", "compra": "call", "1": "call",
        "p": "put", "put": "put", "venda": "put", "-1": "put",
    }
    df["option_type"] = df["option_type"].astype(str).str.strip().str.lower().map(type_map)
    if df["option_type"].isna().any():
        bad = raw.loc[df["option_type"].isna(), "option_type"].astype(str).unique().tolist()
        raise ValueError(f"Tipos de opção não reconhecidos: {bad}")

    expiration_text = df["expiration"].astype(str).str.strip()
    parsed_expiration = pd.to_datetime(expiration_text, errors="coerce", format="%Y-%m-%d")
    unresolved = parsed_expiration.isna()
    if unresolved.any():
        parsed_expiration.loc[unresolved] = pd.to_datetime(
            expiration_text.loc[unresolved], errors="coerce", dayfirst=True
        )
    df["expiration"] = parsed_expiration.dt.normalize()
    if df["expiration"].isna().any():
        raise ValueError("Há vencimentos inválidos")
    if df["strike"].isna().any() or (df["strike"] <= 0).any():
        raise ValueError("Todos os strikes devem ser numéricos e positivos")
    if df["open_interest"].isna().any() or (df["open_interest"] < 0).any():
        raise ValueError("Open interest deve ser numérico e não negativo")

    if config.spot is not None:
        spot = float(config.spot)
    elif "underlying_price" in df and df["underlying_price"].notna().any():
        spot = float(df["underlying_price"].dropna().median())
    else:
        raise ValueError("Informe spot na configuração ou a coluna underlying_price")
    if spot <= 0:
        raise ValueError("O preço do ativo deve ser positivo")

    defaults = {
        "volume": 0.0,
        "previous_open_interest": np.nan,
        "multiplier": config.multiplier,
        "interest_rate": config.interest_rate,
        "dividend_yield": config.dividend_yield,
        "option_price": np.nan,
        "implied_volatility": np.nan,
    }
    for column, default in defaults.items():
        if column not in df:
            df[column] = default
        else:
            df[column] = df[column].fillna(default) if not pd.isna(default) else df[column]
    if (df["multiplier"] <= 0).any():
        raise ValueError("Multiplicadores devem ser positivos")

    valuation = pd.Timestamp(config.valuation_date)
    df["days_to_expiry"] = (df["expiration"] - valuation).dt.total_seconds() / 86400.0
    if (df["days_to_expiry"] < 0).any():
        expired = df.loc[df["days_to_expiry"] < 0, "expiration"].dt.date.unique().tolist()
        raise ValueError(f"A cadeia contém vencimentos expirados: {expired}")
    same_day = df["days_to_expiry"] == 0
    if same_day.any() and config.same_day_hours is None:
        raise ValueError(
            "Opções 0DTE exigem same_day_hours para recalcular gregas e Gamma Flip "
            "sem assumir que o vencimento já ocorreu"
        )
    df["time_to_expiry"] = np.maximum(df["days_to_expiry"], 0.0) / 365.0
    if config.same_day_hours is not None:
        df.loc[same_day, "time_to_expiry"] = config.same_day_hours / (24.0 * 365.0)

    iv = df["implied_volatility"].astype(float)
    finite_iv = iv[np.isfinite(iv) & (iv > 0)]
    should_scale_iv = config.iv_in_percent is True or (
        config.iv_in_percent is None and not finite_iv.empty and finite_iv.median() > 3.0
    )
    if should_scale_iv:
        df["implied_volatility"] = iv / 100.0
    for rate_col in ("interest_rate", "dividend_yield"):
        finite = df[rate_col][np.isfinite(df[rate_col])]
        if not finite.empty and finite.abs().median() > 1.0:
            df[rate_col] = df[rate_col] / 100.0

    greek_names = ["delta", "gamma", "vega", "vanna", "charm"]
    if config.use_vendor_greeks:
        greek_missing = pd.Series(False, index=df.index)
        for greek in greek_names:
            greek_missing |= greek not in df or pd.to_numeric(df[greek], errors="coerce").isna()
    else:
        greek_missing = pd.Series(True, index=df.index)
    invalid_iv = df["implied_volatility"].isna() | (df["implied_volatility"] <= 0)
    cannot_calculate = greek_missing & invalid_iv & (df["time_to_expiry"] > 0)
    if cannot_calculate.any():
        bad = df.loc[cannot_calculate, ["option_type", "strike", "expiration"]]
        raise ValueError(
            "Gregas ausentes e impossíveis de calcular. Forneça implied_volatility válida. "
            f"Primeiras linhas: {bad.head(3).to_dict('records')}"
        )

    vendor_masks = {
        greek: (pd.to_numeric(df[greek], errors="coerce").notna() if greek in df else pd.Series(False, index=df.index))
        for greek in greek_names
    }
    calc = black_scholes_greeks(
        spot,
        df["strike"].to_numpy(),
        df["time_to_expiry"].to_numpy(),
        df["implied_volatility"].to_numpy(),
        df["option_type"].to_numpy(),
        df["interest_rate"].to_numpy(),
        df["dividend_yield"].to_numpy(),
    )
    for greek, values in calc.items():
        if greek not in df or not config.use_vendor_greeks:
            df[greek] = values
        else:
            df[greek] = pd.to_numeric(df[greek], errors="coerce").fillna(pd.Series(values, index=df.index))

    if config.use_vendor_greeks and config.vendor_vega_vanna_per_1pct:
        df.loc[vendor_masks["vega"], "vega"] *= 100.0
        df.loc[vendor_masks["vanna"], "vanna"] *= 100.0
    if config.use_vendor_greeks and config.vendor_charm_per_day:
        df.loc[vendor_masks["charm"], "charm"] *= config.trading_days

    if df[greek_names].isna().any().any():
        bad = df.loc[df[greek_names].isna().any(axis=1), ["option_type", "strike", "expiration"]]
        raise ValueError(
            "Gregas ausentes e impossíveis de calcular. Forneça implied_volatility válida. "
            f"Primeiras linhas: {bad.head(3).to_dict('records')}"
        )
    if (df["gamma"] < 0).any():
        raise ValueError("Gamma da opção deve ser não negativo; o sinal de exposição é aplicado à parte")

    df["underlying_price"] = spot
    return df.sort_values(["expiration", "strike", "option_type"]).reset_index(drop=True), spot


def _gex_sign(types: pd.Series, convention: str) -> np.ndarray:
    if convention == "call_positive_put_negative":
        return np.where(types.eq("call"), 1.0, -1.0)
    if convention == "all_positive":
        return np.ones(len(types))
    return -np.ones(len(types))


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    mask = values.notna() & weights.notna() & (weights >= 0)
    if not mask.any():
        return math.nan
    weight_sum = float(weights[mask].sum())
    return float(np.average(values[mask], weights=weights[mask])) if weight_sum > 0 else float(values[mask].mean())


def _safe_argmax(frame: pd.DataFrame, column: str) -> float | None:
    valid = frame.dropna(subset=[column])
    return None if valid.empty else float(valid.loc[valid[column].idxmax(), "strike"])


def _safe_argmin(frame: pd.DataFrame, column: str) -> float | None:
    valid = frame.dropna(subset=[column])
    return None if valid.empty else float(valid.loc[valid[column].idxmin(), "strike"])


def _share(series: pd.Series) -> pd.Series:
    values = series.abs().fillna(0.0)
    total = float(values.sum())
    return values / total if total > 0 else pd.Series(0.0, index=series.index)


def _zscore(series: pd.Series) -> pd.Series:
    values = series.fillna(0.0).astype(float)
    std = float(values.std(ddof=0))
    return (values - float(values.mean())) / std if std > 0 else pd.Series(0.0, index=series.index)


def _aggregate_by_strike(df: pd.DataFrame, spot: float, config: AnalysisConfig) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for strike, group in df.groupby("strike", sort=True):
        call = group[group["option_type"] == "call"]
        put = group[group["option_type"] == "put"]
        row: dict[str, float] = {"strike": float(strike)}
        for label, side in (("call", call), ("put", put)):
            row[f"oi_{label}"] = float(side["open_interest"].sum())
            row[f"volume_{label}"] = float(side["volume"].sum())
            row[f"delta_oi_{label}"] = float(side["oi_change"].sum(min_count=1)) if not side.empty else math.nan
            row[f"delta_{label}"] = _weighted_mean(side["delta"], side["open_interest"])
            row[f"gamma_{label}"] = _weighted_mean(side["gamma"], side["open_interest"])
            for metric in ("gex", "dex", "vanna_exposure", "vanna_exposure_1pct", "charm_exposure", "charm_exposure_day", "gex_expiry_adjusted", "gex_distance_adjusted"):
                row[f"{metric}_{label}"] = float(side[metric].sum())
        rows.append(row)
    out = pd.DataFrame(rows).sort_values("strike").reset_index(drop=True)
    out["oi_total"] = out["oi_call"] + out["oi_put"]
    out["oi_net"] = out["oi_call"] - out["oi_put"]
    out["volume_total"] = out["volume_call"] + out["volume_put"]
    for metric in ("gex", "dex", "vanna_exposure", "vanna_exposure_1pct", "charm_exposure", "charm_exposure_day", "gex_expiry_adjusted", "gex_distance_adjusted"):
        out[f"{metric}_net"] = out[f"{metric}_call"] + out[f"{metric}_put"]

    out["distance_percent"] = (out["strike"] - spot) / spot * 100.0
    out["distance_weight"] = np.exp(-config.distance_decay * (out["strike"] - spot).abs() / spot)
    out["magnet_score"] = out["gex_net"].abs() / (1.0 + (out["strike"] - spot).abs() / spot)
    out["call_wall_score"] = out["gex_call"].abs() * (
        1.0 + out["volume_call"] / out["oi_call"].replace(0, np.nan)
    ).fillna(1.0)
    out["put_wall_score"] = out["gex_put"].abs() * (
        1.0 + out["volume_put"] / out["oi_put"].replace(0, np.nan)
    ).fillna(1.0)
    out.loc[out["oi_call"] <= 0, "call_wall_score"] = np.nan
    out.loc[out["oi_put"] <= 0, "put_wall_score"] = np.nan
    out["call_resistance_score"] = out["call_wall_score"] * out["distance_weight"]
    out["put_support_score"] = out["put_wall_score"] * out["distance_weight"]
    out.loc[out["strike"] <= spot, "call_resistance_score"] = np.nan
    out.loc[out["strike"] >= spot, "put_support_score"] = np.nan

    total_gamma_abs = out["gex_net"].abs()
    threshold = float(total_gamma_abs.quantile(config.gamma_percentile))
    out["is_gamma_level"] = (total_gamma_abs >= threshold) & (total_gamma_abs > 0)
    out["gamma_level_type"] = np.select(
        [out["is_gamma_level"] & (out["gex_net"] > 0), out["is_gamma_level"] & (out["gex_net"] < 0)],
        ["positivo", "negativo"],
        default="neutro",
    )

    # Métricas compostas usam shares para não somar grandezas de unidades diferentes.
    put_parts = pd.concat(
        [_share(out["gex_put"]), _share(out["oi_put"]), _share(out["dex_put"]), _share(out["delta_oi_put"])],
        axis=1,
    )
    call_parts = pd.concat(
        [_share(out["gex_call"]), _share(out["oi_call"]), _share(out["dex_call"]), _share(out["delta_oi_call"])],
        axis=1,
    )
    out["support_composite"] = put_parts.mean(axis=1) * out["distance_weight"]
    out["resistance_composite"] = call_parts.mean(axis=1) * out["distance_weight"]
    out.loc[out["strike"] >= spot, "support_composite"] = np.nan
    out.loc[out["strike"] <= spot, "resistance_composite"] = np.nan
    out["z_gex"] = _zscore(out["gex_net"])
    out["z_dex"] = _zscore(out["dex_net"])
    out["z_vanna"] = _zscore(out["vanna_exposure_net"])
    out["z_charm"] = _zscore(out["charm_exposure_net"])
    out["dealer_exposure_score"] = out[["z_gex", "z_dex", "z_vanna", "z_charm"]].mean(axis=1)

    out["voi_ratio"] = out["volume_total"] / out["oi_total"].replace(0, np.nan)
    out.loc[out["oi_total"] < config.min_oi_for_volume_ratio, "voi_ratio"] = np.nan
    _assign_clusters(out, config)
    spacing = float(out["strike"].sort_values().diff().dropna().median()) if len(out) > 1 else 0.0
    half_width = spacing / 2.0 if np.isfinite(spacing) else 0.0
    out["zone_low"] = out["strike"] - half_width
    out["zone_high"] = out["strike"] + half_width
    return out


def _assign_clusters(out: pd.DataFrame, config: AnalysisConfig) -> None:
    out["gamma_cluster_id"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    relevant = out.index[out["is_gamma_level"]].tolist()
    if not relevant:
        return
    spacings = out["strike"].diff().dropna()
    median_spacing = float(spacings.median()) if not spacings.empty else math.inf
    max_gap = config.cluster_gap_multiplier * median_spacing
    cluster = 1
    previous: int | None = None
    for index in relevant:
        if previous is not None and float(out.at[index, "strike"] - out.at[previous, "strike"]) > max_gap:
            cluster += 1
        out.at[index, "gamma_cluster_id"] = cluster
        previous = index


def _gamma_flips(df: pd.DataFrame, spot: float, config: AnalysisConfig) -> tuple[list[float], float | None]:
    valid = df[(df["implied_volatility"] > 0) & (df["time_to_expiry"] > 0)]
    if valid.empty:
        return [], None
    low = config.flip_low or min(spot * 0.50, float(valid["strike"].min()) * 0.80)
    high = config.flip_high or max(spot * 1.50, float(valid["strike"].max()) * 1.20)
    if low <= 0 or high <= low:
        raise ValueError("Intervalo inválido para o cálculo do Gamma Flip")
    grid = np.linspace(low, high, config.flip_grid_points)
    signs = _gex_sign(valid["option_type"], config.sign_convention)
    exposures = np.empty(grid.size)
    for j, simulated_spot in enumerate(grid):
        gamma = _black_scholes_gamma(
            simulated_spot,
            valid["strike"].to_numpy(),
            valid["time_to_expiry"].to_numpy(),
            valid["implied_volatility"].to_numpy(),
            valid["interest_rate"].to_numpy(),
            valid["dividend_yield"].to_numpy(),
        )
        exposures[j] = float(np.sum(
            gamma * valid["open_interest"].to_numpy() * valid["multiplier"].to_numpy()
            * simulated_spot**2 * 0.01 * signs
        ))
    flips: list[float] = []
    for j in range(grid.size - 1):
        y1, y2 = exposures[j], exposures[j + 1]
        if y1 == 0:
            flips.append(float(grid[j]))
        elif y1 * y2 < 0:
            root = grid[j] + (-y1 / (y2 - y1)) * (grid[j + 1] - grid[j])
            flips.append(float(root))
    unique = sorted({round(v, 10) for v in flips})
    nearest = min(unique, key=lambda v: abs(v - spot)) if unique else None
    return unique, nearest


def _max_pain(df: pd.DataFrame) -> float | None:
    if df.empty:
        return None
    strikes = np.sort(df["strike"].unique().astype(float))
    call = df[df["option_type"] == "call"]
    put = df[df["option_type"] == "put"]
    pains = []
    for settlement in strikes:
        call_pain = np.maximum(settlement - call["strike"].to_numpy(), 0.0) * call["open_interest"].to_numpy() * call["multiplier"].to_numpy()
        put_pain = np.maximum(put["strike"].to_numpy() - settlement, 0.0) * put["open_interest"].to_numpy() * put["multiplier"].to_numpy()
        pains.append(float(call_pain.sum() + put_pain.sum()))
    return float(strikes[int(np.argmin(pains))])


def _expected_move(df: pd.DataFrame, spot: float) -> dict[str, float | None]:
    if df.empty:
        return {"atm_strike": None, "atm_iv": None, "expected_move_iv": None, "expected_move_straddle": None}
    distances = (df["strike"] - spot).abs()
    atm_strike = float(df.loc[distances.idxmin(), "strike"])
    atm = df[df["strike"] == atm_strike]
    atm_iv = _weighted_mean(atm["implied_volatility"], atm["open_interest"])
    t = float(atm["time_to_expiry"].median())
    move_iv = spot * atm_iv * math.sqrt(t) if np.isfinite(atm_iv) and t > 0 else None
    prices = atm.dropna(subset=["option_price"])
    call_prices = prices.loc[prices["option_type"] == "call", "option_price"]
    put_prices = prices.loc[prices["option_type"] == "put", "option_price"]
    straddle = float(call_prices.median() + put_prices.median()) if not call_prices.empty and not put_prices.empty else None
    return {
        "atm_strike": atm_strike,
        "atm_iv": float(atm_iv) if np.isfinite(atm_iv) else None,
        "expected_move_iv": float(move_iv) if move_iv is not None else None,
        "expected_move_straddle": straddle,
    }


def _expiration_table(df: pd.DataFrame, spot: float, config: AnalysisConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for expiration, group in df.groupby("expiration", sort=True):
        flips, nearest = _gamma_flips(group, spot, config)
        expected = _expected_move(group, spot)
        gex_call = float(group.loc[group["option_type"] == "call", "gex"].sum())
        gex_put = float(group.loc[group["option_type"] == "put", "gex"].sum())
        rows.append({
            "expiration": pd.Timestamp(expiration).date().isoformat(),
            "days_to_expiry": float(group["days_to_expiry"].median()),
            "gex_total": gex_call + gex_put,
            "gex_call": gex_call,
            "gex_put": gex_put,
            "gamma_flip": nearest,
            "gamma_flips_all": ";".join(f"{v:.8g}" for v in flips),
            "max_pain": _max_pain(group),
            **expected,
        })
    return pd.DataFrame(rows)


def _cluster_summary(by_strike: pd.DataFrame) -> list[dict[str, float | int]]:
    clusters: list[dict[str, float | int]] = []
    valid = by_strike.dropna(subset=["gamma_cluster_id"])
    for cluster_id, group in valid.groupby("gamma_cluster_id"):
        weights = group["gex_net"].abs()
        center = float(np.average(group["strike"], weights=weights)) if weights.sum() > 0 else float(group["strike"].mean())
        clusters.append({
            "id": int(cluster_id),
            "low": float(group["zone_low"].min()),
            "high": float(group["zone_high"].max()),
            "center": center,
            "gex_net": float(group["gex_net"].sum()),
            "gex_abs": float(weights.sum()),
        })
    return clusters


def _top_levels(frame: pd.DataFrame, score: str, n: int = 2) -> list[float]:
    valid = frame.dropna(subset=[score]).sort_values(score, ascending=False).head(n)
    return [float(v) for v in valid["strike"]]


def analyze_chain(raw: pd.DataFrame, config: AnalysisConfig | None = None) -> AnalysisResult:
    """Executa a análise completa e retorna resumo, strikes, vencimentos e opções."""
    config = config or AnalysisConfig()
    df, spot = _prepare_chain(raw, config)
    signs = _gex_sign(df["option_type"], config.sign_convention)
    oi = df["open_interest"].to_numpy()
    multiplier = df["multiplier"].to_numpy()
    df["oi_change"] = df["open_interest"] - df["previous_open_interest"]
    df["gex_sign"] = signs
    df["gex"] = df["gamma"] * oi * multiplier * spot**2 * 0.01 * signs
    df["dex"] = df["delta"] * oi * multiplier * spot
    df["vanna_exposure"] = df["vanna"] * oi * multiplier
    df["vanna_exposure_1pct"] = df["vanna_exposure"] * 0.01
    df["charm_exposure"] = df["charm"] * oi * multiplier
    df["charm_exposure_day"] = df["charm_exposure"] / config.trading_days
    df["expiry_weight"] = np.exp(-config.expiry_decay * df["time_to_expiry"])
    df["distance_weight"] = np.exp(-config.distance_decay * (df["strike"] - spot).abs() / spot)
    df["gex_expiry_adjusted"] = df["gex"] * df["expiry_weight"]
    df["gex_distance_adjusted"] = df["gex"] * df["distance_weight"]

    by_strike = _aggregate_by_strike(df, spot, config)
    flips, nearest_flip = _gamma_flips(df, spot, config)
    by_expiration = _expiration_table(df, spot, config)
    future_expirations = by_expiration[by_expiration["days_to_expiry"] >= 0]
    reference_row = future_expirations.iloc[0] if not future_expirations.empty else by_expiration.iloc[0]
    move = reference_row.get("expected_move_iv")
    if pd.isna(move):
        move = None
    by_strike["distance_sigma"] = (by_strike["strike"] - spot) / move if move and move > 0 else np.nan

    call_total = float(by_strike["gex_call"].sum())
    put_total_abs = float(by_strike["gex_put"].abs().sum())
    denominator = abs(call_total) + put_total_abs
    gamma_imbalance = (abs(call_total) - put_total_abs) / denominator if denominator else None
    put_call_gamma_ratio = put_total_abs / abs(call_total) if call_total else None
    abs_gex = by_strike["gex_net"].abs()
    abs_total = float(abs_gex.sum())
    concentration_3 = float(abs_gex.nlargest(3).sum() / abs_total) if abs_total else None
    gamma_center = float(np.average(by_strike["strike"], weights=abs_gex)) if abs_total else None
    call_weights = by_strike["gex_call"].abs()
    put_weights = by_strike["gex_put"].abs()

    delta_change = by_strike[["delta_oi_call", "delta_oi_put"]].sum(axis=1, min_count=1)
    temp = by_strike.assign(delta_oi_total=delta_change)
    support_levels = _top_levels(by_strike, "support_composite")
    resistance_levels = _top_levels(by_strike, "resistance_composite")
    expected_iv = float(reference_row["expected_move_iv"]) if pd.notna(reference_row["expected_move_iv"]) else None
    expected_straddle = float(reference_row["expected_move_straddle"]) if pd.notna(reference_row["expected_move_straddle"]) else None

    summary: dict[str, Any] = {
        "valuation_date": config.valuation_date.isoformat(),
        "spot": spot,
        "sign_convention": config.sign_convention,
        "reference_expiration": str(reference_row["expiration"]),
        "options_count": int(len(df)),
        "strikes_count": int(len(by_strike)),
        "expirations_count": int(len(by_expiration)),
        "gex_total": float(by_strike["gex_net"].sum()),
        "gex_call": call_total,
        "gex_put": float(by_strike["gex_put"].sum()),
        "gamma_flip": nearest_flip,
        "gamma_flips_all": flips,
        "volatility_trigger": nearest_flip,
        "gamma_magnet": _safe_argmax(by_strike, "magnet_score"),
        "call_wall": _safe_argmax(by_strike[by_strike["oi_call"] > 0], "call_wall_score"),
        "put_wall": _safe_argmax(by_strike[by_strike["oi_put"] > 0], "put_wall_score"),
        "call_oi_wall": _safe_argmax(by_strike[by_strike["oi_call"] > 0], "oi_call"),
        "put_oi_wall": _safe_argmax(by_strike[by_strike["oi_put"] > 0], "oi_put"),
        "oi_total_wall": _safe_argmax(by_strike, "oi_total"),
        "call_resistance_level": _safe_argmax(by_strike, "call_resistance_score"),
        "put_support_level": _safe_argmax(by_strike, "put_support_score"),
        "call_delta_wall": _safe_argmax(by_strike[by_strike["oi_call"] > 0], "dex_call"),
        "put_delta_wall": _safe_argmax(by_strike[by_strike["oi_put"] > 0].assign(_abs=lambda x: x["dex_put"].abs()), "_abs"),
        "delta_wall": _safe_argmax(by_strike.assign(_abs=by_strike["dex_net"].abs()), "_abs"),
        "vanna_level": _safe_argmax(by_strike.assign(_abs=by_strike["vanna_exposure_net"].abs()), "_abs"),
        "charm_level": _safe_argmax(by_strike.assign(_abs=by_strike["charm_exposure_net"].abs()), "_abs"),
        "dealer_exposure_level": _safe_argmax(by_strike.assign(_abs=by_strike["dealer_exposure_score"].abs()), "_abs"),
        "volume_oi_level": _safe_argmax(by_strike, "voi_ratio"),
        "new_position_level": _safe_argmax(temp, "delta_oi_total") if df["previous_open_interest"].notna().any() else None,
        "unwind_level": _safe_argmin(temp, "delta_oi_total") if df["previous_open_interest"].notna().any() else None,
        "max_pain": float(reference_row["max_pain"]) if pd.notna(reference_row["max_pain"]) else None,
        "atm_strike": float(reference_row["atm_strike"]) if pd.notna(reference_row["atm_strike"]) else None,
        "atm_iv": float(reference_row["atm_iv"]) if pd.notna(reference_row["atm_iv"]) else None,
        "expected_move_iv": expected_iv,
        "expected_move_iv_lower": spot - expected_iv if expected_iv is not None else None,
        "expected_move_iv_upper": spot + expected_iv if expected_iv is not None else None,
        "expected_move_straddle": expected_straddle,
        "expected_move_straddle_lower": spot - expected_straddle if expected_straddle is not None else None,
        "expected_move_straddle_upper": spot + expected_straddle if expected_straddle is not None else None,
        "range_half_sigma": [spot - 0.5 * expected_iv, spot + 0.5 * expected_iv] if expected_iv is not None else None,
        "range_one_sigma": [spot - expected_iv, spot + expected_iv] if expected_iv is not None else None,
        "range_two_sigma": [spot - 2 * expected_iv, spot + 2 * expected_iv] if expected_iv is not None else None,
        "gamma_imbalance": gamma_imbalance,
        "put_call_gamma_ratio": put_call_gamma_ratio,
        "gamma_concentration_top3": concentration_3,
        "gamma_center": gamma_center,
        "call_gamma_center": float(np.average(by_strike["strike"], weights=call_weights)) if call_weights.sum() else None,
        "put_gamma_center": float(np.average(by_strike["strike"], weights=put_weights)) if put_weights.sum() else None,
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "gamma_clusters": _cluster_summary(by_strike),
    }
    return AnalysisResult(summary=summary, by_strike=by_strike, by_expiration=by_expiration, options=df)
