# -*- coding: utf-8 -*-
"""
Script para generar informe de diagnóstico completo del sistema.
Uso: python scripts/run_diagnostics.py [--days N] [--output RUTA]
"""
import sys
import os
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fx_conservative.diagnostics import SystemDiagnostics, generate_markdown_report
from fx_conservative.config import load_config


def main():
    parser = argparse.ArgumentParser(description="Genera informe de diagnóstico del sistema de trading")
    parser.add_argument("--config", default="config/config_optimized.yaml", help="Ruta al archivo de configuración")
    parser.add_argument("--days", type=int, default=30, help="Días hacia atrás a analizar (default: 30)")
    parser.add_argument("--output", help="Ruta de salida del reporte (default: logs/diagnostic_report_YYYYMMDD.md)")
    
    args = parser.parse_args()
    
    # Cargar configuración
    cfg = load_config(args.config)
    
    # Crear directorio logs si no existe
    os.makedirs(cfg.log_dir, exist_ok=True)
    
    print("=" * 70)
    print("🔍 SISTEMA DE DIAGNÓSTICO Y AUTO-ANÁLISIS")
    print("=" * 70)
    print(f"\n📁 Directorio de logs: {cfg.log_dir}")
    print(f"📅 Periodo de análisis: Últimos {args.days} días")
    print(f"⏰ Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n" + "-" * 70)
    print("\n🔄 Ejecutando análisis completo...\n")
    
    # Ejecutar diagnóstico
    diagnostics = SystemDiagnostics(cfg.log_dir)
    report = diagnostics.analyze_all(lookback_days=args.days)
    
    # Determinar ruta de salida
    if args.output:
        output_path = args.output
    else:
        output_path = os.path.join(
            cfg.log_dir, 
            f"diagnostic_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        )
    
    # Generar reporte Markdown
    generate_markdown_report(report, output_path)
    
    # Mostrar resumen en consola
    print("\n" + "=" * 70)
    print("✅ DIAGNÓSTICO COMPLETADO")
    print("=" * 70)
    
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
    
    print(f"\n{health_emoji} SALUD DEL SISTEMA: {report.system_health_score:.0f}/100 - {health_status}\n")
    
    # Resumen de problemas
    print("📋 RESUMEN DE PROBLEMAS:")
    print(f"   Total: {report.total_issues}")
    print(f"   🔴 Críticos: {report.critical_issues}")
    print(f"   🟠 Altos: {report.high_issues}")
    print(f"   🟡 Medios: {report.medium_issues}")
    print(f"   🔵 Bajos: {report.low_issues}")
    
    # Métricas clave
    if report.metrics_summary:
        print("\n📊 MÉTRICAS CLAVE:")
        m = report.metrics_summary
        
        if "current_nav" in m:
            print(f"   Equity actual: ${m['current_nav']:,.2f}")
        if "nav_change_pct" in m:
            print(f"   Cambio NAV: {m['nav_change_pct']:+.2f}%")
        if "max_drawdown_pct" in m:
            print(f"   Max DD: {m['max_drawdown_pct']:.2f}%")
        if "total_trades" in m:
            print(f"   Trades: {m['total_trades']}")
        if "win_rate" in m:
            print(f"   Win Rate: {m['win_rate']:.1%}")
        if "avg_r" in m:
            print(f"   AvgR: {m['avg_r']:.2f}R")
    
    # Top recomendaciones
    if report.recommendations_summary:
        print("\n🎯 TOP RECOMENDACIONES URGENTES:")
        for i, rec in enumerate(report.recommendations_summary[:3], 1):
            print(f"\n   {i}. {rec}")
    
    # Problemas críticos
    critical_issues = [i for i in report.issues if i.severity == "CRITICAL"]
    if critical_issues:
        print("\n" + "⚠️ " * 20)
        print("\n🔴 PROBLEMAS CRÍTICOS DETECTADOS:")
        for issue in critical_issues:
            print(f"\n   • {issue.title}")
            print(f"     {issue.description}")
            print(f"     ➜ {issue.recommendation}")
        print("\n" + "⚠️ " * 20)
    
    print(f"\n📄 Reporte completo guardado en:")
    print(f"   {output_path}")
    
    print("\n" + "=" * 70)
    print(f"⏰ Finalizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70 + "\n")
    
    # Retornar código de salida según severidad
    if report.critical_issues > 0:
        sys.exit(2)  # Código 2: Problemas críticos
    elif report.high_issues > 0:
        sys.exit(1)  # Código 1: Problemas altos
    else:
        sys.exit(0)  # Código 0: Sin problemas graves


if __name__ == "__main__":
    main()
