# -*- coding: utf-8 -*-
"""
Sistema de Diagnóstico y Auto-Análisis
Genera informes completos para detectar fallos y oportunidades de mejora.
"""
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticIssue:
    """Representa un problema detectado."""
    severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"
    category: str  # "RISK", "PERFORMANCE", "DATA_QUALITY", "SYSTEM", "STRATEGY"
    title: str
    description: str
    impact: str
    recommendation: str
    metric_value: Optional[float] = None
    threshold: Optional[float] = None


@dataclass
class DiagnosticReport:
    """Informe completo de diagnóstico."""
    timestamp: str
    analysis_period_days: int
    total_issues: int
    critical_issues: int
    high_issues: int
    medium_issues: int
    low_issues: int
    issues: List[DiagnosticIssue]
    metrics_summary: Dict[str, Any]
    recommendations_summary: List[str]
    system_health_score: float  # 0-100


class SystemDiagnostics:
    """
    Analizador completo del sistema de trading.
    Detecta problemas, anomalías y oportunidades de mejora.
    """
    
    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        self.issues: List[DiagnosticIssue] = []
        
    def analyze_all(self, lookback_days: int = 30) -> DiagnosticReport:
        """
        Ejecuta análisis completo del sistema.
        """
        logger.info(f"Iniciando análisis de diagnóstico (últimos {lookback_days} días)")
        self.issues = []
        
        # 1. Análisis de calidad de datos
        self._analyze_data_quality()
        
        # 2. Análisis de performance de trading
        self._analyze_trading_performance(lookback_days)
        
        # 3. Análisis de gestión de riesgo
        self._analyze_risk_management(lookback_days)
        
        # 4. Análisis de ejecución de órdenes
        self._analyze_order_execution()
        
        # 5. Análisis de señales vs resultados
        self._analyze_signal_quality()
        
        # 6. Análisis de slippage y costos
        self._analyze_costs()
        
        # 7. Análisis de timing y estacionalidad
        self._analyze_timing_patterns()
        
        # 8. Análisis de sistema (errores, latencia)
        self._analyze_system_health()
        
        # 9. Análisis de parámetros vs mercado
        self._analyze_parameter_drift()
        
        # Generar reporte consolidado
        report = self._generate_report(lookback_days)
        
        logger.info(f"Diagnóstico completado: {report.total_issues} problemas detectados")
        return report
    
    # ========== ANÁLISIS DE CALIDAD DE DATOS ==========
    
    def _analyze_data_quality(self):
        """Detecta problemas en la calidad de datos históricos."""
        logger.info("Analizando calidad de datos...")
        
        # Verificar archivos necesarios
        required_files = ["signals.csv", "orders.csv", "fills.csv", "trades.csv", "equity.csv"]
        for fname in required_files:
            path = os.path.join(self.log_dir, fname)
            if not os.path.exists(path):
                self.issues.append(DiagnosticIssue(
                    severity="HIGH",
                    category="DATA_QUALITY",
                    title=f"Archivo faltante: {fname}",
                    description=f"No se encuentra el archivo {fname} en {self.log_dir}",
                    impact="No se pueden calcular métricas dependientes de este archivo",
                    recommendation=f"Verificar que el TradeLogger esté funcionando correctamente"
                ))
        
        # Analizar equity.csv
        try:
            equity_df = self._load_equity()
            if equity_df.empty:
                self.issues.append(DiagnosticIssue(
                    severity="CRITICAL",
                    category="DATA_QUALITY",
                    title="Sin datos de equity",
                    description="El archivo equity.csv está vacío",
                    impact="No se puede monitorear la evolución del capital",
                    recommendation="Verificar que log_equity() se esté ejecutando en cada ciclo"
                ))
            else:
                # Detectar gaps en equity
                equity_df = equity_df.sort_values("ts")
                time_diffs = equity_df["ts"].diff().dt.total_seconds() / 3600
                max_gap = time_diffs.max()
                if max_gap > 72:  # Más de 3 días
                    self.issues.append(DiagnosticIssue(
                        severity="MEDIUM",
                        category="DATA_QUALITY",
                        title="Gaps en registro de equity",
                        description=f"Detectado gap máximo de {max_gap/24:.1f} días entre registros",
                        impact="Métricas de Sharpe y DD pueden ser imprecisas",
                        recommendation="Asegurar que el scheduler ejecute log_equity() diariamente",
                        metric_value=max_gap/24,
                        threshold=3.0
                    ))
                
                # Detectar valores duplicados
                duplicates = equity_df["ts"].duplicated().sum()
                if duplicates > 0:
                    self.issues.append(DiagnosticIssue(
                        severity="LOW",
                        category="DATA_QUALITY",
                        title="Timestamps duplicados en equity",
                        description=f"Encontrados {duplicates} registros con timestamps duplicados",
                        impact="Puede causar errores en cálculos de retornos",
                        recommendation="Deduplicar registros manteniendo el último valor",
                        metric_value=duplicates
                    ))
        except Exception as e:
            logger.warning(f"Error analizando equity: {e}")
        
        # Analizar trades.csv
        try:
            trades_df = self._load_trades()
            if not trades_df.empty:
                # Detectar trades con R múltiple anormal
                extreme_r = trades_df[np.abs(trades_df["r_multiple"]) > 10]
                if len(extreme_r) > 0:
                    self.issues.append(DiagnosticIssue(
                        severity="HIGH",
                        category="DATA_QUALITY",
                        title="R múltiples anormales detectados",
                        description=f"{len(extreme_r)} trades con |R| > 10 (posible error de cálculo)",
                        impact="Métricas de AvgR y expectativa pueden estar distorsionadas",
                        recommendation="Revisar función size_units() y cálculo de R en log_trade_close()",
                        metric_value=len(extreme_r)
                    ))
                
                # Detectar trades con duración cero
                zero_duration = trades_df[trades_df["hold_days"] < 0.001]
                if len(zero_duration) > 0:
                    self.issues.append(DiagnosticIssue(
                        severity="MEDIUM",
                        category="DATA_QUALITY",
                        title="Trades con duración cero",
                        description=f"{len(zero_duration)} trades con hold_days ≈ 0",
                        impact="Posibles trades cerrados inmediatamente (slippage extremo?)",
                        recommendation="Revisar lógica de entrada/salida y validación de fills",
                        metric_value=len(zero_duration)
                    ))
        except Exception as e:
            logger.warning(f"Error analizando trades: {e}")
    
    # ========== ANÁLISIS DE PERFORMANCE ==========
    
    def _analyze_trading_performance(self, lookback_days: int):
        """Analiza métricas de performance y detecta degradación."""
        logger.info("Analizando performance de trading...")
        
        try:
            trades_df = self._load_trades(lookback_days)
            if trades_df.empty:
                self.issues.append(DiagnosticIssue(
                    severity="INFO",
                    category="PERFORMANCE",
                    title="Sin trades en el periodo",
                    description=f"No se ejecutaron trades en los últimos {lookback_days} días",
                    impact="No hay datos para evaluar performance",
                    recommendation="Normal si el mercado no generó señales válidas"
                ))
                return
            
            # Calcular métricas básicas
            win_rate = (trades_df["pnl_usd"] > 0).mean()
            avg_r = trades_df["r_multiple"].mean()
            median_r = trades_df["r_multiple"].median()
            profit_factor = self._calculate_profit_factor(trades_df)
            
            # PROBLEMA 1: Win Rate muy bajo
            if win_rate < 0.35:
                self.issues.append(DiagnosticIssue(
                    severity="HIGH",
                    category="PERFORMANCE",
                    title="Win Rate por debajo del mínimo",
                    description=f"Win Rate actual: {win_rate:.1%} (mínimo esperado: 35%)",
                    impact="Sistema generando demasiadas pérdidas",
                    recommendation="Revisar filtros de señales (_validate_signal_quality). Considerar aumentar thresholds de volatilidad o ADX.",
                    metric_value=win_rate,
                    threshold=0.35
                ))
            elif win_rate < 0.40:
                self.issues.append(DiagnosticIssue(
                    severity="MEDIUM",
                    category="PERFORMANCE",
                    title="Win Rate subóptimo",
                    description=f"Win Rate actual: {win_rate:.1%} (objetivo: 40-50%)",
                    impact="Rendimiento por debajo del esperado",
                    recommendation="Ajustar filtros de calidad de señal o revisar parámetros de indicadores",
                    metric_value=win_rate,
                    threshold=0.40
                ))
            
            # PROBLEMA 2: Avg R negativo
            if avg_r < -0.1:
                self.issues.append(DiagnosticIssue(
                    severity="CRITICAL",
                    category="PERFORMANCE",
                    title="Expectativa negativa (AvgR < 0)",
                    description=f"AvgR actual: {avg_r:.2f}R (sistema está perdiendo dinero)",
                    impact="Sistema no es rentable a largo plazo",
                    recommendation="URGENTE: Detener trading en vivo. Revisar estrategia completa, filtros y gestión de riesgo.",
                    metric_value=avg_r,
                    threshold=0.0
                ))
            elif avg_r < 0.2:
                self.issues.append(DiagnosticIssue(
                    severity="HIGH",
                    category="PERFORMANCE",
                    title="Expectativa muy baja",
                    description=f"AvgR actual: {avg_r:.2f}R (mínimo recomendado: 0.3R)",
                    impact="Rentabilidad marginal, vulnerable a costos",
                    recommendation="Revisar TP/SL ratio, considerar aumentar TP a 3R o ajustar filtros",
                    metric_value=avg_r,
                    threshold=0.3
                ))
            
            # PROBLEMA 3: Profit Factor bajo
            if profit_factor is not None:
                if profit_factor < 1.0:
                    self.issues.append(DiagnosticIssue(
                        severity="CRITICAL",
                        category="PERFORMANCE",
                        title="Profit Factor < 1.0",
                        description=f"PF actual: {profit_factor:.2f} (pérdidas > ganancias)",
                        impact="Sistema perdiendo más de lo que gana",
                        recommendation="Detener operativa. Revisar sizing, SL/TP y filtros de señales",
                        metric_value=profit_factor,
                        threshold=1.0
                    ))
                elif profit_factor < 1.3:
                    self.issues.append(DiagnosticIssue(
                        severity="HIGH",
                        category="PERFORMANCE",
                        title="Profit Factor bajo",
                        description=f"PF actual: {profit_factor:.2f} (mínimo: 1.5)",
                        impact="Margen de ganancia insuficiente",
                        recommendation="Optimizar filtros de entrada o aumentar TP/SL ratio",
                        metric_value=profit_factor,
                        threshold=1.5
                    ))
            
            # PROBLEMA 4: Performance decreciente (últimos 7 días vs previos)
            if len(trades_df) >= 10:
                cutoff = datetime.now() - timedelta(days=7)
                recent = trades_df[trades_df["entry_ts"] >= cutoff]
                older = trades_df[trades_df["entry_ts"] < cutoff]
                
                if len(recent) >= 3 and len(older) >= 3:
                    recent_avgr = recent["r_multiple"].mean()
                    older_avgr = older["r_multiple"].mean()
                    
                    if recent_avgr < older_avgr - 0.5:
                        self.issues.append(DiagnosticIssue(
                            severity="HIGH",
                            category="PERFORMANCE",
                            title="Degradación de performance reciente",
                            description=f"AvgR últimos 7d: {recent_avgr:.2f}R vs previo: {older_avgr:.2f}R",
                            impact="El sistema está empeorando con el tiempo",
                            recommendation="Posible cambio de régimen de mercado. Considerar re-optimización de parámetros.",
                            metric_value=recent_avgr - older_avgr
                        ))
        
        except Exception as e:
            logger.warning(f"Error analizando performance: {e}")
    
    # ========== ANÁLISIS DE GESTIÓN DE RIESGO ==========
    
    def _analyze_risk_management(self, lookback_days: int):
        """Detecta violaciones de límites de riesgo."""
        logger.info("Analizando gestión de riesgo...")
        
        try:
            equity_df = self._load_equity(lookback_days)
            if equity_df.empty:
                return
            
            # Calcular drawdown
            equity_df = equity_df.sort_values("ts")
            nav = equity_df["nav"].values
            running_max = np.maximum.accumulate(nav)
            dd = (nav / running_max - 1.0) * 100
            max_dd = dd.min()
            current_dd = dd[-1]
            
            # PROBLEMA 1: Drawdown excesivo
            if max_dd < -15:
                self.issues.append(DiagnosticIssue(
                    severity="CRITICAL",
                    category="RISK",
                    title="Drawdown máximo excede límite",
                    description=f"MaxDD: {max_dd:.1f}% (límite crítico: -15%)",
                    impact="Pérdida de capital significativa",
                    recommendation="URGENTE: Reducir risk_pct_per_trade a 0.1% y max_total_risk a 0.4%. Revisar estrategia.",
                    metric_value=max_dd,
                    threshold=-15.0
                ))
            elif max_dd < -12:
                self.issues.append(DiagnosticIssue(
                    severity="HIGH",
                    category="RISK",
                    title="Drawdown elevado",
                    description=f"MaxDD: {max_dd:.1f}% (límite recomendado: -12%)",
                    impact="Riesgo alto de pérdidas mayores",
                    recommendation="Reducir risk_pct_per_trade a 0.15% temporalmente",
                    metric_value=max_dd,
                    threshold=-12.0
                ))
            
            # PROBLEMA 2: Drawdown actual sin recuperación
            if current_dd < -5 and len(nav) > 7:
                days_in_dd = 0
                for i in range(len(nav)-1, -1, -1):
                    if nav[i] >= running_max[i] * 0.99:
                        break
                    days_in_dd += 1
                
                if days_in_dd > 14:
                    self.issues.append(DiagnosticIssue(
                        severity="HIGH",
                        category="RISK",
                        title="Drawdown prolongado sin recuperación",
                        description=f"Drawdown actual: {current_dd:.1f}% durante {days_in_dd} días",
                        impact="Posible cambio de régimen de mercado",
                        recommendation="Considerar pausar trading hasta identificar causa raíz",
                        metric_value=days_in_dd,
                        threshold=14
                    ))
            
            # PROBLEMA 3: Volatilidad de retornos excesiva
            returns = pd.Series(nav).pct_change().dropna()
            if len(returns) > 5:
                daily_vol = returns.std() * 100
                if daily_vol > 2.0:
                    self.issues.append(DiagnosticIssue(
                        severity="MEDIUM",
                        category="RISK",
                        title="Volatilidad de equity elevada",
                        description=f"Volatilidad diaria: {daily_vol:.2f}% (máx recomendado: 2%)",
                        impact="Equity muy errática, dificulta seguir el sistema",
                        recommendation="Reducir risk_pct_per_trade o max_leverage",
                        metric_value=daily_vol,
                        threshold=2.0
                    ))
        
        except Exception as e:
            logger.warning(f"Error analizando riesgo: {e}")
        
        # Analizar concentración de riesgo
        try:
            trades_df = self._load_trades(lookback_days)
            if not trades_df.empty:
                # Concentración por par
                pair_exposure = trades_df.groupby("pair").size()
                max_pair_pct = (pair_exposure.max() / len(trades_df)) * 100
                
                if max_pair_pct > 50:
                    self.issues.append(DiagnosticIssue(
                        severity="MEDIUM",
                        category="RISK",
                        title="Concentración excesiva en un par",
                        description=f"Un par representa {max_pair_pct:.0f}% de los trades",
                        impact="Riesgo no diversificado",
                        recommendation="Revisar max_corr_trades para permitir más diversificación",
                        metric_value=max_pair_pct,
                        threshold=50.0
                    ))
        except Exception as e:
            logger.warning(f"Error analizando concentración: {e}")
    
    # ========== ANÁLISIS DE EJECUCIÓN ==========
    
    def _analyze_order_execution(self):
        """Analiza la calidad de ejecución de órdenes."""
        logger.info("Analizando ejecución de órdenes...")
        
        try:
            orders_df = self._load_orders()
            fills_df = self._load_fills()
            
            if orders_df.empty:
                return
            
            # Tasa de rechazo de órdenes
            orders_df["response"] = orders_df["order_response_json"].apply(
                lambda x: json.loads(x) if isinstance(x, str) else {}
            )
            
            rejected = orders_df["response"].apply(
                lambda r: "orderRejectTransaction" in r or "errorMessage" in r
            ).sum()
            
            rejection_rate = rejected / len(orders_df)
            
            if rejection_rate > 0.1:
                self.issues.append(DiagnosticIssue(
                    severity="HIGH",
                    category="SYSTEM",
                    title="Alta tasa de rechazo de órdenes",
                    description=f"Tasa de rechazo: {rejection_rate:.1%} (máx: 10%)",
                    impact="Señales no ejecutándose, pérdida de oportunidades",
                    recommendation="Revisar validación de SL/TP, units, y lógica de _validate_signal_quality",
                    metric_value=rejection_rate,
                    threshold=0.1
                ))
            
            # Órdenes sin fills correspondientes
            if not fills_df.empty:
                order_pairs = set(orders_df["pair"].unique())
                fill_pairs = set(fills_df["pair"].unique())
                missing_fills = order_pairs - fill_pairs
                
                if missing_fills:
                    self.issues.append(DiagnosticIssue(
                        severity="MEDIUM",
                        category="SYSTEM",
                        title="Órdenes sin fills registrados",
                        description=f"Pares con órdenes pero sin fills: {missing_fills}",
                        impact="Posibles fills no sincronizados",
                        recommendation="Ejecutar sync_transactions() más frecuentemente",
                        metric_value=len(missing_fills)
                    ))
        
        except Exception as e:
            logger.warning(f"Error analizando ejecución: {e}")
    
    # ========== ANÁLISIS DE SEÑALES ==========
    
    def _analyze_signal_quality(self):
        """Compara señales generadas vs trades ejecutados."""
        logger.info("Analizando calidad de señales...")
        
        try:
            signals_df = self._load_signals()
            orders_df = self._load_orders()
            
            if signals_df.empty:
                return
            
            # Tasa de conversión señal -> orden
            conversion_rate = len(orders_df) / len(signals_df) if len(signals_df) > 0 else 0
            
            if conversion_rate < 0.3:
                self.issues.append(DiagnosticIssue(
                    severity="MEDIUM",
                    category="STRATEGY",
                    title="Baja tasa de conversión de señales",
                    description=f"Solo {conversion_rate:.1%} de señales se convierten en órdenes",
                    impact="Muchas señales rechazadas por filtros, posible configuración muy restrictiva",
                    recommendation="Revisar thresholds en _validate_signal_quality. Considerar relajar min_volatility_pct o min_adx.",
                    metric_value=conversion_rate,
                    threshold=0.3
                ))
            elif conversion_rate > 0.8:
                self.issues.append(DiagnosticIssue(
                    severity="MEDIUM",
                    category="STRATEGY",
                    title="Filtros de señales muy permisivos",
                    description=f"{conversion_rate:.1%} de señales se ejecutan (posible sobretrading)",
                    impact="Filtros pueden no estar eliminando señales de baja calidad",
                    recommendation="Aumentar thresholds de validación para mayor selectividad",
                    metric_value=conversion_rate,
                    threshold=0.8
                ))
            
            # Análisis por tipo de señal
            if not orders_df.empty:
                signal_types = signals_df["kind"].value_counts()
                order_types = orders_df["kind"].value_counts()
                
                for stype in signal_types.index:
                    sig_count = signal_types[stype]
                    ord_count = order_types.get(stype, 0)
                    type_conversion = ord_count / sig_count
                    
                    if type_conversion < 0.2:
                        self.issues.append(DiagnosticIssue(
                            severity="LOW",
                            category="STRATEGY",
                            title=f"Señales '{stype}' con muy baja conversión",
                            description=f"Solo {type_conversion:.1%} de señales {stype} se ejecutan",
                            impact=f"Filtros pueden estar sesgados contra {stype}",
                            recommendation=f"Revisar validación específica para {stype} (ej: RSI thresholds para pullbacks)",
                            metric_value=type_conversion
                        ))
        
        except Exception as e:
            logger.warning(f"Error analizando señales: {e}")
    
    # ========== ANÁLISIS DE COSTOS ==========
    
    def _analyze_costs(self):
        """Analiza slippage y costos de transacción."""
        logger.info("Analizando costos...")
        
        try:
            trades_df = self._load_trades()
            if trades_df.empty:
                return
            
            # Slippage implícito (diferencia entry_hint vs entry_price real)
            # Nota: Necesitaríamos guardar entry_hint en trades.csv para esto
            # Por ahora solo analizar si R_multiple vs PnL_USD tiene inconsistencias
            
            trades_df["implied_r"] = trades_df["pnl_usd"] / (trades_df["units"] * np.abs(trades_df["entry_price"] - trades_df["initial_sl"]))
            trades_df["r_diff"] = np.abs(trades_df["implied_r"] - trades_df["r_multiple"])
            
            high_diff = trades_df[trades_df["r_diff"] > 0.3]
            if len(high_diff) > len(trades_df) * 0.2:
                self.issues.append(DiagnosticIssue(
                    severity="MEDIUM",
                    category="SYSTEM",
                    title="Inconsistencias en cálculo de R",
                    description=f"{len(high_diff)} trades con diferencia R_calc vs R_log > 0.3",
                    impact="Posible error en cálculo de PnL o slippage excesivo",
                    recommendation="Revisar cálculo de pnl_usd en log_trade_close() y considerar modelar slippage",
                    metric_value=len(high_diff)
                ))
        
        except Exception as e:
            logger.warning(f"Error analizando costos: {e}")
    
    # ========== ANÁLISIS DE TIMING ==========
    
    def _analyze_timing_patterns(self):
        """Detecta patrones de timing problemáticos."""
        logger.info("Analizando patrones de timing...")
        
        try:
            trades_df = self._load_trades()
            if trades_df.empty or len(trades_df) < 20:
                return
            
            # Analizar día de la semana
            trades_df["entry_dow"] = pd.to_datetime(trades_df["entry_ts"]).dt.dayofweek
            dow_performance = trades_df.groupby("entry_dow")["r_multiple"].mean()
            
            worst_dow = dow_performance.idxmin()
            worst_dow_r = dow_performance.min()
            
            if worst_dow_r < -0.3:
                dow_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                self.issues.append(DiagnosticIssue(
                    severity="MEDIUM",
                    category="STRATEGY",
                    title=f"Performance negativa los {dow_names[worst_dow]}",
                    description=f"AvgR los {dow_names[worst_dow]}: {worst_dow_r:.2f}R",
                    impact="Posible patrón de mercado desfavorable ese día",
                    recommendation=f"Considerar deshabilitar trading los {dow_names[worst_dow]} o ajustar filtros",
                    metric_value=worst_dow_r
                ))
            
            # Analizar duración de trades
            avg_hold = trades_df["hold_days"].mean()
            if avg_hold < 0.5:
                self.issues.append(DiagnosticIssue(
                    severity="MEDIUM",
                    category="STRATEGY",
                    title="Trades con duración muy corta",
                    description=f"Hold promedio: {avg_hold:.1f} días (< 0.5)",
                    impact="Posible sobretrading o SL muy ajustados",
                    recommendation="Considerar aumentar stop_atr_mult de 1.8 a 2.0",
                    metric_value=avg_hold,
                    threshold=0.5
                ))
            elif avg_hold > 7:
                self.issues.append(DiagnosticIssue(
                    severity="LOW",
                    category="STRATEGY",
                    title="Trades con duración muy larga",
                    description=f"Hold promedio: {avg_hold:.1f} días",
                    impact="Capital inmovilizado mucho tiempo",
                    recommendation="Considerar trailing stops más agresivos o TP más cercanos",
                    metric_value=avg_hold,
                    threshold=7.0
                ))
        
        except Exception as e:
            logger.warning(f"Error analizando timing: {e}")
    
    # ========== ANÁLISIS DE SALUD DEL SISTEMA ==========
    
    def _analyze_system_health(self):
        """Detecta problemas técnicos y de infraestructura."""
        logger.info("Analizando salud del sistema...")
        
        # Verificar estructura de directorios
        if not os.path.exists(self.log_dir):
            self.issues.append(DiagnosticIssue(
                severity="CRITICAL",
                category="SYSTEM",
                title="Directorio de logs no existe",
                description=f"No se encuentra {self.log_dir}",
                impact="No se pueden guardar datos de trading",
                recommendation="Crear directorio con TradeLogger o manualmente",
                metric_value=0
            ))
        
        # Verificar variables de entorno
        required_env_vars = ["OANDA_ACCOUNT", "OANDA_TOKEN", "OANDA_ENV"]
        missing_vars = [v for v in required_env_vars if not os.environ.get(v)]
        
        if missing_vars:
            self.issues.append(DiagnosticIssue(
                severity="CRITICAL",
                category="SYSTEM",
                title="Variables de entorno faltantes",
                description=f"Faltan: {', '.join(missing_vars)}",
                impact="OandaAdapter no puede conectarse a la API",
                recommendation="Configurar variables en .env o sistema operativo",
                metric_value=len(missing_vars)
            ))
        
        # Analizar errores en orders.csv (respuestas con errorMessage)
        try:
            orders_df = self._load_orders()
            if not orders_df.empty:
                orders_df["response"] = orders_df["order_response_json"].apply(
                    lambda x: json.loads(x) if isinstance(x, str) else {}
                )
                errors = orders_df["response"].apply(lambda r: "errorMessage" in r).sum()
                error_rate = errors / len(orders_df)
                
                if error_rate > 0.05:
                    self.issues.append(DiagnosticIssue(
                        severity="HIGH",
                        category="SYSTEM",
                        title="Alta tasa de errores de API",
                        description=f"{error_rate:.1%} de órdenes con errorMessage",
                        impact="Problemas de conectividad o validación",
                        recommendation="Revisar logs de OandaAdapter, verificar circuit breaker y retry logic",
                        metric_value=error_rate,
                        threshold=0.05
                    ))
        except Exception as e:
            logger.warning(f"Error analizando errores de API: {e}")
    
    # ========== ANÁLISIS DE PARÁMETROS ==========
    
    def _analyze_parameter_drift(self):
        """Detecta si los parámetros actuales siguen siendo óptimos."""
        logger.info("Analizando drift de parámetros...")
        
        try:
            trades_df = self._load_trades()
            if len(trades_df) < 30:
                return
            
            # Analizar si el ATR promedio ha cambiado significativamente
            # (indicaría cambio de volatilidad de mercado)
            # Necesitaríamos guardar ATR en trades.csv para esto
            
            # Por ahora, analizar si la distribución de R ha cambiado
            recent_30 = trades_df.tail(30)
            older_30 = trades_df.iloc[-60:-30] if len(trades_df) >= 60 else pd.DataFrame()
            
            if not older_30.empty:
                recent_std = recent_30["r_multiple"].std()
                older_std = older_30["r_multiple"].std()
                
                if recent_std > older_std * 1.5:
                    self.issues.append(DiagnosticIssue(
                        severity="MEDIUM",
                        category="STRATEGY",
                        title="Aumento de volatilidad de resultados",
                        description=f"Std(R) reciente: {recent_std:.2f} vs previo: {older_std:.2f}",
                        impact="Parámetros pueden no adaptarse al régimen actual",
                        recommendation="Considerar re-optimización de parámetros o ajuste dinámico de sizing",
                        metric_value=recent_std / older_std,
                        threshold=1.5
                    ))
        
        except Exception as e:
            logger.warning(f"Error analizando drift: {e}")
    
    # ========== GENERACIÓN DE REPORTE ==========
    
    def _generate_report(self, lookback_days: int) -> DiagnosticReport:
        """Genera reporte consolidado."""
        
        # Contar por severidad
        severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for issue in self.issues:
            severity_counts[issue.severity] += 1
        
        # Calcular health score (100 - penalización por problemas)
        penalties = {
            "CRITICAL": 30,
            "HIGH": 15,
            "MEDIUM": 5,
            "LOW": 2,
            "INFO": 0
        }
        total_penalty = sum(severity_counts[sev] * penalties[sev] for sev in severity_counts)
        health_score = max(0, 100 - total_penalty)
        
        # Top recomendaciones
        top_recs = []
        for issue in sorted(self.issues, key=lambda x: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}[x.severity]):
            if issue.severity in ["CRITICAL", "HIGH"] and issue.recommendation not in top_recs:
                top_recs.append(issue.recommendation)
                if len(top_recs) >= 5:
                    break
        
        # Métricas resumen
        metrics_summary = self._calculate_summary_metrics(lookback_days)
        
        return DiagnosticReport(
            timestamp=datetime.now().isoformat(),
            analysis_period_days=lookback_days,
            total_issues=len(self.issues),
            critical_issues=severity_counts["CRITICAL"],
            high_issues=severity_counts["HIGH"],
            medium_issues=severity_counts["MEDIUM"],
            low_issues=severity_counts["LOW"],
            issues=self.issues,
            metrics_summary=metrics_summary,
            recommendations_summary=top_recs,
            system_health_score=health_score
        )
    
    def _calculate_summary_metrics(self, lookback_days: int) -> Dict[str, Any]:
        """Calcula métricas resumen para el reporte."""
        metrics = {}
        
        try:
            # Equity
            equity_df = self._load_equity(lookback_days)
            if not equity_df.empty:
                metrics["current_nav"] = float(equity_df["nav"].iloc[-1])
                metrics["nav_change_pct"] = float((equity_df["nav"].iloc[-1] / equity_df["nav"].iloc[0] - 1) * 100) if len(equity_df) > 1 else 0
                
                nav = equity_df["nav"].values
                running_max = np.maximum.accumulate(nav)
                dd = (nav / running_max - 1.0) * 100
                metrics["max_drawdown_pct"] = float(dd.min())
                metrics["current_drawdown_pct"] = float(dd[-1])
            
            # Trades
            trades_df = self._load_trades(lookback_days)
            if not trades_df.empty:
                metrics["total_trades"] = len(trades_df)
                metrics["win_rate"] = float((trades_df["pnl_usd"] > 0).mean())
                metrics["avg_r"] = float(trades_df["r_multiple"].mean())
                metrics["profit_factor"] = self._calculate_profit_factor(trades_df)
                metrics["avg_hold_days"] = float(trades_df["hold_days"].mean())
            
        except Exception as e:
            logger.warning(f"Error calculando métricas resumen: {e}")
        
        return metrics
    
    # ========== HELPERS ==========
    
    def _load_equity(self, lookback_days: Optional[int] = None) -> pd.DataFrame:
        """Carga datos de equity."""
        path = os.path.join(self.log_dir, "equity.csv")
        if not os.path.exists(path):
            return pd.DataFrame()
        
        df = pd.read_csv(path, parse_dates=["ts"])
        if lookback_days:
            cutoff = datetime.now() - timedelta(days=lookback_days)
            df = df[df["ts"] >= cutoff]
        return df
    
    def _load_trades(self, lookback_days: Optional[int] = None) -> pd.DataFrame:
        """Carga datos de trades."""
        path = os.path.join(self.log_dir, "trades.csv")
        if not os.path.exists(path):
            return pd.DataFrame()
        
        df = pd.read_csv(path, parse_dates=["entry_ts", "exit_ts"])
        if lookback_days:
            cutoff = datetime.now() - timedelta(days=lookback_days)
            df = df[df["entry_ts"] >= cutoff]
        return df
    
    def _load_orders(self) -> pd.DataFrame:
        """Carga datos de órdenes."""
        path = os.path.join(self.log_dir, "orders.csv")
        if not os.path.exists(path):
            return pd.DataFrame()
        return pd.read_csv(path, parse_dates=["ts"])
    
    def _load_fills(self) -> pd.DataFrame:
        """Carga datos de fills."""
        path = os.path.join(self.log_dir, "fills.csv")
        if not os.path.exists(path):
            return pd.DataFrame()
        return pd.read_csv(path, parse_dates=["ts"])
    
    def _load_signals(self) -> pd.DataFrame:
        """Carga datos de señales."""
        path = os.path.join(self.log_dir, "signals.csv")
        if not os.path.exists(path):
            return pd.DataFrame()
        return pd.read_csv(path, parse_dates=["ts"])
    
    def _calculate_profit_factor(self, trades_df: pd.DataFrame) -> Optional[float]:
        """Calcula profit factor."""
        wins = trades_df[trades_df["pnl_usd"] > 0]["pnl_usd"].sum()
        losses = trades_df[trades_df["pnl_usd"] < 0]["pnl_usd"].sum()
        if losses == 0:
            return None
        return float(wins / abs(losses))


