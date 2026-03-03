# -*- coding: utf-8 -*-
import math, json, os
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta, timezone

from .indicators import ema, atr, adx, rsi_wilder, donchian
from .symbols import instrument_for_symbol, symbol_for_instrument, usd_is_quote
from .logger import TradeLogger
from .utils_time import parse_any_ts

@dataclass
class Signal:
    pair: str
    side: str            # "long" / "short"
    kind: str            # "breakout" / "pullback"
    close: float
    atr: float
    ema50: float
    ema200: float
    adx: float
    dch: float
    dcl: float
    rsi2: float

class FXConservativeLive:
    def __init__(self, adapter: Any, cfg, logger: TradeLogger):
        self.adp = adapter
        self.cfg = cfg
        self.log = logger

    # ------------ Datos e indicadores ------------
    def build_df(self, pair: str, count: int = 1200) -> pd.DataFrame:
        ins = instrument_for_symbol(pair)
        df = self.adp.candles(
            instrument=ins, granularity="D", count=count,
            alignment_tz=self.cfg.alignment_tz, daily_hour=self.cfg.daily_alignment_hour, price="M"
        )
        df["EMA50"] = ema(df["Close"], self.cfg.ema_fast)
        df["EMA200"] = ema(df["Close"], self.cfg.ema_slow)
        df["ATR"] = atr(df["High"], df["Low"], df["Close"], 14)
        df["ADX"] = adx(df["High"], df["Low"], df["Close"], 14)
        dch, dcl = donchian(df["High"], df["Low"], self.cfg.donchian_n)
        df["DCH"], df["DCL"] = dch, dcl
        df["RSI2"] = rsi_wilder(df["Close"], self.cfg.rsi_len)
        df["Ret"] = df["Close"].pct_change()
        return df.dropna().copy()

    # ------------ Señales ------------
    def _directional_regime(self, row: pd.Series) -> Tuple[bool, bool]:
        """
        Determina si estamos en régimen alcista o bajista.
        MEJORADO: Filtros adicionales de calidad de tendencia.
        """
        # Requisitos básicos
        long_reg  = (row["Close"] > row["EMA200"]) and (row["EMA50"] > row["EMA200"]) and (row["ADX"] > self.cfg.adx_thresh)
        short_reg = (row["Close"] < row["EMA200"]) and (row["EMA50"] < row["EMA200"]) and (row["ADX"] > self.cfg.adx_thresh)
        
        # Filtro adicional: separación mínima entre EMAs (evitar señales en rangos)
        ema_separation = abs(row["EMA50"] - row["EMA200"]) / row["EMA200"]
        min_separation = 0.002  # 0.2% mínimo de separación
        
        if ema_separation < min_separation:
            return False, False
        
        return long_reg, short_reg
    
    def _validate_signal_quality(self, sig: Signal, df: pd.DataFrame) -> bool:
        """
        Validaciones adicionales de calidad de señal para reducir falsas señales.
        Retorna True si la señal pasa todos los filtros.
        """
        row = df.iloc[-1]
        
        # 1. Validar volatilidad mínima (ATR muy bajo = mercado dormido, evitar)
        if sig.atr < row["Close"] * 0.0005:  # ATR < 0.05% del precio
            return False
        
        # 2. Validar que el ADX está en tendencia fuerte, no solo por encima del umbral
        if sig.adx < self.cfg.adx_thresh * 1.2:  # Requiere 20% más que el umbral mínimo
            return False
        
        # 3. Para breakouts, validar que realmente rompió con fuerza
        if sig.kind == "breakout":
            if sig.side == "long":
                breakout_strength = (sig.close - sig.dch) / sig.atr
                if breakout_strength < 0.1:  # Breakout debe ser al menos 10% de ATR
                    return False
            else:
                breakout_strength = (sig.dcl - sig.close) / sig.atr
                if breakout_strength < 0.1:
                    return False
        
        # 4. Para pullbacks, validar que no estamos muy cerca del SL potencial
        if sig.kind == "pullback":
            potential_sl = sig.close - self.cfg.atr_stop_mult * sig.atr if sig.side == "long" else sig.close + self.cfg.atr_stop_mult * sig.atr
            risk_reward_ratio = abs(sig.close - potential_sl) / sig.atr
            if risk_reward_ratio < 1.0:  # Riesgo/recompensa debe ser razonable
                return False
        
        # 5. Validar volumen si está disponible (proxy de liquidez)
        if "Volume" in df.columns:
            avg_volume = df["Volume"].tail(20).mean()
            if row["Volume"] < avg_volume * 0.3:  # Volumen muy bajo
                return False
        
        return True

    def compute_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """
        Genera señales de trading validadas.
        MEJORADO: Filtros de calidad adicionales.
        """
        signals: List[Signal] = []
        for pair, df in data.items():
            row = df.iloc[-1]
            long_reg, short_reg = self._directional_regime(row)
            sig: Optional[Signal] = None

            if long_reg and (row["Close"] > row["DCH"]):
                sig = Signal(pair, "long", "breakout", row["Close"], row["ATR"], row["EMA50"], row["EMA200"], row["ADX"], row["DCH"], row["DCL"], row["RSI2"])
            elif short_reg and (row["Close"] < row["DCL"]):
                sig = Signal(pair, "short", "breakout", row["Close"], row["ATR"], row["EMA50"], row["EMA200"], row["ADX"], row["DCH"], row["DCL"], row["RSI2"])
            else:
                if long_reg and (row["RSI2"] < self.cfg.rsi_low):
                    sig = Signal(pair, "long", "pullback", row["Close"], row["ATR"], row["EMA50"], row["EMA200"], row["ADX"], row["DCH"], row["DCL"], row["RSI2"])
                elif short_reg and (row["RSI2"] > self.cfg.rsi_high):
                    sig = Signal(pair, "short", "pullback", row["Close"], row["ATR"], row["EMA50"], row["EMA200"], row["ADX"], row["DCH"], row["DCL"], row["RSI2"])

            # Validar calidad de señal antes de agregarla
            if sig and self._validate_signal_quality(sig, df):
                self.log.log_signal(
                    ts=pd.Timestamp.utcnow().isoformat(),
                    pair=sig.pair, side=sig.side, kind=sig.kind, close=sig.close,
                    ema50=sig.ema50, ema200=sig.ema200, adx=sig.adx, dch=sig.dch, dcl=sig.dcl, rsi2=sig.rsi2
                )
                signals.append(sig)
        return signals

    # ------------ Sizing y utilidades ------------
    def _usd_is_quote(self, pair:str) -> bool:
        return usd_is_quote(pair)

    def size_units(self, pair: str, entry: float, stop: float, equity: float, risk_frac: float) -> int:
        """
        Calcula el tamaño de posición basado en riesgo.
        CORREGIDO: Manejo apropiado de pares donde USD no es la quote currency.
        """
        D = abs(entry - stop)
        if D <= 0 or entry <= 0:
            return 0
        
        # Para pares como EURUSD (USD es quote), el riesgo directo es: units * D
        # Para pares como USDJPY (USD es base), el riesgo es: units * D / entry
        if self._usd_is_quote(pair):
            # Ejemplo: EURUSD - riesgo_usd = units * D
            units = (equity * risk_frac) / D
        else:
            # Ejemplo: USDJPY - riesgo_usd = units * D / entry
            # Entonces: units = (equity * risk_frac) / (D / entry) = (equity * risk_frac * entry) / D
            units = (equity * risk_frac * entry) / D
        
        # Limitar a un tamaño razonable (max 10% del equity en notional como safeguard)
        max_notional = equity * 0.10
        current_notional = self.notional_usd(pair, units, entry)
        if current_notional > max_notional:
            units = units * (max_notional / current_notional)
        
        return max(0, int(math.floor(units)))

    def notional_usd(self, pair: str, units: float, price: float) -> float:
        """
        Calcula el valor notional en USD de una posición.
        CORREGIDO: Para pares donde USD es base (USDJPY), notional = units (ya está en USD)
        Para pares donde USD es quote (EURUSD), notional = units * price
        """
        if self._usd_is_quote(pair):
            # EURUSD: 100k units a 1.1000 = 110k USD
            return abs(float(units) * float(price))
        else:
            # USDJPY: 100k units = 100k USD (units ya representa USD)
            return abs(float(units))

    # Riesgo residual de trades abiertos (si conocemos SL exacto)
    def estimate_open_risk_usd(self, trades: List[dict], last_closes: Dict[str,float], equity: float) -> float:
        """
        Estima el riesgo actual de las posiciones abiertas.
        MEJORADO: Manejo correcto de conversiones USD y validaciones.
        """
        risk = 0.0
        for t in trades:
            instrument = t["instrument"]
            # mapa inverso a 'pair'
            pair = symbol_for_instrument(instrument)
            
            units = float(t.get("currentUnits", 0))
            if abs(units) < 1:  # Posición cerrada o insignificante
                continue
            
            side = "long" if units > 0 else "short"
            entry_price = float(t.get("price", last_closes.get(pair, 0.0)))
            
            if entry_price <= 0:
                # Sin precio válido, asumir riesgo conservador
                risk += self.cfg.risk_per_trade * equity
                continue
            
            sl_price = None
            # Intentar traer detalle del trade para extraer SL
            try:
                td = self.adp.trade_details(t["id"])
                sl = td.get("stopLossOrder") or {}
                sl_price = float(sl.get("price")) if "price" in sl else None
            except Exception:
                sl_price = None

            if sl_price is None or sl_price <= 0:
                # Conservador: asigna riesgo_per_trade * equity
                risk += self.cfg.risk_per_trade * equity
                continue

            # Riesgo a SL en unidades de precio
            D = abs(entry_price - sl_price)
            D = max(D, 0.0)
            
            # Calcular riesgo USD dependiendo del par
            if self._usd_is_quote(pair):
                # EURUSD: riesgo = units * D
                pos_risk = abs(units) * D
            else:
                # USDJPY: riesgo = units * D / entry_price
                pos_risk = abs(units) * D / max(entry_price, 1e-12)
            
            risk += pos_risk
            
        return risk

    def correlated_with_open(self, rets: pd.DataFrame, open_dir: Dict[str,str], candidate_pair: str, candidate_side: str) -> bool:
        if len(open_dir)==0:
            return False
        corr = rets.tail(self.cfg.correl_window).corr()
        for p, side in open_dir.items():
            if p==candidate_pair: 
                continue
            cval = corr.get(candidate_pair, pd.Series(dtype=float)).get(p, np.nan)
            if np.isfinite(cval) and cval > self.cfg.correl_threshold and side==candidate_side:
                return True
        return False

    def event_blackout_now(self, events_df: pd.DataFrame, now_utc: pd.Timestamp) -> bool:
        if events_df is None or events_df.empty or not self.cfg.enable_event_blackout:
            return False
        # Ventana +- blackout_min
        for _, r in events_df.iterrows():
            ts = parse_any_ts(str(r['timestamp']))
            blackout = int(r.get('blackout_min', 60))
            start = ts - pd.Timedelta(minutes=blackout)
            end = ts + pd.Timedelta(minutes=blackout)
            if start <= now_utc.tz_convert(ts.tzinfo) <= end:
                return True
        return False

    def load_events(self, events_file: str) -> pd.DataFrame:
        if not os.path.exists(events_file):
            return pd.DataFrame(columns=["timestamp","desc","importance","blackout_min"])
        df = pd.read_csv(events_file, comment='#')
        if 'timestamp' not in df.columns:
            return pd.DataFrame(columns=["timestamp","desc","importance","blackout_min"])
        return df

    # ------------ Ejecución del ciclo diario ------------
    def run_daily_cycle(self):
        # 1) Datos + features
        data = {pair: self.build_df(pair) for pair in self.cfg.pairs}

        # 2) Señales (sobre la última vela cerrada)
        signals = self.compute_signals(data)
        # Prioridad: breakout antes que pullback
        signals.sort(key=lambda s: 2 if s.kind=="breakout" else 1, reverse=True)

        # 3) Estado de cuenta / posiciones
        equity = self.adp.account_equity()
        open_trades = self.adp.list_trades()
        open_dir = {}
        for t in open_trades:
            pair = symbol_for_instrument(t["instrument"])
            side = "long" if float(t.get("currentUnits",0))>0 else "short"
            open_dir[pair] = side

        # 4) Eventos (blackout)
        events_df = self.load_events(self.cfg.events_file)
        now_utc = pd.Timestamp.utcnow().tz_localize("UTC")
        if self.event_blackout_now(events_df, now_utc):
            # Registrar y salir sin abrir
            return {"opened": 0, "signals": [(s.pair, s.side, s.kind) for s in signals], "reason":"blackout_events"}

        # 5) Correlaciones
        rets = pd.DataFrame({p: d["Ret"] for p,d in data.items()})

        # 6) Cupo de riesgo exacto
        last_close_map = {p: d["Close"].iloc[-1] for p,d in data.items()}
        used_risk_usd = self.estimate_open_risk_usd(open_trades, last_close_map, equity)
        risk_cupo = max(0.0, self.cfg.total_risk_cap * equity - used_risk_usd)

        opened = 0
        # 7) Apalancamiento actual aprox
        notional_open = 0.0
        for t in open_trades:
            pair = symbol_for_instrument(t["instrument"])
            price = last_close_map.get(pair, float(t.get("price", 0.0)))
            units = abs(float(t.get("currentUnits", 0.0)))
            notional_open += self.notional_usd(pair, units, price)

        # 8) Por cada señal (breakout primero)
        for sig in signals:
            if sig.pair in open_dir:
                continue  # ya hay posición en ese par
            # SL/TP en función de ATR
            if sig.side=="long":
                stop = sig.close - self.cfg.atr_stop_mult * sig.atr
                tp   = sig.close + self.cfg.tp_R * (sig.close - stop)
            else:
                stop = sig.close + self.cfg.atr_stop_mult * sig.atr
                tp   = sig.close - self.cfg.tp_R * (stop - sig.close)

            risk_this = self.cfg.risk_per_trade * (0.5 if sig.kind=="pullback" else 1.0)
            if equity * risk_this > risk_cupo:
                continue

            units = self.size_units(sig.pair, sig.close, stop, equity, risk_this)
            if units <= 0:
                continue

            # Correlación
            if self.correlated_with_open(rets, open_dir, sig.pair, sig.side):
                units = max(0, int(math.floor(units * 0.5)))
                if units <= 0:
                    continue

            # Apalancamiento: capar si excede
            notional_add = self.notional_usd(sig.pair, units, sig.close)
            if (notional_open + notional_add) / max(equity,1e-9) > self.cfg.max_gross_leverage:
                allowed = self.cfg.max_gross_leverage * equity - notional_open
                scale = max(0.0, allowed / max(notional_add,1e-9))
                units = max(0, int(math.floor(units * scale)))
                notional_add = self.notional_usd(sig.pair, units, sig.close)
                if units <= 0:
                    continue

            # Enviar orden
            resp = self.adp.place_bracket_market(
                instrument=instrument_for_symbol(sig.pair), side=sig.side, units=units,
                sl_price=stop, tp_price=tp,
                client_tag="fx_cons_v1", client_comment=f"{sig.kind}"
            )
            # Log
            self.log.log_order(
                ts=pd.Timestamp.utcnow().isoformat(), pair=sig.pair, side=sig.side, kind=sig.kind,
                units=units, sl=stop, tp=tp, atr=sig.atr, entry_hint=sig.close, response=resp
            )

            # Intentar extraer fill inmediato (Market FOK)
            try:
                # Respuesta suele incluir 'orderFillTransaction'
                oft = resp.get("orderFillTransaction") or {}
                trade_opened = oft.get("tradeOpened") or {}
                trade_id = trade_opened.get("tradeID") or oft.get("tradeID")
                fill_price = float(oft.get("price")) if "price" in oft else None
                if trade_id and fill_price is not None:
                    self.log.log_fill(
                        ts=pd.Timestamp.utcnow().isoformat(), tradeID=str(trade_id), pair=sig.pair,
                        side=sig.side, units=units, price=fill_price, fill_json=oft
                    )
                    # Registrar entrada en estado para luego calcular R al cierre
                    st = self.log.load_state()
                    entries = st.get("entries", {})
                    entries[str(trade_id)] = {
                        "pair": sig.pair, "side": sig.side, "units": units,
                        "entry_price": fill_price, "initial_sl": stop, "initial_tp": tp,
                        "entry_ts": pd.Timestamp.utcnow().isoformat()
                    }
                    st["entries"] = entries
                    # actualizar last txn id si existe
                    ltid = self.adp.last_transaction_id()
                    st["last_transaction_id"] = ltid
                    self.log.save_state(st)
            except Exception:
                pass

            # Fallback para brokers que no devuelven un "fill" tipo OANDA (ej: Alpaca).
            # Guardamos una "entrada pendiente" identificada por el order id.
            try:
                if isinstance(resp, dict):
                    oid = resp.get("id")
                    sym = resp.get("symbol") or resp.get("instrument")
                    filled_avg = resp.get("filled_avg_price")
                else:
                    oid = getattr(resp, "id", None)
                    sym = getattr(resp, "symbol", None) or getattr(resp, "instrument", None)
                    filled_avg = getattr(resp, "filled_avg_price", None)

                if oid:
                    st = self.log.load_state()
                    entries = st.get("entries", {})
                    if str(oid) not in entries:
                        entries[str(oid)] = {
                            "pair": sig.pair,
                            "side": sig.side,
                            "units": units,
                            "entry_price": float(filled_avg) if filled_avg not in (None, "") else None,
                            "entry_hint": float(sig.close),
                            "initial_sl": float(stop),
                            "initial_tp": float(tp),
                            "entry_ts": pd.Timestamp.utcnow().isoformat(),
                            "instrument": sym or instrument_for_symbol(sig.pair),
                        }
                        st["entries"] = entries
                        st["last_transaction_id"] = self.adp.last_transaction_id()
                        self.log.save_state(st)
            except Exception:
                pass

            # Actualizar notional_open y risk_cupo
            notional_open += notional_add
            risk_cupo = max(0.0, risk_cupo - equity * risk_this)
            opened += 1
            if opened >= self.cfg.max_positions:
                break

        # Registrar NAV
        self.log.log_equity(pd.Timestamp.utcnow().isoformat(), equity)
        return {"opened": opened, "signals": [(s.pair, s.side, s.kind) for s in signals]}

    # ------------ Trailing: actualizar todos los abiertos con ATR*mult ------------
    def update_all_trailings(self):
        """
        Actualiza trailing stops de todas las posiciones abiertas.
        MEJORADO: Implementa breakeven automático y trailing más inteligente.
        """
        # Necesitamos ATR actual por par
        data = {pair: self.build_df(pair) for pair in self.cfg.pairs}
        latest_atr = {pair: df["ATR"].iloc[-1] for pair, df in data.items()}
        last_close = {pair: df["Close"].iloc[-1] for pair, df in data.items()}

        trades = self.adp.list_trades()
        updated = 0
        moved_to_breakeven = 0
        
        for t in trades:
            ins = t["instrument"]
            pair = symbol_for_instrument(ins)
            
            atr_now = latest_atr.get(pair)
            if atr_now is None: 
                continue
            
            current_price = last_close.get(pair)
            if current_price is None:
                continue
            
            units = float(t.get("currentUnits", 0))
            if abs(units) < 1:
                continue
            
            side = "long" if units > 0 else "short"
            entry_price = float(t.get("price", 0))
            
            if entry_price <= 0:
                continue
            
            # Obtener SL actual
            try:
                td = self.adp.trade_details(t["id"])
                current_sl = None
                sl_order = td.get("stopLossOrder")
                
                if sl_order and "price" in sl_order:
                    current_sl = float(sl_order["price"])
                
                # Calcular profit en ATRs
                if side == "long":
                    profit_atr = (current_price - entry_price) / atr_now if atr_now > 0 else 0
                else:
                    profit_atr = (entry_price - current_price) / atr_now if atr_now > 0 else 0
                
                # BREAKEVEN: Si estamos 1.5R en profit, mover SL a breakeven + pequeño profit
                if profit_atr >= 1.5:
                    breakeven_price = entry_price + (0.3 * atr_now if side == "long" else -0.3 * atr_now)
                    
                    # Solo actualizar si el nuevo BE es mejor que el SL actual
                    should_update = False
                    if current_sl is None:
                        should_update = True
                    elif side == "long" and breakeven_price > current_sl:
                        should_update = True
                    elif side == "short" and breakeven_price < current_sl:
                        should_update = True
                    
                    if should_update:
                        try:
                            # Delegar al adapter: OANDA usa TradeCRCDO, otros brokers pueden hacer replace de la orden SL.
                            self.adp.set_stop_loss(t["id"], breakeven_price)
                            moved_to_breakeven += 1
                            continue  # No aplicar trailing si movimos a BE
                        except Exception as e:
                            # Si falla, continuar con trailing normal
                            pass
                
                # TRAILING NORMAL: Solo si no estamos en breakeven
                distance = self.cfg.atr_trail_mult * atr_now
                
                # Asegurar que el trailing no está demasiado cerca del precio actual
                min_distance = atr_now * 0.8  # Mínimo 80% de ATR
                distance = max(distance, min_distance)
                
                try:
                    self.adp.update_trailing_stop(t["id"], trail_distance=distance)
                    updated += 1
                except Exception as e:
                    # ignora fallo puntual
                    pass
                    
            except Exception as e:
                # Si no podemos obtener detalles, skip
                continue
                
        return {"updated_trailings": updated, "moved_to_breakeven": moved_to_breakeven}

    # ------------ Sincronizar transacciones y cerrar trades en log ------------
    def sync_transactions(self):
        # If the broker adapter knows how to sync, delegate (Alpaca, etc.).
        adp_sync = getattr(self.adp, "sync_transactions", None)
        if callable(adp_sync):
            try:
                return adp_sync(self.log)
            except TypeError:
                # Adapter has a different signature; fall back to legacy OANDA flow.
                pass

        st = self.log.load_state()
        last_id = st.get("last_transaction_id")

        # Si nunca hemos guardado un id, lee el actual sin procesar histórico
        if last_id is None:
            st["last_transaction_id"] = self.adp.last_transaction_id()
            self.log.save_state(st)
            return {"synced": 0, "note": "initialized last_transaction_id"}

        transactions = self.adp.transactions_since(last_id)
        if not transactions:
            return {"synced": 0}

        # Actualiza last_transaction_id al último
        new_last = transactions[-1].get("id", last_id)
        st["last_transaction_id"] = new_last

        entries = st.get("entries", {})
        synced = 0
        for tx in transactions:
            ttype = tx.get("type","").upper()
            # Cuando se cierra un trade por SL/TP o cierre manual,
            # OANDA emite transacciones que incluyen info en 'tradesClosed' o campos similares.
            trades_closed = tx.get("tradesClosed") or []
            for c in trades_closed:
                trade_id = str(c.get("tradeID"))
                realized_pl = float(c.get("realizedPL", 0.0))
                price = float(c.get("price", tx.get("price", 0.0)))
                units = float(c.get("units", 0.0))
                # Buscar entrada registrada
                ent = entries.pop(trade_id, None)
                if ent is None:
                    # Desconocido: registra de forma básica
                    self.log.log_trade_close(
                        entry_ts=None, exit_ts=tx.get("time"), pair=tx.get("instrument","?"),
                        side=None, units=units, entry_price=None, exit_price=price,
                        initial_sl=None, initial_tp=None, pnl_usd=realized_pl, r_multiple=None,
                        hold_days=None, reason_exit=ttype, trade_id=trade_id
                    )
                else:
                    # Calcular R múltiple: pnl_usd / riesgo_inicial_usd
                    pair = ent["pair"]; side = ent["side"]
                    entry_price = float(ent["entry_price"]); initial_sl = float(ent["initial_sl"]); initial_tp = float(ent["initial_tp"])
                    # riesgo inicial en USD
                    D = (entry_price - initial_sl) if side=="long" else (initial_sl - entry_price)
                    D = max(D, 1e-12)
                    if self._usd_is_quote(pair):
                        risk_usd = abs(float(ent["units"])) * D
                    else:
                        risk_usd = abs(float(ent["units"])) * D / max(entry_price,1e-12)
                    r_mult = realized_pl / max(risk_usd, 1e-12)
                    # Duración
                    import pandas as pd
                    entry_ts = pd.to_datetime(ent["entry_ts"])
                    exit_ts = pd.to_datetime(tx.get("time"))
                    hold_days = (exit_ts - entry_ts).total_seconds()/86400.0

                    self.log.log_trade_close(
                        entry_ts=entry_ts.isoformat(), exit_ts=exit_ts.isoformat(),
                        pair=pair, side=side, units=ent["units"], entry_price=entry_price,
                        exit_price=price, initial_sl=initial_sl, initial_tp=initial_tp,
                        pnl_usd=realized_pl, r_multiple=r_mult, hold_days=hold_days,
                        reason_exit=ttype, trade_id=trade_id
                    )
                synced += 1

        st["entries"] = entries
        self.log.save_state(st)
        return {"synced": synced}
