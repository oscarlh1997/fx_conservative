# 🚀 GUÍA RÁPIDA DE INICIO

## ⏱️ 5 Minutos para Empezar

### 1️⃣ Instalación (2 min)

```powershell
# Clonar o descargar el proyecto
cd fx_conservative_oanda

# Instalar dependencias
python -m pip install -r requirements.txt
```

### 2️⃣ Configuración (2 min)

```powershell
# Configurar variables de entorno
$env:OANDA_TOKEN="tu_token_aqui"
$env:OANDA_ACCOUNT="tu_account_id"
$env:OANDA_ENV="practice"
```

**¿Dónde obtener estos datos?**
1. Crear cuenta en [OANDA Practice](https://www.oanda.com/forex-trading/demo-account)
2. Ir a "Manage API Access"
3. Generar token y copiar Account ID

### 3️⃣ Validación (1 min)

```powershell
# Ejecutar tests
python -m pytest tests/ -v

# Todos deben pasar ✅
```

---

## 📊 Primer Backtest (5 min)

```powershell
# Backtest con configuración optimizada (últimos 4 años)
python scripts/main.py backtest --config config/config_optimized.yaml --start 2020-01-01 --end 2024-12-31
```

**Qué esperar**:
- Win Rate: 42-48%
- Sharpe Ratio: 0.8-1.2
- Max DD: 10-15%
- Archivos generados en `logs/`:
  - `backtest_equity_2020-01-01_2024-12-31.csv`
  - `backtest_trades_2020-01-01_2024-12-31.csv`

**Análisis**:
```powershell
# Ver métricas del backtest
python scripts/main.py metrics --config config/config_optimized.yaml
```

---

## 🎯 Primer Forward Test (10 min)

### Modo Manual (una ejecución)

```powershell
# Ejecutar un ciclo (usa última vela D1 cerrada)
python scripts/main.py run-once --config config/config_optimized.yaml
```

Esto:
1. ✅ Descarga datos de OANDA
2. ✅ Calcula indicadores
3. ✅ Genera señales
4. ✅ Verifica riesgo y correlación
5. ✅ Envía órdenes si hay señales válidas
6. ✅ Guarda logs

### Modo Daemon (ejecución automática)

```powershell
# Ejecuta automáticamente cada día a las 17:00 NY
python scripts/main.py daemon --config config/config_optimized.yaml
```

⚠️ **Dejar corriendo en un VPS o PC siempre encendido**

---

## 📁 Estructura de Archivos

```
logs/
  ├── signals.csv       # Señales generadas
  ├── orders.csv        # Órdenes enviadas
  ├── fills.csv         # Ejecuciones confirmadas
  ├── trades.csv        # Trades cerrados con PnL
  └── equity.csv        # Evolución del equity

state/
  └── state.json        # Estado interno (last_transaction_id, entries)

config/
  ├── config.yaml              # Config original
  ├── config_optimized.yaml    # Config mejorada ⭐
  └── events.csv               # Eventos macro (NFP, CPI, etc.)
```

---

## 🔍 Monitoreo Diario

### Ver Métricas

```powershell
python scripts/main.py metrics --config config/config_optimized.yaml
```

Output ejemplo:
```json
{
  "#Trades": 15,
  "WinRate": 0.47,
  "ProfitFactor": 1.8,
  "AvgR": 0.65,
  "LastNAV": 102500.00,
  "Sharpe": 1.05,
  "MaxDrawdown": -0.08
}
```

### Actualizar Trailing Stops

```powershell
# Ejecutar diariamente para recalibrar trailing stops
python scripts/main.py update-trailing --config config/config_optimized.yaml
```

### Ejemplo con RiskMonitor

```powershell
# Script avanzado con alertas
python scripts/example_with_risk_monitor.py
```

---

## ⚙️ Configuración Básica

### Archivo: `config/config_optimized.yaml`

**Parámetros Críticos**:
```yaml
# Pares a tradear
pairs: [EURUSD, GBPUSD, AUDUSD, USDJPY]

# Riesgo por trade (0.20% = $200 por cada $100k)
risk_per_trade: 0.002

# Riesgo total máximo (0.8% = $800 por cada $100k)
total_risk_cap: 0.008

# Apalancamiento máximo (1.5x)
max_gross_leverage: 1.5

# Stops
atr_stop_mult: 1.8      # 1.8 ATR de distancia
atr_trail_mult: 3.5     # 3.5 ATR para trailing
tp_R: 2.5               # Take profit a 2.5R

# Posiciones simultáneas
max_positions: 4
```

---

## 🎓 Casos de Uso Comunes

### Caso 1: Solo Backtest (Investigación)

```powershell
# Probar diferentes períodos
python scripts/main.py backtest --config config/config_optimized.yaml --start 2022-01-01 --end 2023-12-31

# Comparar con config original
python scripts/main.py backtest --config config/config.yaml --start 2022-01-01 --end 2023-12-31
```

### Caso 2: Forward Test Supervisado

```powershell
# Ejecutar manualmente después de cada cierre D1 (17:00 NY)
# En PowerShell, programar tarea:
python scripts/main.py run-once --config config/config_optimized.yaml
```

### Caso 3: Automatizado 24/7

```powershell
# Daemon en VPS
python scripts/main.py daemon --config config/config_optimized.yaml

# Agregar logs:
python scripts/main.py daemon --config config/config_optimized.yaml >> daemon.log 2>&1
```

### Caso 4: Solo Actualizar Trailing

```powershell
# Tarea programada (cron/Task Scheduler) cada 6 horas
python scripts/main.py update-trailing --config config/config_optimized.yaml
```

---

## 🛡️ Checklist de Seguridad

Antes de usar en LIVE (con dinero real):

- [ ] ✅ Backtest muestra Sharpe > 0.8
- [ ] ✅ Forward test en Practice por 3+ meses
- [ ] ✅ Win rate > 40% en forward test
- [ ] ✅ Max DD < 15% en forward test
- [ ] ✅ Tests unitarios pasan: `pytest tests/ -v`
- [ ] ✅ Entiendes cada parámetro del config
- [ ] ✅ Eventos macro configurados en `events.csv`
- [ ] ✅ Alertas de RiskMonitor funcionan
- [ ] ✅ Capital de riesgo (solo dinero que puedes perder)
- [ ] ✅ Empiezas con <$5k en Live

---

## 📞 Comandos Útiles

```powershell
# Ver ayuda general
python scripts/main.py --help

# Ayuda de un comando específico
python scripts/main.py backtest --help

# Ver logs en tiempo real (Windows)
Get-Content logs/equity.csv -Wait

# Limpiar logs (CUIDADO)
Remove-Item logs/*.csv

# Ejecutar un test específico
python -m pytest tests/test_strategy.py::TestPositionSizing::test_size_units_eurusd_long -v
```

---

## 🔥 Errores Comunes

### Error: "Faltan variables de entorno"
```powershell
# Solución: Configurar OANDA_TOKEN y OANDA_ACCOUNT
$env:OANDA_TOKEN="tu_token"
$env:OANDA_ACCOUNT="tu_account"
$env:OANDA_ENV="practice"
```

### Error: "Circuit breaker activado"
```
Solución: Muchos errores de API consecutivos
1. Verificar conexión a internet
2. Verificar que token es válido
3. Esperar 5 minutos y reintentar
```

### Error: "No se recibieron velas"
```
Solución: 
1. Verificar que el par está bien escrito (EURUSD, no EUR/USD)
2. Verificar horario (fuera de fin de semana)
```

### Warning: "Drawdown excesivo"
```
Solución:
1. Revisar parámetros de riesgo
2. Reducir risk_per_trade
3. Detener trading temporalmente
4. Analizar trades perdedores
```

---

## 📚 Siguiente Nivel

Una vez dominado lo básico:

1. **Optimización de Parámetros**
   - Probar diferentes valores de ATR multipliers
   - Ajustar ADX threshold según pares

2. **Análisis Avanzado**
   - Calcular correlación entre señales y volatilidad macro
   - Backtests rolling para validar robustez

3. **Personalización**
   - Agregar nuevos pares (EUR/GBP, AUD/NZD, etc.)
   - Implementar filtros adicionales (tiempo del día, sesión)

4. **Monitoreo Profesional**
   - Dashboards con Grafana
   - Alertas por Telegram/email
   - Integración con base de datos

---

## 🎯 Meta a 6 Meses

**Objetivo**: Sistema robusto generando 12-18% anual con DD < 12%

**Plan**:
- Mes 1-3: Backtest y optimización
- Mes 4-6: Forward test en Practice
- Mes 7+: Live con capital pequeño

**KPIs a Trackear**:
- Win Rate > 42%
- Sharpe Ratio > 0.8
- Max DD < 12%
- Profit Factor > 1.5

---

**¡Éxito en tu trading! 📈**
