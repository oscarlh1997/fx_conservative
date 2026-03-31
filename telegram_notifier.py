# -*- coding: utf-8 -*-
"""
Módulo de notificaciones por Telegram.

Setup:
  1. Abre Telegram y busca @BotFather
  2. Envía /newbot y sigue las instrucciones
  3. Copia el token que te da (algo como 123456:ABC-DEF...)
  4. Busca tu bot en Telegram y envíale cualquier mensaje
  5. Abre en tu navegador: https://api.telegram.org/bot<TU_TOKEN>/getUpdates
  6. Busca "chat":{"id": XXXXXXX} — ese es tu chat_id
  7. Pon ambos valores en config_forex.yaml
"""
import logging
import json
from urllib.request import Request, urlopen
from urllib.error import URLError
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    """Envía notificaciones al bot de Telegram."""

    def __init__(self, token: str, chat_id: str, enabled: bool = True):
        self.token = token
        self.chat_id = str(chat_id)
        self.enabled = enabled and bool(token) and bool(chat_id)

        if self.enabled:
            logger.info("Telegram notifier activado")
        else:
            logger.info("Telegram notifier desactivado (sin token/chat_id)")

    def send(self, message: str, silent: bool = False) -> bool:
        """Envía un mensaje. Retorna True si se envió correctamente."""
        if not self.enabled:
            return False

        try:
            url = BASE_URL.format(token=self.token)
            payload = json.dumps({
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_notification": silent,
            }).encode("utf-8")

            req = Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=10) as resp:
                return resp.status == 200

        except URLError as e:
            logger.warning(f"Error enviando Telegram: {e}")
            return False
        except Exception as e:
            logger.warning(f"Error inesperado Telegram: {e}")
            return False

    # ----------------------------------------------------------------
    # Mensajes predefinidos para eventos de trading
    # ----------------------------------------------------------------
    def notify_trade_opened(self, pair: str, side: str, strategy: str,
                            units: float, entry: float, sl: float, tp: float,
                            risk_pct: float, confidence: float):
        emoji = "🟢" if side == "long" else "🔴"
        rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
        msg = (
            f"{emoji} <b>TRADE ABIERTO</b>\n\n"
            f"<b>{pair}</b> {side.upper()}\n"
            f"Estrategia: {strategy}\n"
            f"Entrada: {entry}\n"
            f"Stop Loss: {sl}\n"
            f"Take Profit: {tp}\n"
            f"R:R = {rr:.1f}:1\n"
            f"Unidades: {units:,.0f}\n"
            f"Riesgo: {risk_pct:.2%}\n"
            f"Confianza: {confidence:.0%}"
        )
        self.send(msg)

    def notify_trade_closed(self, pair: str, side: str, pnl: float,
                            r_multiple: Optional[float], reason: str):
        emoji = "✅" if pnl >= 0 else "❌"
        r_str = f"{r_multiple:+.2f}R" if r_multiple is not None else "?"
        msg = (
            f"{emoji} <b>TRADE CERRADO</b>\n\n"
            f"<b>{pair}</b> {side.upper()}\n"
            f"PnL: {pnl:+,.2f} USD\n"
            f"Resultado: {r_str}\n"
            f"Razón: {reason}"
        )
        self.send(msg)

    def notify_signal(self, pair: str, side: str, strategy: str, regime: str):
        msg = (
            f"📊 <b>SEÑAL DETECTADA</b>\n\n"
            f"<b>{pair}</b> {side.upper()}\n"
            f"Estrategia: {strategy}\n"
            f"Régimen: {regime}"
        )
        self.send(msg, silent=True)

    def notify_regime_change(self, regimes: Dict[str, str]):
        lines = [f"  {pair}: {regime}" for pair, regime in sorted(regimes.items())]
        msg = (
            f"📈 <b>REGÍMENES ACTUALES</b>\n\n"
            + "\n".join(lines)
        )
        self.send(msg, silent=True)

    def notify_trailing_update(self, pair: str, old_sl: float, new_sl: float):
        msg = (
            f"🔄 <b>TRAILING STOP</b>\n\n"
            f"<b>{pair}</b>\n"
            f"SL: {old_sl} → {new_sl}"
        )
        self.send(msg, silent=True)

    def notify_circuit_breaker(self, drawdown: float, pause_until: str):
        msg = (
            f"🚨 <b>CIRCUIT BREAKER ACTIVADO</b>\n\n"
            f"Drawdown: {drawdown:.1%}\n"
            f"Trading pausado hasta: {pause_until}\n\n"
            f"⚠️ Revisa las posiciones manualmente"
        )
        self.send(msg)

    def notify_strategy_paused(self, strategy: str, profit_factor: float,
                               pause_until: str):
        msg = (
            f"⏸️ <b>ESTRATEGIA PAUSADA</b>\n\n"
            f"<b>{strategy}</b>\n"
            f"Profit Factor: {profit_factor:.2f} (< 0.8)\n"
            f"Pausada hasta: {pause_until}"
        )
        self.send(msg)

    def notify_daily_summary(self, equity: float, open_positions: int,
                             signals_today: int, trades_opened: int,
                             regimes: Dict[str, str]):
        trending = sum(1 for r in regimes.values() if r == "trending")
        ranging = sum(1 for r in regimes.values() if r == "ranging")
        volatile = sum(1 for r in regimes.values() if r == "volatile")

        msg = (
            f"📋 <b>RESUMEN DIARIO</b>\n\n"
            f"Equity: {equity:,.2f} EUR\n"
            f"Posiciones abiertas: {open_positions}\n"
            f"Señales hoy: {signals_today}\n"
            f"Trades abiertos hoy: {trades_opened}\n\n"
            f"Regímenes:\n"
            f"  Tendencia: {trending} pares\n"
            f"  Rango: {ranging} pares\n"
            f"  Volátil: {volatile} pares"
        )
        self.send(msg)

    def notify_error(self, error: str):
        msg = (
            f"⚠️ <b>ERROR</b>\n\n"
            f"<code>{error[:500]}</code>"
        )
        self.send(msg)

    def notify_startup(self):
        msg = (
            f"🚀 <b>BOT INICIADO</b>\n\n"
            f"Adaptive Forex Strategy activa.\n"
            f"Monitoreando mercados."
        )
        self.send(msg)
