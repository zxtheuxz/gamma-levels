from datetime import date

import numpy as np
import pandas as pd
import pytest

from gamma_levels.core import AnalysisConfig, analyze_chain, black_scholes_greeks


def _chain() -> pd.DataFrame:
    rows = []
    for strike, call_oi, put_oi, call_gamma, put_gamma in [
        (90.0, 40, 200, 0.010, 0.012),
        (100.0, 300, 350, 0.020, 0.018),
        (110.0, 250, 60, 0.015, 0.011),
    ]:
        rows.extend([
            {
                "option_type": "call", "strike": strike, "expiration": "2026-08-21",
                "open_interest": call_oi, "volume": 20, "delta": 0.55,
                "gamma": call_gamma, "vega": 10.0, "vanna": -0.1, "charm": -0.2,
                "implied_volatility": 0.25, "underlying_price": 100.0, "multiplier": 100,
                "option_price": 3.0,
            },
            {
                "option_type": "put", "strike": strike, "expiration": "2026-08-21",
                "open_interest": put_oi, "volume": 15, "delta": -0.45,
                "gamma": put_gamma, "vega": 10.0, "vanna": 0.1, "charm": -0.2,
                "implied_volatility": 0.27, "underlying_price": 100.0, "multiplier": 100,
                "option_price": 2.5,
            },
        ])
    return pd.DataFrame(rows)


def test_gex_sign_and_aggregation() -> None:
    result = analyze_chain(_chain(), AnalysisConfig(valuation_date=date(2026, 7, 27)))
    at_100 = result.by_strike.set_index("strike").loc[100.0]
    assert at_100["gex_call"] == pytest.approx(60_000.0)
    assert at_100["gex_put"] == pytest.approx(-63_000.0)
    assert at_100["gex_net"] == pytest.approx(-3_000.0)
    assert result.summary["max_pain"] == 100.0
    assert result.summary["call_wall"] in {100.0, 110.0}
    assert result.summary["put_wall"] in {90.0, 100.0}


def test_black_scholes_put_call_gamma_and_delta() -> None:
    greeks = black_scholes_greeks(
        100.0,
        np.array([100.0, 100.0]),
        np.array([1.0, 1.0]),
        np.array([0.2, 0.2]),
        np.array(["call", "put"]),
        np.array([0.05, 0.05]),
        np.array([0.0, 0.0]),
    )
    assert greeks["gamma"][0] == pytest.approx(greeks["gamma"][1])
    assert greeks["delta"][0] == pytest.approx(0.63683, rel=1e-4)
    assert greeks["delta"][1] == pytest.approx(-0.36317, rel=1e-4)


def test_calculates_missing_greeks_from_iv() -> None:
    raw = _chain().drop(columns=["delta", "gamma", "vega", "vanna", "charm"])
    result = analyze_chain(
        raw,
        AnalysisConfig(valuation_date="2026-07-27", use_vendor_greeks=False),
    )
    assert result.options[["delta", "gamma", "vega", "vanna", "charm"]].notna().all().all()
    assert (result.options["gamma"] > 0).all()


def test_requires_iv_if_greeks_are_missing() -> None:
    raw = _chain().drop(columns=["delta", "gamma", "vega", "vanna", "charm", "implied_volatility"])
    with pytest.raises(ValueError, match="implied_volatility"):
        analyze_chain(raw, AnalysisConfig(valuation_date="2026-07-27"))


def test_chain_with_calls_only_has_no_put_wall() -> None:
    raw = _chain().query("option_type == 'call'").copy()
    result = analyze_chain(raw, AnalysisConfig(valuation_date="2026-07-27"))
    assert result.summary["call_wall"] is not None
    assert result.summary["put_wall"] is None
    assert result.summary["put_oi_wall"] is None
    assert result.summary["gamma_flip"] is None


def test_accepts_portuguese_column_aliases() -> None:
    raw = _chain().rename(columns={
        "option_type": "tipo",
        "expiration": "vencimento",
        "open_interest": "interesse_aberto",
        "underlying_price": "preco_ativo",
        "implied_volatility": "volatilidade_implicita",
    })
    result = analyze_chain(raw, AnalysisConfig(valuation_date="2026-07-27"))
    assert result.summary["options_count"] == 6


def test_converts_vendor_greek_units() -> None:
    result = analyze_chain(
        _chain(),
        AnalysisConfig(
            valuation_date="2026-07-27",
            vendor_vega_vanna_per_1pct=True,
            vendor_charm_per_day=True,
        ),
    )
    call_90 = result.options.query("option_type == 'call' and strike == 90").iloc[0]
    assert call_90["vanna"] == pytest.approx(-10.0)
    assert call_90["vanna_exposure_1pct"] == pytest.approx(-400.0)
    assert call_90["charm_exposure_day"] == pytest.approx(-800.0)


def test_zero_dte_requires_remaining_hours() -> None:
    raw = _chain().assign(expiration="2026-07-27")
    with pytest.raises(ValueError, match="0DTE"):
        analyze_chain(raw, AnalysisConfig(valuation_date="2026-07-27"))
    result = analyze_chain(
        raw,
        AnalysisConfig(valuation_date="2026-07-27", same_day_hours=4.0),
    )
    assert (result.options["time_to_expiry"] > 0).all()
