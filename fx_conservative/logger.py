# -*- coding: utf-8 -*-
import os, csv, json, datetime as dt
from typing import Dict, Any

class TradeLogger:
    def __init__(self, log_dir: str, state_path: str):
        self.log_dir = log_dir
        self.state_path = state_path
        os.makedirs(self.log_dir, exist_ok=True)
        # Only try to create the state directory when there actually is one
        state_dir = os.path.dirname(os.path.abspath(self.state_path))
        if state_dir:
            os.makedirs(state_dir, exist_ok=True)
        # Asegurar cabeceras
        self._ensure_csv("signals.csv", [
            "ts","pair","side","kind","close","ema50","ema200","adx","dch","dcl","rsi2"
        ])
        self._ensure_csv("orders.csv", [
            "ts","pair","side","kind","units","sl","tp","atr","entry_hint","order_response_json"
        ])
        self._ensure_csv("fills.csv", [
            "ts","tradeID","pair","side","units","price","fill_json"
        ])
        self._ensure_csv("trades.csv", [
            "entry_ts","exit_ts","pair","side","units","entry_price","exit_price",
            "initial_sl","initial_tp","pnl_usd","r_multiple","hold_days","reason_exit","trade_id"
        ])
        self._ensure_csv("equity.csv", [
            "ts","nav"
        ])

    def _ensure_csv(self, name, headers):
        path = os.path.join(self.log_dir, name)
        if not os.path.exists(path):
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f); w.writerow(headers)

    def write_row(self, name, row):
        path = os.path.join(self.log_dir, name)
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(row)

    def log_signal(self, **kwargs):
        self.write_row("signals.csv", [
            kwargs.get("ts"), kwargs.get("pair"), kwargs.get("side"), kwargs.get("kind"),
            kwargs.get("close"), kwargs.get("ema50"), kwargs.get("ema200"),
            kwargs.get("adx"), kwargs.get("dch"), kwargs.get("dcl"), kwargs.get("rsi2")
        ])

    def log_order(self, **kwargs):
        self.write_row("orders.csv", [
            kwargs.get("ts"), kwargs.get("pair"), kwargs.get("side"), kwargs.get("kind"),
            kwargs.get("units"), kwargs.get("sl"), kwargs.get("tp"),
            kwargs.get("atr"), kwargs.get("entry_hint"),
            json.dumps(kwargs.get("response", {}), ensure_ascii=False)
        ])

    def log_fill(self, **kwargs):
        self.write_row("fills.csv", [
            kwargs.get("ts"), kwargs.get("tradeID"), kwargs.get("pair"),
            kwargs.get("side"), kwargs.get("units"), kwargs.get("price"),
            json.dumps(kwargs.get("fill_json", {}), ensure_ascii=False)
        ])

    def log_trade_close(self, **kwargs):
        self.write_row("trades.csv", [
            kwargs.get("entry_ts"), kwargs.get("exit_ts"), kwargs.get("pair"),
            kwargs.get("side"), kwargs.get("units"), kwargs.get("entry_price"),
            kwargs.get("exit_price"), kwargs.get("initial_sl"), kwargs.get("initial_tp"),
            kwargs.get("pnl_usd"), kwargs.get("r_multiple"), kwargs.get("hold_days"),
            kwargs.get("reason_exit"), kwargs.get("trade_id")
        ])

    def log_equity(self, ts, nav):
        self.write_row("equity.csv", [ts, nav])

    # ---- Estado persistente (last_transaction_id, registros de entrada por trade_id) ----
    def load_state(self) -> Dict[str, Any]:
        if not os.path.exists(self.state_path):
            return {"last_transaction_id": None, "entries": {}}
        with open(self.state_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_state(self, state: Dict[str, Any]):
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
