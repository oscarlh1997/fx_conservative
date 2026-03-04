# -*- coding: utf-8 -*-
import argparse, os, sys, json
from datetime import datetime
import pandas as pd

from fx_conservative.config import load_config
from fx_conservative.logger import TradeLogger
from fx_conservative.alpaca_adapter import AlpacaAdapter
from fx_conservative.strategy import FXConservativeLive
from fx_conservative.utils_time import next_daily_close_eu_madrid
from fx_conservative.metrics import compute_trade_metrics, compute_equity_metrics
from fx_conservative.backtest_offline import offline_backtest, BTConfig


def make_adapter():
    return AlpacaAdapter()


def cmd_run_once(args):
    cfg = load_config(args.config)
    logger = TradeLogger(cfg.log_dir, cfg.state_path)
    adp = make_adapter()
    strat = FXConservativeLive(adp, cfg, logger)

    # Sincroniza transacciones pendientes antes de operar (para cerrar trades del log si hubo SL/TP)
    try:
        sync_res = strat.sync_transactions()
        print("sync:", sync_res)
    except Exception as e:
        print("sync error (continuamos):", e)

    res = strat.run_daily_cycle()
    print("run-once result:", res)

def cmd_daemon(args):
    cfg = load_config(args.config)
    logger = TradeLogger(cfg.log_dir, cfg.state_path)
    adp = make_adapter()
    strat = FXConservativeLive(adp, cfg, logger)

    print("Daemon iniciado. Esperando a cada cierre de mercado NYSE (daily_alignment_hour en ET). Ctrl+C para salir.")
    while True:
        try:
            target = next_daily_close_eu_madrid(cfg.daily_alignment_hour)
            now = pd.Timestamp.now(tz="Europe/Madrid")
            wait_s = max(5, (target - now).total_seconds())
            print(f"Próximo ciclo a: {target} (Madrid). Esperando {int(wait_s)} s...")
            import time; time.sleep(wait_s)
            # Breve pausa para asegurar que la barra diaria ya está disponible en Alpaca
            time.sleep(30)
            # Sincroniza fills/cierres antes del nuevo ciclo
            try:
                sync_res = strat.sync_transactions()
                print("sync:", sync_res)
            except Exception as e:
                print("sync error:", e)
            # Ejecuta ciclo
            res = strat.run_daily_cycle()
            print(datetime.utcnow().isoformat(), "ejecutado:", res)
            # Actualiza trailing stops
            try:
                tr_res = strat.update_all_trailings()
                print("trailings:", tr_res)
            except Exception as e:
                print("trailing error:", e)
            time.sleep(60)
        except KeyboardInterrupt:
            print("\nSaliendo por el usuario.")
            break
        except Exception as e:
            print("Error en ciclo:", e)
            import time; time.sleep(30)

def cmd_update_trailing(args):
    cfg = load_config(args.config)
    logger = TradeLogger(cfg.log_dir, cfg.state_path)
    adp = make_adapter()
    strat = FXConservativeLive(adp, cfg, logger)
    res = strat.update_all_trailings()
    print(res)

def cmd_metrics(args):
    cfg = load_config(args.config)
    trades_stats = compute_trade_metrics(os.path.join(cfg.log_dir, "trades.csv"))
    equity_stats = compute_equity_metrics(os.path.join(cfg.log_dir, "equity.csv"))
    print("==== Métricas de Trades ====")
    print(json.dumps(trades_stats, indent=2, ensure_ascii=False))
    print("==== Métricas de Equity ====")
    print(json.dumps(equity_stats, indent=2, ensure_ascii=False))

def cmd_backtest(args):
    cfg = load_config(args.config)
    adp = AlpacaAdapter()
    bt_cfg = BTConfig(
        risk_per_trade=cfg.risk_per_trade, total_risk_cap=cfg.total_risk_cap,
        ema_fast=cfg.ema_fast, ema_slow=cfg.ema_slow, donchian_n=cfg.donchian_n, adx_thresh=cfg.adx_thresh,
        atr_stop_mult=cfg.atr_stop_mult, atr_trail_mult=cfg.atr_trail_mult, tp_R=cfg.tp_R,
        rsi_len=cfg.rsi_len, rsi_low=cfg.rsi_low, rsi_high=cfg.rsi_high,
        max_gross_leverage=cfg.max_gross_leverage, correl_window=cfg.correl_window,
        correl_threshold=cfg.correl_threshold, max_positions=cfg.max_positions
    )
    eq, tr = offline_backtest(adp, cfg.pairs, args.start, args.end, cfg.spreads, bt_cfg,
                              alignment_tz=cfg.alignment_tz, daily_hour=cfg.daily_alignment_hour)
    # Guardar resultados
    out_dir = cfg.log_dir
    os.makedirs(out_dir, exist_ok=True)
    eq.to_csv(os.path.join(out_dir, f"backtest_equity_{args.start}_{args.end}.csv"))
    tr.to_csv(os.path.join(out_dir, f"backtest_trades_{args.start}_{args.end}.csv"), index=False)
    print("Backtest terminado. Archivos guardados en", out_dir)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="FX Conservative (Alpaca) - Runner")
    sub = ap.add_subparsers()

    p1 = sub.add_parser("run-once", help="Ejecuta un ciclo diario una vez (opera con la última vela cerrada)")
    p1.add_argument("--config", default="config/config.yaml")
    p1.set_defaults(func=cmd_run_once)

    p2 = sub.add_parser("daemon", help="Ejecuta el ciclo a cada cierre D1 (segun daily_alignment_hour en NY)")
    p2.add_argument("--config", default="config/config.yaml")
    p2.set_defaults(func=cmd_daemon)

    p3 = sub.add_parser("update-trailing", help="Actualiza el trailing de todas las posiciones abiertas")
    p3.add_argument("--config", default="config/config.yaml")
    p3.set_defaults(func=cmd_update_trailing)

    p4 = sub.add_parser("metrics", help="Calcula métricas de eficiencia a partir de logs")
    p4.add_argument("--config", default="config/config.yaml")
    p4.set_defaults(func=cmd_metrics)

    p5 = sub.add_parser("backtest", help="Backtest offline (market data de Alpaca)")
    p5.add_argument("--config", default="config/config.yaml")
    p5.add_argument("--start", required=True, help="YYYY-MM-DD")
    p5.add_argument("--end", required=True, help="YYYY-MM-DD")
    p5.set_defaults(func=cmd_backtest)

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()
