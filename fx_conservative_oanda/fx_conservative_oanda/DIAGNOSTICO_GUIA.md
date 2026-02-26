# 🔍 SISTEMA DE DIAGNÓSTICO Y AUTO-MEJORA

## ¿Qué es el Sistema de Diagnóstico?

Un **analizador automático** que revisa todo tu sistema de trading para detectar:
- ❌ **Fallos críticos** que pueden causar pérdidas
- 📉 **Degradación de performance**
- 🐛 **Problemas de calidad de datos**
- ⚙️ **Errores técnicos del sistema**
- 🎯 **Oportunidades de optimización**

## 📊 ¿Qué Analiza?

### 1. Calidad de Datos (DATA_QUALITY)
- ✅ Archivos necesarios presentes
- ✅ Sin gaps en registros de equity
- ✅ Sin valores duplicados
- ✅ Cálculos de R múltiple correctos
- ✅ Trades sin duración cero

### 2. Performance de Trading (PERFORMANCE)
- ✅ Win Rate dentro de rangos aceptables (35-60%)
- ✅ AvgR positivo (mínimo 0.3R)
- ✅ Profit Factor > 1.5
- ✅ Sin degradación reciente
- ✅ Expectativa positiva

### 3. Gestión de Riesgo (RISK)
- ✅ Drawdown < 12% (crítico: 15%)
- ✅ Sin drawdowns prolongados (>14 días)
- ✅ Volatilidad de equity < 2% diario
- ✅ Diversificación adecuada (sin concentración >50% en un par)

### 4. Ejecución de Órdenes (SYSTEM)
- ✅ Tasa de rechazo < 10%
- ✅ Órdenes con fills correspondientes
- ✅ Sin errores de API frecuentes (>5%)
- ✅ Circuit breaker funcionando

### 5. Calidad de Señales (STRATEGY)
- ✅ Tasa de conversión señal→orden entre 30-80%
- ✅ Filtros balanceados (ni muy restrictivos ni muy permisivos)
- ✅ Balance entre breakouts y pullbacks

### 6. Costos y Slippage (SYSTEM)
- ✅ Cálculo de PnL consistente
- ✅ Slippage dentro de rangos esperados
- ✅ R teórico vs R real coherente

### 7. Timing y Estacionalidad (STRATEGY)
- ✅ Sin días de semana con performance negativa persistente
- ✅ Duración de trades apropiada (0.5-7 días)
- ✅ Sin overtrading ni undertrading

### 8. Salud del Sistema (SYSTEM)
- ✅ Variables de entorno configuradas
- ✅ Directorios necesarios existentes
- ✅ Conectividad con OANDA estable

### 9. Drift de Parámetros (STRATEGY)
- ✅ Parámetros siguen siendo óptimos
- ✅ Sin cambio de régimen de mercado no detectado
- ✅ Volatilidad de resultados estable

---

## 🚀 Cómo Usar

### OPCIÓN 1: Automático (Recomendado)

El scheduler ejecuta diagnósticos **automáticamente todos los lunes a las 08:00 UTC**.

Solo tienes que:
1. Iniciar el scheduler (ver `SCHEDULER_GUIA.md`)
2. Revisar el reporte cada lunes en `logs/diagnostic_report_YYYYMMDD.md`

**No requiere acción manual** ✅

---

### OPCIÓN 2: Manual (Bajo Demanda)

Cuando necesites un análisis inmediato:

```powershell
# Análisis básico (últimos 30 días)
python scripts/run_diagnostics.py

# Análisis de 60 días
python scripts/run_diagnostics.py --days 60

# Análisis con salida personalizada
python scripts/run_diagnostics.py --output mi_diagnostico.md

# Con configuración específica
python scripts/run_diagnostics.py --config config/config.yaml --days 90
```

**Cuándo usar:**
- Después de cambiar parámetros del sistema
- Si sospechas problemas
- Antes de aumentar capital
- Mensualmente como mínimo

---

## 📄 Interpretación del Reporte

### Health Score (Puntaje de Salud)

| Score | Estado | Acción |
|-------|--------|--------|
| 80-100 🟢 | EXCELENTE | Continuar operando normalmente |
| 60-79 🟡 | BUENO | Monitorear, considerar ajustes menores |
| 40-59 🟠 | NECESITA ATENCIÓN | Revisar problemas HIGH y MEDIUM urgentemente |
| 0-39 🔴 | CRÍTICO | DETENER trading hasta resolver problemas |

**Cálculo:**
```
Score = 100 - (CRITICAL × 30 + HIGH × 15 + MEDIUM × 5 + LOW × 2)
```

---

### Niveles de Severidad

