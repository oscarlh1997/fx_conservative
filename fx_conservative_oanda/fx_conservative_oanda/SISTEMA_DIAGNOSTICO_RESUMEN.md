# 📊 RESUMEN COMPLETO DEL SISTEMA DE AUTO-MEJORA

## ✅ Sistema Implementado

Has recibido un **sistema completo de diagnóstico y auto-regulación** que detecta fallos y sugiere mejoras automáticamente.

---

## 🎯 ¿Qué Hace Exactamente?

### 1. **Recolección de Datos**
El sistema analiza automáticamente:
- ✅ **Equity**: Evolución del capital, drawdowns, volatilidad
- ✅ **Trades**: Win rate, AvgR, profit factor, duración
- ✅ **Señales**: Tasa de conversión, filtros efectivos
- ✅ **Órdenes**: Rechazos, errores de API, ejecución
- ✅ **Sistema**: Salud técnica, conectividad, integridad de datos

### 2. **Análisis Inteligente**
Ejecuta **9 tipos de análisis**:

#### 📁 Calidad de Datos
- Verifica archivos necesarios existen
- Detecta gaps en registros
- Identifica valores anómalos (R > 10, trades duración 0)
- Valida consistencia de timestamps

#### 📊 Performance de Trading
- Compara Win Rate vs objetivos (35-60%)
- Valida expectativa positiva (AvgR > 0.3R)
- Detecta degradación reciente (últimos 7 días vs previos)
- Calcula Profit Factor

#### ⚠️ Gestión de Riesgo
- Monitorea drawdown máximo (límite: -12%)
- Detecta drawdowns prolongados (>14 días sin recuperación)
- Analiza volatilidad de equity (<2% diario)
- Identifica concentración excesiva (>50% en un par)

#### ⚙️ Ejecución de Órdenes
- Tasa de rechazo (<10%)
- Errores de API frecuentes
- Órdenes sin fills correspondientes

#### 🎯 Calidad de Señales
- Tasa de conversión señal→orden (óptimo: 30-80%)
- Balance entre tipos de señales (breakout/pullback)
- Efectividad de filtros

#### 💰 Costos y Slippage
- Consistencia R teórico vs R real
- Slippage implícito
- Impacto de comisiones

#### 📅 Timing y Estacionalidad
- Performance por día de semana
- Duración promedio de trades (óptimo: 0.5-7 días)
- Patrones temporales

#### 🏥 Salud del Sistema
- Variables de entorno configuradas
- Directorios necesarios existentes
- Circuit breaker funcionando

#### 📈 Drift de Parámetros
- Cambios en volatilidad de mercado
- Parámetros siguen siendo óptimos
- Detección de cambio de régimen

### 3. **Detección de Problemas**
Clasifica problemas en **5 niveles de severidad**:

| Nivel | Impacto | Acción |
|-------|---------|--------|
| 🔴 CRITICAL | Pérdidas importantes | **DETENER TRADING** |
| 🟠 HIGH | Afecta rentabilidad | Resolver en 24-48h |
| 🟡 MEDIUM | Reduce eficiencia | Planificar en 1-2 semanas |
| 🔵 LOW | Mejora incremental | Backlog, opcional |
| ℹ️ INFO | Solo informativo | Sin acción |

### 4. **Generación de Recomendaciones**
Para cada problema detectado, proporciona:
- ✅ **Descripción clara** del problema
- ✅ **Impacto** en el sistema
- ✅ **Recomendación específica** (qué cambiar y cómo)
- ✅ **Valores de métricas** (actual vs umbral)

**Ejemplo:**
```
🟠 Win Rate por debajo del mínimo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Descripción: Win Rate actual: 32% (mínimo esperado: 35%)
Impacto: Sistema generando demasiadas pérdidas
Recomendación: Revisar filtros de señales (_validate_signal_quality). 
               Considerar aumentar thresholds de volatilidad o ADX.
Métrica: 0.32 (umbral: 0.35)
```

### 5. **Health Score (0-100)**
Calcula un **puntaje único** que resume la salud total del sistema:

```
Score = 100 - (CRITICAL×30 + HIGH×15 + MEDIUM×5 + LOW×2)
```

| Score | Estado | |
|-------|--------|-|
| 80-100 | 🟢 EXCELENTE | Todo OK |
| 60-79 | 🟡 BUENO | Mejoras menores |
| 40-59 | 🟠 ATENCIÓN | Acción requerida |
| 0-39 | 🔴 CRÍTICO | **DETENER** |

