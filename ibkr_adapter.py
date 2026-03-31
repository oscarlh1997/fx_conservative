# -*- coding: utf-8 -*-
"""
Interactive Brokers Adapter para forex (y equities si se desea).

Usa ib_async para conectarse a IB Gateway / TWS.

Requisitos:
  pip install ib_async pandas

Configuración:
  - IB Gateway corriendo en localhost, puerto 4002 (paper) o 4001 (live)
  - API habilitada en IB Gateway: Configure > Settings > API > Enable ActiveX and Socket Clients
  - "Read-Only API" DESACTIVADO (necesitamos enviar órdenes)

Notas sobre forex en IBKR:
  - Los pares se expresan como "EURUSD" pero IBKR los trata como "EUR" base, "USD" quote
  - Las órdenes forex son siempre en unidades de la divisa BASE
  - El apalancamiento máximo ESMA para retail: 30:1 majors, 20:1 minors
  - Horario forex: domingo 17:00 ET — viernes 17:00 ET (continuo)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class IBKRAdapter:
    """
    Adapter de Interactive Brokers para la estrategia forex adaptativa.
    Implementa la misma interfaz que AlpacaAdapter.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,          # 4002 = paper, 4001 = live
        client_id: int = 1,
        timeout: int = 30,
        currency: str = "EUR",     # Divisa base de la cuenta (España = EUR)
    ):
        try:
            from ib_async import IB, util
        except ImportError:
            raise RuntimeError(
                "Falta dependencia 'ib_async'. Instala con: pip install ib_async"
            )

        self._IB = IB
        self._util = util
        self.host = host
        self.port = port
        self.client_id = client_id
        self.timeout = timeout
        self.account_currency = currency

        # Fix para Python 3.10+: crear event loop si no existe
        util.startLoop()

        # Conectar
        self.ib = self._IB()
        self._connect()

    def _connect(self):
        """Conecta a IB Gateway / TWS. Reintenta 3 veces."""
        for attempt in range(3):
            try:
                if self.ib.isConnected():
                    return
                self.ib.connect(
                    self.host, self.port, clientId=self.client_id,
                    timeout=self.timeout, readonly=False
                )
                logger.info(f"Conectado a IBKR en {self.host}:{self.port}")
                return
            except Exception as e:
                logger.warning(f"Intento {attempt+1}/3 de conexión fallido: {e}")
                time.sleep(3)

        raise RuntimeError(
            f"No se pudo conectar a IB Gateway en {self.host}:{self.port}. "
            "Verifica que IB Gateway está corriendo y la API está habilitada."
        )

    def _ensure_connected(self):
        """Reconecta si la conexión se perdió."""
        if not self.ib.isConnected():
            logger.warning("Conexión IBKR perdida, reconectando...")
            self._connect()

    # ----------------------------------------------------------------
    # Helpers: construir contratos (forex + metales preciosos)
    # ----------------------------------------------------------------
    # Metales preciosos disponibles como London Spot en IBKR (no-US)
    METALS = {
        "XAUUSD": {"symbol": "XAUUSD", "secType": "CMDTY", "exchange": "SMART", "currency": "USD"},
        "XAGUSD": {"symbol": "XAGUSD", "secType": "CMDTY", "exchange": "SMART", "currency": "USD"},
    }

    def _make_contract(self, pair: str):
        """
        Crea el contrato IBKR apropiado según el instrumento:
          - XAUUSD / XAGUSD → Commodity (London Spot Gold/Silver)
          - Todo lo demás → Forex (CASH)
        """
        from ib_async import Forex, Contract

        pair = pair.upper().replace("/", "").replace(".", "")

        # Metales preciosos
        if pair in self.METALS:
            m = self.METALS[pair]
            return Contract(
                secType=m["secType"],
                symbol=m["symbol"],
                exchange=m["exchange"],
                currency=m["currency"],
            )

        # Forex estándar
        if len(pair) != 6:
            raise ValueError(f"Instrumento inválido: {pair}. "
                           f"Debe ser 6 chars (EURUSD) o un metal ({list(self.METALS.keys())})")
        return Forex(pair)

    def _is_metal(self, pair: str) -> bool:
        """Retorna True si el par es un metal precioso."""
        return pair.upper().replace("/", "").replace(".", "") in self.METALS

    def _pair_from_contract(self, contract) -> str:
        """Extrae el nombre del par/instrumento del contrato."""
        sec_type = getattr(contract, "secType", "")
        symbol = getattr(contract, "symbol", "")

        # Metales: el symbol ya es XAUUSD / XAGUSD
        if sec_type == "CMDTY" and symbol in self.METALS:
            return symbol

        # Forex: intentar .pair primero
        pair_attr = getattr(contract, "pair", None)
        if pair_attr:
            return pair_attr.replace(".", "")

        # Fallback: symbol + currency
        quote = getattr(contract, "currency", "")
        return f"{symbol}{quote}"

    # ----------------------------------------------------------------
    # Datos de velas (históricos)
    # ----------------------------------------------------------------
    # Mapa de granularidad a parámetros IBKR
    GRAN_MAP = {
        "D":    {"barSize": "1 day",    "cal_mult": 1.5},
        "1D":   {"barSize": "1 day",    "cal_mult": 1.5},
        "4H":   {"barSize": "4 hours",  "cal_mult": 0.25},
        "1H":   {"barSize": "1 hour",   "cal_mult": 0.07},
        "15min": {"barSize": "15 mins", "cal_mult": 0.016},
        "5min":  {"barSize": "5 mins",  "cal_mult": 0.006},
    }

    def candles(
        self,
        instrument: str,
        granularity: str = "D",
        count: int = 500,
        alignment_tz: str = "America/New_York",
        daily_hour: int = 17,
        price: str = "M",
    ) -> pd.DataFrame:
        """
        Descarga velas de IBKR para forex o metales preciosos.

        Args:
            instrument: Par forex (EURUSD) o metal (XAUUSD, XAGUSD).
            granularity: 'D' (diario), '4H' (4 horas), '1H' (1 hora).
            count: Número de barras a solicitar.

        Returns:
            DataFrame con columnas Open, High, Low, Close, Volume.
        """
        self._ensure_connected()

        gran = self.GRAN_MAP.get(granularity)
        if gran is None:
            raise ValueError(f"Granularidad no soportada: '{granularity}'. "
                           f"Opciones: {list(self.GRAN_MAP.keys())}")

        contract = self._make_contract(instrument)
        self.ib.qualifyContracts(contract)

        # Calcular duración: count barras × días por barra × margen
        duration_days = int(max(30, count * gran["cal_mult"]))
        if duration_days > 365:
            years = max(1, duration_days // 365)
            duration_str = f"{years} Y"
        else:
            duration_str = f"{duration_days} D"

        what_to_show = "MIDPOINT"

        bars = self.ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration_str,
            barSizeSetting=gran["barSize"],
            whatToShow=what_to_show,
            useRTH=False,
            formatDate=2,
            keepUpToDate=False,
        )

        if not bars:
            logger.warning(f"Sin datos para {instrument}")
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        df = self._util.df(bars)
        return self._normalize_bars(df, count)

    def candles_between(
        self,
        instrument: str,
        start: str,
        end: str,
        granularity: str = "D",
        alignment_tz: str = "America/New_York",
        daily_hour: int = 17,
        price: str = "M",
    ) -> pd.DataFrame:
        """Descarga velas diarias entre dos fechas."""
        self._ensure_connected()

        contract = self._make_contract(instrument)
        self.ib.qualifyContracts(contract)

        start_dt = pd.to_datetime(start, utc=True)
        end_dt = pd.to_datetime(end, utc=True)

        # Calcular duración
        delta_days = max(1, (end_dt - start_dt).days)
        if delta_days > 365:
            years = max(1, delta_days // 365)
            duration_str = f"{years} Y"
        else:
            duration_str = f"{delta_days} D"

        # IBKR endDateTime formato: "YYYYMMDD HH:MM:SS UTC"
        end_str = end_dt.strftime("%Y%m%d %H:%M:%S") + " UTC"

        bars = self.ib.reqHistoricalData(
            contract,
            endDateTime=end_str,
            durationStr=duration_str,
            barSizeSetting="1 day",
            whatToShow="MIDPOINT",
            useRTH=False,
            formatDate=2,
            keepUpToDate=False,
        )

        if not bars:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        df = self._util.df(bars)
        return self._normalize_bars(df, count=None)

    def _normalize_bars(self, df: pd.DataFrame, count: Optional[int]) -> pd.DataFrame:
        """Normaliza el DataFrame de ib_async al formato de la estrategia."""
        if df.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        # ib_async devuelve columnas: date, open, high, low, close, volume, ...
        df = df.copy()

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], utc=True)
            df = df.set_index("date")
        elif not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, utc=True)

        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")

        df = df.sort_index()

        col_map = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
        df = df.rename(columns=col_map)

        out = pd.DataFrame(index=df.index)
        for col in ("Open", "High", "Low", "Close"):
            if col in df.columns:
                out[col] = df[col].astype(float).values
        out["Volume"] = df["Volume"].astype(float).values if "Volume" in df.columns else 0.0

        if count is not None:
            out = out.tail(int(count))

        return out

    # ----------------------------------------------------------------
    # Cuenta / equity
    # ----------------------------------------------------------------
    def account_equity(self) -> float:
        """Retorna el equity (NetLiquidation) de la cuenta en EUR."""
        self._ensure_connected()
        self.ib.reqAccountSummary()
        time.sleep(1)  # Esperar a que lleguen los datos

        # Buscar en account values
        account_values = self.ib.accountSummary()
        for av in account_values:
            if av.tag == "NetLiquidation" and av.currency == self.account_currency:
                equity = float(av.value)
                if equity <= 0:
                    raise ValueError(f"Equity inválido: {equity}")
                return equity

        # Fallback: buscar en cualquier divisa
        for av in account_values:
            if av.tag == "NetLiquidation":
                equity = float(av.value)
                if equity > 0:
                    return equity

        raise RuntimeError("No se pudo obtener el equity de la cuenta")

    # ----------------------------------------------------------------
    # Posiciones abiertas
    # ----------------------------------------------------------------
    def list_trades(self) -> List[Dict[str, Any]]:
        """Lista las posiciones abiertas (forex + metales preciosos)."""
        self._ensure_connected()
        positions = self.ib.positions()
        out: List[Dict[str, Any]] = []

        # Tipos de contrato que gestionamos
        VALID_TYPES = {"CASH", "CMDTY"}

        for pos in positions:
            contract = pos.contract
            sec_type = getattr(contract, "secType", "")
            if sec_type not in VALID_TYPES:
                continue

            pair = self._pair_from_contract(contract)
            qty = float(pos.position)
            avg_cost = float(pos.avgCost)

            # Obtener precio actual
            current_price = avg_cost  # Fallback
            try:
                ticker = self.ib.reqMktData(contract, "", False, False)
                self.ib.sleep(1)
                if ticker.midpoint() and ticker.midpoint() > 0:
                    current_price = ticker.midpoint()
                elif ticker.last and ticker.last > 0:
                    current_price = ticker.last
                self.ib.cancelMktData(contract)
            except Exception:
                pass

            out.append({
                "id": pair,
                "instrument": pair,
                "currentUnits": qty,
                "price": avg_cost,
                "currentPrice": current_price,
                "contract": contract,  # Para uso interno
            })

        return out

    # ----------------------------------------------------------------
    # Órdenes bracket
    # ----------------------------------------------------------------
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
        Envía una orden de mercado con bracket (SL + TP) a IBKR.

        Args:
            instrument: Par forex (EURUSD) o metal (XAUUSD, XAGUSD).
            side: 'long' o 'short'.
            units: Cantidad (divisa base para forex, onzas para metales).
            sl_price: Precio de stop-loss.
            tp_price: Precio de take-profit.
        """
        from ib_async import MarketOrder, LimitOrder, StopOrder, Order

        self._ensure_connected()

        if units <= 0:
            raise ValueError(f"Units debe ser positivo: {units}")
        if sl_price <= 0 or tp_price <= 0:
            raise ValueError(f"SL/TP deben ser positivos: SL={sl_price}, TP={tp_price}")
        if side not in ("long", "short"):
            raise ValueError(f"side debe ser 'long' o 'short', recibido: {side}")

        contract = self._make_contract(instrument)
        self.ib.qualifyContracts(contract)

        # Cantidad: forex en unidades enteras, metales en onzas (enteras para IBKR)
        is_metal = self._is_metal(instrument)
        qty = int(round(units))
        if qty <= 0:
            raise ValueError(f"Cantidad después de redondear es 0: {units}")

        action = "BUY" if side == "long" else "SELL"
        reverse_action = "SELL" if side == "long" else "BUY"

        # Redondear precios: forex 5 decimales, metales 2 decimales
        price_decimals = 2 if is_metal else 5
        sl_price = round(float(sl_price), price_decimals)
        tp_price = round(float(tp_price), price_decimals)

        # Crear bracket manualmente (parent + 2 child orders con parentId)
        parent_order = MarketOrder(action, qty)
        parent_order.tif = "GTC"
        parent_order.transmit = False

        tp_order = LimitOrder(reverse_action, qty, tp_price)
        tp_order.tif = "GTC"
        tp_order.transmit = False

        sl_order = StopOrder(reverse_action, qty, sl_price)
        sl_order.tif = "GTC"
        sl_order.transmit = True  # Último hijo transmite todos

        # Enviar parent primero
        parent_trade = self.ib.placeOrder(contract, parent_order)
        self.ib.sleep(1)

        parent_id = parent_trade.order.orderId
        tp_order.parentId = parent_id
        sl_order.parentId = parent_id

        tp_trade = self.ib.placeOrder(contract, tp_order)
        sl_trade = self.ib.placeOrder(contract, sl_order)

        self.ib.sleep(2)  # Esperar confirmación

        logger.info(f"Bracket enviado: {instrument} {side} qty={qty} "
                   f"SL={sl_price} TP={tp_price} parentId={parent_id}")

        return {
            "id": str(parent_id),
            "symbol": instrument,
            "side": side,
            "qty": qty,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "parent_order_id": parent_id,
            "tp_order_id": tp_trade.order.orderId,
            "sl_order_id": sl_trade.order.orderId,
            "status": str(parent_trade.orderStatus.status),
        }

    # ----------------------------------------------------------------
    # Detalles de trade (SL/TP actuales)
    # ----------------------------------------------------------------
    def trade_details(self, trade_id: str) -> Dict[str, Any]:
        """
        Busca las órdenes SL y TP abiertas para un par forex.
        trade_id = par (ej: "EURUSD") o orderId del parent.
        """
        self._ensure_connected()
        open_orders = self.ib.openOrders()

        out: Dict[str, Any] = {}
        instrument = str(trade_id).upper()

        for order in open_orders:
            # Filtrar por instrumento
            contract = getattr(order, "contract", None)
            if contract is None:
                continue
            pair = self._pair_from_contract(contract)
            if pair != instrument:
                # También buscar por parentId
                parent_id = getattr(order, "parentId", 0)
                if str(parent_id) != str(trade_id) and str(getattr(order, "orderId", "")) != str(trade_id):
                    continue

            order_type = getattr(order, "orderType", "").upper()

            if order_type == "STP" and "stopLossOrder" not in out:
                stop_price = getattr(order, "auxPrice", None)
                if stop_price:
                    out["stopLossOrder"] = {
                        "price": str(stop_price),
                        "orderID": str(getattr(order, "orderId", "")),
                    }

            elif order_type == "LMT" and "takeProfitOrder" not in out:
                limit_price = getattr(order, "lmtPrice", None)
                if limit_price:
                    out["takeProfitOrder"] = {
                        "price": str(limit_price),
                        "orderID": str(getattr(order, "orderId", "")),
                    }

        return out

    # ----------------------------------------------------------------
    # Modificar stop loss
    # ----------------------------------------------------------------
    def set_stop_loss(self, trade_id: str, stop_price: float) -> Dict[str, Any]:
        """Modifica el precio del stop-loss de una posición."""
        self._ensure_connected()

        if stop_price <= 0:
            raise ValueError(f"stop_price debe ser positivo: {stop_price}")

        # Redondear según tipo: metales 2 decimales, forex 5
        decimals = 2 if self._is_metal(str(trade_id)) else 5
        stop_price = round(float(stop_price), decimals)

        # Encontrar la orden SL actual
        td = self.trade_details(trade_id)
        slo = td.get("stopLossOrder", {})
        order_id = slo.get("orderID")

        if not order_id:
            raise RuntimeError(f"No se encontró stopLossOrder para {trade_id}")

        # Buscar la orden en las open orders
        for trade in self.ib.openTrades():
            if str(trade.order.orderId) == str(order_id):
                # Modificar el precio del stop
                trade.order.auxPrice = stop_price
                self.ib.placeOrder(trade.contract, trade.order)
                self.ib.sleep(1)

                logger.info(f"SL modificado para {trade_id}: nuevo precio = {stop_price}")
                return {
                    "id": str(order_id),
                    "new_stop_price": stop_price,
                    "status": str(trade.orderStatus.status),
                }

        raise RuntimeError(f"No se encontró la orden SL con id {order_id}")

    # ----------------------------------------------------------------
    # Trailing stop (aproximado)
    # ----------------------------------------------------------------
    def update_trailing_stop(self, trade_id: str, trail_distance: float) -> Dict[str, Any]:
        """
        Actualiza el trailing stop basándose en el precio actual.
        IBKR tiene trailing stops nativos, pero usamos la misma lógica
        que la estrategia: mover SL manualmente basado en precio + distancia.
        """
        if trail_distance <= 0:
            raise ValueError(f"trail_distance debe ser positivo: {trail_distance}")

        self._ensure_connected()
        symbol = str(trade_id).upper()

        # Buscar posición
        positions = self.ib.positions()
        pos = None
        for p in positions:
            pair = self._pair_from_contract(p.contract)
            if pair == symbol:
                pos = p
                break

        if pos is None:
            raise RuntimeError(f"No hay posición abierta para {symbol}")

        qty = float(pos.position)
        side = "long" if qty > 0 else "short"

        # Obtener precio actual
        contract = self._make_contract(symbol)
        self.ib.qualifyContracts(contract)
        ticker = self.ib.reqMktData(contract, "", False, False)
        self.ib.sleep(2)
        cur_price = ticker.midpoint()
        self.ib.cancelMktData(contract)

        if not cur_price or cur_price <= 0:
            raise RuntimeError(f"No se pudo obtener precio actual para {symbol}")

        # Calcular nuevo SL
        if side == "long":
            new_sl = cur_price - trail_distance
        else:
            new_sl = cur_price + trail_distance

        return self.set_stop_loss(symbol, new_sl)

    # ----------------------------------------------------------------
    # Transacciones
    # ----------------------------------------------------------------
    def last_transaction_id(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def transactions_since(self, from_id: str) -> List[Dict[str, Any]]:
        return []

    def sync_transactions(self, trade_logger) -> Dict[str, Any]:
        """
        Sincroniza trades cerrados con el trade logger.
        Revisa el state y verifica si las posiciones siguen abiertas.
        """
        self._ensure_connected()
        st = trade_logger.load_state()
        entries = st.get("entries", {})
        if not isinstance(entries, dict):
            entries = {}

        # Obtener posiciones actuales (forex + metales)
        current_positions = set()
        VALID_TYPES = {"CASH", "CMDTY"}
        for p in self.ib.positions():
            if getattr(p.contract, "secType", "") in VALID_TYPES:
                pair = self._pair_from_contract(p.contract)
                if abs(float(p.position)) > 0:
                    current_positions.add(pair)

        synced = 0
        updated_entries = 0

        for oid in list(entries.keys()):
            ent = entries.get(oid, {})
            if not isinstance(ent, dict):
                continue

            symbol = str(ent.get("instrument") or ent.get("pair") or "")
            side = str(ent.get("side", "")).lower()
            units = float(ent.get("units", 0))

            if not symbol or units <= 0 or side not in ("long", "short"):
                continue

            # Si la posición sigue abierta, no hacer nada
            if symbol in current_positions:
                continue

            # Posición cerrada: calcular PnL
            entry_price = ent.get("entry_price") or ent.get("entry_hint")
            if entry_price is None or float(entry_price) <= 0:
                continue

            ep = float(entry_price)
            initial_sl = ent.get("initial_sl")
            initial_tp = ent.get("initial_tp")
            strategy = ent.get("strategy", "trend")

            # Buscar ejecuciones recientes para determinar exit price
            exit_price = None
            try:
                executions = self.ib.executions()
                contract = self._make_contract(symbol)
                for exe in sorted(executions, key=lambda e: getattr(e, "time", ""), reverse=True):
                    exe_pair = self._pair_from_contract(exe.contract)
                    if exe_pair == symbol:
                        exit_price = float(exe.price)
                        break
            except Exception:
                pass

            if exit_price is None:
                continue

            qty = abs(units)
            pnl = (exit_price - ep) * qty if side == "long" else (ep - exit_price) * qty

            # R-multiple
            r_mult = None
            if initial_sl not in (None, "", 0, 0.0):
                risk_per_unit = abs(ep - float(initial_sl))
                risk_total = qty * risk_per_unit
                if risk_total > 0:
                    r_mult = pnl / risk_total

            # Registrar en trade logger
            trade_logger.log_trade_close(
                entry_ts=ent.get("entry_ts"),
                exit_ts=datetime.now(timezone.utc).isoformat(),
                pair=symbol,
                side=side,
                units=qty,
                entry_price=ep,
                exit_price=exit_price,
                initial_sl=initial_sl,
                initial_tp=initial_tp,
                pnl_usd=pnl,
                r_multiple=r_mult,
                hold_days=None,
                reason_exit="CLOSE",
                trade_id=str(oid),
            )

            # Registrar en recently_closed para el autorregulador
            recently_closed = st.get("recently_closed", [])
            recently_closed.append({
                "strategy": strategy,
                "r_multiple": r_mult,
                "pnl": pnl,
                "pair": symbol,
            })
            st["recently_closed"] = recently_closed

            entries.pop(oid, None)
            synced += 1

        st["entries"] = entries
        st["last_transaction_id"] = datetime.now(timezone.utc).isoformat()
        trade_logger.save_state(st)

        return {"synced": synced, "updated_entries": updated_entries, "broker": "ibkr"}

    # ----------------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------------
    def disconnect(self):
        """Desconecta de IBKR limpiamente."""
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Desconectado de IBKR")

    def __del__(self):
        try:
            self.disconnect()
        except Exception:
            pass
