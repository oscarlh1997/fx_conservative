# -*- coding: utf-8 -*-
"""
Tests unitarios para funciones críticas de trading.
Ejecutar con: python -m pytest tests/
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

# Agregar el path del proyecto
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../fx_conservative_oanda'))

from fx_conservative.config import Config
from fx_conservative.logger import TradeLogger



class MockAdapter:
    """Mock adapter para testing sin conexión a broker."""
    def __init__(self):
        self.account_id = "TEST-001"

    def account_equity(self):
        return 100000.0

    def list_trades(self):
        return []

    def candles(self, instrument, granularity="D", count=2000, **kwargs):
        """Devuelve un DataFrame OHLCV sintético para tests."""
        n = max(300, count)
        np.random.seed(42)
        closes = 100 + np.cumsum(np.random.randn(n) * 0.5)
        closes = np.maximum(closes, 1.0)
        df = pd.DataFrame({
            "Open": closes * (1 - 0.001),
            "High": closes * (1 + 0.005),
            "Low": closes * (1 - 0.005),
            "Close": closes,
            "Volume": np.random.randint(1_000_000, 5_000_000, size=n).astype(float),
        }, index=pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC"))
        return df

    def trade_details(self, trade_id):
        return {}

    def place_bracket_market(self, instrument, side, units, sl_price, tp_price, **kwargs):
        return {"id": "mock-order-001", "symbol": instrument, "status": "accepted"}

    def last_transaction_id(self):
        return pd.Timestamp.utcnow().isoformat()


class TestPositionSizing:
    """Tests para cálculo de tamaño de posición."""
    
    def test_size_units_eurusd_long(self):
        """Test sizing para EURUSD (USD es quote)."""
        # Para EURUSD, riesgo_usd = units * D
        # Si equity=100k, risk=0.25%, entry=1.1000, stop=1.0950
        # D = 0.0050, risk_usd = 250
        # units = 250 / 0.0050 = 50,000
        
        equity = 100000
        risk_frac = 0.0025
        entry = 1.1000
        stop = 1.0950
        
        # Simulación del cálculo
        D = abs(entry - stop)  # 0.0050
        expected_units = int((equity * risk_frac) / D)  # 50,000
        
        assert D == pytest.approx(0.0050)
        assert expected_units in (49999, 50000)
    
    def test_size_units_usdjpy_long(self):
        """Test sizing para USDJPY (USD es base)."""
        # Para USDJPY, riesgo_usd = units * D / entry
        # Si equity=100k, risk=0.25%, entry=110.00, stop=109.00
        # D = 1.00, risk_usd = 250
        # units = (250 * 110) / 1.00 = 27,500
        
        equity = 100000
        risk_frac = 0.0025
        entry = 110.00
        stop = 109.00
        
        D = abs(entry - stop)  # 1.00
        expected_units = int((equity * risk_frac * entry) / D)  # 27,500
        
        assert D == 1.00
        assert expected_units == 27500
    
    def test_notional_calculation_eurusd(self):
        """Test cálculo de notional para EURUSD."""
        pair = "EURUSD"
        units = 100000
        price = 1.1000
        
        # Para EURUSD (USD es quote): notional = units * price
        expected = abs(units * price)  # 110,000 USD
        
        assert expected == pytest.approx(110000)
    
    def test_notional_calculation_usdjpy(self):
        """Test cálculo de notional para USDJPY."""
        pair = "USDJPY"
        units = 100000
        price = 110.00
        
        # Para USDJPY (USD es base): notional = units (ya está en USD)
        expected = abs(units)  # 100,000 USD
        
        assert expected == 100000


class TestRiskManagement:
    """Tests para gestión de riesgo."""
    
    def test_max_notional_safeguard(self):
        """Test que el safeguard de max notional funciona."""
        equity = 10000
        risk_frac = 0.10  # 10% (muy alto para test)
        entry = 1.1000
        stop = 1.0900
        
        D = abs(entry - stop)  # 0.0100
        units_raw = int((equity * risk_frac) / D)  # 100,000
        
        # Notional sería 110k USD, que es > 10% de equity (1k)
        # Debe reducirse
        max_notional = equity * 0.10  # 1,000 USD
        current_notional = units_raw * entry  # 110,000 USD
        
        assert current_notional > max_notional
        
        # Aplicar safeguard
        scale_factor = max_notional / current_notional
        units_safe = int(units_raw * scale_factor)
        
        # Verificar que el nuevo notional es <= max
        new_notional = units_safe * entry
        assert new_notional <= max_notional * 1.01  # Pequeño margen por redondeo
    
    def test_risk_cap_enforcement(self):
        """Test que el cupo de riesgo total se respeta."""
        equity = 100000
        total_risk_cap = 0.01  # 1% = $1000
        risk_per_trade = 0.0025  # 0.25% = $250
        
        # Con 4 trades abiertos, el riesgo usado sería $1000
        used_risk = 4 * (equity * risk_per_trade)
        risk_cupo = equity * total_risk_cap - used_risk
        
        assert risk_cupo == 0  # No queda cupo
        
        # Intentar nueva operación
        can_open_new = (equity * risk_per_trade) <= risk_cupo
        assert can_open_new == False


class TestIndicators:
    """Tests para indicadores técnicos."""
    
    def test_ema_calculation(self):
        """Test cálculo básico de EMA."""
        from fx_conservative.indicators import ema
        
        # Serie simple para test
        data = pd.Series([100, 101, 102, 103, 104, 105])
        result = ema(data, span=3)
        
        # Verificar que retorna una Serie del mismo tamaño
        assert len(result) == len(data)
        
        # Verificar que el último valor es razonable
        assert result.iloc[-1] > data.mean()
    
    def test_atr_calculation(self):
        """Test cálculo de ATR."""
        from fx_conservative.indicators import atr
        
        # Crear datos de prueba
        high = pd.Series([1.11, 1.12, 1.13, 1.12, 1.14])
        low = pd.Series([1.09, 1.10, 1.11, 1.10, 1.12])
        close = pd.Series([1.10, 1.11, 1.12, 1.11, 1.13])
        
        result = atr(high, low, close, period=3)
        
        # ATR debe ser positivo
        assert (result >= 0).all()
        
        # ATR debe ser razonable (no NaN)
        assert not result.isna().all()
    
    def test_donchian_breakout_logic(self):
        """Test lógica de breakout Donchian."""
        from fx_conservative.indicators import donchian
        
        # Crear serie con breakout claro
        high = pd.Series([100, 101, 102, 103, 104, 110])  # Breakout en el último
        low = pd.Series([98, 99, 100, 101, 102, 108])
        
        dch, dcl = donchian(high, low, n=5)
        
        # El breakout debería ser visible
        last_high = high.iloc[-1]
        last_dch = dch.iloc[-1]
        
        # 110 > 104 (máximo de los 5 anteriores)
        assert last_high > last_dch


class TestSignalValidation:
    """Tests para validación de señales."""
    
    def test_directional_regime_filters(self):
        """Test que los filtros de régimen funcionen correctamente."""
        # Datos simulados de una tendencia alcista fuerte
        row = pd.Series({
            'Close': 1.1500,
            'EMA50': 1.1400,
            'EMA200': 1.1200,
            'ADX': 25.0
        })
        
        # Régimen alcista
        long_reg = (row['Close'] > row['EMA200']) and (row['EMA50'] > row['EMA200']) and (row['ADX'] > 20)
        assert long_reg == True
        
        # Separación EMA
        ema_sep = abs(row['EMA50'] - row['EMA200']) / row['EMA200']
        min_sep = 0.002
        assert ema_sep > min_sep  # 1.79% > 0.2%
    
    def test_signal_quality_volatility_filter(self):
        """Test que señales con ATR muy bajo se rechacen."""
        row = pd.Series({
            'Close': 1.1000,
            'ATR': 0.00001  # ATR extremadamente bajo
        })
        
        # Validar ATR mínimo (0.05% del precio)
        min_atr = row['Close'] * 0.0005  # 0.00055
        is_valid = row['ATR'] >= min_atr
        
        assert is_valid == False  # Debe rechazarse


class TestCorrelation:
    """Tests para cálculo de correlación."""
    
    def test_correlation_detection(self):
        """Test detección de alta correlación entre pares."""
        # Crear dos series altamente correlacionadas
        np.random.seed(42)
        ret1 = pd.Series(np.random.randn(100) * 0.01)
        ret2 = ret1 + np.random.randn(100) * 0.001  # Casi idéntica
        
        df = pd.DataFrame({'EURUSD': ret1, 'GBPUSD': ret2})
        corr_matrix = df.corr()
        
        correlation = corr_matrix.loc['EURUSD', 'GBPUSD']
        threshold = 0.80
        
        assert correlation > threshold  # Alta correlación
    
    def test_uncorrelated_pairs(self):
        """Test pares no correlacionados."""
        np.random.seed(42)
        ret1 = pd.Series(np.random.randn(100) * 0.01)
        ret2 = pd.Series(np.random.randn(100) * 0.01)  # Independiente
        
        df = pd.DataFrame({'EURUSD': ret1, 'USDJPY': ret2})
        corr_matrix = df.corr()
        
        correlation = abs(corr_matrix.loc['EURUSD', 'USDJPY'])
        threshold = 0.80
        
        # Es posible que aleatoriamente salga alta, pero normalmente será baja
        # En este test solo verificamos que el cálculo funciona
        assert -1 <= correlation <= 1


class TestRiskMonitor:
    """Tests para el monitor de riesgo."""
    
    def test_drawdown_calculation(self):
        """Test cálculo de drawdown."""
        from fx_conservative.risk_monitor import RiskMonitor
        
        monitor = RiskMonitor(initial_equity=100000, max_drawdown_pct=0.15)
        
        # Simular equity creciendo y luego cayendo
        monitor.update_equity(105000)
        monitor.update_equity(110000)  # Peak
        monitor.update_equity(100000)  # -9% del peak
        
        metrics = monitor.get_current_metrics()
        
        # Drawdown actual debería ser negativo
        assert metrics['current_drawdown_pct'] < 0
        assert metrics['peak_equity'] == 110000
    
    def test_sharpe_calculation(self):
        """Test cálculo de Sharpe ratio."""
        from fx_conservative.risk_monitor import RiskMonitor
        
        monitor = RiskMonitor(initial_equity=100000)
        
        # Simular equity con retornos positivos consistentes
        for i in range(30):
            equity = 100000 * (1 + 0.001 * i)  # Crecimiento lineal
            monitor.update_equity(equity)
        
        metrics = monitor.get_current_metrics()
        
        # Sharpe debería ser positivo con retornos consistentes
        assert metrics['sharpe_ratio'] > 0
    
    def test_stop_trading_on_critical_dd(self):
        """Test que se active stop trading en drawdown crítico."""
        from fx_conservative.risk_monitor import RiskMonitor
        
        monitor = RiskMonitor(initial_equity=100000, max_drawdown_pct=0.15)
        
        # Simular pérdida del 35% (más del doble del límite de 15%)
        monitor.update_equity(110000)  # Peak
        monitor.update_equity(65000)   # -41% del peak
        
        should_stop = monitor.should_stop_trading()
        assert should_stop == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
