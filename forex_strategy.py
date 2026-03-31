# -*- coding: utf-8 -*-
"""
Adaptive Forex Strategy v2 — Con mejoras avanzadas.

MEJORAS IMPLEMENTADAS:
  1. Filtro de sobreextensión (TrendStrategy) — evita entradas tardías
  2. Filtro de ruptura peligrosa (MeanReversion) — evita "cuchillos cayendo"
  3. Control de exposición por divisa — evita sobre-exposición a USD/EUR
  4. Filtro de sesión — adapta estrategia según sesión (Asia/London/NY)
  5. Hard cap de riesgo — Kelly nunca supera 1% absoluto
  6. Trailing progresivo mejorado — 4 niveles basados en R-múltiplo
  7. Detección de ruptura de estructura — MR no entra si hay breakout
  8. Proxy de VIX via volatilidad — reduce riesgo en alta vol global
  9. Filtro de conflicto bias macro — deduce dirección de tendencia USD/EUR
"""
import math
import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta, timezone
from collections import defaultdict

logger = logging.getLogger(__name__)


# ============================================================
# Señal de trading
# ============================================================
@dataclass
class ForexSignal:
    pair: str
    side: str           # "long" / "short"
    strategy: str       # "trend" / "mean_reversion"
    regime: str         # "trending" / "ranging" / "volatile"
    entry: float
    stop: float
    tp: float
    atr: float
    confidence: float   # 0.0 - 1.0 (del regulador)
    risk_R: float       # R:R ratio
    meta: Dict = field(default_factory=dict)


# ============================================================
# Indicadores (puros, sin estado)
# ============================================================
def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    mask = plus_dm < minus_dm
    plus_dm[mask] = 0
    minus_dm[~mask] = 0
    atr_val = atr(high, low, close, n)
    plus_di = 100 * (plus_dm.ewm(span=n, adjust=False).mean() / atr_val)
    minus_di = 100 * (minus_dm.ewm(span=n, adjust=False).mean() / atr_val)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-12)
    return dx.ewm(span=n, adjust=False).mean()


