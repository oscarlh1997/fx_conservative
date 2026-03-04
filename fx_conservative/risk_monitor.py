# -*- coding: utf-8 -*-
"""
Sistema de monitoreo de riesgo en tiempo real.
Calcula métricas de performance, drawdown, y alertas.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class RiskMonitor:
    """
    Monitor de riesgo que trackea métricas en tiempo real y genera alertas.
    """
    
    def __init__(self, initial_equity: float, max_drawdown_pct: float = 0.15, 
                 min_sharpe: float = 0.5, lookback_days: int = 30):
        self.initial_equity = initial_equity
        self.max_drawdown_pct = max_drawdown_pct
        self.min_sharpe = min_sharpe
        self.lookback_days = lookback_days
        
        # Estado interno
        self.equity_history: List[Dict] = []
        self.trade_history: List[Dict] = []
        self.peak_equity = initial_equity
        self.alerts: List[str] = []
    
    def update_equity(self, equity: float, timestamp: Optional[datetime] = None):
        """Actualiza el equity actual y calcula métricas."""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        self.equity_history.append({
            'timestamp': timestamp,
            'equity': equity
        })
        
        # Actualizar peak
        if equity > self.peak_equity:
            self.peak_equity = equity
        
        # Calcular drawdown actual
        current_dd = (equity - self.peak_equity) / self.peak_equity
        
        # Generar alerta si el drawdown excede el límite
        if current_dd < -self.max_drawdown_pct:
            alert = f"⚠️ ALERTA DRAWDOWN: {current_dd:.2%} (límite: {-self.max_drawdown_pct:.2%})"
            self.alerts.append(alert)
            logger.warning(alert)
    
    def add_trade(self, pnl: float, r_multiple: float, duration_days: float, 
                  pair: str, side: str, timestamp: Optional[datetime] = None):
        """Registra un trade cerrado."""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        self.trade_history.append({
            'timestamp': timestamp,
            'pnl': pnl,
            'r_multiple': r_multiple,
            'duration_days': duration_days,
            'pair': pair,
            'side': side
        })
    
    def get_current_metrics(self) -> Dict:
        """
        Calcula métricas actuales de performance.
        """
        if not self.equity_history:
            return {}
        
        df_eq = pd.DataFrame(self.equity_history)
        current_equity = df_eq['equity'].iloc[-1]
        
        # Retornos
        returns = df_eq['equity'].pct_change().dropna()
        
        # Sharpe (anualizado a 252 días de trading)
        if len(returns) > 1:
            sharpe = (returns.mean() / (returns.std() + 1e-12)) * np.sqrt(252)
        else:
            sharpe = 0.0
        
        # Drawdown
        peak = df_eq['equity'].cummax()
        dd = (df_eq['equity'] - peak) / peak
        max_dd = dd.min()
        current_dd = (current_equity - self.peak_equity) / self.peak_equity
        
        # Métricas de trades (últimos lookback_days)
        cutoff = pd.Timestamp.utcnow().tz_localize(None) - timedelta(days=self.lookback_days)
        recent_trades = []
        for t in self.trade_history:
            ts = t['timestamp']
            # Normalize to naive datetime for comparison
            if hasattr(ts, 'tzinfo') and getattr(ts, 'tzinfo', None) is not None:
                try:
                    ts_naive = ts.replace(tzinfo=None)
                except Exception:
                    ts_naive = ts
            else:
                ts_naive = ts
            if hasattr(ts_naive, 'to_pydatetime'):
                ts_naive = ts_naive.to_pydatetime().replace(tzinfo=None)
            if ts_naive > cutoff.to_pydatetime():
                recent_trades.append(t)
        
        if recent_trades:
            df_tr = pd.DataFrame(recent_trades)
            win_rate = (df_tr['pnl'] > 0).mean()
            avg_r = df_tr['r_multiple'].mean()
            
            wins = df_tr[df_tr['pnl'] > 0]['pnl'].sum()
            losses = abs(df_tr[df_tr['pnl'] < 0]['pnl'].sum())
            profit_factor = wins / losses if losses > 0 else np.inf
        else:
            win_rate = 0.0
            avg_r = 0.0
            profit_factor = 0.0
        
        metrics = {
            'current_equity': current_equity,
            'total_return_pct': (current_equity - self.initial_equity) / self.initial_equity,
            'sharpe_ratio': sharpe,
            'max_drawdown_pct': max_dd,
            'current_drawdown_pct': current_dd,
            'win_rate': win_rate,
            'avg_r_multiple': avg_r,
            'profit_factor': profit_factor,
            'total_trades': len(self.trade_history),
            'recent_trades': len(recent_trades),
            'peak_equity': self.peak_equity
        }
        
        # Generar alertas si performance está deteriorándose
        if sharpe < self.min_sharpe and len(returns) > 20:
            alert = f"⚠️ ALERTA SHARPE BAJO: {sharpe:.2f} (mínimo: {self.min_sharpe:.2f})"
            if alert not in self.alerts:
                self.alerts.append(alert)
                logger.warning(alert)
        
        if win_rate < 0.35 and len(recent_trades) >= 10:
            alert = f"⚠️ ALERTA WIN RATE BAJO: {win_rate:.2%} (últimos {len(recent_trades)} trades)"
            if alert not in self.alerts:
                self.alerts.append(alert)
                logger.warning(alert)
        
        return metrics
    
    def get_alerts(self) -> List[str]:
        """Retorna alertas activas."""
        return self.alerts.copy()
    
    def clear_alerts(self):
        """Limpia alertas."""
        self.alerts.clear()
    
    def should_stop_trading(self) -> bool:
        """
        Determina si se debe detener el trading por riesgo excesivo.
        """
        if not self.equity_history:
            return False
        
        current_equity = self.equity_history[-1]['equity']
        current_dd = (current_equity - self.peak_equity) / self.peak_equity
        
        # Detener si el drawdown es mayor al doble del límite
        if current_dd < -2 * self.max_drawdown_pct:
            logger.critical(f"STOP TRADING: Drawdown crítico {current_dd:.2%}")
            return True
        
        # Detener si perdimos más del 30% del capital inicial
        if current_equity < self.initial_equity * 0.70:
            logger.critical(f"STOP TRADING: Pérdida de capital > 30%")
            return True
        
        return False
    
    def export_metrics_report(self) -> str:
        """
        Genera reporte en formato markdown con métricas actuales.
        """
        metrics = self.get_current_metrics()
        
        if not metrics:
            return "# Sin datos suficientes para generar reporte\n"
        
        report = f"""# Reporte de Performance - {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

## Métricas Principales

- **Equity Actual**: ${metrics['current_equity']:,.2f}
- **Retorno Total**: {metrics['total_return_pct']:.2%}
- **Peak Equity**: ${metrics['peak_equity']:,.2f}

## Métricas de Riesgo

- **Sharpe Ratio**: {metrics['sharpe_ratio']:.2f}
- **Max Drawdown**: {metrics['max_drawdown_pct']:.2%}
- **Drawdown Actual**: {metrics['current_drawdown_pct']:.2%}

## Métricas de Trading ({self.lookback_days} días)

- **Win Rate**: {metrics['win_rate']:.2%}
- **Avg R-Multiple**: {metrics['avg_r_multiple']:.2f}
- **Profit Factor**: {metrics['profit_factor']:.2f}
- **Trades Recientes**: {metrics['recent_trades']}
- **Total Trades**: {metrics['total_trades']}

## Alertas Activas

"""
        if self.alerts:
            for alert in self.alerts:
                report += f"- {alert}\n"
        else:
            report += "✅ Sin alertas activas\n"
        
        return report
