# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, Tuple, List
from .indicators import ema, atr, adx, rsi_wilder, donchian
from .symbols import instrument_for_symbol, usd_is_quote

@dataclass
class BTConfig:
    risk_per_trade: float = 0.0025
    total_risk_cap: float = 0.010
    ema_fast: int = 50
    ema_slow: int = 200
    donchian_n: int = 20
    adx_thresh: float = 20.0
    atr_stop_mult: float = 1.5
    atr_trail_mult: float = 3.0
    tp_R: float = 2.0
    rsi_len: int = 2
    rsi_low: float = 5.0
    rsi_high: float = 95.0
    max_gross_leverage: float = 2.0
    correl_window: int = 90
    correl_threshold: float = 0.80
    max_positions: int = 5
    # Para acciones, modelamos slippage como USD absoluto (no "pips").
    slippage_abs: float = 0.01
    commission_pct: float = 0.00002  # Comisión 0.002%

def _usd_is_quote(symbol: str) -> bool:
    return bool(usd_is_quote(symbol))

def _size_units(pair, entry, stop, equity, risk_frac):
    D = abs(entry - stop)
    if D<=0 or entry<=0: return 0
    if _usd_is_quote(pair):
        units = (equity * risk_frac) / D
    else:
        units = (equity * risk_frac * entry) / D
    # Safeguard: máximo 10% del equity en notional
    max_notional = equity * 0.10
    if _usd_is_quote(pair):
        current_notional = units * entry
    else:
        current_notional = units
    if current_notional > max_notional:
        units = units * (max_notional / current_notional)
    return max(0, int(np.floor(units)))

def _apply_slippage(price: float, side: str, slippage_abs: float, symbol: str) -> float:
    """
    Aplica slippage realista a la ejecución.
    Para LONG, el fill es peor (más alto), para SHORT es peor (más bajo).
    """
    s = float(slippage_abs)
    return price + s if side == "long" else price - s

def _calculate_commission(units: float, price: float, commission_pct: float, symbol: str) -> float:
    """
    Calcula comisión en USD basada en el notional.
    """
    if _usd_is_quote(symbol):
        notional = abs(units) * price
    else:
        notional = abs(units)
    return notional * commission_pct