### 6. **Reportes Automatizados**
Genera **2 tipos de reportes**:

#### 📄 Reporte Markdown Completo
- Salud del sistema
- Resumen de problemas
- Métricas clave
- TOP recomendaciones urgentes
- Detalle completo por categoría

**Ubicación:** `logs/diagnostic_report_YYYYMMDD.md`

#### 📊 Log en Consola
- Resumen ejecutivo
- Problemas críticos destacados
- Top 3 recomendaciones

---

## 🔄 Ejecución Automática

### Programación
El scheduler ejecuta diagnósticos **automáticamente**:

```
LUNES 08:00 UTC → Diagnóstico completo semanal
                  ↓
                  Analiza últimos 30 días
                  ↓
                  Genera reporte en logs/
                  ↓
                  Alerta si problemas CRITICAL
```

**No requiere intervención manual** ✅

### Integración con Scheduler
```python
# Ya configurado en auto_scheduler.py
schedule.every().monday.at("08:00").do(self.generate_diagnostic_report)
```

---

## 🛠️ Ejecución Manual

### Uso Básico
```powershell
# Análisis estándar (30 días)
python scripts/run_diagnostics.py

# Análisis extendido (90 días)
python scripts/run_diagnostics.py --days 90

# Con salida personalizada
python scripts/run_diagnostics.py --output mi_reporte.md
```

### Código de Salida
El script retorna códigos de error para integración CI/CD:
- `0` = Todo OK (sin HIGH/CRITICAL)
- `1` = Problemas HIGH detectados
- `2` = Problemas CRITICAL detectados

---

## 📋 Información que Necesita el Sistema

### Archivos de Entrada (en `logs/`)
```
logs/
├── equity.csv       → Evolución del capital (ts, nav)
├── trades.csv       → Trades cerrados (entry, exit, PnL, R)
├── signals.csv      → Señales generadas
├── orders.csv       → Órdenes enviadas
└── fills.csv        → Fills ejecutados
```

### Estructura Necesaria

#### `equity.csv`
```csv
ts,nav
2026-02-01T00:00:00,100000.00
2026-02-02T00:00:00,100250.50
2026-02-03T00:00:00,99875.25
```
**Necesario para:** Calcular DD, Sharpe, volatilidad

---

#### `trades.csv`
```csv
entry_ts,exit_ts,pair,side,units,entry_price,exit_price,initial_sl,initial_tp,pnl_usd,r_multiple,hold_days,reason_exit,trade_id
2026-02-01,2026-02-05,EURUSD,long,10000,1.0850,1.0920,1.0830,1.0900,70.00,0.88,4.2,tp,12345
```
**Necesario para:** Win Rate, AvgR, Profit Factor, performance

---

#### `signals.csv`
```csv
ts,pair,side,kind,close,ema50,ema200,adx,dch,dcl,rsi2
2026-02-01T17:05:00,EURUSD,long,breakout,1.0850,1.0800,1.0750,28,1.0860,1.0720,45
```
**Necesario para:** Tasa de conversión, efectividad de filtros

---

#### `orders.csv`
```csv
ts,pair,side,kind,units,sl,tp,atr,entry_hint,order_response_json
2026-02-01T17:06:00,EURUSD,long,breakout,10000,1.0830,1.0900,0.0015,1.0850,"{...}"
```
**Necesario para:** Tasa de rechazo, errores de API

---

#### `fills.csv`
```csv
ts,tradeID,pair,side,units,price,fill_json
2026-02-01T17:06:15,12345,EURUSD,long,10000,1.0851,"{...}"
```
**Necesario para:** Validar órdenes ejecutadas

---

## 🎯 Problemas que Detecta Automáticamente

### Ejemplos Reales

#### 1. Sistema Perdiendo Dinero
```
🔴 CRITICAL: Expectativa negativa (AvgR < 0)
AvgR actual: -0.15R (sistema está perdiendo dinero)
→ URGENTE: Detener trading en vivo. Revisar estrategia completa.
```

#### 2. Drawdown Excesivo
```
🔴 CRITICAL: Drawdown máximo excede límite
MaxDD: -16.2% (límite crítico: -15%)
→ Reducir risk_pct_per_trade a 0.1% y max_total_risk a 0.4%
```

