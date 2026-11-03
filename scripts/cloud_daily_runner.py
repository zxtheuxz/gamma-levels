"""
Runner Autônomo de Nuvem (GitHub Actions + Telegram + Relatórios para n8n/Gemini)
=================================================================================
Executa o Scanner de Tiro Rápido da B3 (45 ações líquidas) e o Scanner de Opções
dos EUA (36 ações/ETFs na CBOE), atualiza o cache leve `cloud_cache/`, grava os
relatórios atualizados em `cloud_reports/` e envia o resumo mastigado no Telegram.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.scan_tiro_rapido_d3 import LIQUID_45, run_scan_payload  # noqa: E402
from scripts.scan_us_options_d3 import evaluate_ticker_today  # noqa: E402


def load_telegram_creds() -> tuple[str, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    env_file = ROOT / ".env.telegram"
    if (not token or not chat_id) and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() == "TELEGRAM_BOT_TOKEN" and not token:
                    token = v.strip()
                elif k.strip() == "TELEGRAM_CHAT_ID" and not chat_id:
                    chat_id = v.strip()
    return token, chat_id


def send_telegram_message(token: str, chat_id: str, text: str) -> bool:
    if not token or not chat_id:
        print("[Telegram] Credenciais ausentes; pulando envio.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return bool(res.get("ok"))
    except Exception as e:
        print(f"[Telegram] Erro ao enviar: {e}")
        return False


def update_cloud_b3_cache() -> None:
    """Atualiza cloud_cache/b3_tail35 com os pregões recém-processados."""
    dst = ROOT / "cloud_cache" / "b3_tail35"
    dst.mkdir(parents=True, exist_ok=True)
    raw_cache_files = sorted((ROOT / "results" / "option_patterns" / "daily_raw_cache").glob("2026-*_v2.parquet"))
    raw_df = pd.concat([pd.read_parquet(p) for p in raw_cache_files], ignore_index=True) if raw_cache_files else pd.DataFrame()

    for tk in LIQUID_45:
        p_cloud = dst / f"{tk}.parquet"
        p_hist = ROOT / "results" / "option_patterns" / "cache_v2" / f"{tk}.parquet"
        base_df = pd.read_parquet(p_cloud) if p_cloud.exists() else (pd.read_parquet(p_hist).tail(35) if p_hist.exists() else pd.DataFrame())
        if not raw_df.empty:
            r_tk = raw_df[raw_df["ticker"] == tk]
            if not r_tk.empty:
                if not base_df.empty:
                    r_tk = r_tk[~r_tk["trade_date"].isin(set(base_df["trade_date"]))]
                    base_df = pd.concat([base_df, r_tk], ignore_index=True)
                else:
                    base_df = r_tk.copy()
        if not base_df.empty:
            base_df = base_df.sort_values("trade_date").tail(35).reset_index(drop=True)
            base_df.to_parquet(p_cloud, index=False)


def run_us_scan_payload() -> list[dict]:
    today = date.today()
    cache_dir = ROOT / "results" / "us_options" / "cache_v1"
    parquet_files = sorted(cache_dir.glob("*_us_panel_v1.parquet"))
    if not parquet_files:
        parquet_files = sorted((ROOT / "cloud_cache" / "us_tail35").glob("*_us_panel_v1.parquet"))

    from concurrent.futures import ThreadPoolExecutor, as_completed
    hist_map = {pf.name.split("_")[0]: pd.read_parquet(pf) for pf in parquet_files}
    signals = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(evaluate_ticker_today, tk, df_h, today): tk for tk, df_h in hist_map.items()}
        for f in as_completed(futs):
            res = f.result()
            if res is not None:
                signals.append(res)
    signals.sort(key=lambda x: (x["n_rules"], x["best_wr"], x["cp_vol_ratio"]), reverse=True)
    return signals


def format_telegram_briefing(b3_payload: dict, us_signals: list[dict]) -> str:
    eval_dt = b3_payload.get("eval_date", "")
    d3_lim = b3_payload.get("session_d3", "")
    m2 = b3_payload.get("mesa2_abert_d1", [])
    m1 = b3_payload.get("mesa1_fim_d0", [])
    all_b3 = m2 + m1

    lines = [
        f"🌙 <b>FECHAMENTO DO DIA — RADAR B3 &amp; EUA</b>",
        f"📅 Fechamento Base: <b>{eval_dt}</b>",
        "",
    ]

    if not all_b3:
        lines.append("🔴 <b>NENHUM ATIVO LIBERADO NA B3 HOJE</b>")
        lines.append("• Nenhuma opção cumpriu os filtros matemáticos para amanhã.")
    else:
        for h in all_b3[:5]:
            br = h["best_rule"]
            min_st = round(h["spot"] * 0.985, 2)
            ideal_min = h.get("ideal_buy_min", round(h["opt_close"] * 0.95, 2))
            ideal_max = h.get("ideal_buy_max", round(h["opt_close"] * 1.03, 2))
            max_lim = h.get("max_buy_limit") or h.get("opt_max_open_d1") or round(h["opt_close"] * 1.05, 2)
            lim_low = round(ideal_max + 0.01, 2)
            t20 = h.get("target_20") or h.get("target_20_ref")
            t40 = h.get("target_40") or h.get("target_40_ref")
            exp_d3 = h.get("d3_limit_date") or d3_lim

            lines.extend([
                f"🟢 <b>SINAL PREPARADO P/ AMANHÃ (10h05): <code>{h['opt_ticker']}</code> ({h['ticker']})</b>",
                "",
                "🔎 <b>Condição da Ação-Mãe ({0}):</b>".format(h["ticker"]),
                f"• Fechamento Hoje: <b>R$ {h['spot']:.2f}</b>",
                f"• Piso mínimo exigido amanhã às 10h05: <b>R$ {min_st:.2f}</b>",
                f"• Taxa de Acerto do Padrão: <b>{br['wr']:.1f}%</b>",
                "",
                f"💵 <b>Tabela de Preço da Opção (<code>{h['opt_ticker']}</code> — Fech R$ {h['opt_close']:.2f}):</b>",
                f"🟢 <b>R$ {ideal_min:.2f} a R$ {ideal_max:.2f}</b> ➡️ Compra excelente!",
                f"🟡 <b>R$ {lim_low:.2f} a R$ {max_lim:.2f}</b> ➡️ Compra no limite (aceitável)",
                f"🔴 <b>Acima de R$ {max_lim:.2f}</b> ➡️ Cara demais (ficar de fora)",
                "",
                "🎯 <b>Alvos de Lucro:</b>",
                f"• <b>Alvo 1 (+20%):</b> R$ {t20:.2f} <i>(realizar metade)</i>",
                f"• <b>Alvo 2 (+40%):</b> R$ {t40:.2f} <i>(zerar tudo)</i>",
                f"• <b>Vencimento do Trade:</b> máximo 3 pregões (até {exp_d3})",
                "",
            ])

    lines.append("───")
    lines.append(f"🇺🇸 <b>RADAR OPÇÕES EUA ({len(us_signals)} sinais):</b>")
    if not us_signals:
        lines.append("• Nenhum sinal ativo nos EUA hoje.")
    else:
        for s in us_signals[:4]:
            c = s["core_atm"]
            t20_us = c["mid"] * 1.20
            lines.append(
                f"🟢 <b>{s['ticker']}</b> (${s['spot']:.2f}) ➡️ Call <code>${c['strike']}C</code> @ <b>US$ {c['mid']:.2f}</b> (Alvo +20%: <b>US$ {t20_us:.2f}</b> | Acerto {s['best_wr']:.1f}%)"
            )

    lines.append("")
    lines.append("💬 <i>Às 10h05 de amanhã te mando a validação ao vivo da abertura!</i>")
    return "\n".join(lines)


def main() -> None:
    print("[Cloud Runner] 1/4 Executando Scanner Tiro Rápido B3...")
    b3_payload = run_scan_payload(do_download=True)
    update_cloud_b3_cache()

    print("[Cloud Runner] 2/4 Executando Scanner Opções EUA (CBOE)...")
    us_signals = run_us_scan_payload()

    reports_dir = ROOT / "cloud_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    consolidated = {
        "updated_at": date.today().isoformat(),
        "b3_tiro_rapido": b3_payload,
        "us_cboe_signals": us_signals,
        "bovak205_position": {
            "ticker": "BOVAK205",
            "qty": 67,
            "entry_price": 8.90,
            "total_invested": 596.30,
            "strike": 205.00,
            "expiration": "2026-11-19",
            "last_bova11_close": 165.40,
            "last_opt_close": 0.02,
            "note": "Manter em custodia sem vender a preco de po ate 19/11/2026.",
        },
    }
    (reports_dir / "latest_daily_briefing.json").write_text(
        json.dumps(consolidated, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    msg = format_telegram_briefing(b3_payload, us_signals)
    (reports_dir / "latest_daily_briefing.md").write_text(msg, encoding="utf-8")

    token, chat_id = load_telegram_creds()
    if "--no-telegram" not in sys.argv:
        print("[Cloud Runner] 3/4 Enviando briefing no Telegram...")
        ok = send_telegram_message(token, chat_id, msg)
        print(f"[Cloud Runner] Envio Telegram: {'SUCESSO' if ok else 'FALHOU'}")
    print("[Cloud Runner] 4/4 Concluído!")


if __name__ == "__main__":
    main()
