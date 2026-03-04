# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd


class AlpacaAdapter:
    """
    Alpaca adapter for US equities via Trading API + Stock Historical Data.

    Configuration:
    - Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables.
    - Set ALPACA_PAPER=true (default) for paper trading, false for live.
    - symbols in config.yaml should be valid US equity tickers (SPY, QQQ, etc.).

    Notes:
    - FX pairs (EURUSD, etc.) are NOT supported by Alpaca's Trading API.
    - Trailing/breakeven stops are implemented by replacing the existing stop-loss
      order price once per daily cycle (not a native trailing distance).
    - Bracket orders require Margin or greater account for short side.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper: Optional[bool] = None,
    ):
        # Load .env file if python-dotenv is available (optional dependency)
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        try:
            from alpaca.trading.client import TradingClient
            from alpaca.data.historical import StockHistoricalDataClient
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Falta dependencia 'alpaca-py'. Instala requirements.txt antes de usar."
            ) from e

        self._TradingClient = TradingClient
        self._StockHistoricalDataClient = StockHistoricalDataClient

        api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY", "")
        if paper is None:
            paper = os.environ.get("ALPACA_PAPER", "true").strip().lower() in ("1", "true", "yes", "y")

        if not (api_key and secret_key):
            raise RuntimeError(
                "Faltan credenciales Alpaca. Define ALPACA_API_KEY y ALPACA_SECRET_KEY "
                "como variables de entorno o en un archivo .env en el directorio de trabajo."
            )

        self.trading = self._TradingClient(api_key, secret_key, paper=bool(paper))
        self.data = self._StockHistoricalDataClient(api_key, secret_key)

    # -------- Datos de velas --------
    def candles(
        self,
        instrument: str,
        granularity: str = "D",
        count: int = 2000,
        alignment_tz: str = "America/New_York",
        daily_hour: int = 16,
        price: str = "M",
    ) -> pd.DataFrame:
        """
        Descarga velas diarias de Alpaca para un símbolo de renta variable.

        Args:
            instrument: Símbolo del activo (p.ej. SPY, QQQ).
            granularity: Solo se soporta 'D' o '1D' (barras diarias).
            count: Número máximo de barras a solicitar.
            alignment_tz: Zona horaria de alineación (informativo; Alpaca usa ET internamente).
            daily_hour: Hora de cierre de sesión (informativo; Alpaca usa el cierre del mercado).
            price: Ignorado; siempre se usa precio de mercado (OHLCV).

        Returns:
            DataFrame con columnas Open, High, Low, Close, Volume indexado por timestamp UTC.
        """
        if granularity not in ("D", "1D"):
            raise ValueError(
                f"AlpacaAdapter solo soporta granularidad diaria ('D' o '1D'). "
                f"Recibido: '{granularity}'"
            )

        # Request a window wide enough to account for weekends and holidays.
        # count * 1.5 ensures we always get at least 'count' trading days.
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=int(max(60, count * 1.5)))

        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        req = StockBarsRequest(
            symbol_or_symbols=instrument,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            limit=int(count),
        )
        bars = self.data.get_stock_bars(req)

        # alpaca-py returns a BarSet; access .df property
        df = getattr(bars, "df", None)
        if df is None or df.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        # Normalize MultiIndex (symbol, timestamp) into a flat OHLCV frame
        if isinstance(df.index, pd.MultiIndex):
            df = df.reset_index()
            # Filter to only this symbol in case multiple symbols were returned
            sym_col = "symbol" if "symbol" in df.columns else df.columns[0]
            df = df[df[sym_col] == instrument].copy()
            ts_col = "timestamp" if "timestamp" in df.columns else df.columns[1]
            df = df.rename(columns={ts_col: "time"})
            df = df.set_index("time")
        else:
            df = df.copy()

        df.index = pd.to_datetime(df.index, utc=True)
        df = df.sort_index()

        # Rename to strategy-expected capitalised column names
        col_map = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
        df = df.rename(columns=col_map)

        out = pd.DataFrame(index=df.index)
        for col in ("Open", "High", "Low", "Close"):
            out[col] = df[col].astype(float).values
        out["Volume"] = df["Volume"].astype(float).values if "Volume" in df.columns else 0.0

        # Return only the last 'count' bars
        return out.tail(int(count))

    def candles_between(
        self,
        instrument: str,
        start: str,
        end: str,
        granularity: str = "D",
        alignment_tz: str = "America/New_York",
        daily_hour: int = 16,
        price: str = "M",
    ) -> pd.DataFrame:
        """
        Descarga velas diarias entre dos fechas (útil para backtest offline).
        """
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        start_dt = pd.to_datetime(start, utc=True).to_pydatetime()
        end_dt = pd.to_datetime(end, utc=True).to_pydatetime()

        req = StockBarsRequest(
            symbol_or_symbols=instrument,
            timeframe=TimeFrame.Day,
            start=start_dt,
            end=end_dt,
        )
        bars = self.data.get_stock_bars(req)
        df = getattr(bars, "df", None)
        if df is None or df.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        if isinstance(df.index, pd.MultiIndex):
            df = df.reset_index()
            sym_col = "symbol" if "symbol" in df.columns else df.columns[0]
            df = df[df[sym_col] == instrument].copy()
            ts_col = "timestamp" if "timestamp" in df.columns else df.columns[1]
            df = df.rename(columns={ts_col: "time"})
            df = df.set_index("time")
        else:
            df = df.copy()

        df.index = pd.to_datetime(df.index, utc=True)
        df = df.sort_index()
        col_map = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
        df = df.rename(columns=col_map)

        out = pd.DataFrame(index=df.index)
        for col in ("Open", "High", "Low", "Close"):
            out[col] = df[col].astype(float).values
        out["Volume"] = df["Volume"].astype(float).values if "Volume" in df.columns else 0.0
        return out

    # -------- Cuenta / equity --------
    def account_equity(self) -> float:
        acct = self.trading.get_account()
        equity = float(getattr(acct, "equity", 0.0))
        if equity <= 0:
            raise ValueError(f"Equity invalido: {equity}")
        return equity

    # -------- Posiciones --------
    def list_trades(self) -> List[Dict[str, Any]]:
        positions = self.trading.get_all_positions()
        out: List[Dict[str, Any]] = []
        for p in positions:
            sym = str(getattr(p, "symbol"))
            qty = float(getattr(p, "qty", 0.0))
            side = str(getattr(p, "side", "long")).lower()
            signed_qty = qty if side == "long" else -abs(qty)
            out.append(
                {
                    "id": sym,  # Use symbol as stable id (netted position per symbol)
                    "instrument": sym,
                    "currentUnits": signed_qty,
                    "price": float(getattr(p, "avg_entry_price", 0.0)),
                    "currentPrice": float(getattr(p, "current_price", 0.0)),
                }
            )
        return out

    # -------- Ordenes --------
    def place_bracket_market(
        self,
        instrument: str,
        side: str,
        units: float,
        sl_price: float,
        tp_price: float,
        client_tag: Optional[str] = None,
        client_comment: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Envía una orden de mercado con bracket (stop-loss + take-profit) a Alpaca.

        Args:
            instrument: Símbolo (p.ej. SPY).
            side: 'long' o 'short'.
            units: Cantidad de acciones (puede ser fraccionaria si la cuenta lo soporta).
            sl_price: Precio de stop-loss.
            tp_price: Precio de take-profit.
        """
        if units <= 0:
            raise ValueError(f"Units debe ser positivo: {units}")
        if sl_price <= 0 or tp_price <= 0:
            raise ValueError(f"SL/TP deben ser positivos: SL={sl_price}, TP={tp_price}")
        if side not in ("long", "short"):
            raise ValueError(f"side debe ser 'long' o 'short', recibido: {side}")

        # Validate SL/TP direction relative to side
        if side == "long" and sl_price >= tp_price:
            raise ValueError(
                f"Para LONG el SL ({sl_price}) debe ser < TP ({tp_price})"
            )
        if side == "short" and sl_price <= tp_price:
            raise ValueError(
                f"Para SHORT el SL ({sl_price}) debe ser > TP ({tp_price})"
            )

        from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest

        order_side = OrderSide.BUY if side == "long" else OrderSide.SELL

        # Use fractional qty if units is non-integer, else integer.
        qty = float(units) if units != int(units) else int(units)

        req = MarketOrderRequest(
            symbol=instrument,
            qty=qty,
            side=order_side,
            # GTC keeps exit legs working across sessions.
            time_in_force=TimeInForce.GTC,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(float(tp_price), 4)),
            stop_loss=StopLossRequest(stop_price=round(float(sl_price), 4)),
        )
        o = self.trading.submit_order(req)

        # Normalize response to dict for logger compatibility.
        if hasattr(o, "model_dump"):
            return o.model_dump()
        if hasattr(o, "dict"):
            return o.dict()
        return {
            "id": str(getattr(o, "id", "")),
            "symbol": instrument,
            "side": side,
            "qty": qty,
            "status": str(getattr(o, "status", "submitted")),
        }

    # -------- Detalles / SL/TP management --------
    def trade_details(self, trade_id: str) -> Dict[str, Any]:
        """
        For Alpaca, trade_id is the symbol. We find the current stop-loss order (if any).
        Returns a dict shaped like the strategy expects: stopLossOrder/takeProfitOrder (best-effort).
        """
        symbol = str(trade_id)

        # Get open orders for this symbol; bracket legs are represented as separate orders.
        try:
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus

            req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol], nested=False)
            orders = self.trading.get_orders(req)
        except Exception:
            orders = self.trading.get_orders()
            orders = [o for o in orders if str(getattr(o, "symbol", "")) == symbol and str(getattr(o, "status", "")).lower() in ("new", "accepted", "open")]

        stop_o = None
        tp_o = None
        for o in orders:
            otype = str(getattr(o, "type", "")).lower()
            if "stop" in otype and stop_o is None:
                stop_o = o
            if ("limit" in otype or "take_profit" in otype) and tp_o is None:
                tp_o = o

        out: Dict[str, Any] = {}
        if stop_o is not None:
            sp = getattr(stop_o, "stop_price", None)
            if sp is not None:
                out["stopLossOrder"] = {"price": str(sp), "orderID": str(getattr(stop_o, "id", ""))}
        if tp_o is not None:
            lp = getattr(tp_o, "limit_price", None)
            if lp is not None:
                out["takeProfitOrder"] = {"price": str(lp), "orderID": str(getattr(tp_o, "id", ""))}
        return out

    def set_stop_loss(self, trade_id: str, stop_price: float) -> Dict[str, Any]:
        """
        Replace the existing stop-loss order for a symbol.
        """
        if stop_price <= 0:
            raise ValueError(f"stop_price debe ser positivo: {stop_price}")

        td = self.trade_details(trade_id)
        slo = td.get("stopLossOrder") or {}
        oid = slo.get("orderID")
        if not oid:
            raise RuntimeError(f"No se encontro stopLossOrder abierto para {trade_id}")

        from alpaca.trading.requests import ReplaceOrderRequest

        rep = ReplaceOrderRequest(stop_price=float(stop_price))
        o = self.trading.replace_order_by_id(str(oid), rep)
        if hasattr(o, "model_dump"):
            return o.model_dump()
        if hasattr(o, "dict"):
            return o.dict()
        return {"id": getattr(o, "id", None)}

    def update_trailing_stop(self, trade_id: str, trail_distance: float) -> Dict[str, Any]:
        """
        Strategy passes a distance in price units. We approximate trailing by moving the stop-loss
        price once per day based on current mark price.
        """
        if trail_distance <= 0:
            raise ValueError(f"trail_distance debe ser positivo: {trail_distance}")

        symbol = str(trade_id)
        pos = None
        for p in self.trading.get_all_positions():
            if str(getattr(p, "symbol", "")) == symbol:
                pos = p
                break
        if pos is None:
            raise RuntimeError(f"No hay posicion abierta para {symbol}")

        side = str(getattr(pos, "side", "long")).lower()
        cur = float(getattr(pos, "current_price", 0.0))
        if cur <= 0:
            raise RuntimeError(f"Precio actual invalido para {symbol}: {cur}")

        new_sl = cur - float(trail_distance) if side == "long" else cur + float(trail_distance)
        return self.set_stop_loss(symbol, new_sl)

    # -------- Transacciones (best-effort) --------
    def last_transaction_id(self) -> str:
        # Use a timestamp-based marker.
        return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()

    def transactions_since(self, from_id: str) -> List[Dict[str, Any]]:
        # Not implemented: transaction feed does not map 1:1.
        return []

    def sync_transactions(self, trade_logger) -> Dict[str, Any]:
        """
        Sync fills/closures for entries stored in TradeLogger state.

        State format (created by strategy fallback):
          entries[order_id] = {
            pair, side, units, entry_price|None, entry_hint, initial_sl, initial_tp,
            entry_ts, instrument
          }

        We:
        - For pending entries: fetch parent order and set entry_price when filled.
        - For filled entries: if the position is no longer open, find the filled exit leg (TP/SL),
          compute PnL, log trade close, and remove from state.
        """
        st = trade_logger.load_state()
        entries = st.get("entries", {}) or {}
        if not isinstance(entries, dict):
            entries = {}

        def _to_dict(obj: Any) -> Dict[str, Any]:
            if obj is None:
                return {}
            if isinstance(obj, dict):
                return obj
            if hasattr(obj, "model_dump"):
                try:
                    return obj.model_dump()
                except Exception:
                    pass
            if hasattr(obj, "dict"):
                try:
                    return obj.dict()
                except Exception:
                    pass
            d: Dict[str, Any] = {}
            for k in dir(obj):
                if k.startswith("_"):
                    continue
                try:
                    v = getattr(obj, k)
                except Exception:
                    continue
                if isinstance(v, (str, int, float, bool, type(None))):
                    d[k] = v
            return d

        def _parse_ts(x: Any) -> Optional[pd.Timestamp]:
            if x in (None, ""):
                return None
            try:
                return pd.to_datetime(str(x), utc=True)
            except Exception:
                return None

        def _get_order(order_id: str, nested: Optional[bool] = None):
            # alpaca-py versions differ; try best-effort.
            if nested is None:
                return self.trading.get_order_by_id(str(order_id))
            try:
                return self.trading.get_order_by_id(str(order_id), nested=bool(nested))
            except TypeError:
                return self.trading.get_order_by_id(str(order_id))

        def _has_open_position(symbol: str) -> bool:
            try:
                for p in self.trading.get_all_positions():
                    if str(getattr(p, "symbol", "")) == symbol:
                        qty = float(getattr(p, "qty", 0.0))
                        if abs(qty) > 0:
                            return True
                return False
            except Exception:
                return False

        synced = 0
        updated_entries = 0

        # Work on a stable list because we may delete entries.
        for oid in list(entries.keys()):
            ent = entries.get(oid) or {}
            if not isinstance(ent, dict):
                continue

            symbol = str(ent.get("instrument") or ent.get("pair") or "")
            side = str(ent.get("side") or "").lower()
            units = float(ent.get("units") or 0.0)
            entry_price = ent.get("entry_price", None)
            entry_hint = ent.get("entry_hint", None)
            initial_sl = ent.get("initial_sl", None)
            initial_tp = ent.get("initial_tp", None)
            entry_ts = _parse_ts(ent.get("entry_ts"))

            if not symbol or units <= 0 or side not in ("long", "short"):
                continue

            # 1) Populate entry fill price if missing.
            if entry_price in (None, "", 0, 0.0):
                try:
                    o = _get_order(oid, nested=False)
                    od = _to_dict(o)
                    status = str(od.get("status", getattr(o, "status", ""))).lower()
                    fpx = od.get("filled_avg_price", getattr(o, "filled_avg_price", None))
                    fts = od.get("filled_at", getattr(o, "filled_at", None))
                    if status == "filled" and fpx not in (None, ""):
                        ent["entry_price"] = float(fpx)
                        if entry_ts is None and fts not in (None, ""):
                            ent["entry_ts"] = str(fts)
                        entries[oid] = ent
                        updated_entries += 1
                except Exception:
                    pass

                # If still missing, we can't compute PnL yet.
                if ent.get("entry_price") in (None, "", 0, 0.0):
                    continue

            # 2) If position still open, nothing to close.
            if _has_open_position(symbol):
                continue

            # 3) Position is closed: find exit order/price (filled leg).
            exit_price = None
            exit_ts = None
            reason = "CLOSE"
            try:
                o = _get_order(oid, nested=True)
                od = _to_dict(o)
                legs = od.get("legs") or getattr(o, "legs", None) or []

                # Legs can be list of objects or dicts.
                for leg in legs or []:
                    ld = _to_dict(leg)
                    lstatus = str(ld.get("status", "")).lower()
                    if lstatus != "filled":
                        continue
                    ltype = str(ld.get("type", "")).lower()
                    px = ld.get("filled_avg_price") or ld.get("filled_avg_price", None)
                    ts = ld.get("filled_at") or ld.get("filled_at", None) or ld.get("updated_at") or ld.get("submitted_at")
                    if px not in (None, ""):
                        exit_price = float(px)
                        exit_ts = _parse_ts(ts)
                        if "stop" in ltype:
                            reason = "STOP_LOSS"
                        elif "limit" in ltype:
                            reason = "TAKE_PROFIT"
                        else:
                            reason = "EXIT"
                        break
            except Exception:
                pass

            # Fallback: if no filled leg found, best-effort from most recent closed filled order for symbol
            # that happened after the entry timestamp (avoid matching older trades).
            if exit_price is None:
                try:
                    from alpaca.trading.requests import GetOrdersRequest
                    from alpaca.trading.enums import QueryOrderStatus

                    req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, symbols=[symbol], nested=False)
                    orders = self.trading.get_orders(req)
                except Exception:
                    orders = []

                ent_ts = _parse_ts(ent.get("entry_ts"))
                best = None
                best_ts = None
                for o2 in orders or []:
                    od2 = _to_dict(o2)
                    if str(od2.get("status", "")).lower() != "filled":
                        continue
                    px = od2.get("filled_avg_price")
                    if px in (None, ""):
                        continue
                    ts = _parse_ts(od2.get("filled_at") or od2.get("updated_at") or od2.get("submitted_at"))
                    if ts is None:
                        continue
                    if ent_ts is not None and ts < ent_ts:
                        continue
                    if best_ts is None or ts > best_ts:
                        best_ts = ts
                        best = od2
                if best is not None:
                    exit_price = float(best.get("filled_avg_price"))
                    exit_ts = best_ts
                    otype = str(best.get("type", "")).lower()
                    if "stop" in otype:
                        reason = "STOP_LOSS"
                    elif "limit" in otype:
                        reason = "TAKE_PROFIT"

            if exit_price is None:
                # Can't safely log a close without a price.
                continue

            ep = float(ent.get("entry_price") or entry_hint or 0.0)
            if ep <= 0:
                continue

            qty = abs(float(units))
            pnl = (exit_price - ep) * qty if side == "long" else (ep - exit_price) * qty

            # Risk in USD: for equities, qty * abs(entry - stop). If no SL, r_multiple is None.
            r_mult = None
            try:
                if initial_sl not in (None, "", 0, 0.0):
                    risk_usd = qty * abs(ep - float(initial_sl))
                    if risk_usd > 0:
                        r_mult = pnl / risk_usd
            except Exception:
                r_mult = None

            # Hold duration
            ets = _parse_ts(ent.get("entry_ts")) or entry_ts
            xts = exit_ts or pd.Timestamp.utcnow().tz_localize("UTC")
            hold_days = None
            try:
                if ets is not None and xts is not None:
                    hold_days = (xts - ets).total_seconds() / 86400.0
            except Exception:
                hold_days = None

            trade_logger.log_trade_close(
                entry_ts=str(ets.isoformat()) if ets is not None else ent.get("entry_ts"),
                exit_ts=str(xts.isoformat()) if xts is not None else None,
                pair=str(ent.get("pair") or symbol),
                side=side,
                units=qty,
                entry_price=ep,
                exit_price=exit_price,
                initial_sl=initial_sl,
                initial_tp=initial_tp,
                pnl_usd=pnl,
                r_multiple=r_mult,
                hold_days=hold_days,
                reason_exit=reason,
                trade_id=str(oid),
            )

            # Remove from state so it won't be logged twice.
            entries.pop(oid, None)
            synced += 1

        st["entries"] = entries
        st["last_transaction_id"] = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        trade_logger.save_state(st)

        return {"synced": synced, "updated_entries": updated_entries, "broker": "alpaca"}