#### 3. Win Rate Bajo
```
🟠 HIGH: Win Rate por debajo del mínimo
Win Rate: 32% (mínimo: 35%)
→ Revisar filtros _validate_signal_quality, aumentar ADX threshold
```

#### 4. Datos Faltantes
```
🟠 HIGH: Archivo faltante: trades.csv
→ Verificar que TradeLogger esté funcionando correctamente
```

#### 5. Órdenes Rechazadas
```
🟠 HIGH: Alta tasa de rechazo de órdenes
18% rechazadas (máx: 10%)
→ Revisar validación de SL/TP y units
```

#### 6. Filtros Muy Restrictivos
```
🟡 MEDIUM: Baja tasa de conversión de señales
Solo 18% de señales ejecutadas
→ Relajar min_volatility_pct o min_adx
```

#### 7. Concentración Excesiva
```
🟡 MEDIUM: Concentración excesiva en un par
EURUSD representa 65% de trades
→ Revisar max_corr_trades para diversificar
```

#### 8. Performance Degradándose
```
🟠 HIGH: Degradación de performance reciente
AvgR últimos 7d: -0.2R vs previo: 0.5R
→ Posible cambio de régimen. Re-optimizar parámetros.
```

#### 9. Gaps en Datos
```
🟡 MEDIUM: Gaps en registro de equity
Gap máximo de 5.2 días entre registros
→ Asegurar que scheduler ejecute log_equity() diariamente
```

#### 10. Variables de Entorno
```
🔴 CRITICAL: Variables de entorno faltantes
Faltan: OANDA_TOKEN, OANDA_ACCOUNT
→ Configurar en .env o sistema operativo
```

---

## 📈 Workflow de Mejora Continua

```
┌─────────────────────────────────────┐
│  LUNES 08:00 UTC                    │
│  Diagnóstico automático             │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Genera reporte en logs/            │
│  diagnostic_report_YYYYMMDD.md      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Health Score < 60?                 │
└──────────────┬──────────────────────┘
       NO │             │ SÍ
          │             ▼
          │   ┌─────────────────────────┐
          │   │ Revisar TOP             │
          │   │ RECOMENDACIONES         │
          │   └─────────┬───────────────┘
          │             │
          │             ▼
          │   ┌─────────────────────────┐
          │   │ Aplicar cambios         │
          │   │ sugeridos               │
          │   └─────────┬───────────────┘
          │             │
          │             ▼
          │   ┌─────────────────────────┐
          │   │ Re-ejecutar diagnóstico │
          │   │ (manual)                │
          │   └─────────┬───────────────┘
          │             │
          ▼             ▼
┌─────────────────────────────────────┐
│  Continuar operando                 │
│  Monitorear métricas                │
└──────────────┬──────────────────────┘
               │
               ▼
      [Siguiente Lunes]
```

---

## 🔧 Archivos del Sistema

### Nuevos Archivos Creados

```
fx_conservative/
└── diagnostics.py                    # Motor de análisis (600+ líneas)
    ├── DiagnosticIssue              # Clase para problemas
    ├── DiagnosticReport             # Clase para reportes
    ├── SystemDiagnostics            # Analizador principal
    └── generate_markdown_report()   # Generador de reportes

scripts/
├── run_diagnostics.py               # Script de ejecución manual
└── auto_scheduler.py                # Actualizado con diagnóstico

docs/
└── DIAGNOSTICO_GUIA.md              # Esta guía completa
```

### Actualizaciones

```
scripts/auto_scheduler.py
├── + import diagnostics
├── + generate_diagnostic_report()   # Nueva función
└── + schedule lunes 08:00           # Nueva tarea programada
```

---

## 📊 Métricas Objetivo

El sistema compara contra estos **umbrales**:

| Métrica | CRITICAL | HIGH | MEDIUM | OBJETIVO | EXCELENTE |
|---------|----------|------|--------|----------|-----------|
| **Win Rate** | <25% | <35% | <40% | 45% | >55% |
| **AvgR** | <0 | <0.3R | <0.5R | 0.7R | >1.0R |
| **Profit Factor** | <1.0 | <1.3 | <1.5 | 2.0 | >2.5 |
| **Max DD** | >-15% | >-12% | >-10% | -8% | <-5% |
| **Rechazo Órdenes** | >25% | >10% | >5% | 2% | <1% |
| **Conversión Señal** | <10% | <30% | - | 50% | >70% |
| **Volatilidad Equity** | >5% | >2% | >1.5% | 1% | <0.5% |

