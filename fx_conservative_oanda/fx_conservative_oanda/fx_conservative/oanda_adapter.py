# -*- coding: utf-8 -*-
import os, time, math, json
import pandas as pd
from typing import List, Dict, Any, Optional
import logging

import oandapyV20
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.accounts import AccountSummary
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.endpoints.trades import TradeList, TradeSetDependentOrders, TradeDetails
from oandapyV20.endpoints.positions import PositionList
from oandapyV20.endpoints.transactions import TransactionsSinceID, Transactions
from oandapyV20.exceptions import V20Error

# Configurar logging
logger = logging.getLogger(__name__)

PAIR_MAP = {
    "EURUSD":"EUR_USD","GBPUSD":"GBP_USD","AUDUSD":"AUD_USD","NZDUSD":"NZD_USD",
    "USDJPY":"USD_JPY","USDCHF":"USD_CHF","USDCAD":"USD_CAD"
}
USD_IS_QUOTE = {"EURUSD":True,"GBPUSD":True,"AUDUSD":True,"NZDUSD":True,"USDJPY":False,"USDCHF":False,"USDCAD":False}

class OandaAdapter:
    """
    Adapter mejorado con reintentos, validación y circuit breaker.
    """
    def __init__(self, account_id:Optional[str]=None, token:Optional[str]=None, env:Optional[str]=None, max_retries:int=3):
        self.account_id = account_id or os.environ.get("OANDA_ACCOUNT")
        token = token or os.environ.get("OANDA_TOKEN")
        env = env or os.environ.get("OANDA_ENV","practice")
        if not (self.account_id and token):
            raise RuntimeError("Faltan variables de entorno OANDA_ACCOUNT y/o OANDA_TOKEN")
        self.api = oandapyV20.API(access_token=token, environment=env)
        self.max_retries = max_retries
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        
    def _execute_with_retry(self, request_func, *args, **kwargs):
        """
        Ejecuta una request con reintentos exponenciales.
        Implementa circuit breaker si hay demasiados errores consecutivos.
        """
        if self.consecutive_errors >= self.max_consecutive_errors:
            raise RuntimeError(f"Circuit breaker activado: {self.consecutive_errors} errores consecutivos")
        
        for attempt in range(self.max_retries):
            try:
                result = request_func(*args, **kwargs)
                self.consecutive_errors = 0  # Reset en éxito
                return result
            except V20Error as e:
                logger.warning(f"Error OANDA (intento {attempt+1}/{self.max_retries}): {e}")
                self.consecutive_errors += 1
                
                # Errores no recuperables
                if e.code in [400, 401, 403, 404]:
                    raise
                
                if attempt < self.max_retries - 1:
                    sleep_time = (2 ** attempt) * 0.5  # Backoff exponencial
                    time.sleep(sleep_time)
                else:
                    raise
            except Exception as e:
                logger.error(f"Error inesperado (intento {attempt+1}/{self.max_retries}): {e}")
                self.consecutive_errors += 1
                if attempt < self.max_retries - 1:
                    time.sleep(1)
                else:
                    raise
        
        raise RuntimeError("Máximo de reintentos alcanzado")

    # -------- Datos de velas --------
    def candles(self, instrument: str, granularity: str = "D", count: int = 2000,
                alignment_tz: str = "America/New_York", daily_hour: int = 17, price: str = "M"):
        """
        Obtiene velas con validación de datos.
        MEJORADO: Validación y limpieza de datos.
        """
        def _request():
            params = dict(
                count=count, granularity=granularity, price=price,
                alignmentTimezone=alignment_tz, dailyAlignment=daily_hour, includeFirst=True
            )
            r = InstrumentsCandles(instrument=instrument, params=params)
            self.api.request(r)
            return r.response
        
        response = self._execute_with_retry(_request)
        cs = response.get("candles", [])
        
        if not cs:
            logger.warning(f"No se recibieron velas para {instrument}")
            return pd.DataFrame(columns=["time","Open","High","Low","Close","Volume","complete"])
        
        rows=[]
        for c in cs:
            try:
                t = pd.to_datetime(c["time"])
                m = c.get("mid") or c.get("ask") or c.get("bid")
                
                if not m:
                    continue
                
                o, h, l, cl = float(m["o"]), float(m["h"]), float(m["l"]), float(m["c"])
                
                # Validación básica de datos
                if not (0 < o < 1e6 and 0 < h < 1e6 and 0 < l < 1e6 and 0 < cl < 1e6):
                    logger.warning(f"Precio fuera de rango en {instrument} @ {t}: O={o}, H={h}, L={l}, C={cl}")
                    continue
                
                if h < l or h < o or h < cl or l > o or l > cl:
                    logger.warning(f"Relación H/L/O/C inválida en {instrument} @ {t}")
                    continue
                
                rows.append([t, o, h, l, cl, int(c.get("volume", 0)), bool(c.get("complete", False))])
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Error procesando vela de {instrument}: {e}")
                continue
        
        if not rows:
            return pd.DataFrame(columns=["time","Open","High","Low","Close","Volume","complete"])
        
        df = pd.DataFrame(rows, columns=["time","Open","High","Low","Close","Volume","complete"]).set_index("time").sort_index()
        return df[df["complete"]==True].drop(columns=["complete"])

    # Rango entre fechas (para backtest offline)
    def candles_between(self, instrument: str, start: str, end: str,
                        granularity="D", alignment_tz="America/New_York", daily_hour=17, price="M"):
        # OANDA limita por count; iterar por tramos si hace falta. Simplificamos: obtenemos count grande y filtramos.
        df = self.candles(instrument, granularity=granularity, count=5000,
                          alignment_tz=alignment_tz, daily_hour=daily_hour, price=price)
        return df.loc[start:end]

    # -------- Cuenta / equity --------
    def account_summary(self) -> Dict[str, Any]:
        def _request():
            r = AccountSummary(self.account_id)
            self.api.request(r)
            return r.response["account"]
        return self._execute_with_retry(_request)

    def account_equity(self) -> float:
        summary = self.account_summary()
        nav = float(summary.get("NAV", 0))
        if nav <= 0:
            raise ValueError(f"NAV inválido: {nav}")
        return nav

    def last_transaction_id(self) -> str:
        return self.account_summary()["lastTransactionID"]

    # -------- Órdenes y trades --------
    def place_bracket_market(self, instrument: str, side: str, units: int, sl_price: float, tp_price: float,
                             client_tag: Optional[str]=None, client_comment: Optional[str]=None, client_id: Optional[str]=None):
        """
        Envía orden market con SL y TP.
        MEJORADO: Validaciones previas al envío.
        """
        # Validaciones
        if units <= 0:
            raise ValueError(f"Units debe ser positivo: {units}")
        
        if sl_price <= 0 or tp_price <= 0:
            raise ValueError(f"SL/TP deben ser positivos: SL={sl_price}, TP={tp_price}")
        
        # Validar que SL y TP están del lado correcto
        if side == "long":
            if sl_price >= tp_price:
                raise ValueError(f"Para LONG, SL debe ser < TP: SL={sl_price}, TP={tp_price}")
        else:
            if sl_price <= tp_price:
                raise ValueError(f"Para SHORT, SL debe ser > TP: SL={sl_price}, TP={tp_price}")
        
        def _request():
            order = {
                "order": {
                    "type": "MARKET",
                    "instrument": instrument,
                    "units": str(units if side=="long" else -abs(units)),
                    "timeInForce": "FOK",
                    "positionFill": "DEFAULT",
                    "stopLossOnFill": {"price": f"{sl_price:.5f}"},
                    "takeProfitOnFill": {"price": f"{tp_price:.5f}"}
                }
            }
            if client_tag or client_comment or client_id:
                order["order"]["clientExtensions"] = {}
                if client_tag:
                    order["order"]["clientExtensions"]["tag"] = str(client_tag)[:100]  # Límite de OANDA
                if client_comment:
                    order["order"]["clientExtensions"]["comment"] = str(client_comment)[:100]
                if client_id:
                    order["order"]["clientExtensions"]["id"] = str(client_id)[:100]

            r = OrderCreate(self.account_id, data=order)
            self.api.request(r)
            return r.response
        
        return self._execute_with_retry(_request)

    def list_trades(self) -> List[Dict[str, Any]]:
        def _request():
            r = TradeList(self.account_id)
            self.api.request(r)
            return r.response.get("trades", [])
        return self._execute_with_retry(_request)

    def trade_details(self, trade_id: str) -> Dict[str, Any]:
        def _request():
            r = TradeDetails(self.account_id, tradeID=trade_id)
            self.api.request(r)
            return r.response.get("trade", {})
        return self._execute_with_retry(_request)

    def update_trailing_stop(self, trade_id: str, trail_distance: float):
        """
        Actualiza trailing stop de un trade.
        MEJORADO: Validación de distancia mínima.
        """
        if trail_distance <= 0:
            raise ValueError(f"Trail distance debe ser positivo: {trail_distance}")
        
        def _request():
            data = {"tradeID": trade_id, "trailingStopLoss": {"distance": f"{trail_distance:.5f}"}}
            r = TradeSetDependentOrders(self.account_id, tradeSpecifier=trade_id, data=data)
            self.api.request(r)
            return r.response
        
        return self._execute_with_retry(_request)

    # -------- Transacciones --------
    def transactions_since(self, from_id: str) -> List[Dict[str, Any]]:
        def _request():
            r = TransactionsSinceID(self.account_id, params={"id": str(from_id)})
            self.api.request(r)
            return r.response.get("transactions", [])
        return self._execute_with_retry(_request)

    def all_transactions(self, page_size: int = 100) -> List[Dict[str, Any]]:
        def _request():
            r = Transactions(self.account_id, params={"pageSize": page_size})
            self.api.request(r)
            return r.response.get("transactions", [])
        return self._execute_with_retry(_request)