def offline_backtest(adapter, pairs: List[str], start: str, end: str,
                     spreads: Dict[str,float], cfg: BTConfig, alignment_tz="America/New_York", daily_hour=17):
    # Descargar datos
    data = {}
    for p in pairs:
        ins = instrument_for_symbol(p)
        df = adapter.candles_between(ins, start, end, granularity="D",
                                     alignment_tz=alignment_tz, daily_hour=daily_hour, price="M")
        df["EMA50"] = ema(df["Close"], cfg.ema_fast)
        df["EMA200"] = ema(df["Close"], cfg.ema_slow)
        df["ATR"] = atr(df["High"], df["Low"], df["Close"], 14)
        df["ADX"] = adx(df["High"], df["Low"], df["Close"], 14)
        dch, dcl = donchian(df["High"], df["Low"], cfg.donchian_n)
        df["DCH"], df["DCL"] = dch, dcl
        df["RSI2"] = rsi_wilder(df["Close"], cfg.rsi_len)
        df["Ret"] = df["Close"].pct_change()
        data[p] = df.dropna().copy()

    # Timeline común
    index = sorted(set().union(*[df.index for df in data.values()]))
    index = pd.DatetimeIndex(index)

    equity = 100_000.0
    cash = equity
    positions = {}
    equity_curve=[]; trades=[]

    def notional_usd(pair, units, price):
        return units*price if _usd_is_quote(pair) else units

    def gross_leverage(notional_add=0.0):
        notional = sum([notional_usd(p, pos["units"], pos["last_price"]) for p,pos in positions.items()])
        return (abs(notional) + abs(notional_add)) / equity if equity>0 else np.inf

    returns_panel = pd.DataFrame({p: d["Ret"] for p,d in data.items()}).reindex(index).fillna(0.0)

    for i in range(1, len(index)-1):
        t = index[i]; t_prev = index[i-1]; t_next = index[i+1]

        # Actualizar PnL y salidas
        day_pnl = 0.0
        for pair in list(positions.keys()):
            df = data[pair]
            if t not in df.index: continue
            o, h, l, c = df.loc[t, ["Open","High","Low","Close"]]
            pos = positions[pair]
            pos["last_price"] = c
            atr_now = df.loc[t, "ATR"]
            if pos["side"]=="long":
                pos["peak"] = max(pos["peak"], h)
                trail = pos["peak"] - cfg.atr_trail_mult * atr_now
                pos["stop"] = max(pos["stop"], trail)
                sl_hit = l <= pos["stop"]
                tp_hit = h >= pos["tp"]
            else:
                pos["trough"] = min(pos["trough"], l)
                trail = pos["trough"] + cfg.atr_trail_mult * atr_now
                pos["stop"] = min(pos["stop"], trail)
                sl_hit = h >= pos["stop"]
                tp_hit = l <= pos["tp"]

            time_exit = (t - pos["entry_time"]).days >= 30

            exit_reason=None; exit_price=None
            if sl_hit:
                exit_reason="SL"; exit_price = pos["stop"]
            elif tp_hit:
                exit_reason="TP"; exit_price = pos["tp"]
            elif time_exit:
                exit_reason="TIME"; exit_price = o

            if exit_reason:
                # Apply slippage on exit fill (adverse)
                exit_price_filled = _apply_slippage(exit_price, pos["side"], cfg.slippage_abs, pair)
                if pos["side"]=="long":
                    pnl = pos["units"] * (exit_price_filled - pos["entry"])
                else:
                    pnl = pos["units"] * (pos["entry"] - exit_price_filled)
                if not _usd_is_quote(pair):
                    pnl = pnl / max(exit_price_filled, 1e-12)
                # Deduct round-trip commission (entry + exit)
                commission = (
                    _calculate_commission(pos["units"], pos["entry"], cfg.commission_pct, pair)
                    + _calculate_commission(pos["units"], exit_price_filled, cfg.commission_pct, pair)
                )
                pnl -= commission
                cash += pnl
                equity = cash
                # R multiple (based on initial risk before slippage)
                D = (pos["entry"] - pos["initial_sl"]) if pos["side"]=="long" else (pos["initial_sl"] - pos["entry"])
                D = max(D, 1e-12)
                risk_usd = (pos["units"] * D) if _usd_is_quote(pair) else (pos["units"] * D / max(pos["entry"],1e-12))
                r_mult = pnl / max(risk_usd, 1e-12)
                trades.append({
                    "entry_ts": pos["entry_time"], "exit_ts": t, "pair": pair, "side": pos["side"], "units": pos["units"],
                    "entry_price": pos["entry"], "exit_price": exit_price_filled, "initial_sl": pos["initial_sl"], "initial_tp": pos["tp"],
                    "pnl_usd": pnl, "r_multiple": r_mult, "hold_days": (t - pos["entry_time"]).days, "reason_exit": exit_reason
                })
                del positions[pair]
            else:
                # mark to market
                prev_close = df.loc[t_prev,"Close"] if t_prev in df.index else pos["entry"]
                if pos["side"]=="long":
                    dp = pos["units"] * (c - prev_close)
                else:
                    dp = pos["units"] * (prev_close - c)
                if not _usd_is_quote(pair):
                    dp = dp / c
                day_pnl += dp

        cash += day_pnl
        equity = cash

        # Generar señales en t y entrar en t_next (si hay datos)
        # cupo de riesgo
        used_risk = 0.0
        for p, pos in positions.items():
            D = (pos["entry"] - pos["initial_sl"]) if pos["side"]=="long" else (pos["initial_sl"] - pos["entry"])
            D = max(D, 0.0)
            if _usd_is_quote(p):
                used_risk += pos["units"] * D
            else:
                used_risk += pos["units"] * D / max(pos["entry"],1e-12)
        risk_cupo = max(0.0, cfg.total_risk_cap * equity - used_risk)

        open_count = len(positions)
        if open_count < cfg.max_positions:
            candidates=[]
            for pair, df in data.items():
                if t not in df.index or t_next not in df.index or pair in positions:
                    continue
                row = df.loc[t]
                ema50, ema200, adxv = row["EMA50"], row["EMA200"], row["ADX"]
                dch, dcl, rsi2 = row["DCH"], row["DCL"], row["RSI2"]
                long_reg = (row["Close"] > ema200) and (ema50 > ema200) and (adxv > cfg.adx_thresh)
                short_reg= (row["Close"] < ema200) and (ema50 < ema200) and (adxv > cfg.adx_thresh)
                signal=None; priority=0
                if long_reg and row["Close"]>dch: signal=("long","breakout"); priority=2
                elif short_reg and row["Close"]<dcl: signal=("short","breakout"); priority=2
                elif long_reg and rsi2<5: signal=("long","pullback"); priority=1
                elif short_reg and rsi2>95: signal=("short","pullback"); priority=1
                if signal:
                    candidates.append((pair, signal, priority))

            # Ordenar por prioridad
            candidates.sort(key=lambda x: -x[2])

            # Correlación rolling
            corr_mat = returns_panel.loc[:t].tail(cfg.correl_window).corr() if cfg.correl_window>10 else None

            for pair, (side, kind), _ in candidates:
                df = data[pair]; row_t = df.loc[t]; row_next = df.loc[t_next]

                entry = row_next["Open"]  # aproximamos fill al open del siguiente día
                entry = _apply_slippage(entry, side, cfg.slippage_abs, pair)  # adverse fill
                atr_now = row_t["ATR"]
                if side=="long":
                    stop = entry - cfg.atr_stop_mult * atr_now
                    tp   = entry + cfg.tp_R * (entry - stop)
                else:
                    stop = entry + cfg.atr_stop_mult * atr_now
                    tp   = entry - cfg.tp_R * (stop - entry)
                risk_this = cfg.risk_per_trade * (0.5 if kind=="pullback" else 1.0)
                if equity*risk_this > risk_cupo: 
                    continue
                units = _size_units(pair, entry, stop, equity, risk_this)
                if units<=0: continue

                # Correlación con abiertas
                correlated=False
                if corr_mat is not None and len(positions)>0:
                    for op, pos in positions.items():
                        if op==pair: continue
                        cval = corr_mat.get(pair, pd.Series(dtype=float)).get(op, np.nan)
                        if np.isfinite(cval) and cval > cfg.correl_threshold and pos["side"]==side:
                            correlated=True; break
                if correlated:
                    units = int(np.floor(units*0.5))
                    if units<=0: continue

                # Apalancamiento
                notional_add = units*entry if _usd_is_quote(pair) else units
                if (sum([notional_usd(p, po["units"], data[p].loc[t,"Close"]) for p, po in positions.items()]) + notional_add)/max(equity,1e-12) > cfg.max_gross_leverage:
                    allowed = cfg.max_gross_leverage*equity - sum([notional_usd(p, po["units"], data[p].loc[t,"Close"]) for p, po in positions.items()])
                    scale = max(0.0, allowed/max(notional_add,1e-12))
                    units = int(np.floor(units*scale))
                    if units<=0: continue

                # Deduct entry commission immediately
                entry_commission = _calculate_commission(units, entry, cfg.commission_pct, pair)
                cash -= entry_commission
                equity = cash

                positions[pair] = {
                    "side": side, "units": units, "entry_time": t_next,
                    "entry": entry, "initial_sl": stop, "tp": tp, "stop": stop, "last_price": entry,
                    "peak": entry if side=="long" else -np.inf,
                    "trough": entry if side=="short" else np.inf
                }
                risk_cupo -= equity*risk_this
                if len(positions)>=cfg.max_positions or risk_cupo < cfg.risk_per_trade*equity:
                    break

        equity_curve.append({"time": t, "equity": equity})

    eq = pd.DataFrame(equity_curve).set_index("time")
    tr = pd.DataFrame(trades)
    return eq, tr