def generate_markdown_report(report: DiagnosticReport, output_path: str):
    """
    Genera un reporte en formato Markdown legible.
    """
    severity_icons = {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "MEDIUM": "🟡",
        "LOW": "🔵",
        "INFO": "ℹ️"
    }
    
    category_icons = {
        "RISK": "⚠️",
        "PERFORMANCE": "📊",
        "DATA_QUALITY": "📁",
        "SYSTEM": "⚙️",
        "STRATEGY": "🎯"
    }
    
    lines = []
    lines.append("# 🔍 INFORME DE DIAGNÓSTICO DEL SISTEMA")
    lines.append("")
    lines.append(f"**Fecha:** {report.timestamp}")
    lines.append(f"**Periodo analizado:** Últimos {report.analysis_period_days} días")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Health Score
    if report.system_health_score >= 80:
        health_emoji = "🟢"
        health_status = "EXCELENTE"
    elif report.system_health_score >= 60:
        health_emoji = "🟡"
        health_status = "BUENO"
    elif report.system_health_score >= 40:
        health_emoji = "🟠"
        health_status = "NECESITA ATENCIÓN"
    else:
        health_emoji = "🔴"
        health_status = "CRÍTICO"
    
    lines.append(f"## {health_emoji} SALUD DEL SISTEMA: {report.system_health_score:.0f}/100 - {health_status}")
    lines.append("")
    
    # Resumen de problemas
    lines.append("### 📋 Resumen de Problemas Detectados")
    lines.append("")
    lines.append(f"- **Total:** {report.total_issues}")
    lines.append(f"- 🔴 **Críticos:** {report.critical_issues}")
    lines.append(f"- 🟠 **Altos:** {report.high_issues}")
    lines.append(f"- 🟡 **Medios:** {report.medium_issues}")
    lines.append(f"- 🔵 **Bajos:** {report.low_issues}")
    lines.append("")
    
    # Métricas clave
    if report.metrics_summary:
        lines.append("### 📈 Métricas Clave del Periodo")
        lines.append("")
        m = report.metrics_summary
        
        if "current_nav" in m:
            lines.append(f"- **Equity actual:** ${m['current_nav']:,.2f}")
        if "nav_change_pct" in m:
            lines.append(f"- **Cambio NAV:** {m['nav_change_pct']:+.2f}%")
        if "max_drawdown_pct" in m:
            lines.append(f"- **Max Drawdown:** {m['max_drawdown_pct']:.2f}%")
        if "total_trades" in m:
            lines.append(f"- **Trades ejecutados:** {m['total_trades']}")
        if "win_rate" in m:
            lines.append(f"- **Win Rate:** {m['win_rate']:.1%}")
        if "avg_r" in m:
            lines.append(f"- **AvgR:** {m['avg_r']:.2f}R")
        if "profit_factor" in m:
            pf = m['profit_factor'] if m['profit_factor'] is not None else 0
            lines.append(f"- **Profit Factor:** {pf:.2f}")
        
        lines.append("")
    
    # Top recomendaciones
    if report.recommendations_summary:
        lines.append("### 🎯 TOP RECOMENDACIONES URGENTES")
        lines.append("")
        for i, rec in enumerate(report.recommendations_summary, 1):
            lines.append(f"{i}. {rec}")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    # Detalle de problemas por categoría
    lines.append("## 📝 DETALLE DE PROBLEMAS")
    lines.append("")
    
    # Agrupar por categoría
    issues_by_category = {}
    for issue in report.issues:
        if issue.category not in issues_by_category:
            issues_by_category[issue.category] = []
        issues_by_category[issue.category].append(issue)
    
    for category in ["RISK", "PERFORMANCE", "DATA_QUALITY", "SYSTEM", "STRATEGY"]:
        if category not in issues_by_category:
            continue
        
        issues = sorted(issues_by_category[category], 
                       key=lambda x: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}[x.severity])
        
        lines.append(f"### {category_icons[category]} {category.replace('_', ' ').title()}")
        lines.append("")
        
        for issue in issues:
            lines.append(f"#### {severity_icons[issue.severity]} {issue.title}")
            lines.append("")
            lines.append(f"**Severidad:** {issue.severity}")
            lines.append("")
            lines.append(f"**Descripción:** {issue.description}")
            lines.append("")
            lines.append(f"**Impacto:** {issue.impact}")
            lines.append("")
            lines.append(f"**Recomendación:** {issue.recommendation}")
            lines.append("")
            
            if issue.metric_value is not None:
                metric_str = f"{issue.metric_value:.2f}"
                if issue.threshold is not None:
                    metric_str += f" (umbral: {issue.threshold:.2f})"
                lines.append(f"**Métrica:** {metric_str}")
                lines.append("")
            
            lines.append("---")
            lines.append("")
    
    # Guardar
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    logger.info(f"Reporte generado en: {output_path}")
