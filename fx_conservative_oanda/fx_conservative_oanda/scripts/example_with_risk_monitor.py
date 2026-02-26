# -*- coding: utf-8 -*-
"""
Script de ejemplo: Integrar RiskMonitor en el ciclo de trading.

Este ejemplo muestra cómo usar el RiskMonitor para:
1. Detectar drawdowns peligrosos
2. Generar alertas
3. Detener trading si el riesgo es crítico
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fx_conservative.config import load_config
from fx_conservative.logger import TradeLogger
from fx_conservative.oanda_adapter import OandaAdapter
from fx_conservative.strategy import FXConservativeLive
from fx_conservative.risk_monitor import RiskMonitor
import pandas as pd


def main():
    # Cargar configuración
    cfg = load_config("config/config_optimized.yaml")
    logger = TradeLogger(cfg.log_dir, cfg.state_path)
    
    # Conectar a OANDA
    adp = OandaAdapter()
    strat = FXConservativeLive(adp, cfg, logger)
    
    # Inicializar RiskMonitor
    initial_equity = adp.account_equity()
    risk_monitor = RiskMonitor(
        initial_equity=initial_equity,
        max_drawdown_pct=0.12,  # 12% max DD
        min_sharpe=0.6,
        lookback_days=30
    )
    
    print(f"💰 Equity Inicial: ${initial_equity:,.2f}")
    print("🔍 RiskMonitor iniciado")
    print("=" * 60)
    
    # Actualizar con equity actual
    current_equity = adp.account_equity()
    risk_monitor.update_equity(current_equity)
    
    # Cargar trades históricos del log si existen
    try:
        trades_df = pd.read_csv(os.path.join(cfg.log_dir, "trades.csv"))
        if not trades_df.empty:
            for _, trade in trades_df.iterrows():
                risk_monitor.add_trade(
                    pnl=trade['pnl_usd'],
                    r_multiple=trade['r_multiple'],
                    duration_days=trade['hold_days'],
                    pair=trade['pair'],
                    side=trade['side'],
                    timestamp=pd.to_datetime(trade['exit_ts'])
                )
            print(f"📊 Cargados {len(trades_df)} trades históricos")
    except FileNotFoundError:
        print("ℹ️  No hay trades históricos")
    
    # Obtener métricas actuales
    metrics = risk_monitor.get_current_metrics()
    
    print("\n📈 MÉTRICAS ACTUALES")
    print("=" * 60)
    print(f"Equity: ${metrics.get('current_equity', 0):,.2f}")
    print(f"Retorno Total: {metrics.get('total_return_pct', 0):.2%}")
    print(f"Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
    print(f"Max Drawdown: {metrics.get('max_drawdown_pct', 0):.2%}")
    print(f"DD Actual: {metrics.get('current_drawdown_pct', 0):.2%}")
    print(f"Win Rate: {metrics.get('win_rate', 0):.2%}")
    print(f"Avg R-Multiple: {metrics.get('avg_r_multiple', 0):.2f}")
    print(f"Profit Factor: {metrics.get('profit_factor', 0):.2f}")
    print(f"Total Trades: {metrics.get('total_trades', 0)}")
    
    # Verificar alertas
    alerts = risk_monitor.get_alerts()
    if alerts:
        print("\n⚠️  ALERTAS ACTIVAS")
        print("=" * 60)
        for alert in alerts:
            print(f"  {alert}")
    else:
        print("\n✅ Sin alertas activas")
    
    # Verificar si se debe detener trading
    should_stop = risk_monitor.should_stop_trading()
    if should_stop:
        print("\n🛑 STOP TRADING ACTIVADO - Riesgo Crítico Detectado")
        print("   No se ejecutarán nuevas operaciones hasta revisar")
        return
    
    # Si todo está bien, ejecutar ciclo normal
    print("\n🚀 Ejecutando ciclo de trading...")
    
    try:
        # Sincronizar transacciones
        sync_res = strat.sync_transactions()
        print(f"   Sync: {sync_res}")
        
        # Ejecutar ciclo
        result = strat.run_daily_cycle()
        print(f"   Resultado: {result}")
        
        # Actualizar equity post-ciclo
        new_equity = adp.account_equity()
        risk_monitor.update_equity(new_equity)
        
        # Generar reporte
        print("\n" + "=" * 60)
        print(risk_monitor.export_metrics_report())
        
    except Exception as e:
        print(f"\n❌ Error durante ejecución: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
