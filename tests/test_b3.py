from __future__ import annotations

import io
import zipfile
from datetime import date

import httpx
import pandas as pd
import pytest

from gamma_levels.b3 import B3Client, B3FileUnavailable, parse_option_reference, parse_price_report


def _zip(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_parses_nested_price_report_without_extracting_xml() -> None:
    xml = b"""<?xml version='1.0' encoding='UTF-8'?>
    <Document><PricRpt><Dt>2026-07-27</Dt><TckrSymb>PETRH400</TckrSymb>
    <FinInstrmAttrbts><OpnIntrst>1200</OpnIntrst><BestBidPric>2.00</BestBidPric>
    <BestAskPric>2.10</BestAskPric><FrstPric>2.05</FrstPric><MinPric>1.90</MinPric>
    <MaxPric>2.20</MaxPric><LastPric>2.08</LastPric><RglrTxsQty>40</RglrTxsQty>
    <RglrTraddCtrcts>10000</RglrTraddCtrcts><NtlRglrVol>2050000</NtlRglrVol>
    </FinInstrmAttrbts></PricRpt></Document>"""
    inner = _zip({"BVBG.086.01_final.xml": xml})
    outer = _zip({"PR260727.zip": inner})
    frame = parse_price_report(outer)
    row = frame.iloc[0]
    assert row["ticker"] == "PETRH400"
    assert row["open_interest"] == pytest.approx(1200)
    assert row["bid"] == pytest.approx(2.0)
    assert row["financial_volume"] == pytest.approx(2_050_000)


def test_reads_pe_self_extracting_archive_as_zip_only() -> None:
    content = b"20260727\nPETRH400;C;E;20260821;40.0;2.08;31.5\n"
    executable = _zip({"PE260727.txt": content})
    outer = _zip({"PE260727.ex_": executable})
    frame = parse_option_reference(outer)
    row = frame.iloc[0]
    assert row["ticker"] == "PETRH400"
    assert row["option_type"] == "call"
    assert row["style"] == "european"
    assert row["implied_volatility"] == pytest.approx(0.315)


def test_missing_trading_day_is_reported_as_unavailable(tmp_path) -> None:
    client = B3Client(tmp_path)
    client.client.close()
    client.client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"sem arquivo"))
    )
    with pytest.raises(B3FileUnavailable, match="não publicado"):
        client.download("PR", date(2026, 2, 16))
    client.close()


def test_parsed_report_cache_is_sharded_and_reused(tmp_path, monkeypatch) -> None:
    client = B3Client(tmp_path)
    trading_date = date(2026, 7, 27)
    expected = pd.DataFrame([{"ticker": "ITUB4", "close": 40.0}])
    calls = {"parse": 0}

    def first_load(*_args, **_kwargs):
        calls["parse"] += 1
        return b"raw", expected.copy()

    monkeypatch.setattr(client, "_load_with_retry", first_load)
    _, initial = client._load_parsed_report("PR", trading_date, lambda _blob: expected, {"ITUB"})
    monkeypatch.setattr(client, "download", lambda *_args, **_kwargs: b"raw")
    _, cached = client._load_parsed_report("PR", trading_date, lambda _blob: expected, {"ITUB"})

    assert calls["parse"] == 1
    assert initial.equals(cached)
    assert client._parsed_path("PR", trading_date, {"ITUB"}).name == "PR_ITUB.parquet"
    client.close()