#### 🔴 CRITICAL (Críticos)
**Qué significa:** Problemas que **pueden causar pérdidas importantes**.

**Ejemplos:**
- AvgR < 0 (sistema perdiendo dinero)
- Profit Factor < 1.0
- Max Drawdown > 15%
- Sin archivos de datos
- Variables de entorno faltantes

**Acción:** ⚠️ **DETENER TRADING INMEDIATAMENTE**
- Revisar el problema
- Aplicar recomendación sugerida
- Re-ejecutar diagnóstico
- Solo continuar cuando esté resuelto

---

#### 🟠 HIGH (Altos)
**Qué significa:** Problemas **que afectan significativamente la rentabilidad**.

**Ejemplos:**
- Win Rate < 35%
- AvgR < 0.3R
- Drawdown > 12%
- Performance degradándose
- Alta tasa de rechazo de órdenes (>10%)

**Acción:** 🚨 **ACCIÓN URGENTE (24-48h)**
- Aplicar recomendaciones
- Ajustar parámetros
- Monitorear de cerca

---

#### 🟡 MEDIUM (Medios)
**Qué significa:** Problemas que **reducen eficiencia** pero no son críticos.

**Ejemplos:**
- Win Rate subóptimo (35-40%)
- Filtros muy restrictivos o permisivos
- Concentración en un par >50%
- Gaps en datos de equity
- Volatilidad de equity elevada

**Acción:** 📅 **PLANIFICAR MEJORAS (1-2 semanas)**
- Añadir a lista de tareas
- Considerar ajustes
- No urgente pero importante

---

#### 🔵 LOW (Bajos)
**Qué significa:** **Oportunidades de mejora** menores.

**Ejemplos:**
- Timestamps duplicados
- Performance negativa un día específico
- Duración de trades muy larga/corta
- Señales de un tipo con baja conversión

**Acción:** 💡 **OPCIONAL (backlog)**
- Mejora incremental
- Implementar cuando sea conveniente

---

#### ℹ️ INFO (Informativos)
**Qué significa:** Información **sin acción requerida**.

**Ejemplos:**
- Sin trades en el periodo (normal si no hubo señales)

**Acción:** 👀 **SOLO LEER**

---

## 🎯 Sección "TOP RECOMENDACIONES URGENTES"

Las **5 acciones más importantes** para mejorar el sistema, ordenadas por prioridad.

**Ejemplo:**
```
1. URGENTE: Detener trading en vivo. Revisar estrategia completa (AvgR negativo)
2. Reducir risk_pct_per_trade a 0.1% y max_total_risk a 0.4%
3. Revisar filtros de señales (_validate_signal_quality)
4. Ejecutar sync_transactions() más frecuentemente
5. Aumentar min_volatility_pct de 0.5% a 0.8%
```

**Acción:** ✅ Ejecutar estas recomendaciones **en orden** hasta resolver problemas HIGH/CRITICAL.

---

## 📊 Sección "MÉTRICAS CLAVE DEL PERIODO"

Vista rápida del estado actual:

```
- Equity actual: $102,345.67
- Cambio NAV: +2.35%
- Max Drawdown: -5.2%
- Trades ejecutados: 23
- Win Rate: 47.8%
- AvgR: 0.42R
- Profit Factor: 1.67
```

**Interpretación:**
- ✅ **Verde:** Si Equity ↑, AvgR > 0.3, WinRate > 40%, PF > 1.5
- 🟡 **Amarillo:** Valores aceptables pero mejorables
- 🔴 **Rojo:** Por debajo de mínimos aceptables

---

## 🔧 Detalle de Problemas por Categoría

El reporte agrupa problemas en **5 categorías**:

### ⚠️ RISK (Gestión de Riesgo)
Problemas relacionados con control de pérdidas.

**Umbrales:**
- MaxDD < -12% → MEDIUM
- MaxDD < -15% → CRITICAL
- DD sin recuperación >14 días → HIGH
- Volatilidad equity >2% → MEDIUM

**Soluciones comunes:**
- Reducir `risk_pct_per_trade`
- Reducir `max_total_risk`
- Aumentar `stop_atr_mult`
- Revisar correlación

---

### 📊 PERFORMANCE (Rendimiento)
Problemas de rentabilidad.

**Umbrales:**
- WinRate < 35% → HIGH
- WinRate < 40% → MEDIUM
- AvgR < 0 → CRITICAL
- AvgR < 0.3R → HIGH
- PF < 1.0 → CRITICAL
- PF < 1.5 → HIGH
- Degradación >0.5R en 7d → HIGH

**Soluciones comunes:**
- Ajustar filtros en `_validate_signal_quality`
- Aumentar `min_adx`, `min_volatility_pct`
- Aumentar TP ratio
- Revisar pares tradeable