def rsi(series: pd.Series, n: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_g = gain.ewm(span=n, adjust=False).mean()
    avg_l = loss.ewm(span=n, adjust=False).mean()
    rs = avg_g / (avg_l + 1e-12)
    return 100 - 100 / (1 + rs)


def bollinger(close: pd.Series, n: int = 20, nstd: float = 2.0):
    mid = close.rolling(n).mean()
    std = close.rolling(n).std()
    upper = mid + nstd * std
    lower = mid - nstd * std
    pct_b = (close - lower) / (upper - lower + 1e-12)
    return upper, mid, lower, pct_b


def donchian(high: pd.Series, low: pd.Series, n: int = 20):
    return high.rolling(n).max(), low.rolling(n).min()


def volatility_regime(atr_series: pd.Series, lookback: int = 60) -> pd.Series:
    return atr_series / (atr_series.rolling(lookback).mean() + 1e-12)


# ============================================================
# MEJORA 4: Filtro de sesión
# ============================================================
class SessionFilter:
    """
    Adapta la estrategia según la sesión de mercado.
    - Asia (00:00-07:00 UTC): mercado lateral → favorece mean reversion
    - London (07:00-16:00 UTC): tendencia → favorece trend following
    - New York (13:00-22:00 UTC): tendencia → favorece trend following
    - Overlap London/NY (13:00-16:00 UTC): más volátil, mejor para ambas
    """

    @staticmethod
    def get_session(utc_hour: int) -> str:
        if 0 <= utc_hour < 7:
            return "asia"
        elif 7 <= utc_hour < 13:
            return "london"
        elif 13 <= utc_hour < 16:
            return "overlap"
        elif 16 <= utc_hour < 22:
            return "new_york"
        else:
            return "asia"

    @staticmethod
    def is_strategy_appropriate(session: str, strategy: str) -> bool:
        """Verifica si la estrategia es apropiada para la sesión actual."""
        if session == "asia":
            # Asia es rangosa — mean reversion OK, trend solo si señal fuerte
            return True  # No bloqueamos, pero ajustamos confianza
        return True  # London/NY/overlap: todas las estrategias OK

    @staticmethod
    def session_confidence_multiplier(session: str, strategy: str) -> float:
        """Multiplica confianza según sesión y estrategia."""
        if session == "asia":
            if strategy == "trend":
                return 0.7  # Menos confianza en trends durante Asia
            else:
                return 1.1  # Más confianza en MR durante Asia
        elif session in ("london", "overlap"):
            if strategy == "trend":
                return 1.1  # Más confianza en trends durante London/overlap
            else:
                return 0.9
        return 1.0


# ============================================================
# MEJORA 3: Control de exposición por divisa
# ============================================================
class CurrencyExposure:
    """
    Evita sobre-exposición a una divisa.
    Ejemplo: EURUSD long + GBPUSD long + AUDUSD long = todo SHORT USD.
    """

    # Mapa de pares a divisas
    PAIR_CURRENCIES = {
        "EURUSD": ("EUR", "USD"), "GBPUSD": ("GBP", "USD"),
        "USDJPY": ("USD", "JPY"), "USDCHF": ("USD", "CHF"),
        "USDCAD": ("USD", "CAD"), "AUDUSD": ("AUD", "USD"),
        "NZDUSD": ("NZD", "USD"), "EURGBP": ("EUR", "GBP"),
        "AUDNZD": ("AUD", "NZD"), "EURJPY": ("EUR", "JPY"),
        "GBPJPY": ("GBP", "JPY"), "EURCHF": ("EUR", "CHF"),
        "XAUUSD": ("XAU", "USD"), "XAGUSD": ("XAG", "USD"),
    }

    def __init__(self, max_exposure_per_currency: int = 3):
        self.max_exposure = max_exposure_per_currency

    def calculate_exposure(self, open_trades: List[Dict]) -> Dict[str, int]:
        """Calcula exposición actual por divisa."""
        exposure = defaultdict(int)
        for t in open_trades:
            pair = t.get("instrument", "")
            units = float(t.get("currentUnits", 0))
            currencies = self.PAIR_CURRENCIES.get(pair)
            if not currencies:
                continue
            base, quote = currencies
            if units > 0:  # Long base, short quote
                exposure[base] += 1
                exposure[quote] -= 1
            else:  # Short base, long quote
                exposure[base] -= 1
                exposure[quote] += 1
        return dict(exposure)

    def would_exceed_exposure(self, pair: str, side: str,
                               current_exposure: Dict[str, int]) -> bool:
        """Verifica si un nuevo trade excedería el límite de exposición."""
        currencies = self.PAIR_CURRENCIES.get(pair)
        if not currencies:
            return False

        base, quote = currencies
        sim_exposure = dict(current_exposure)

        if side == "long":
            sim_exposure[base] = sim_exposure.get(base, 0) + 1
            sim_exposure[quote] = sim_exposure.get(quote, 0) - 1
        else:
            sim_exposure[base] = sim_exposure.get(base, 0) - 1
            sim_exposure[quote] = sim_exposure.get(quote, 0) + 1

        for ccy, exp in sim_exposure.items():
            if abs(exp) > self.max_exposure:
                logger.info(f"Exposición {ccy}: {exp} excedería límite {self.max_exposure}")
                return True
        return False


# ============================================================
# MEJORA 9: Bias macro por precio (proxy sin datos externos)
# ============================================================
class MacroBias:
    """
    Deduce bias de divisas principales usando EMAs de largo plazo.
    Si EURUSD trending down → USD bullish, EUR bearish.
    No necesita datos externos — usa los mismos datos de IBKR.
    """

    @staticmethod
    def derive_currency_bias(pair_data: Dict[str, pd.DataFrame]) -> Dict[str, str]:
        """Deriva bias por divisa desde los datos de los pares."""
        bias = defaultdict(lambda: "neutral")
        usd_signals = []

        # Usar pares contra USD para derivar bias USD
        usd_pairs = {
            "EURUSD": "quote",   # EURUSD down → USD bullish
            "GBPUSD": "quote",
            "AUDUSD": "quote",
            "USDJPY": "base",    # USDJPY up → USD bullish
            "USDCHF": "base",
            "USDCAD": "base",
        }

        for pair, role in usd_pairs.items():
            if pair not in pair_data:
                continue
            df = pair_data[pair]
            if len(df) < 200:
                continue

            ema50 = df["EMA50"].iloc[-1]
            ema200 = df["EMA200"].iloc[-1]

            if role == "quote":
                # EURUSD: si EMA50 < EMA200 → par bajando → USD bullish
                if ema50 < ema200:
                    usd_signals.append(1)
                elif ema50 > ema200:
                    usd_signals.append(-1)
            else:
                # USDJPY: si EMA50 > EMA200 → par subiendo → USD bullish
                if ema50 > ema200:
                    usd_signals.append(1)
                elif ema50 < ema200:
                    usd_signals.append(-1)

        if usd_signals:
            avg = sum(usd_signals) / len(usd_signals)
            if avg > 0.3:
                bias["USD"] = "bullish"
            elif avg < -0.3:
                bias["USD"] = "bearish"

        return dict(bias)

    @staticmethod
    def conflicts_with_bias(pair: str, side: str,
                            bias: Dict[str, str]) -> bool:
        """Verifica si un trade va contra el bias macro."""
        currencies = CurrencyExposure.PAIR_CURRENCIES.get(pair)
        if not currencies:
            return False

        base, quote = currencies

        # Si compramos base y base es bearish → conflicto
        if side == "long" and bias.get(base) == "bearish":
            return True
        # Si vendemos base y base es bullish → conflicto
        if side == "short" and bias.get(base) == "bullish":
            return True
        # Si compramos base = vendemos quote, y quote es bullish → conflicto
        if side == "long" and bias.get(quote) == "bullish":
            return True
        if side == "short" and bias.get(quote) == "bearish":
            return True

        return False


# ============================================================
# Detector de régimen
# ============================================================
class RegimeDetector:
    def __init__(self, adx_trend=25, adx_range=20, vol_spike=1.5):
        self.adx_trend = adx_trend
        self.adx_range = adx_range
        self.vol_spike = vol_spike

    def detect(self, df: pd.DataFrame) -> str:
        row = df.iloc[-1]
        vol_ratio = row.get("VolRatio", 1.0)

        if vol_ratio > self.vol_spike:
            return "volatile"

        adx_val = row["ADX"]
        ema_separation = abs(row["EMA20"] - row["EMA50"]) / (row["EMA50"] + 1e-12)

        if adx_val > self.adx_trend and ema_separation > 0.002:
            return "trending"
        elif adx_val < self.adx_range:
            return "ranging"
        else:
            return "ambiguous"


# ============================================================
# Helpers: metales preciosos
# ============================================================
_METALS = {"XAUUSD", "XAGUSD"}

def is_metal(pair: str) -> bool:
    return pair.upper() in _METALS

def price_decimals(pair: str) -> int:
    if is_metal(pair):
        return 2
    # Pares JPY usan 3 decimales
    if pair.upper().endswith("JPY"):
        return 3
    return 5


# ============================================================
# MEJORA 1: Trend Following con filtro de sobreextensión
# ============================================================
class TrendStrategy:
    """
    Entry: Pullback a EMA20 en dirección de tendencia EMA50/200.
    MEJORA: Filtra entradas cuando el precio está sobreextendido
    (demasiado lejos de EMA200 → la tendencia puede estar agotada).
    """

    def __init__(self, cfg):
        self.atr_stop = cfg.get("atr_stop_mult", 1.5)
        self.tp_R = cfg.get("tp_R", 3.0)
        self.atr_trail = cfg.get("atr_trail_mult", 2.5)
        self.rsi_floor = cfg.get("rsi_trend_floor", 35)
        self.rsi_ceil = cfg.get("rsi_trend_ceil", 65)
        self.overextension_atr = cfg.get("overextension_atr_mult", 4.0)

    def _is_overextended(self, price: float, ema200: float, atr_val: float) -> bool:
        """MEJORA 1: Evita entrar en tendencias agotadas."""
        if atr_val <= 0:
            return False
        distance = abs(price - ema200)
        return distance > self.overextension_atr * atr_val

    def scan(self, pair: str, df: pd.DataFrame) -> Optional[ForexSignal]:
        if len(df) < 50:
            return None
        row = df.iloc[-1]
        prev = df.iloc[-2]

        c = row["Close"]
        ema20 = row["EMA20"]
        ema50 = row["EMA50"]
        ema200 = row["EMA200"]
        atr_val = row["ATR"]
        rsi_val = row["RSI14"]

        if atr_val <= 0 or c <= 0:
            return None

        # MEJORA 1: filtro de sobreextensión
        if self._is_overextended(c, ema200, atr_val):
            logger.debug(f"{pair}: sobreextendido ({abs(c-ema200)/atr_val:.1f} ATR de EMA200)")
            return None

        sig = None

        # LONG
        if c > ema200 and ema20 > ema50 > ema200:
            touched_ema = prev["Low"] <= ema20 * 1.002 and c > ema20
            rsi_ok = self.rsi_floor < rsi_val < self.rsi_ceil + 10

            if touched_ema and rsi_ok:
                stop = c - self.atr_stop * atr_val
                sl_dist = c - stop
                tp = c + self.tp_R * sl_dist
                sig = ForexSignal(
                    pair=pair, side="long", strategy="trend",
                    regime="trending", entry=c,
                    stop=round(stop, price_decimals(pair)),
                    tp=round(tp, price_decimals(pair)), atr=atr_val,
                    confidence=0.0, risk_R=self.tp_R,
                    meta={"ema20": ema20, "adx": row["ADX"],
                          "extension_atr": abs(c - ema200) / atr_val}
                )

        # SHORT
        elif c < ema200 and ema20 < ema50 < ema200:
            touched_ema = prev["High"] >= ema20 * 0.998 and c < ema20
            rsi_ok = self.rsi_ceil > rsi_val > self.rsi_floor - 10

            if touched_ema and rsi_ok:
                stop = c + self.atr_stop * atr_val
                sl_dist = stop - c
                tp = c - self.tp_R * sl_dist
                sig = ForexSignal(
                    pair=pair, side="short", strategy="trend",
                    regime="trending", entry=c,
                    stop=round(stop, price_decimals(pair)),
                    tp=round(tp, price_decimals(pair)), atr=atr_val,
                    confidence=0.0, risk_R=self.tp_R,
                    meta={"ema20": ema20, "adx": row["ADX"],
                          "extension_atr": abs(c - ema200) / atr_val}
                )

        return sig


# ============================================================
# MEJORA 2: Mean Reversion con filtro de ruptura peligrosa
# ============================================================
class MeanReversionStrategy:
    """
    Entry: Precio en Bollinger Band extremo + RSI extremo.
    MEJORA 2: No entra si ADX está subiendo (tendencia empezando)
    o si hay ruptura de estructura (Donchian breakout).
    """

    def __init__(self, cfg):
        self.bb_period = cfg.get("bb_period", 20)
        self.bb_std = cfg.get("bb_std", 2.0)
        self.rsi_low = cfg.get("rsi_mr_low", 25)
        self.rsi_high = cfg.get("rsi_mr_high", 75)
        self.atr_stop_extra = cfg.get("atr_mr_stop", 0.5)
        self.adx_rising_threshold = cfg.get("adx_rising_threshold", 25)

    def _is_dangerous_reversal(self, df: pd.DataFrame) -> bool:
        """MEJORA 2: Detecta si es peligroso hacer mean reversion."""
        if len(df) < 10:
            return False

        row = df.iloc[-1]
        adx_now = row["ADX"]
        adx_prev = df["ADX"].iloc[-5]

        # ADX subiendo y ya alto → tendencia empezando, no hacer MR
        adx_rising = adx_now > adx_prev * 1.15 and adx_now > self.adx_rising_threshold

        # Ruptura de estructura: precio rompió Donchian de 20 períodos
        structure_break = (row["Close"] >= row["DCH"] or row["Close"] <= row["DCL"])

        if adx_rising and structure_break:
            logger.debug(f"Dangerous reversal: ADX rising {adx_prev:.0f}→{adx_now:.0f} + structure break")
            return True

        return False

    def scan(self, pair: str, df: pd.DataFrame) -> Optional[ForexSignal]:
        if len(df) < 30:
            return None

        # MEJORA 2: no entrar si hay ruptura peligrosa
        if self._is_dangerous_reversal(df):
            return None

        row = df.iloc[-1]

        c = row["Close"]
        bb_upper = row["BB_Upper"]
        bb_mid = row["BB_Mid"]
        bb_lower = row["BB_Lower"]
        pct_b = row["PctB"]
        rsi_val = row["RSI14"]
        atr_val = row["ATR"]

        if atr_val <= 0 or c <= 0:
            return None

        sig = None

        # LONG: precio por debajo de BB inferior + RSI oversold
        if c <= bb_lower and rsi_val < self.rsi_low:
            stop = c - self.atr_stop_extra * atr_val
            tp = bb_mid
            sl_dist = c - stop
            tp_dist = tp - c

            if sl_dist > 0 and tp_dist > 0:
                rr = tp_dist / sl_dist
                if rr >= 1.2:
                    sig = ForexSignal(
                        pair=pair, side="long", strategy="mean_reversion",
                        regime="ranging", entry=c,
                        stop=round(stop, price_decimals(pair)),
                        tp=round(tp, price_decimals(pair)), atr=atr_val,
                        confidence=0.0, risk_R=round(rr, 2),
                        meta={"bb_lower": bb_lower, "bb_mid": bb_mid,
                              "pct_b": pct_b, "adx": row["ADX"]}
                    )

        # SHORT
        elif c >= bb_upper and rsi_val > self.rsi_high:
            stop = c + self.atr_stop_extra * atr_val
            tp = bb_mid
            sl_dist = stop - c
            tp_dist = c - tp

            if sl_dist > 0 and tp_dist > 0:
                rr = tp_dist / sl_dist
                if rr >= 1.2:
                    sig = ForexSignal(
                        pair=pair, side="short", strategy="mean_reversion",
                        regime="ranging", entry=c,
                        stop=round(stop, price_decimals(pair)),
                        tp=round(tp, price_decimals(pair)), atr=atr_val,
                        confidence=0.0, risk_R=round(rr, 2),
                        meta={"bb_upper": bb_upper, "bb_mid": bb_mid,
                              "pct_b": pct_b, "adx": row["ADX"]}
                    )

        return sig


# ============================================================
# Autorregulador (Kelly + Equity Curve + MEJORA 5: hard cap)
# ============================================================
class SelfRegulator:
    """
    MEJORA 5: Hard cap — Kelly nunca supera 1% absoluto.
    MEJORA 8: Proxy VIX — usa volatilidad media de pares como proxy.
    """

    def __init__(self, cfg, trade_logger, notifier=None):
        self.base_risk = cfg.get("base_risk_per_trade", 0.01)
        self.max_risk = cfg.get("max_risk_per_trade", 0.02)
        self.min_risk = cfg.get("min_risk_per_trade", 0.002)
        # MEJORA 5: hard cap absoluto
        self.hard_cap_risk = cfg.get("hard_cap_risk", 0.01)
        self.kelly_fraction = cfg.get("kelly_fraction", 0.25)
        self.lookback = cfg.get("regulator_lookback", 20)
        self.dd_reduce = cfg.get("dd_reduce_threshold", 0.05)
        self.dd_pause = cfg.get("dd_pause_threshold", 0.10)
        self.pause_days = cfg.get("pause_days", 5)
        self.log = trade_logger
        self.notifier = notifier

    def load_performance(self) -> Dict:
        st = self.log.load_state()
        return st.get("regulator", {
            "trend": {"trades": [], "paused_until": None},
            "mean_reversion": {"trades": [], "paused_until": None},
            "peak_equity": 0.0,
            "global_paused_until": None,
        })

    def save_performance(self, perf: Dict):
        st = self.log.load_state()
        st["regulator"] = perf
        self.log.save_state(st)

    def record_trade(self, strategy: str, r_multiple: float):
        perf = self.load_performance()
        if strategy not in perf:
            perf[strategy] = {"trades": [], "paused_until": None}
        perf[strategy]["trades"].append(round(r_multiple, 4))
        perf[strategy]["trades"] = perf[strategy]["trades"][-self.lookback:]
        self.save_performance(perf)

    def update_equity_peak(self, current_equity: float):
        perf = self.load_performance()
        if current_equity > perf.get("peak_equity", 0):
            perf["peak_equity"] = current_equity
        self.save_performance(perf)

    def _strategy_confidence(self, trades: List[float]) -> float:
        if len(trades) < 5:
            return 0.5
        wins = [t for t in trades if t > 0]
        losses = [t for t in trades if t <= 0]
        win_rate = len(wins) / len(trades)
        profit_factor = (sum(wins)) / (abs(sum(losses)) + 1e-12) if losses else 3.0
        pf_score = min(1.0, profit_factor / 2.0)
        wr_score = min(1.0, win_rate / 0.55)
        confidence = (pf_score * 0.6 + wr_score * 0.4)
        return round(max(0.1, min(1.0, confidence)), 3)

    def _kelly_risk(self, trades: List[float]) -> float:
        if len(trades) < 10:
            return self.base_risk
        wins = [t for t in trades if t > 0]
        losses = [t for t in trades if t <= 0]
        if not wins or not losses:
            return self.base_risk
        W = len(wins) / len(trades)
        R = np.mean(wins) / (abs(np.mean(losses)) + 1e-12)
        kelly = W - (1 - W) / R
        if kelly <= 0:
            return self.min_risk
        optimal = kelly * self.kelly_fraction
        # MEJORA 5: hard cap
        return max(self.min_risk, min(self.hard_cap_risk, optimal))

    def get_risk_for_signal(self, signal: ForexSignal, current_equity: float,
                            vol_proxy: float = 1.0,
                            session_mult: float = 1.0) -> float:
        """
        Retorna riesgo ajustado. Integra Kelly + confianza + equity curve
        + circuit breaker + MEJORA 8 (vol proxy) + MEJORA 4 (sesión).
        """
        perf = self.load_performance()
        now = datetime.now(timezone.utc)

        # 1) Circuit breaker global
        paused = perf.get("global_paused_until")
        if paused:
            pause_dt = pd.to_datetime(paused, utc=True)
            if now < pause_dt:
                logger.warning(f"CIRCUIT BREAKER activo hasta {paused}")
                return 0.0

        # 2) Check drawdown desde peak
        peak = perf.get("peak_equity", current_equity)
        if peak > 0:
            dd = (peak - current_equity) / peak
            if dd > self.dd_pause:
                pause_until = (now + timedelta(days=self.pause_days)).isoformat()
                perf["global_paused_until"] = pause_until
                self.save_performance(perf)
                logger.warning(f"DRAWDOWN {dd:.1%} > {self.dd_pause:.0%}. Pausa hasta {pause_until}")
                if self.notifier:
                    try:
                        self.notifier.notify_circuit_breaker(dd, pause_until)
                    except Exception:
                        pass
                return 0.0
        else:
            dd = 0.0

        # 3) Check pausa de sub-estrategia
        strat_perf = perf.get(signal.strategy, {"trades": [], "paused_until": None})
        strat_paused = strat_perf.get("paused_until")
        if strat_paused:
            pause_dt = pd.to_datetime(strat_paused, utc=True)
            if now < pause_dt:
                logger.info(f"'{signal.strategy}' pausada hasta {strat_paused}")
                return 0.0

        trades = strat_perf.get("trades", [])

        # 4) Kelly base
        kelly_risk = self._kelly_risk(trades)

        # 5) Confianza
        confidence = self._strategy_confidence(trades)
        signal.confidence = confidence

        # 6) Drawdown adjustment
        dd_multiplier = 0.5 if dd > self.dd_reduce else 1.0

        # 7) Volatility adjustment (régimen local)
        vol_multiplier = 0.5 if signal.regime == "volatile" else 1.0

        # MEJORA 8: Global vol proxy (alta vol en todo el mercado → reducir)
        global_vol_mult = 0.7 if vol_proxy > 1.3 else 1.0

        # MEJORA 4: Session multiplier
        session_multiplier = max(0.5, min(1.2, session_mult))

        # Riesgo final
        final_risk = (kelly_risk * confidence * dd_multiplier *
                      vol_multiplier * global_vol_mult * session_multiplier)

        # MEJORA 5: hard cap absoluto
        final_risk = max(self.min_risk, min(self.hard_cap_risk, final_risk))

        logger.info(f"Riesgo {signal.pair} [{signal.strategy}]: "
                    f"kelly={kelly_risk:.4f} conf={confidence:.2f} "
                    f"dd={dd_multiplier} vol={vol_multiplier} "
                    f"gvol={global_vol_mult} sess={session_multiplier:.1f} "
                    f"→ {final_risk:.4f}")

        return final_risk

    def check_strategy_health(self):
        perf = self.load_performance()
        now = datetime.now(timezone.utc)
        for strat_name in ["trend", "mean_reversion"]:
            sp = perf.get(strat_name, {"trades": [], "paused_until": None})
            trades = sp.get("trades", [])
            if len(trades) < 10:
                continue
            wins = [t for t in trades if t > 0]
            losses = [t for t in trades if t <= 0]
            pf = sum(wins) / (abs(sum(losses)) + 1e-12) if losses else 999
            if pf < 0.8:
                pause_until = (now + timedelta(days=3)).isoformat()
                sp["paused_until"] = pause_until
                perf[strat_name] = sp
                logger.warning(f"Pausando '{strat_name}' (PF={pf:.2f}) hasta {pause_until}")
                if self.notifier:
                    try:
                        self.notifier.notify_strategy_paused(strat_name, pf, pause_until)
                    except Exception:
                        pass
        self.save_performance(perf)


# ============================================================
# Motor principal v2
# ============================================================
class AdaptiveForexStrategy:
    """
    Orquestador principal con mejoras integradas.
    """

    def __init__(self, adapter, cfg: Dict, trade_logger, notifier=None):
        self.adp = adapter
        self.cfg = cfg
        self.log = trade_logger
        self.notifier = notifier

        self.regime_detector = RegimeDetector(
            adx_trend=cfg.get("adx_trend_threshold", 25),
            adx_range=cfg.get("adx_range_threshold", 20),
            vol_spike=cfg.get("vol_spike_threshold", 1.5),
        )
        self.trend = TrendStrategy(cfg)
        self.mean_rev = MeanReversionStrategy(cfg)
        self.regulator = SelfRegulator(cfg, trade_logger, notifier)

        # MEJORAS nuevas
        self.session_filter = SessionFilter()
        self.currency_exposure = CurrencyExposure(
            max_exposure_per_currency=cfg.get("max_currency_exposure", 3)
        )
        self.macro_bias = MacroBias()
        self.use_macro_filter = cfg.get("use_macro_filter", True)
        self.use_session_filter = cfg.get("use_session_filter", True)
        self.use_currency_exposure = cfg.get("use_currency_exposure", True)

        self.pairs_trend = cfg.get("pairs_trend", [])
        self.pairs_mr = cfg.get("pairs_mean_reversion", [])
        self.all_pairs = list(set(self.pairs_trend + self.pairs_mr))
        self.max_positions = cfg.get("max_positions", 6)
        self.max_correlation = cfg.get("max_correlation", 0.75)
        self.max_gross_leverage = cfg.get("max_gross_leverage", 3.0)
        self.granularity = cfg.get("granularity", "D")
        self.min_bars = cfg.get("min_bars_required", 200)
        self.bb_std = cfg.get("bb_std", 2.0)

    def build_df(self, pair: str, count: int = 500) -> pd.DataFrame:
        df = self.adp.candles(
            instrument=pair, granularity=self.granularity, count=count
        )
        if df.empty or len(df) < self.min_bars:
            logger.warning(f"Datos insuficientes para {pair}: {len(df)} barras "
                         f"(mínimo {self.min_bars})")
            return df

        df["EMA20"] = ema(df["Close"], 20)
        df["EMA50"] = ema(df["Close"], 50)
        df["EMA200"] = ema(df["Close"], 200)
        df["ATR"] = atr(df["High"], df["Low"], df["Close"], 14)
        df["ADX"] = adx(df["High"], df["Low"], df["Close"], 14)
        df["RSI14"] = rsi(df["Close"], 14)

        bb_u, bb_m, bb_l, pct_b = bollinger(df["Close"], 20, self.bb_std)
        df["BB_Upper"] = bb_u
        df["BB_Mid"] = bb_m
        df["BB_Lower"] = bb_l
        df["PctB"] = pct_b

        dch, dcl = donchian(df["High"], df["Low"], 20)
        df["DCH"] = dch
        df["DCL"] = dcl

        df["VolRatio"] = volatility_regime(df["ATR"], 60)
        df["Ret"] = df["Close"].pct_change()

        return df.dropna().copy()

    def _validate_freshness(self, data: Dict[str, pd.DataFrame]) -> bool:
        now = pd.Timestamp.now(tz="UTC")
        freshness_map = {
            "D": 96, "1D": 96, "4H": 12, "1H": 3,
            "15min": 1, "5min": 0.5,
        }
        max_age_hours = freshness_map.get(self.granularity, 96)
        for pair, df in data.items():
            if df.empty:
                return False
            last = df.index[-1]
            if hasattr(last, 'tz') and last.tz is None:
                last = last.tz_localize("UTC")
            age_hours = (now - last).total_seconds() / 3600
            if age_hours > max_age_hours:
                logger.warning(f"Datos obsoletos {pair}: {age_hours:.1f}h "
                             f"(max {max_age_hours}h)")
                return False
        return True

    def size_units(self, pair: str, entry: float, stop: float,
                   equity: float, risk_frac: float) -> float:
        D = abs(entry - stop)
        if D <= 0 or entry <= 0:
            return 0.0
        units = (equity * risk_frac) / D
        max_notional = equity * self.max_gross_leverage
        notional = units * entry
        if notional > max_notional:
            units = units * (max_notional / notional)
        return round(max(0.0, units), 0)

    def _check_correlation(self, rets: pd.DataFrame, candidate: str,
                           open_pairs: List[str]) -> bool:
        if not open_pairs or candidate not in rets.columns:
            return True
        corr = rets.tail(60).corr()
        for p in open_pairs:
            if p not in corr.columns:
                continue
            c = corr.loc[candidate, p] if candidate in corr.index else 0
            if abs(c) > self.max_correlation:
                logger.info(f"Correlación {candidate}-{p}: {c:.2f} > {self.max_correlation}")
                return False
        return True

    def _calculate_global_vol_proxy(self, data: Dict[str, pd.DataFrame]) -> float:
        """MEJORA 8: calcula proxy de volatilidad global."""
        vol_ratios = []
        for pair, df in data.items():
            if not df.empty and "VolRatio" in df.columns:
                vol_ratios.append(df["VolRatio"].iloc[-1])
        return np.mean(vol_ratios) if vol_ratios else 1.0

    # ----------- Ciclo principal v2 -----------
    def run_daily_cycle(self) -> Dict:
        """Ciclo principal con todas las mejoras integradas."""

        # 0) Salud de sub-estrategias
        self.regulator.check_strategy_health()

        # 1) Descargar datos
        data = {}
        for pair in self.all_pairs:
            try:
                data[pair] = self.build_df(pair)
            except Exception as e:
                logger.error(f"Error descargando {pair}: {e}")

        # 2) Validar frescura
        if not self._validate_freshness(data):
            return {"opened": 0, "signals": [], "reason": "stale_data"}

        # 3) Estado de cuenta
        equity = self.adp.account_equity()
        self.regulator.update_equity_peak(equity)

        open_trades = self.adp.list_trades()
        open_pairs = [t["instrument"] for t in open_trades]

        if len(open_trades) >= self.max_positions:
            logger.info(f"Max posiciones ({self.max_positions})")
            return {"opened": 0, "signals": [], "reason": "max_positions"}

        # MEJORA 4: Detectar sesión actual
        utc_hour = datetime.now(timezone.utc).hour
        session = self.session_filter.get_session(utc_hour)

        # MEJORA 3: Calcular exposición actual por divisa
        currency_exp = self.currency_exposure.calculate_exposure(open_trades)

        # MEJORA 9: Derivar bias macro
        macro_bias = self.macro_bias.derive_currency_bias(data)

        # MEJORA 8: Proxy de volatilidad global
        global_vol = self._calculate_global_vol_proxy(data)

        # 4) Generar señales
        signals: List[ForexSignal] = []
        regimes = {}

        for pair, df in data.items():
            if len(df) < 50:
                continue

            regime = self.regime_detector.detect(df)
            regimes[pair] = regime

            sig = None

            if regime == "trending" or (regime == "ambiguous" and pair in self.pairs_trend):
                sig = self.trend.scan(pair, df)

            if sig is None and (regime == "ranging" or
                                (regime == "ambiguous" and pair in self.pairs_mr)):
                sig = self.mean_rev.scan(pair, df)

            if sig is not None:
                sig.regime = regime
                signals.append(sig)

        # 5) Priorizar
        signals.sort(key=lambda s: s.risk_R * s.atr, reverse=True)

        # 6) Correlaciones
        rets = pd.DataFrame({p: d["Ret"] for p, d in data.items() if "Ret" in d.columns})

        # 7) Ejecutar con filtros mejorados
        opened = 0
        for sig in signals:
            if sig.pair in open_pairs:
                continue
            if len(open_pairs) + opened >= self.max_positions:
                break

            # Correlación
            if not self._check_correlation(rets, sig.pair, open_pairs):
                continue

            # MEJORA 3: exposición por divisa
            if self.use_currency_exposure:
                if self.currency_exposure.would_exceed_exposure(
                    sig.pair, sig.side, currency_exp
                ):
                    logger.info(f"Skip {sig.pair}: excedería exposición divisa")
                    continue

            # MEJORA 9: conflicto con bias macro
            if self.use_macro_filter:
                if self.macro_bias.conflicts_with_bias(sig.pair, sig.side, macro_bias):
                    logger.info(f"Skip {sig.pair} {sig.side}: contra bias macro {macro_bias}")
                    continue

            # MEJORA 4: session confidence multiplier
            session_mult = self.session_filter.session_confidence_multiplier(
                session, sig.strategy
            )

            # Consultar regulador con mejoras integradas
            risk = self.regulator.get_risk_for_signal(
                sig, equity,
                vol_proxy=global_vol,
                session_mult=session_mult
            )
            if risk <= 0:
                continue

            units = self.size_units(sig.pair, sig.entry, sig.stop, equity, risk)
            if units <= 0:
                continue

            # Ejecutar orden
            try:
                resp = self.adp.place_bracket_market(
                    instrument=sig.pair, side=sig.side, units=units,
                    sl_price=sig.stop, tp_price=sig.tp,
                )
            except Exception as e:
                logger.error(f"Error enviando orden {sig.pair}: {e}")
                continue

            logger.info(f"ABIERTO: {sig.pair} {sig.side} {sig.strategy} "
                       f"units={units} entry={sig.entry} SL={sig.stop} "
                       f"TP={sig.tp} risk={risk:.4f} conf={sig.confidence:.2f} "
                       f"session={session}")

            if self.notifier:
                try:
                    self.notifier.notify_trade_opened(
                        sig.pair, sig.side, sig.strategy, units,
                        sig.entry, sig.stop, sig.tp, risk, sig.confidence
                    )
                except Exception:
                    pass

            try:
                oid = resp.get("id") if isinstance(resp, dict) else getattr(resp, "id", None)
                if oid:
                    st = self.log.load_state()
                    entries = st.get("entries", {})
                    entries[str(oid)] = {
                        "pair": sig.pair, "instrument": sig.pair,
                        "side": sig.side, "strategy": sig.strategy,
                        "units": units, "entry_price": sig.entry,
                        "entry_hint": sig.entry,
                        "initial_sl": sig.stop, "initial_tp": sig.tp,
                        "entry_ts": datetime.now(timezone.utc).isoformat(),
                        "confidence": sig.confidence, "regime": sig.regime,
                        "session": session,
                    }
                    st["entries"] = entries
                    self.log.save_state(st)
            except Exception as e:
                logger.error(f"Error guardando state {sig.pair}: {e}")

            # Actualizar exposición para los siguientes trades del ciclo
            if self.use_currency_exposure:
                currencies = CurrencyExposure.PAIR_CURRENCIES.get(sig.pair)
                if currencies:
                    base, quote = currencies
                    if sig.side == "long":
                        currency_exp[base] = currency_exp.get(base, 0) + 1
                        currency_exp[quote] = currency_exp.get(quote, 0) - 1
                    else:
                        currency_exp[base] = currency_exp.get(base, 0) - 1
                        currency_exp[quote] = currency_exp.get(quote, 0) + 1

            open_pairs.append(sig.pair)
            opened += 1

        self.log.log_equity(datetime.now(timezone.utc).isoformat(), equity)

        if self.notifier:
            try:
                self.notifier.notify_daily_summary(
                    equity, len(open_trades), len(signals), opened, regimes
                )
            except Exception:
                pass

        return {
            "opened": opened,
            "signals": [(s.pair, s.side, s.strategy, s.regime) for s in signals],
            "regimes": regimes,
            "session": session,
            "global_vol": round(global_vol, 2),
            "macro_bias": macro_bias,
        }

    # ----------- MEJORA 6: Trailing stops progresivo -----------
    def update_all_trailings(self) -> Dict:
        """Trailing progresivo con 4 niveles basados en R-múltiplo."""
        data = {}
        for pair in self.all_pairs:
            try:
                data[pair] = self.build_df(pair, count=100)
            except Exception:
                continue

        trades = self.adp.list_trades()
        updated = 0

        for t in trades:
            pair = t["instrument"]
            if pair not in data:
                continue

            df = data[pair]
            if df.empty:
                continue

            atr_now = df["ATR"].iloc[-1]
            current_price = df["Close"].iloc[-1]
            units = float(t.get("currentUnits", 0))
            entry = float(t.get("price", 0))

            if abs(units) < 1 or entry <= 0 or atr_now <= 0:
                continue

            side = "long" if units > 0 else "short"

            try:
                td = self.adp.trade_details(t["id"])
                current_sl = None
                sl_order = td.get("stopLossOrder")
                if sl_order and "price" in sl_order:
                    current_sl = float(sl_order["price"])
            except Exception:
                continue

            # Profit en R (usando ATR como proxy de riesgo)
            if side == "long":
                profit_atr = (current_price - entry) / atr_now
            else:
                profit_atr = (entry - current_price) / atr_now

            # MEJORA 6: Trailing progresivo con 4 niveles
            if profit_atr >= 3.0:
                # Nivel 4: profit excelente → trailing muy tight
                trail = 0.8 * atr_now
            elif profit_atr >= 2.0:
                # Nivel 3: buen profit → tight trailing
                trail = 1.2 * atr_now
            elif profit_atr >= 1.0:
                # Nivel 2: en profit → medio
                trail = 1.8 * atr_now
            else:
                # Nivel 1: inicio → amplio
                trail = 2.5 * atr_now

            # Breakeven: si profit > 1.5 ATR, mover SL a entry + pequeño buffer
            if profit_atr >= 1.5:
                buffer = 0.3 * atr_now
                be_price = entry + (buffer if side == "long" else -buffer)
                if current_sl is None or \
                   (side == "long" and be_price > current_sl) or \
                   (side == "short" and be_price < current_sl):
                    try:
                        self.adp.set_stop_loss(
                            t["id"], round(be_price, price_decimals(pair))
                        )
                        updated += 1
                        if self.notifier:
                            try:
                                self.notifier.notify_trailing_update(
                                    pair, current_sl or 0, be_price
                                )
                            except Exception:
                                pass
                        continue
                    except Exception as e:
                        logger.warning(f"Error breakeven {pair}: {e}")

            # Trailing normal
            if side == "long":
                proposed_sl = current_price - trail
                if current_sl is not None and proposed_sl <= current_sl:
                    continue
            else:
                proposed_sl = current_price + trail
                if current_sl is not None and proposed_sl >= current_sl:
                    continue

            try:
                self.adp.set_stop_loss(
                    t["id"], round(proposed_sl, price_decimals(pair))
                )
                updated += 1
                logger.info(f"Trail {pair}: SL → {proposed_sl:.5f} "
                           f"(profit {profit_atr:.1f} ATR, trail {trail/atr_now:.1f} ATR)")
            except Exception as e:
                logger.warning(f"Error trailing {pair}: {e}")

        return {"updated": updated}

    # ----------- Sync -----------
    def sync_transactions(self) -> Dict:
        sync_fn = getattr(self.adp, "sync_transactions", None)
        if not callable(sync_fn):
            return {"synced": 0}

        result = sync_fn(self.log)

        st = self.log.load_state()
        closed = st.get("recently_closed", [])
        for tc in closed:
            r_mult = tc.get("r_multiple")
            strat = tc.get("strategy", "trend")
            if r_mult is not None:
                self.regulator.record_trade(strat, float(r_mult))

            if self.notifier:
                try:
                    self.notifier.notify_trade_closed(
                        tc.get("pair", "?"), tc.get("side", "?"),
                        float(tc.get("pnl", 0)),
                        float(r_mult) if r_mult is not None else None,
                        tc.get("reason", "CLOSE"),
                    )
                except Exception:
                    pass

        st["recently_closed"] = []
        self.log.save_state(st)

        return result
