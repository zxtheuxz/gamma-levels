from __future__ import annotations

import io
from datetime import date
from typing import Annotated

import pandas as pd
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .service import RefreshService
from .study_service import StudyService, config_from_payload
from .market_context import CorporateActionClient


app = FastAPI(
    title="Gamma Levels Swing",
    description="Scanner local B3 D-1 para compra de CALL",
    version="0.3.3",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
service = RefreshService()
study_services: dict[str, StudyService] = {"PETR4": StudyService(ticker="PETR4")}


def annual_service(ticker: str = "PETR4") -> StudyService:
    wanted = ticker.upper()
    if wanted not in study_services:
        study_services[wanted] = StudyService(ticker=wanted)
    return study_services[wanted]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.3.3"}


@app.get("/api/status")
def status() -> dict[str, object]:
    return service.status()


@app.post("/api/refresh", status_code=202)
def refresh(full_history: bool | None = None) -> dict[str, object]:
    if not service.start_refresh(full_history):
        raise HTTPException(status_code=409, detail="Já existe uma atualização em andamento")
    return {"accepted": True, "full_history": full_history, "status": service.status()}


@app.post("/api/backtest", status_code=202)
def backtest(payload: dict[str, object] | None = Body(default=None)) -> dict[str, object]:
    config = config_from_payload(payload)
    selected = annual_service(config.ticker)
    if not selected.start(config):
        raise HTTPException(status_code=409, detail=f"Já existe um processamento de {config.ticker} em andamento")
    return {"accepted": True, "config": config.to_dict(), "status": selected.status()}


@app.get("/api/backtest/status")
def backtest_status(ticker: str = "PETR4") -> dict[str, object]:
    return annual_service(ticker).status()


@app.get("/api/backtest/latest")
def latest_backtest(ticker: str = "PETR4") -> dict[str, object]:
    return annual_service(ticker).database.latest_backtest_summary()


@app.get("/api/backtest/trades/{trade_id:path}")
def backtest_trade(trade_id: str, ticker: str = "PETR4") -> dict[str, object]:
    result = annual_service(ticker).database.trade_detail(trade_id)
    if not result:
        raise HTTPException(status_code=404, detail="Operação de backtest não encontrada")
    return result


@app.post("/api/backtest/corporate-actions/{ticker}")
def import_corporate_actions(ticker: str, payload: dict[str, str] = Body(...)) -> dict[str, object]:
    content = payload.get("csv") or ""
    if not content.strip():
        raise HTTPException(status_code=400, detail="Conteúdo CSV ausente")
    imported = CorporateActionClient.import_csv(annual_service(ticker).database, ticker.upper(), content)
    return {"imported": imported, "ticker": ticker.upper()}


@app.get("/api/signals")
def signals(trade_date: date | None = None) -> dict[str, object]:
    assets = service.database.latest_assets(trade_date)
    effective_date = trade_date or service.database.latest_date()
    counts = {
        label: sum(1 for item in assets if item["status"] == label)
        for label in ("COMPRAR CALL", "AGUARDAR", "DESCARTAR")
    }
    return {
        "trade_date": effective_date.isoformat() if effective_date else None,
        "source": "B3 D-1",
        "counts": counts,
        "assets": assets,
        "config": service.config.to_dict(),
    }


@app.get("/api/assets/{ticker}")
def asset(ticker: str, trade_date: date | None = None) -> dict[str, object]:
    wanted = ticker.upper()
    assets = service.database.latest_assets(trade_date)
    for item in assets:
        if item["ticker"].upper() == wanted or item["asset_root"].upper() == wanted:
            bars = service.database.bars(item["ticker"], trade_date or service.database.latest_date(), 120)
            return {"asset": item, "bars": bars.to_dict("records")}
    raise HTTPException(status_code=404, detail="Ativo não encontrado no ranking")


@app.get("/api/history")
def history() -> dict[str, object]:
    payload = service.database.history_summary()
    payload["annual_study"] = annual_service("PETR4").database.latest_backtest_summary()
    return payload


@app.get("/api/data-quality")
def data_quality() -> dict[str, object]:
    rows = service.database.frame(
        "SELECT trade_date,status,manifest_json,loaded_at FROM market_sessions ORDER BY trade_date DESC LIMIT 120"
    )
    return {"sessions": rows.to_dict("records"), "status": service.status()}


@app.get("/api/export.xlsx")
def export_excel(trade_date: Annotated[date | None, Query()] = None) -> StreamingResponse:
    assets = service.database.latest_assets(trade_date)
    if not assets:
        raise HTTPException(status_code=404, detail="Nenhum resultado disponível para exportar")
    effective_date = trade_date or service.database.latest_date()
    ranking = pd.json_normalize(assets, sep="_")
    signals_frame = ranking.loc[ranking["status"].eq("COMPRAR CALL")].copy()
    history_payload = service.database.history_summary()
    history_frame = pd.DataFrame(history_payload["rows"])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        signals_frame.to_excel(writer, sheet_name="Sinais", index=False)
        ranking.to_excel(writer, sheet_name="Ranking_20", index=False)
        history_frame.to_excel(writer, sheet_name="Historico", index=False)
        pd.DataFrame(
            [
                {"campo": "Data-base", "valor": effective_date.isoformat() if effective_date else ""},
                {"campo": "Fonte", "valor": "B3 D-1"},
                {"campo": "Estratégia", "valor": "Compra de CALL — swing de alta"},
                {"campo": "Vencimento", "valor": "10 a 60 dias"},
                {"campo": "Delta", "valor": "0,55 a 0,80"},
            ]
        ).to_excel(writer, sheet_name="Metadados", index=False)
    output.seek(0)
    filename = f"gamma_levels_swing_{effective_date.isoformat() if effective_date else 'sem_data'}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/backtest/export.xlsx")