---

## 🚀 Cómo Empezar

### 1. Verificar que tienes datos
```powershell
# Listar archivos en logs/
Get-ChildItem logs\*.csv

# Debería mostrar: equity.csv, trades.csv, signals.csv, orders.csv, fills.csv
```

### 2. Ejecutar primer diagnóstico
```powershell
python scripts/run_diagnostics.py
```

### 3. Revisar el reporte
```powershell
# Ver reporte generado
Get-Content logs\diagnostic_report_*.md

# O abrirlo en VS Code/Notepad
code logs\diagnostic_report_20260225.md
```

### 4. Aplicar recomendaciones
Si hay problemas HIGH/CRITICAL:
1. Leer "TOP RECOMENDACIONES URGENTES"
2. Aplicar cambios sugeridos
3. Re-ejecutar diagnóstico
4. Verificar mejora

### 5. Activar diagnóstico automático
```powershell
# Iniciar scheduler (incluye diagnóstico semanal)
python scripts/auto_scheduler.py
```

---

## 💡 Casos de Uso

### Caso 1: Sistema Nuevo (Sin Historial)
```
Día 1: Iniciar trading
Día 7: Primer diagnóstico manual
  → Probablemente muchos INFO (normal, pocos datos)
Día 30: Diagnóstico automático (lunes)
  → Ya hay datos suficientes para análisis real
```

### Caso 2: Sistema en Producción
```
Cada Lunes: Revisar reporte automático (5 min)
Si Health Score > 80: ✅ Todo bien
Si Health Score 60-79: 📋 Planificar mejoras
Si Health Score < 60: 🚨 Acción inmediata
```

### Caso 3: Después de Cambiar Parámetros
```
1. Hacer cambios en config
2. Ejecutar: python scripts/run_diagnostics.py --days 7
3. Verificar no introdujiste nuevos problemas
4. Monitorear 1 semana
5. Re-ejecutar diagnóstico
```

### Caso 4: Sospecha de Problemas
```
1. Ejecutar: python scripts/run_diagnostics.py --days 14
2. Buscar problemas HIGH/CRITICAL
3. Leer recomendaciones
4. Aplicar fixes
5. Re-ejecutar al día siguiente
```

---

## ⚙️ Personalización

### Ajustar Umbrales
Editar `fx_conservative/diagnostics.py`:

```python
# Ejemplo: Cambiar umbral de Win Rate
if win_rate < 0.30:  # Era 0.35
    self.issues.append(DiagnosticIssue(
        severity="HIGH",
        ...
```

### Añadir Nuevos Análisis
```python
def _analyze_custom_metric(self):
    """Análisis personalizado."""
    # Tu lógica aquí
    pass

# En analyze_all():
self._analyze_custom_metric()
```

### Cambiar Frecuencia
Editar `scripts/auto_scheduler.py`:

```python
# Ejemplo: Diagnóstico diario en vez de semanal
schedule.every().day.at("08:00").do(self.generate_diagnostic_report)
```

---

## 📞 Troubleshooting

### "No genera reporte"
1. Verificar logs/ existe
2. Verificar permisos de escritura
3. Ver logs/scheduler.log para errores

### "Todos los problemas son INFO"
✅ **Esto es BUENO** - significa que el sistema está funcionando perfectamente

### "Health Score = 0"
Muchos problemas detectados. Revisar:
1. ¿Datos suficientes? (mínimo 7 días)
2. ¿Sistema configurado correctamente?
3. ¿Variables de entorno OK?

### "Error al leer CSV"
1. Verificar formato de archivos
2. Abrir CSV en Excel para validar
3. Regenerar archivos si están corruptos

---

## ✅ Resumen

**Tienes ahora:**
1. ✅ Sistema que se auto-analiza semanalmente
2. ✅ Detección de 50+ tipos de problemas
3. ✅ Recomendaciones específicas para cada problema
4. ✅ Health Score 0-100 fácil de entender
5. ✅ Reportes automáticos en Markdown
6. ✅ Ejecución manual bajo demanda
7. ✅ Integración completa con scheduler
8. ✅ Documentación exhaustiva

**El sistema detecta:**
- 🔴 Problemas que causan pérdidas
- 📉 Degradación de performance
- 🐛 Errores técnicos
- 📊 Calidad de datos
- 🎯 Oportunidades de mejora

**Sin intervención manual** → Cada lunes tendrás un diagnóstico completo 🚀
