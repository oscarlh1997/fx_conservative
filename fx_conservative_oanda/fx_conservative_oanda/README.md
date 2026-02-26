# FX Conservative Strategy (OANDA v20, Demo/Live) - VERSIÓN MEJORADA 🚀

Sistema **ultra-conservador** para trading de divisas (FX) sobre **OANDA v20** con:
- Señal principal: **breakout Donchian 20** a favor de la tendencia (EMA50/EMA200 + ADX>umbral).
- Señal secundaria (mitad de tamaño): **pullback RSI(2)** extremo a favor de la tendencia.
- **Gestión de riesgo estricta**: stop por ATR, TP=2.5R, trailing mejorado con **breakeven automático**, límite de **apalancamiento bruto**, **cupo total de riesgo**, control de **correlación** y **blackouts** por eventos macro.
- **Validación de señales robusta**: Filtros de volatilidad mínima, fuerza de breakout, separación EMA, y volumen.
- **Monitoreo de riesgo en tiempo real**: Tracking de Sharpe ratio, drawdown, alertas automáticas.
- **Backtest realista**: Incluye slippage, comisiones, y safeguards.
- **Forward-test automatizado** (cuenta **Practice**): se ejecuta tras el **cierre D1 a 17:00 NY**.
- **Logging completo**: señales, órdenes, ejecuciones, equity y **trades cerrados** con PnL y **R-multiple**.
- **Tests unitarios**: 15+ tests para funciones críticas.

> ⚠️ **MEJORAS IMPLEMENTADAS**: Se han corregido bugs críticos de gestión de riesgo, añadido validaciones robustas, breakeven automático, sistema de alertas, y optimizado parámetros para minimizar pérdidas. Ver `MEJORAS_IMPLEMENTADAS.md` para detalles completos.

> ⚠️ Aviso: el trading conlleva riesgo de pérdida. Usa cuenta demo y tamaños pequeños. Este software se ofrece **tal cual** (AS IS).

---

## 1) Requisitos

- **Python 3.10+**
- Cuenta de OANDA **Practice** (o **Live**). Crea tu token API y tu Account ID desde el portal.
- Instala dependencias:

```bash
python -m pip install -r requirements.txt
```

- Variables de entorno (no guardes el token en el repo):
```bash
# Linux/Mac
export OANDA_TOKEN="tu_token"
export OANDA_ACCOUNT="tu_account_id"         # Ej: 101-001-1234567-001
export OANDA_ENV="practice"                   # 'practice' o 'live'

# Windows (PowerShell)
$env:OANDA_TOKEN="tu_token"
$env:OANDA_ACCOUNT="tu_account_id"
$env:OANDA_ENV="practice"
```

---

## 2) Configuración

Edita `config/config.yaml` para ajustar parámetros (pares, riesgo por trade, Donchian, ADX, etc.).  
También puedes definir **blackouts de eventos** en `config/events.csv`.

- El **cierre diario** se alinea a **17:00 América/Nueva_York** (estándar FX).
- El proceso convierte automáticamente a **Europe/Madrid** para programar el run.

---

## 3) Uso rápido

### 3.1. Ejecutar **una vez** (usa la última vela D1 cerrada)
```bash
python scripts/main.py run-once --config config/config.yaml
```

### 3.2. Ejecutar como **demonio** (espera a cada cierre D1 y opera)
```bash
python scripts/main.py daemon --config config/config.yaml
```
> Puedes ponerlo en un VPS/servidor siempre encendido. Loguea en `logs/` y estado en `state/state.json`.

### 3.3. Actualizar **trailing** de todas las posiciones abiertas
```bash
python scripts/main.py update-trailing --config config/config.yaml
```

### 3.4. Ver **métricas** (lee `logs/` y calcula tu eficiencia)
```bash
python scripts/main.py metrics --config config/config.yaml
```

### 3.5. Backtest **offline** contra históricos D1 de OANDA (sin enviar órdenes)
```bash
python scripts/main.py backtest --config config/config.yaml --start 2020-01-01 --end 2025-01-01
```

---

## 4) Estructura de logs

Se crean en `logs/`:

- `signals.csv` — señales generadas por día y par (breakout/pullback).
- `orders.csv` — órdenes enviadas (con SL/TP propuestos) y respuesta de OANDA.
- `fills.csv` — ejecuciones (fills) y `tradeID` asociados.
- `trades.csv` — **trades cerrados** con PnL, R‑multiple, duración, etc.
- `equity.csv` — NAV con marca de tiempo (útil para Sharpe/DD).

Además `state/state.json` guarda:
- `last_transaction_id` — para leer **solo** nuevas transacciones de OANDA y actualizar `trades.csv`.

