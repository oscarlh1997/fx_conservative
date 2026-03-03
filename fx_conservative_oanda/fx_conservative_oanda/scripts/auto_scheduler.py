# -*- coding: utf-8 -*-
"""
Scheduler automático para trading en horarios específicos del mercado FX.

Este módulo permite:
1. Ejecutar trading solo en horarios de mercado abierto
2. Evitar fines de semana y festivos
3. Actualizar trailing stops periódicamente
4. Sincronizar transacciones automáticamente
5. Generar reportes periódicos
"""
import sys
import os
import time
import schedule
from datetime import datetime, time as dt_time
import pytz
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fx_conservative.config import load_config
from fx_conservative.logger import TradeLogger
from fx_conservative.strategy import FXConservativeLive
from fx_conservative.risk_monitor import RiskMonitor
from fx_conservative.diagnostics import SystemDiagnostics, generate_markdown_report
import pandas as pd

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def make_adapter():
    from fx_conservative.alpaca_adapter import AlpacaAdapter
    return AlpacaAdapter()


class TradingScheduler:
    """
    Scheduler automático que ejecuta trading en horarios específicos.
    """
    
    def __init__(self, config_path: str = "config/config_optimized.yaml"):
        self.config_path = config_path
        self.cfg = load_config(config_path)
        self.logger = TradeLogger(self.cfg.log_dir, self.cfg.state_path)
        self.adp = make_adapter()
        self.strat = FXConservativeLive(self.adp, self.cfg, self.logger)
        
        # Inicializar RiskMonitor
        initial_equity = self.adp.account_equity()
        self.risk_monitor = RiskMonitor(
            initial_equity=initial_equity,
            max_drawdown_pct=0.12,
            min_sharpe=0.6,
            lookback_days=30
        )
        
        # Cargar trades históricos
        self._load_historical_trades()
        
        logger.info(f"✅ TradingScheduler inicializado con equity: ${initial_equity:,.2f}")
    
    def _load_historical_trades(self):
        """Carga trades históricos en el RiskMonitor."""
        try:
            trades_df = pd.read_csv(os.path.join(self.cfg.log_dir, "trades.csv"))
            if not trades_df.empty:
                for _, trade in trades_df.iterrows():
                    self.risk_monitor.add_trade(
                        pnl=trade['pnl_usd'],
                        r_multiple=trade['r_multiple'],
                        duration_days=trade['hold_days'],
                        pair=trade['pair'],
                        side=trade['side'],
                        timestamp=pd.to_datetime(trade['exit_ts'])
                    )
                logger.info(f"📊 Cargados {len(trades_df)} trades históricos")
        except FileNotFoundError:
            logger.info("ℹ️  No hay trades históricos")
    
    def is_forex_market_open(self) -> bool:
        """
        Verifica si el mercado FX está abierto.
        FX opera 24/5: Lunes 00:00 GMT - Viernes 23:59 GMT
        """
        now_utc = datetime.now(pytz.UTC)
        
        # Verificar fin de semana
        weekday = now_utc.weekday()
        if weekday == 5:  # Sábado
            return False
        if weekday == 6:  # Domingo (antes de 22:00 UTC)
            if now_utc.hour < 22:
                return False
        
        # Viernes después de 22:00 UTC se considera cerrado
        if weekday == 4 and now_utc.hour >= 22:
            return False
        
        return True
    
    def is_safe_trading_time(self) -> bool:
        """
        Verifica si es un horario seguro para operar.
        Evita las primeras horas del domingo y últimas del viernes.
        """
        now_utc = datetime.now(pytz.UTC)
        weekday = now_utc.weekday()
        hour = now_utc.hour
        
        # Domingo: solo después de 23:00 UTC (apertura de Sydney)
        if weekday == 6 and hour < 23:
            return False
        
        # Viernes: solo hasta 20:00 UTC (antes del cierre)
        if weekday == 4 and hour >= 20:
            return False
        
        return True
    
    def execute_daily_cycle(self):
        """Ejecuta el ciclo diario de trading."""
        try:
            # Verificar si el mercado está abierto
            if not self.is_forex_market_open():
                logger.info("⏸️  Mercado cerrado - no se ejecuta ciclo")
                return
            
            if not self.is_safe_trading_time():
                logger.info("⏸️  Fuera de horario seguro - no se ejecuta ciclo")
                return
            
            # Verificar si debemos detener trading por riesgo
            if self.risk_monitor.should_stop_trading():
                logger.critical("🛑 STOP TRADING ACTIVADO - Riesgo crítico detectado")
                return
            
            logger.info("🚀 Iniciando ciclo diario de trading...")
            
            # Sincronizar transacciones
            sync_res = self.strat.sync_transactions()
            logger.info(f"   Sync: {sync_res}")
            
            # Actualizar equity en RiskMonitor
            current_equity = self.adp.account_equity()
            self.risk_monitor.update_equity(current_equity)
            
            # Ejecutar ciclo de trading
            result = self.strat.run_daily_cycle()
            logger.info(f"   Resultado: {result}")
            
            # Verificar alertas
            alerts = self.risk_monitor.get_alerts()
            if alerts:
                logger.warning("⚠️  ALERTAS ACTIVAS:")
                for alert in alerts:
                    logger.warning(f"   {alert}")
            
            logger.info("✅ Ciclo diario completado")
            
        except Exception as e:
            logger.error(f"❌ Error en ciclo diario: {e}", exc_info=True)
    
    def update_trailings(self):
        """Actualiza trailing stops de posiciones abiertas."""
        try:
            if not self.is_forex_market_open():
                logger.info("⏸️  Mercado cerrado - no se actualizan trailings")
                return
            
            logger.info("🔄 Actualizando trailing stops...")
            result = self.strat.update_all_trailings()
            logger.info(f"   Resultado: {result}")
            
        except Exception as e:
            logger.error(f"❌ Error actualizando trailings: {e}", exc_info=True)
    
    def sync_transactions(self):
        """Sincroniza transacciones y actualiza trades cerrados."""
        try:
            logger.info("🔄 Sincronizando transacciones...")
            result = self.strat.sync_transactions()
            logger.info(f"   Resultado: {result}")
            
        except Exception as e:
            logger.error(f"❌ Error sincronizando transacciones: {e}", exc_info=True)
    
    def generate_daily_report(self):
        """Genera reporte diario de performance."""
        try:
            logger.info("📊 Generando reporte diario...")
            
            # Actualizar equity
            current_equity = self.adp.account_equity()
            self.risk_monitor.update_equity(current_equity)
            
            # Generar reporte de métricas
            report = self.risk_monitor.export_metrics_report()
            
            # Guardar en archivo
            report_path = os.path.join(self.cfg.log_dir, f"daily_report_{datetime.now().strftime('%Y%m%d')}.md")
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report)
            
            logger.info(f"   Reporte guardado en: {report_path}")
            
            # Log métricas principales
            metrics = self.risk_monitor.get_current_metrics()
            logger.info(f"   Equity: ${metrics.get('current_equity', 0):,.2f}")
            logger.info(f"   Retorno: {metrics.get('total_return_pct', 0):.2%}")
            logger.info(f"   Sharpe: {metrics.get('sharpe_ratio', 0):.2f}")
            logger.info(f"   DD: {metrics.get('current_drawdown_pct', 0):.2%}")
            
        except Exception as e:
            logger.error(f"❌ Error generando reporte: {e}", exc_info=True)
    
    def generate_diagnostic_report(self):
        """
        Genera informe completo de diagnóstico del sistema.
        Detecta fallos, anomalías y oportunidades de mejora.
        """
        try:
            logger.info("🔍 Generando informe de diagnóstico...")
            
            # Crear directorio logs si no existe
            os.makedirs(self.cfg.log_dir, exist_ok=True)
            
            # Ejecutar análisis completo
            diagnostics = SystemDiagnostics(self.cfg.log_dir)
            report = diagnostics.analyze_all(lookback_days=30)
            
            # Generar reporte en Markdown
            diagnostic_path = os.path.join(
                self.cfg.log_dir, 
                f"diagnostic_report_{datetime.now().strftime('%Y%m%d')}.md"
            )
            generate_markdown_report(report, diagnostic_path)
            
            # Log resumen
            logger.info(f"   ✅ Diagnóstico completado")
            logger.info(f"   📋 Salud del sistema: {report.system_health_score:.0f}/100")
            logger.info(f"   🔴 Problemas críticos: {report.critical_issues}")
            logger.info(f"   🟠 Problemas altos: {report.high_issues}")
            logger.info(f"   🟡 Problemas medios: {report.medium_issues}")
            logger.info(f"   📄 Reporte guardado en: {diagnostic_path}")
            
            # Alertar si hay problemas críticos
            if report.critical_issues > 0:
                logger.warning("⚠️  SE DETECTARON PROBLEMAS CRÍTICOS - REVISAR REPORTE URGENTEMENTE")
            
        except Exception as e:
            logger.error(f"❌ Error generando diagnóstico: {e}", exc_info=True)
    
    def setup_schedule(self):
        """
        Configura el schedule de tareas automáticas.
        
        Programación:
        - Ciclo de trading: Diariamente a las 17:05 NY (después del cierre D1)
        - Trailing stops: Cada 6 horas
        - Sincronización: Cada 2 horas
        - Reporte diario: Todos los días a las 23:00 UTC
        - Diagnóstico semanal: Todos los lunes a las 08:00 UTC
        """
        # Ciclo principal de trading (17:05 hora de Nueva York)
        # Se ejecuta 5 minutos después del cierre D1 oficial
        schedule.every().day.at("22:05").do(self.execute_daily_cycle)  # 17:05 NY = 22:05 UTC (horario estándar)
        
        # Actualización de trailing stops (cada 6 horas)
        schedule.every().day.at("00:00").do(self.update_trailings)
        schedule.every().day.at("06:00").do(self.update_trailings)
        schedule.every().day.at("12:00").do(self.update_trailings)
        schedule.every().day.at("18:00").do(self.update_trailings)
        
        # Sincronización de transacciones (cada 2 horas)
        schedule.every().day.at("01:00").do(self.sync_transactions)
        schedule.every().day.at("03:00").do(self.sync_transactions)
        schedule.every().day.at("05:00").do(self.sync_transactions)
        schedule.every().day.at("07:00").do(self.sync_transactions)
        schedule.every().day.at("09:00").do(self.sync_transactions)
        schedule.every().day.at("11:00").do(self.sync_transactions)
        schedule.every().day.at("13:00").do(self.sync_transactions)
        schedule.every().day.at("15:00").do(self.sync_transactions)
        schedule.every().day.at("17:00").do(self.sync_transactions)
        schedule.every().day.at("19:00").do(self.sync_transactions)
        schedule.every().day.at("21:00").do(self.sync_transactions)
        schedule.every().day.at("23:00").do(self.sync_transactions)
        
        # Reporte diario
        schedule.every().day.at("23:00").do(self.generate_daily_report)
        
        # Diagnóstico completo semanal (todos los lunes a las 08:00 UTC)
        schedule.every().monday.at("08:00").do(self.generate_diagnostic_report)
        
        logger.info("📅 Schedule configurado:")
        logger.info("   - Trading: 17:05 NY (22:05 UTC) diario")
        logger.info("   - Trailing: Cada 6 horas (00, 06, 12, 18 UTC)")
        logger.info("   - Sync: Cada 2 horas")
        logger.info("   - Reporte: 23:00 UTC diario")
        logger.info("   - Diagnóstico: Lunes 08:00 UTC semanal")
    
    def run(self):
        """
        Inicia el scheduler y lo mantiene corriendo.
        """
        logger.info("=" * 60)
        logger.info("🤖 TRADING SCHEDULER INICIADO")
        logger.info("=" * 60)
        
        # Configurar schedule
        self.setup_schedule()
        
        # Mostrar próximas tareas
        logger.info("\n📋 Próximas tareas programadas:")
        for job in schedule.jobs[:5]:
            logger.info(f"   - {job}")
        
        logger.info("\n⏰ Esperando próxima ejecución... (Ctrl+C para detener)\n")
        
        # Loop principal
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Verificar cada minuto
                
        except KeyboardInterrupt:
            logger.info("\n\n🛑 Scheduler detenido por el usuario")
            logger.info("=" * 60)


def main():
    """Punto de entrada principal."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Trading Scheduler Automático")
    parser.add_argument(
        "--config",
        default="config/config_optimized.yaml",
        help="Ruta al archivo de configuración"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Ejecuta un ciclo de test inmediato"
    )
    
    args = parser.parse_args()
    
    # Crear scheduler
    scheduler = TradingScheduler(args.config)
    
    if args.test:
        # Modo test: ejecuta un ciclo inmediato
        logger.info("🧪 MODO TEST - Ejecutando ciclo inmediato")
        scheduler.execute_daily_cycle()
        scheduler.update_trailings()
        scheduler.generate_daily_report()
        logger.info("✅ Test completado")
    else:
        # Modo normal: inicia el scheduler
        scheduler.run()


if __name__ == "__main__":
    main()
