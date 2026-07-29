import pandas as pd
import pytest

from gamma_levels.excel_results import prepare_profit_chain


def _profit_chain() -> pd.DataFrame:
    return pd.DataFrame([
        {"ticker": "CALL90", "option_type": "call", "strike": 90, "expiration": "2026-08-21", "open_interest": 10, "implied_volatility": 0.20},
        {"ticker": "CALL100", "option_type": "call", "strike": 100, "expiration": "2026-08-21", "open_interest": 20, "implied_volatility": 0.0},
        {"ticker": "CALL110", "option_type": "call", "strike": 110, "expiration": "2026-08-21", "open_interest": 10, "implied_volatility": 0.30},
        {"ticker": "PUT100", "option_type": "put", "strike": 100, "expiration": "2026-08-21", "open_interest": 15, "implied_volatility": 0.24},
    ])


def test_interpolates_zero_iv_inside_same_smile() -> None:
    prepared, quality = prepare_profit_chain(_profit_chain())
    row = prepared.set_index("ticker").loc["CALL100"]
    assert row["iv_used"] == pytest.approx(0.25)
    assert row["iv_source"] == "Interpolada"
    assert row["data_quality_flag"] == "IV_INTERPOLADA"
    assert quality["imputed_iv_count"] == 1
    assert quality["excluded_iv_count"] == 0


def test_b3_reference_recovers_bad_strike_and_expiration() -> None:
    raw = _profit_chain()
    raw.loc[0, "strike"] = 0.0
    raw.loc[0, "expiration"] = "2026-08-06"
    reference = pd.DataFrame({
        "ticker": ["CALL90"],
        "option_type_b3": ["call"],
        "strike_b3": [90.0],
        "expiration_b3": [pd.Timestamp("2026-08-21")],
    }).set_index("ticker")

    prepared, quality = prepare_profit_chain(raw, b3_reference=reference)
    row = prepared.set_index("ticker").loc["CALL90"]
    assert row["strike"] == pytest.approx(90.0)
    assert row["expiration"] == pd.Timestamp("2026-08-21")
    assert row["strike_source"] == "B3_CORRIGIDO"
    assert row["expiration_source"] == "B3_CORRIGIDO"
    assert quality["strike_recovered_count"] == 1
    assert quality["expiration_recovered_count"] == 1
