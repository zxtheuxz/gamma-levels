"""Verificação diária D-1 da cesta operacional de 11 ativos.

Para cada ticker da cesta o script roda duas leituras sobre o mesmo pregão:

1. A variante que colocou o ticker na cesta (escolha por ativo).
2. A regra global `score_85`, que a auditoria de 30/07/2026 apontou como a unidade
   correta de avaliação agregada.

Um ticker só é tratado como ativado quando o scanner devolve `COMPRAR CALL`, isto é,
quando score, RSI, setup, CALL elegível, relação risco/retorno e projeção conservadora
passam simultaneamente. Nada aqui antecipa sinal: o que não passou fica registrado com
o motivo do bloqueio.

Uso:
    python scripts/daily_basket_scan.py                 # baixa D-1 e verifica
    python scripts/daily_basket_scan.py --sem-download  # usa o que já está no banco
    python scripts/daily_basket_scan.py --data 2026-07-29
    python scripts/daily_basket_scan.py --sempre        # manda Telegram mesmo sem ativação
    python scripts/daily_basket_scan.py --sem-telegram
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gamma_levels.b3 import B3Client  # noqa: E402
from gamma_levels.storage import Database  # noqa: E402
from gamma_levels.study import standard_variants  # noqa: E402
from gamma_levels.swing import SwingConfig, SwingScanner  # noqa: E402


# Variante que colocou cada ticker na cesta, conforme o ranking consolidado dos 75 ativos.
# ITSA4 é inclusão exploratória de baixa amostra (score_75 + PARTIAL_25_CALCULATED).
BASKET: dict[str, str] = {
    "VALE3": "ema_21_72",
    "BBDC4": "score_85",
    "PETR3": "score_75",
    "BBAS3": "score_75",
    "B3SA3": "region_lookback_20",
    "CMIG4": "rr_125",
    "ITUB4": "score_75",
    "PRIO3": "region_lookback_50",
    "USIM5": "region_lookback_20",
    "PETR4": "score_85",
    "ITSA4": "score_75",
}
GLOBAL_VARIANT = "score_85"
HISTORY_SESSIONS = 140  # mesma janela de contexto usada pelo estudo anual
RSI_PATTERN = re.compile(r"RSI\s+([\d.,]+)")


def load_variants() -> dict[str, SwingConfig]:
    return {config.variant: config for config in standard_variants(HISTORY_SESSIONS)}


def asset_root_for(database: Database, ticker: str) -> str | None:
    frame = database.frame(
        "SELECT asset_root FROM underlying_bars WHERE ticker=? ORDER BY trade_date DESC LIMIT 1",
        (ticker,),
    )
    if frame.empty:
        return None
    return str(frame.iloc[0]["asset_root"])


def ingest_latest(database: Database, data_dir: Path) -> date | None:
    """Carrega todo pregão publicado depois da última sessão do banco.

    Não basta olhar `latest_available_date()`: a consulta de disponibilidade da B3 às
    vezes ignora o pregão mais recente, e a rotina pode ficar dias sem rodar. Por isso o
    script varre cada dia útil entre a última sessão carregada e ontem, carregando o que
    existir. Assim nenhum pregão é perdido nem baixado duas vezes.
    """
    loaded = set(database.loaded_dates())
    if not loaded:
        raise SystemExit("Banco diário vazio; rode a atualização completa antes.")
    newest = max(loaded)
    candidates = [
        newest + timedelta(days=offset)
        for offset in range(1, (date.today() - newest).days)
    ]
    candidates = [item for item in candidates if item.weekday() < 5 and item not in loaded]
    if not candidates:
        print(f"Nenhum pregão novo desde {newest:%d/%m/%Y}.", flush=True)
        return newest

    stored = newest
    with B3Client(data_dir) as client:
        for candidate in candidates:
            if not client.is_available(candidate):
                print(f"  {candidate:%d/%m/%Y} sem arquivo publicado — pulando", flush=True)
                continue
            print(f"Baixando pregão {candidate:%d/%m/%Y} da B3...", flush=True)
            try:
                session = client.load_session(
                    candidate,
                    include_instruments=not database.has_instruments(),
                    progress=lambda message: print(f"  {message}", flush=True),
                )
            except Exception as exc:
                print(f"  {candidate:%d/%m/%Y} falhou: {exc}", flush=True)
                continue
            database.store_session(session)
            stored = candidate
            print(f"Pregão {candidate:%d/%m/%Y} armazenado.", flush=True)
    return stored


def rsi_from(asset: dict[str, Any]) -> float | None:
    for reason in asset.get("reasons") or []:
        found = RSI_PATTERN.search(str(reason))
        if found:
            return float(found.group(1).replace(",", "."))
    return None


def conservative_5d(asset: dict[str, Any]) -> float | None:
    projections = asset.get("projections") or {}
    horizon = (projections.get("horizons") or {}).get("5") or {}
    value = horizon.get("conservative")
    return float(value) if value is not None else None


def blockers(asset: dict[str, Any], config: SwingConfig) -> list[str]:
    """Lista, na ordem da regra, tudo que impediu o status COMPRAR CALL."""
    missing: list[str] = []
    score = float(asset.get("score") or 0.0)
    if score < config.buy_score:
        missing.append(f"score {score:.2f} < {config.buy_score:.0f}")
    rsi = rsi_from(asset)
    if config.rsi_entry_floor > 0 and rsi is not None and rsi < config.rsi_entry_floor:
        missing.append(f"RSI {rsi:.1f} < {config.rsi_entry_floor:.0f}")
    if not asset.get("setup"):
        missing.append("sem setup")
    if not asset.get("selected_call"):
        missing.append("sem CALL aprovada")
    reward_risk = float(asset.get("reward_risk") or 0.0)
    if reward_risk < config.min_reward_risk:
        missing.append(f"RR {reward_risk:.2f} < {config.min_reward_risk:.2f}")
    conservative = conservative_5d(asset)
    if conservative is None:
        missing.append("sem projeção")
    elif conservative < 0.10:
        missing.append(f"projeção 5d {conservative * 100:.2f}% < 10%")
    return missing


def scan_one(
    database: Database, ticker: str, root: str, variant: SwingConfig,
    trade_date: date, cache: dict[tuple[Any, ...], Any],
) -> dict[str, Any]:
    config = replace(
        variant,
        universe_size=1,
        max_buy_signals=1,
        history_sessions=HISTORY_SESSIONS,
        fixed_ticker=ticker,
        fixed_asset_root=root,
    )
    scanner = SwingScanner(database, config, cache)
    assets = scanner.run(trade_date)
    if not assets:
        raise RuntimeError(f"{ticker}: scanner não devolveu resultado em {trade_date}")
    asset = assets[0]
    call = asset.get("selected_call") or {}
    return {
        "ticker": ticker,
        "variant": config.variant,
        "status": asset.get("status"),
        "score": float(asset.get("score") or 0.0),
        "buy_score": float(config.buy_score),
        "setup": asset.get("setup"),
        "spot": asset.get("spot"),
        "reward_risk": float(asset.get("reward_risk") or 0.0),
        "min_reward_risk": float(config.min_reward_risk),
        "call": call.get("ticker"),
        "call_strike": call.get("strike"),
        "call_expiration": call.get("expiration"),
        "max_entry_premium": (asset.get("projections") or {}).get("max_entry_premium"),
        "projection_5d": conservative_5d(asset),
        "rsi": rsi_from(asset),
        "blockers": blockers(asset, config),
        "data_quality": asset.get("data_quality"),
    }


def format_line(row: dict[str, Any]) -> str:
    call = row["call"] or "-"
    projection = row["projection_5d"]
    projection_text = f"{projection * 100:6.2f}%" if projection is not None else "     -"
    return (
        f"{row['ticker']:<6} {row['variant']:<19} {str(row['status']):<12} "
        f"{row['score']:6.2f}/{row['buy_score']:.0f} RR {row['reward_risk']:5.2f} "
        f"{call:<10} 5d {projection_text}  {'; '.join(row['blockers']) or 'todos os filtros passaram'}"
    )


def telegram_credentials() -> tuple[str | None, str | None]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    env_file = ROOT / ".env.telegram"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key == "TELEGRAM_BOT_TOKEN" and not token:
                token = value
            elif key == "TELEGRAM_CHAT_ID" and not chat_id:
                chat_id = value
    return token, chat_id


def send_telegram(text: str) -> bool:
    import httpx

    token, chat_id = telegram_credentials()
    if not token or not chat_id:
        print("Telegram não configurado (.env.telegram ausente ou incompleto).", flush=True)
        return False
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=20.0,
        )
        response.raise_for_status()
    except Exception as exc:
        print(f"Falha ao enviar Telegram: {exc}", flush=True)
        return False
    print("Telegram enviado.", flush=True)
    return True


def build_message(trade_date: date, rows: list[dict[str, Any]], activated: list[dict[str, Any]]) -> str:
    lines = [f"Gamma Levels — cesta D-1 {trade_date:%d/%m/%Y}"]
    if activated:
        lines.append("")
        lines.append(f"ATIVOU: {len(activated)} sinal(is) COMPRAR CALL")
        for row in activated:
            premium = row["max_entry_premium"]
            premium_text = f"{premium:.2f}" if premium is not None else "-"
            projection = row["projection_5d"]
            projection_text = f"{projection * 100:.2f}%" if projection is not None else "-"
            lines.append(
                f"- {row['ticker']} ({row['variant']}): {row['call']} | score {row['score']:.2f} "
                f"| RR {row['reward_risk']:.2f} | prêmio máx {premium_text} | proj. 5d {projection_text} "
                f"| {row['setup']}"
            )
    else:
        lines.append("")
        lines.append("Nenhuma ativação. Nenhum dos 11 gerou COMPRAR CALL.")

    waiting = [row for row in rows if row["status"] == "AGUARDAR"]
    if waiting:
        closest = sorted(waiting, key=lambda item: item["buy_score"] - item["score"])[:3]
        lines.append("")
        lines.append("Mais próximos (sem sinal):")
        for row in closest:
            lines.append(
                f"- {row['ticker']} ({row['variant']}): score {row['score']:.2f}/{row['buy_score']:.0f} "
                f"— {'; '.join(row['blockers'])}"
            )
    lines.append("")
    lines.append("Verificação automática; não é recomendação. Confira antes de operar.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verificação diária D-1 da cesta de 11 ativos")
    parser.add_argument("--data", help="Data do pregão a avaliar (YYYY-MM-DD); padrão: último carregado")
    parser.add_argument("--sem-download", action="store_true", help="Não busca pregão novo na B3")
    parser.add_argument("--sem-telegram", action="store_true", help="Não envia mensagem no Telegram")
    parser.add_argument("--sempre", action="store_true", help="Envia Telegram mesmo sem ativação")
    parser.add_argument(
        "--tickers", help="Subconjunto da cesta, separado por vírgula (padrão: os 11)"
    )
    args = parser.parse_args()

    selected = dict(BASKET)
    if args.tickers:
        wanted = {item.strip().upper() for item in args.tickers.split(",") if item.strip()}
        unknown = wanted - set(BASKET)
        if unknown:
            raise SystemExit(f"Ticker fora da cesta: {', '.join(sorted(unknown))}")
        selected = {ticker: variant for ticker, variant in BASKET.items() if ticker in wanted}

    data_dir = ROOT / "data"
    database = Database(data_dir / "gamma_levels.db")

    if not args.sem_download and not args.data:
        ingest_latest(database, data_dir)

    loaded = database.loaded_dates()
    if not loaded:
        raise SystemExit("Banco diário vazio.")
    trade_date = date.fromisoformat(args.data) if args.data else loaded[-1]
    if trade_date not in set(loaded):
        raise SystemExit(f"Pregão {trade_date} não está carregado no banco diário.")
    print(
        f"Data-base: {trade_date:%d/%m/%Y} | pregões no banco: {len(loaded)} "
        f"({loaded[0]:%d/%m/%Y} a {loaded[-1]:%d/%m/%Y})",
        flush=True,
    )
    if len(loaded) < HISTORY_SESSIONS:
        print(
            f"Atenção: o estudo usa {HISTORY_SESSIONS} pregões de contexto e o banco tem {len(loaded)}. "
            "Rode scripts/extend_daily_history.py para igualar a janela.",
            flush=True,
        )

    variants = load_variants()
    cache: dict[tuple[Any, ...], Any] = {}
    rows: list[dict[str, Any]] = []
    print("\n--- Variante própria de cada ativo ---", flush=True)
    for ticker, variant_name in selected.items():
        root = asset_root_for(database, ticker)
        if root is None:
            print(f"{ticker:<6} sem barras no banco diário — ignorado", flush=True)
            continue
        row = scan_one(database, ticker, root, variants[variant_name], trade_date, cache)
        rows.append(row)
        print(format_line(row), flush=True)

    print(f"\n--- Regra global {GLOBAL_VARIANT} ---", flush=True)
    global_rows: list[dict[str, Any]] = []
    for ticker in selected:
        root = asset_root_for(database, ticker)
        if root is None:
            continue
        row = scan_one(database, ticker, root, variants[GLOBAL_VARIANT], trade_date, cache)
        global_rows.append(row)
        print(format_line(row), flush=True)

    combined = rows + [row for row in global_rows if row["variant"] != BASKET.get(row["ticker"])]
    activated = [row for row in combined if row["status"] == "COMPRAR CALL"]
    print(
        f"\nResumo {trade_date:%d/%m/%Y}: {len(activated)} ativação(ões), "
        f"{sum(1 for row in combined if row['status'] == 'AGUARDAR')} em AGUARDAR, "
        f"{sum(1 for row in combined if row['status'] == 'DESCARTAR')} em DESCARTAR "
        f"(de {len(combined)} leituras).",
        flush=True,
    )

    if not args.sem_telegram and (activated or args.sempre):
        send_telegram(build_message(trade_date, combined, activated))
    elif not args.sem_telegram:
        print("Sem ativação: Telegram não enviado (use --sempre para forçar).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