---

### 📁 DATA_QUALITY (Calidad de Datos)
Problemas de integridad de datos.

**Umbrales:**
- Archivo faltante → HIGH/CRITICAL
- Gaps >3 días → MEDIUM
- R múltiples |R| > 10 → HIGH
- Trades duración cero → MEDIUM

**Soluciones comunes:**
- Verificar TradeLogger funciona
- Ejecutar sync más frecuente
- Revisar cálculo de `pnl_usd`
- Deduplicar registros

---

### ⚙️ SYSTEM (Sistema/Infraestructura)
Problemas técnicos.

**Umbrales:**
- Variables entorno faltantes → CRITICAL
- Directorio logs no existe → CRITICAL
- Tasa rechazo >10% → HIGH
- Errores API >5% → HIGH

**Soluciones comunes:**
- Configurar `.env`
- Crear directorios
- Revisar validación SL/TP
- Verificar circuit breaker

---

### 🎯 STRATEGY (Estrategia)
Problemas de lógica de trading.

**Umbrales:**
- Conversión señal→orden <30% → MEDIUM (muy restrictivo)
- Conversión señal→orden >80% → MEDIUM (muy permisivo)
- Performance negativa un día → MEDIUM
- Hold avg <0.5d → MEDIUM (SL muy ajustado)
- Hold avg >7d → LOW (capital inmovilizado)

**Soluciones comunes:**
- Ajustar thresholds de validación
- Balancear filtros
- Deshabilitar días problemáticos
- Ajustar `stop_atr_mult` o trailing

---

## 🔄 Workflow de Mejora Continua

### Ciclo Recomendado

```
1. LUNES 08:00 UTC
   ↓
   Diagnóstico automático ejecuta
   ↓
2. LUNES 09:00 
   ↓
   Revisar reporte (10 min)
   ↓
3. Si Health Score < 60
   ↓
   Aplicar TOP RECOMENDACIONES (1-2h)
   ↓
4. MARTES
   ↓
   Re-ejecutar diagnóstico manual
   ↓
5. Verificar mejora
   ↓
6. SIGUIENTE LUNES: Repetir
```

### Mensualmente

```
1. Ejecutar diagnóstico 90 días
   python scripts/run_diagnostics.py --days 90

2. Analizar tendencias a largo plazo

3. Considerar re-optimización de parámetros si:
   - Std(R) aumentó >50%
   - AvgR bajó >0.3R vs promedio histórico
   - Win Rate bajó >10% vs promedio

4. Documentar cambios en CHANGELOG.md
```

---

## 📈 Ejemplos de Problemas y Soluciones

### Ejemplo 1: Win Rate Bajo

**Problema detectado:**
```
🟠 Win Rate por debajo del mínimo
Win Rate actual: 32% (mínimo esperado: 35%)
Sistema generando demasiadas pérdidas
```

**Recomendación:**
```
Revisar filtros de señales (_validate_signal_quality). 
Considerar aumentar thresholds de volatilidad o ADX.
```

**Acción:**
1. Editar `config_optimized.yaml`:
   ```yaml
   min_volatility_pct: 0.8  # Era 0.5
   min_adx: 22              # Era 20
   ```
2. Re-ejecutar diagnóstico en 7 días
3. Verificar Win Rate mejoró

---

### Ejemplo 2: Drawdown Excesivo

**Problema detectado:**
```
🔴 Drawdown máximo excede límite
MaxDD: -16.2% (límite crítico: -15%)
Pérdida de capital significativa
```

**Recomendación:**
```
URGENTE: Reducir risk_pct_per_trade a 0.1% y max_total_risk a 0.4%. 
Revisar estrategia.
```

**Acción:**
1. **DETENER trading inmediatamente**
2. Editar `config_optimized.yaml`:
   ```yaml
   risk_pct_per_trade: 0.1   # Era 0.2
   max_total_risk: 0.4       # Era 0.8
   ```
3. Revisar trades recientes en `logs/trades.csv`
4. Identificar causa raíz (¿muchos SL? ¿par específico?)
5. Solo reactivar tras 5 días sin nuevos trades problemáticos

---

### Ejemplo 3: Alta Tasa de Rechazo

**Problema detectado:**
```
🟠 Alta tasa de rechazo de órdenes
Tasa de rechazo: 18% (máx: 10%)
Señales no ejecutándose, pérdida de oportunidades
```

**Recomendación:**
```
Revisar validación de SL/TP, units, y lógica de _validate_signal_quality
```

