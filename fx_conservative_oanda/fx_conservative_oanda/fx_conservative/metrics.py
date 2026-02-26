# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
from typing import Dict

def compute_trade_metrics(trades_csv: str) -> Dict:
    try:
        tr = pd.read_csv(trades_csv, parse_dates=["entry_ts","exit_ts"])
    except FileNotFoundError:
        return {}
    if tr.empty:
        return {}

    # PnL y R
    pnl = tr["pnl_usd"]
    r   = tr["r_multiple"]

    # Win/Loss
    wins = pnl[pnl>0].sum()
    losses = pnl[pnl<0].sum()

    out = {}
    out["#Trades"] = int(len(tr))
    out["WinRate"] = float((pnl>0).mean())
    out["ProfitFactor"] = float(wins/abs(losses)) if losses!=0 else None
    out["AvgR"] = float(r.mean())
    out["MedianR"] = float(r.median())
    out["AvgPnL"] = float(pnl.mean())

    # Por par
    out["ByPair"] = tr.groupby("pair")["r_multiple"].mean().to_dict()

    # Duración media
    tr["hold_days"] = (tr["exit_ts"] - tr["entry_ts"]).dt.total_seconds() / 86400.0
    out["AvgHoldDays"] = float(tr["hold_days"].mean())

    return out

def compute_equity_metrics(equity_csv: str) -> Dict:
    try:
        eq = pd.read_csv(equity_csv, parse_dates=["ts"]).sort_values("ts")
    except FileNotFoundError:
        return {}
    if eq.empty:
        return {}
    eq['nav'] = eq['nav'].astype(float)
    nav = eq['nav']
    ret = nav.pct_change().dropna()
    if ret.empty:
        return {"LastNAV": float(nav.iloc[-1])}
    ann = 252
    sharpe = (ret.mean() / (ret.std() + 1e-12)) * np.sqrt(ann)
    roll_max = nav.cummax()
    dd = nav/roll_max - 1.0
    out = {
        "LastNAV": float(nav.iloc[-1]),
        "Sharpe": float(sharpe),
        "MaxDrawdown": float(dd.min()),
    }
    return out
