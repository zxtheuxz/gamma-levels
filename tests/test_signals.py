from datetime import date

import pandas as pd
import pytest

from gamma_levels.core import AnalysisConfig, analyze_chain
from gamma_levels.signals import (
    SignalConfig,
    black_scholes_price,
    build_signals,
    build_strength_scores,
    rank_option_candidates,
)


def _chain() -> pd.DataFrame:
    rows = []
    for expiration, dte_mult in (("2026-08-07", 1.0), ("2026-08-21", 1.2)):
        for strike, call_oi, put_oi in ((90.0, 50, 250), (100.0, 300, 300), (110.0, 250, 50)):
            rows.extend([
                {
                    "ticker": f"C{strike:.0f}{expiration[-2:]}", "option_type": "call", "strike": strike,
                    "expiration": expiration, "open_interest": call_oi * dte_mult, "volume": 30,
                    "delta": 0.60 if strike == 100 else (0.80 if strike == 90 else 0.30),
                    "gamma": 0.02, "vega": 0.1, "vanna": -0.1, "charm": -0.2,
                    "implied_volatility": 0.25, "underlying_price": 100.0, "multiplier": 100,
                    "option_price": 4.0, "bid": 3.9, "ask": 4.1, "iv_source": "Profit",
                },
                {
                    "ticker": f"P{strike:.0f}{expiration[-2:]}", "option_type": "put", "strike": strike,
                    "expiration": expiration, "open_interest": put_oi * dte_mult, "volume": 25,
                    "delta": -0.60 if strike == 100 else (-0.30 if strike == 90 else -0.80),
                    "gamma": 0.02, "vega": 0.1, "vanna": 0.1, "charm": -0.2,
                    "implied_volatility": 0.27, "underlying_price": 100.0, "multiplier": 100,
                    "option_price": 4.2, "bid": 4.1, "ask": 4.3, "iv_source": "Profit",
                },
            ])
    return pd.DataFrame(rows)


def test_strength_scores_are_bounded_and_labeled() -> None:
    result = analyze_chain(_chain(), AnalysisConfig(valuation_date=date(2026, 7, 27)))
    scores = build_strength_scores(result)
    assert scores["support_strength"].between(0, 100).all()
    assert scores["resistance_strength"].between(0, 100).all()
    assert set(scores["support_strength_label"]).issubset({"FRACO", "MODERADO", "FORTE", "MUITO FORTE"})


def test_option_ranking_respects_delta_and_minimum_dte() -> None:
    result = analyze_chain(_chain(), AnalysisConfig(valuation_date="2026-07-27"))
    ranked = rank_option_candidates(result.options, SignalConfig(horizon_days=5, delta_min=0.5, delta_max=0.7))
    assert not ranked.empty
    assert ranked["days_to_expiry"].ge(7).all()
    assert ranked["abs_delta"].between(0.5, 0.7).all()


def test_signal_targets_follow_direction() -> None:
    result = analyze_chain(_chain(), AnalysisConfig(valuation_date="2026-07-27"))
    signals = build_signals(result).signals
    for row in signals.itertuples(index=False):
        targets = [getattr(row, f"target_{index}") for index in range(1, 4)]
        targets = [target for target in targets if pd.notna(target)]
        if row.direction == "ALTA":
            assert all(target > row.trigger for target in targets)
        else:
            assert all(target < row.trigger for target in targets)


def test_black_scholes_prices_move_with_underlying_and_iv() -> None:
    call_low = black_scholes_price(95, 100, 0.1, 0.25, "call", 0.1, 0.0)
    call_high = black_scholes_price(105, 100, 0.1, 0.25, "call", 0.1, 0.0)
    put_low = black_scholes_price(95, 100, 0.1, 0.25, "put", 0.1, 0.0)
    put_high = black_scholes_price(105, 100, 0.1, 0.25, "put", 0.1, 0.0)
    call_high_iv = black_scholes_price(105, 100, 0.1, 0.30, "call", 0.1, 0.0)
    assert call_high > call_low
    assert put_low > put_high
    assert call_high_iv > call_high