**Acción:**
1. Revisar `logs/orders.csv` para ver errorMessage
2. Causas comunes:
   - SL/TP muy cerca del precio (< pip mínimo)
   - Units calculados incorrectamente
   - Margin insuficiente
3. Añadir validación extra en `size_units()`:
   ```python
   # Asegurar que SL está a distancia mínima
   min_distance = atr * 0.5
   if abs(entry - sl) < min_distance:
       logger.warning(f"SL muy cerca: {abs(entry-sl)} < {min_distance}")
       return 0
   ```

---

### Ejemplo 4: Filtros Muy Restrictivos

**Problema detectado:**
```
🟡 Baja tasa de conversión de señales
Solo 18% de señales se convierten en órdenes
Muchas señales rechazadas por filtros, configuración muy restrictiva
```

**Recomendación:**
```
Revisar thresholds en _validate_signal_quality. 
Considerar relajar min_volatility_pct o min_adx.
```

**Acción:**
1. Revisar `logs/signals.csv` vs `logs/orders.csv`
2. Identificar cuál filtro rechaza más
3. Ajustar gradualmente:
   ```yaml
   min_volatility_pct: 0.6  # Era 0.8
   min_adx: 18              # Era 22
   ```
4. Monitorear Win Rate (no debe bajar)

---

## 🛠️ Troubleshooting

### "No se encuentra archivo X.csv"

**Causa:** TradeLogger no está guardando datos.

**Solución:**
1. Verificar que `log_dir` existe en config
2. Crear manualmente: `mkdir logs`
3. Ejecutar un ciclo de trading
4. Verificar archivos se crean

---

### "Todos los problemas son INFO"

**Causa:** Sistema funcionando correctamente 🎉

**Solución:** Ninguna. Health Score debería estar >80.

---

### "Health Score muy bajo sin problemas aparentes"

**Causa:** Muchos problemas MEDIUM/LOW acumulados.

**Solución:**
1. Revisar categoría STRATEGY
2. Aplicar mejoras incrementales
3. Re-ejecutar en 1 semana

---

### "Diagnóstico tarda mucho"

**Causa:** Muchos trades/datos históricos.

**Solución:**
1. Reducir `--days`: `python scripts/run_diagnostics.py --days 14`
2. Normal con >1000 trades

---

### "Error al cargar CSV"

**Causa:** Archivo corrupto o formato incorrecto.

**Solución:**
1. Verificar última línea de CSV no está cortada
2. Abrir con Excel/Notepad para ver
3. Restaurar desde backup si existe

---

## 📋 Checklist de Mejora Continua

### Semanal (Automático)
- [ ] Diagnóstico ejecutado lunes 08:00 UTC
- [ ] Reporte revisado
- [ ] Problemas CRITICAL resueltos
- [ ] Problemas HIGH planificados

### Mensual (Manual)
- [ ] Ejecutar `python scripts/run_diagnostics.py --days 90`
- [ ] Comparar Health Score vs mes anterior
- [ ] Revisar tendencias de AvgR y Win Rate
- [ ] Actualizar parámetros si es necesario
- [ ] Documentar cambios

### Trimestral
- [ ] Análisis profundo de 180 días
- [ ] Re-optimización completa si régimen cambió
- [ ] Backtest con nuevos parámetros
- [ ] Actualizar documentación

---

## 🎯 Métricas Objetivo

| Métrica | Mínimo Aceptable | Objetivo | Excelente |
|---------|------------------|----------|-----------|
| Health Score | 60 | 80 | 90+ |
| Win Rate | 35% | 45% | 55%+ |
| AvgR | 0.2R | 0.4R | 0.6R+ |
| Profit Factor | 1.3 | 1.7 | 2.0+ |
| Max DD | -15% | -10% | -5% |
| Sharpe Ratio | 0.5 | 1.0 | 1.5+ |

---

## 💡 Tips Avanzados

### 1. Comparar Reportes
```powershell
# Guardar reportes con fechas
python scripts/run_diagnostics.py --output logs/diagnostic_2026_02_25.md
python scripts/run_diagnostics.py --output logs/diagnostic_2026_03_25.md

# Comparar manualmente para ver evolución
```

### 2. Automatizar Alertas
Modificar `generate_diagnostic_report()` en `auto_scheduler.py` para enviar email si `critical_issues > 0`.

### 3. Exportar a JSON
```python
# Añadir al final de run_diagnostics.py
import json
with open("diagnostic.json", "w") as f:
    json.dump(asdict(report), f, indent=2)
```

### 4. Integrar con Dashboard
Parsear `diagnostic_report_*.md` para mostrar en Grafana/Streamlit.

---

**¡Tu sistema ahora se auto-analiza y sugiere mejoras automáticamente! 🚀**
