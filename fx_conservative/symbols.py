# -*- coding: utf-8 -*-
"""
Symbol helpers.

This project targets Alpaca US equities by default, so most symbols are used as-is (e.g. SPY).
If you need to translate between "strategy symbols" and "broker symbols", populate SYMBOL_MAP.
"""

from __future__ import annotations

from typing import Dict


# Optional: custom mapping from strategy symbol -> broker symbol.
SYMBOL_MAP: Dict[str, str] = {}

# For risk sizing on FX-style symbols: whether USD is quote (EURUSD) vs base (USDJPY).
USD_IS_QUOTE: Dict[str, bool] = {
    "EURUSD": True,
    "GBPUSD": True,
    "AUDUSD": True,
    "NZDUSD": True,
    "USDJPY": False,
    "USDCHF": False,
    "USDCAD": False,
}


def instrument_for_symbol(symbol: str) -> str:
    """Convert strategy symbol into broker symbol (defaults to identity)."""
    return SYMBOL_MAP.get(symbol, symbol)


def symbol_for_instrument(instrument: str) -> str:
    """Convert broker symbol into strategy symbol (best-effort)."""
    # Normalize common "XXX_YYY" or "XXX/YYY" formats back into "XXXYYY".
    s = instrument.replace("_", "").replace("/", "")
    if len(s) == 6 and s.isalpha():
        return s.upper()
    return instrument


def usd_is_quote(symbol: str) -> bool:
    """
    Best-effort guess used by risk sizing.
    - Known FX pairs use USD_IS_QUOTE.
    - For symbols like BTC/USD, assume USD is quote if it ends with /USD.
    - For symbols like USDJPY or USD/JPY, assume USD is base.
    - Otherwise default to True (common for US equities quoted in USD).
    """
    if symbol in USD_IS_QUOTE:
        return bool(USD_IS_QUOTE[symbol])

    s = symbol.replace("_", "").replace("/", "")
    if s.startswith("USD") and not s.endswith("USD"):
        return False
    if s.endswith("USD") and not s.startswith("USD"):
        return True
    return True

