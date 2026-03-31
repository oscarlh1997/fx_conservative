#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adaptive Forex Strategy — Daemon & CLI (IBKR Edition)

Modos:
  test-connection   Verifica conexión a IBKR y muestra datos de prueba
  run-once          Ejecuta un solo ciclo de análisis + trading
  daemon            Corre continuamente: señales 1x/día + trailing cada N horas
  update-trailing   Actualiza trailing stops una vez
  sync              Sincroniza trades cerrados con el broker
  status            Muestra estado del regulador y posiciones

Uso:
  python main_forex.py test-connection --config config_forex.yaml
  python main_forex.py run-once --config config_forex.yaml
  python main_forex.py daemon --config config_forex.yaml
"""
import argparse
import logging
import time
import sys
import json
import os
import yaml
from datetime import datetime, timezone, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/forex_strategy.log", mode="a"),
    ]
)
logger = logging.getLogger(__name__)


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def create_adapter(cfg: dict):
    from ibkr_adapter import IBKRAdapter
    return IBKRAdapter(
        host=cfg.get("ibkr_host", "127.0.0.1"),
        port=cfg.get("ibkr_port", 4002),
        client_id=cfg.get("ibkr_client_id", 1),
        currency=cfg.get("account_currency", "EUR"),
    )


class SimpleTradeLogger:
    """Trade logger minimalista incluido para que funcione out-of-the-box."""

    def __init__(self, log_dir="logs", state_path="state/state.json"):
        self.log_dir = log_dir
        self.state_path = state_path
        Path(log_dir).mkdir(exist_ok=True)
        Path(state_path).parent.mkdir(exist_ok=True)

    def load_state(self) -> dict:
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def save_state(self, state: dict):
        with open(self.state_path, "w") as f:
            json.dump(state, f, indent=2, default=str)

    def log_equity(self, ts, equity):
        with open(os.path.join(self.log_dir, "equity.log"), "a") as f:
            f.write(f"{ts},{equity:.2f}\n")

    def log_signal(self, **kw):
        with open(os.path.join(self.log_dir, "signals.log"), "a") as f:
            f.write(json.dumps(kw, default=str) + "\n")

    def log_order(self, **kw):
        with open(os.path.join(self.log_dir, "orders.log"), "a") as f:
            f.write(json.dumps(kw, default=str) + "\n")

    def log_fill(self, **kw):
        with open(os.path.join(self.log_dir, "fills.log"), "a") as f:
            f.write(json.dumps(kw, default=str) + "\n")

    def log_trade_close(self, **kw):
        with open(os.path.join(self.log_dir, "closed_trades.log"), "a") as f:
            f.write(json.dumps(kw, default=str) + "\n")
        logger.info(f"Trade cerrado: {kw.get('pair')} {kw.get('side')} "
                   f"PnL={kw.get('pnl_usd', 0):.2f} R={kw.get('r_multiple', '?')}")


def create_logger(cfg):
    return SimpleTradeLogger(
        log_dir=cfg.get("log_dir", "logs"),
        state_path=cfg.get("state_path", "state/state.json"),
    )


def create_notifier(cfg):
    """Crea el notificador de Telegram (opcional)."""
    try:
        from telegram_notifier import TelegramNotifier
        return TelegramNotifier(
            token=cfg.get("telegram_token", ""),
            chat_id=cfg.get("telegram_chat_id", ""),
            enabled=cfg.get("telegram_enabled", False),
        )
    except ImportError:
        logger.info("telegram_notifier.py no encontrado, notificaciones desactivadas")
        return None


def test_connection(cfg):
    print("\n=== TEST DE CONEXION IBKR ===\n")
    print(f"Conectando a {cfg.get('ibkr_host', '127.0.0.1')}:{cfg.get('ibkr_port', 4002)}...")

    try:
        adapter = create_adapter(cfg)
        print("Conexion exitosa\n")
    except Exception as e:
        print(f"ERROR: {e}")
        print("\nVerifica que:")
        print("  1. IB Gateway esta corriendo")
        print("  2. API habilitada: Configure > Settings > API")
        print(f"  3. Puerto {cfg.get('ibkr_port', 4002)} configurado")
        print("  4. 'Read-Only API' DESACTIVADO")
        return

    try:
        equity = adapter.account_equity()
        print(f"Equity: {equity:,.2f} {cfg.get('account_currency', 'EUR')}")
    except Exception as e:
        print(f"Error obteniendo equity: {e}")

    test_pair = cfg.get("pairs_trend", ["EURUSD"])[0]
    print(f"\nDescargando datos de {test_pair}...")
    try:
        df = adapter.candles(test_pair, granularity="D", count=10)
        print(f"Ultimas 5 barras de {test_pair}:")
        print(df.tail(5).to_string())
        age = (datetime.now(timezone.utc) - df.index[-1].to_pydatetime()).total_seconds() / 86400
        print(f"\nUltima barra: {df.index[-1]}")
        print(f"Antiguedad: {age:.1f} dias {'(OK)' if age < 4 else '(ALERTA: datos obsoletos)'}")
    except Exception as e:
        print(f"Error descargando datos: {e}")

    try:
        trades = adapter.list_trades()
        print(f"\nPosiciones abiertas: {len(trades)}")
        for t in trades:
            print(f"  {t['instrument']}: {t['currentUnits']} @ {t['price']}")
    except Exception as e:
        print(f"Error listando posiciones: {e}")

    adapter.disconnect()
    print("\n=== TEST COMPLETADO ===")


def run_once(cfg):
    adapter = create_adapter(cfg)
    trade_log = create_logger(cfg)
    notifier = create_notifier(cfg)
    from forex_strategy import AdaptiveForexStrategy
    strategy = AdaptiveForexStrategy(adapter, cfg, trade_log, notifier)

    sync_result = strategy.sync_transactions()
    logger.info(f"Sync: {sync_result}")

    result = strategy.run_daily_cycle()
    logger.info(f"Result: {result}")
    adapter.disconnect()
    return result


def update_trailing(cfg):
    adapter = create_adapter(cfg)
    trade_log = create_logger(cfg)
    notifier = create_notifier(cfg)
    from forex_strategy import AdaptiveForexStrategy
    strategy = AdaptiveForexStrategy(adapter, cfg, trade_log, notifier)
    result = strategy.update_all_trailings()
    logger.info(f"Trailing update: {result}")
    adapter.disconnect()
    return result


def show_status(cfg):
    tl = create_logger(cfg)
    st = tl.load_state()
    reg = st.get("regulator", {})
    entries = st.get("entries", {})

    print("\n=== AUTORREGULADOR ===")
    for strat in ["trend", "mean_reversion"]:
        sp = reg.get(strat, {})
        trades = sp.get("trades", [])
        paused = sp.get("paused_until", "No")
        if trades:
            wins = [t for t in trades if t > 0]
            losses = [t for t in trades if t <= 0]
            wr = len(wins) / len(trades) * 100
            avg_r = sum(trades) / len(trades)
            pf = sum(wins) / (abs(sum(losses)) + 1e-12) if losses else 999
            print(f"\n  {strat}: {len(trades)} trades | WR {wr:.0f}% | "
                  f"R avg {avg_r:+.2f} | PF {pf:.2f} | Pausa: {paused}")
        else:
            print(f"\n  {strat}: sin datos")

    print(f"\n  Peak equity: {reg.get('peak_equity', 0):,.2f}")
    print(f"  Circuit breaker: {reg.get('global_paused_until', 'No')}")

    print(f"\n=== POSICIONES ({len(entries)}) ===")
    for oid, e in entries.items():
        print(f"  {e.get('pair')} {e.get('side')} [{e.get('strategy')}] "
              f"qty={e.get('units')} SL={e.get('initial_sl')} TP={e.get('initial_tp')}")

    closed_path = os.path.join(cfg.get("log_dir", "logs"), "closed_trades.log")
    if os.path.exists(closed_path):
        print(f"\n=== ULTIMOS TRADES CERRADOS ===")
        with open(closed_path) as f:
            lines = f.readlines()[-10:]
        for line in lines:
            try:
                t = json.loads(line.strip())
                r = t.get("r_multiple")
                r_str = f"{float(r):+.2f}R" if r not in (None, "?", None) else "?"
                print(f"  {t.get('pair')} {t.get('side')} "
                      f"PnL={float(t.get('pnl_usd', 0)):+.2f} {r_str}")
            except Exception:
                pass


def daemon(cfg):
    import pytz
    tz_name = cfg.get("alignment_tz", "America/New_York")
    hour = cfg.get("daily_alignment_hour", 17)
    granularity = cfg.get("granularity", "D")

    # Intervalos en minutos (más flexible)
    signal_min = cfg.get("signal_interval_minutes",
                         cfg.get("signal_interval_hours", 4) * 60)
    trail_min = cfg.get("trailing_interval_minutes",
                        cfg.get("trailing_interval_hours", 2) * 60)
    sync_min = cfg.get("sync_interval_minutes", 30)
    sleep_sec = cfg.get("loop_sleep_seconds", 30)

    logger.info(f"Daemon iniciado ({granularity}) | Senales: cada {signal_min} min | "
               f"Trail: cada {trail_min} min | Sync: cada {sync_min} min")
    logger.info(f"IBKR: {cfg.get('ibkr_host')}:{cfg.get('ibkr_port')}")
    logger.info(f"Pares: {len(set(cfg.get('pairs_trend',[]) + cfg.get('pairs_mean_reversion',[])))} instrumentos")

    notifier = create_notifier(cfg)
    if notifier:
        notifier.notify_startup()

    # Ejecutar al inicio
    last_signal = datetime.now(timezone.utc) - timedelta(minutes=signal_min)
    last_trail = datetime.now(timezone.utc) - timedelta(minutes=trail_min)
    last_sync = datetime.now(timezone.utc)
    last_signal_day = None

    while True:
        try:
            now = datetime.now(timezone.utc)
            local = now.astimezone(pytz.timezone(tz_name))
            is_weekday = local.weekday() < 5

            # === SEÑALES ===
            should_signal = False
            min_since_signal = (now - last_signal).total_seconds() / 60

            if granularity in ("D", "1D"):
                # Modo diario: una vez al día a la hora fija
                today = local.date()
                if local.hour == hour and last_signal_day != today and is_weekday:
                    should_signal = True
                    last_signal_day = today
            else:
                # Modo intradiario: cada N minutos
                if min_since_signal >= signal_min and is_weekday:
                    should_signal = True

            if should_signal:
                logger.info(f"=== CICLO DE SEÑALES ({granularity}) ===")
                try:
                    run_once(cfg)
                except Exception as e:
                    logger.error(f"Error en ciclo: {e}", exc_info=True)
                    if notifier:
                        notifier.notify_error(f"Error ciclo señales: {e}")
                last_signal = now

            # === TRAILING ===
            min_since_trail = (now - last_trail).total_seconds() / 60
            if min_since_trail >= trail_min and is_weekday:
                try:
                    update_trailing(cfg)
                except Exception as e:
                    logger.error(f"Error trailing: {e}", exc_info=True)
                last_trail = now

            # === SYNC ===
            min_since_sync = (now - last_sync).total_seconds() / 60
            if min_since_sync >= sync_min and is_weekday:
                try:
                    adapter = create_adapter(cfg)
                    tl = create_logger(cfg)
                    from forex_strategy import AdaptiveForexStrategy
                    s = AdaptiveForexStrategy(adapter, cfg, tl, notifier)
                    r = s.sync_transactions()
                    if r.get("synced", 0) > 0:
                        logger.info(f"Sync: {r}")
                    adapter.disconnect()
                except Exception as e:
                    logger.error(f"Error sync: {e}")
                last_sync = now

            time.sleep(sleep_sec)

        except KeyboardInterrupt:
            logger.info("Daemon detenido (Ctrl+C)")
            break
        except Exception as e:
            logger.error(f"Error inesperado: {e}", exc_info=True)
            time.sleep(60)


def main():
    p = argparse.ArgumentParser(description="Adaptive Forex Strategy (IBKR)")
    p.add_argument("command", choices=[
        "test-connection", "run-once", "daemon", "update-trailing", "sync", "status"
    ])
    p.add_argument("--config", default="config_forex.yaml")
    args = p.parse_args()

    Path("logs").mkdir(exist_ok=True)
    Path("state").mkdir(exist_ok=True)
    cfg = load_config(args.config)

    cmds = {
        "test-connection": test_connection,
        "run-once": run_once,
        "daemon": daemon,
        "update-trailing": update_trailing,
        "status": show_status,
        "sync": lambda c: _run_sync(c),
    }
    cmds[args.command](cfg)


def _run_sync(cfg):
    adapter = create_adapter(cfg)
    tl = create_logger(cfg)
    notifier = create_notifier(cfg)
    from forex_strategy import AdaptiveForexStrategy
    s = AdaptiveForexStrategy(adapter, cfg, tl, notifier)
    r = s.sync_transactions()
    logger.info(f"Sync: {r}")
    adapter.disconnect()


if __name__ == "__main__":
    main()