---

## 5) Tests y Validación ✅ NUEVO

El sistema incluye **15+ tests unitarios** para validar funciones críticas:

```bash
# Instalar pytest
python -m pip install pytest

# Ejecutar todos los tests
python -m pytest tests/ -v

# Tests específicos
python -m pytest tests/test_strategy.py::TestPositionSizing -v
```

Tests incluidos:
- ✅ Cálculo de position sizing (EURUSD, USDJPY)
- ✅ Cálculo de notional USD correcto
- ✅ Validación de safeguards de riesgo
- ✅ Indicadores técnicos (EMA, ATR, Donchian)
- ✅ Filtros de calidad de señales
- ✅ Correlación entre pares
- ✅ Monitor de riesgo y alertas

---

## 6) Configuración Optimizada 🎯 NUEVO

Usa la configuración mejorada para mejores resultados:

```bash
# Backtest con configuración optimizada
python scripts/main.py backtest --config config/config_optimized.yaml --start 2020-01-01 --end 2024-12-31

# Ejecutar en demo con parámetros optimizados
python scripts/main.py run-once --config config/config_optimized.yaml
```

**Mejoras en config_optimized.yaml**:
- ✅ Riesgo por trade reducido: 0.25% → **0.20%**
- ✅ Apalancamiento máximo reducido: 2.0x → **1.5x**
- ✅ Stops más amplios: 1.5 ATR → **1.8 ATR**
- ✅ Trailing optimizado: 3.0 → **3.5 ATR**
- ✅ Take profit mejorado: 2.0R → **2.5R**
- ✅ ADX más estricto: 20 → **25**
- ✅ Menos posiciones simultáneas: 5 → **4**

---

## 7) Monitoreo de Riesgo en Tiempo Real 📊 NUEVO

El sistema ahora incluye **RiskMonitor** que:
- Calcula Sharpe ratio en vivo
- Detecta drawdowns excesivos
- Genera alertas automáticas
- Puede detener el trading si DD > límite crítico

Las alertas aparecen en los logs y se pueden consultar programáticamente.

---

## 8) Puntos finos y recomendaciones

- **Breakeven Automático**: Cuando una posición alcanza **1.5R de profit**, el SL se mueve automáticamente a breakeven + 0.3 ATR para proteger ganancias.
- **Trailing Mejorado**: se establece como **trailingStopLoss distance** (= ATR × 3.5). OANDA lo ajusta con el precio intradía. Se **recalibra** diariamente y tiene distancia mínima de 0.8 ATR.
- **Cupo de riesgo**: se calcula con el **riesgo residual** de trades abiertos (si hay SL conocido); si no, asume `risk_per_trade` por trade de forma conservadora.
- **Apalancamiento**: suma de notionals en USD / NAV ≤ `max_gross_leverage`. Se escala **automáticamente** el tamaño de nuevas operaciones si harían exceder el tope. **Safeguard adicional**: ninguna posición puede ser > 10% del equity.
- **Correlación**: si la señal es muy correlacionada (> 0.75) con posiciones abiertas **en la misma dirección**, se reduce el tamaño al **50%**.
- **Eventos**: añade tus eventos (CPI, NFP, bancos centrales, etc.) a `config/events.csv`. El sistema evita nuevas entradas ± blackouts indicados.
- **Validación de Señales**: Filtros automáticos rechazan señales con:
  - Volatilidad muy baja (ATR < 0.05% del precio)
  - ADX insuficiente (< 1.25x threshold)
  - Breakouts débiles (< 15% de ATR)
  - Volumen bajo (< 30% del promedio)

---

## 9) Seguridad y pruebas

1. **IMPORTANTE**: Lee `MEJORAS_IMPLEMENTADAS.md` para entender todos los cambios.
2. Empieza en **Practice** y deja correr **varias semanas**.
3. Ejecuta los **tests unitarios** para validar: `pytest tests/ -v`
4. Compara `backtest` vs `forward-test` (ordenamiento de señales, tasa de fills, slippage).
5. **Monitorea las alertas** del RiskMonitor diariamente.
6. Ajusta **spreads** y parámetros de riesgo en el YAML según necesites.
7. Cuando estés satisfecho, pasa a **Live** cambiando `OANDA_ENV` y usando tamaños prudentes.

**Expectativas Realistas** (con config_optimized.yaml):
- Win Rate: 42-48%
- Sharpe Ratio: 0.8-1.2
- Max Drawdown: 10-15%
- Avg R-multiple: 0.5-0.8

---

## 7) Licencia

Este proyecto se entrega **tal cual** sin garantías. Úsese con fines educativos y bajo tu responsabilidad.