def export_backtest_excel(ticker: str = "PETR4") -> StreamingResponse:
    selected = annual_service(ticker)
    summary = selected.database.latest_backtest_summary()
    if not summary.get("run"):
        raise HTTPException(status_code=404, detail="Nenhum estudo anual disponível")
    run = pd.DataFrame([summary["run"]])
    metrics = pd.DataFrame(summary.get("metrics") or [])
    trades = pd.DataFrame(summary.get("trades") or [])
    with selected.database.connect() as connection:
        run_id = int(summary["run"]["id"])
        paths = pd.read_sql_query(
            """SELECT p.* FROM trade_path p JOIN backtest_trades t ON t.trade_id=p.trade_id
            WHERE t.run_id=? ORDER BY p.trade_id,p.trade_date""", connection, params=(run_id,)
        )
        regions = pd.read_sql_query(
            "SELECT * FROM region_snapshots WHERE run_id=? ORDER BY variant,trade_date,region_type",
            connection, params=(run_id,),
        )
        quality = pd.read_sql_query(
            "SELECT * FROM market_sessions ORDER BY trade_date", connection
        )
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        run.to_excel(writer, sheet_name="Resumo", index=False)
        metrics.to_excel(writer, sheet_name="Estrategias", index=False)
        trades.to_excel(writer, sheet_name="Operacoes", index=False)
        paths.to_excel(writer, sheet_name="Trajetoria", index=False)
        regions.to_excel(writer, sheet_name="Regioes", index=False)
        metrics[[column for column in metrics.columns if column in {
            "variant", "strategy", "overlap_mode", "sample", "trades", "expectancy", "profit_factor"
        }]].to_excel(writer, sheet_name="Variantes", index=False)
        quality.to_excel(writer, sheet_name="Qualidade", index=False)
        pd.DataFrame([
            {"campo": "Ativo", "valor": ticker.upper()},
            {"campo": "Fonte", "valor": "B3 D-1"},
            {"campo": "Entrada", "valor": "Ordem limitada pelo prêmio máximo de D-1"},
            {"campo": "Métrica principal", "valor": "Expectativa líquida"},
            {"campo": "Sobreposição", "valor": "Independente e posição única"},
        ]).to_excel(writer, sheet_name="Metodologia", index=False)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="backtest_anual_{ticker.upper()}.xlsx"'},
    )
