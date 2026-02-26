# 🤖 GUÍA DEL SCHEDULER AUTOMÁTICO

## ¿Qué hace el Auto Scheduler?

El **Auto Scheduler** ejecuta tu bot de trading **automáticamente** en horarios específicos sin necesidad de intervención manual. Es como tener un asistente que:

✅ Opera solo cuando el mercado FX está abierto (Lunes-Viernes)  
✅ Ejecuta el ciclo de trading diariamente a las 17:05 NY  
✅ Actualiza trailing stops cada 6 horas  
✅ Sincroniza transacciones cada 2 horas  
✅ Genera reportes diarios automáticamente  
✅ Respeta alertas del RiskMonitor  
✅ Se detiene automáticamente si detecta riesgo crítico  

---

## 📅 Programación de Tareas

### Ciclo Principal de Trading
- **Cuándo**: Diariamente a las **17:05 NY** (22:05 UTC horario estándar)
- **Qué hace**: Ejecuta `run_daily_cycle()` - genera señales y envía órdenes
- **Por qué a esa hora**: Es 5 minutos después del cierre oficial de vela D1 en FX

### Actualización de Trailing Stops
- **Cuándo**: Cada **6 horas** (00:00, 06:00, 12:00, 18:00 UTC)
- **Qué hace**: Recalibra trailing stops con ATR actual, aplica breakeven
- **Por qué**: El ATR cambia con la volatilidad, necesita ajuste regular

### Sincronización de Transacciones
- **Cuándo**: Cada **2 horas**
- **Qué hace**: Lee nuevas transacciones de OANDA, registra trades cerrados
- **Por qué**: Mantiene logs actualizados con SL/TP ejecutados

### Reporte Diario
- **Cuándo**: Diariamente a las **23:00 UTC**
- **Qué hace**: Genera reporte con métricas (Sharpe, DD, Win Rate, etc.)
- **Dónde**: Guarda en `logs/daily_report_YYYYMMDD.md`

---

## 🚀 OPCIÓN 1: Ejecutar Manualmente (Desarrollo/Testing)

### Instalación
```powershell
# Instalar dependencia adicional
python -m pip install schedule
```

### Ejecutar
```powershell
# Modo normal (queda corriendo 24/7)
python scripts/auto_scheduler.py --config config/config_optimized.yaml

# Modo test (ejecuta un ciclo inmediato y termina)
python scripts/auto_scheduler.py --config config/config_optimized.yaml --test
```

### Ventajas
- ✅ Control total sobre inicio/detención
- ✅ Puedes ver logs en tiempo real
- ✅ Ideal para testing

### Desventajas
- ❌ Debes mantener la ventana de PowerShell abierta
- ❌ Si cierras sesión, se detiene
- ❌ Si Windows se reinicia, hay que iniciarlo manualmente

---

## 🎯 OPCIÓN 2: Tarea Programada de Windows (Producción)

### Instalación

**Paso 1**: Abrir PowerShell como **Administrador**
```powershell
# Clic derecho en PowerShell → "Ejecutar como administrador"
```

**Paso 2**: Navegar al directorio del proyecto
```powershell
cd C:\Users\n487807\Downloads\fx_conservative_oanda\fx_conservative_oanda\scripts
```

**Paso 3**: Ejecutar el script de instalación
```powershell
.\install_windows_service.ps1
```

**Paso 4**: Iniciar la tarea
```powershell
Start-ScheduledTask -TaskName "FXConservativeTrading"
```

### Ventajas
- ✅ Se inicia automáticamente al arrancar Windows
- ✅ Corre en background (no necesita ventana abierta)
- ✅ Sigue corriendo aunque cierres sesión
- ✅ Se reinicia automáticamente si falla
- ✅ **Recomendado para producción**

### Desventajas
- ❌ Requiere privilegios de administrador
- ❌ Logs solo en archivo (no consola)

---

## 🛠️ Comandos Útiles (Tarea Programada)

### Ver Estado
```powershell
Get-ScheduledTask -TaskName "FXConservativeTrading"
```

### Iniciar
```powershell
Start-ScheduledTask -TaskName "FXConservativeTrading"
```

### Detener
```powershell
Stop-ScheduledTask -TaskName "FXConservativeTrading"
```

### Ver Logs en Tiempo Real
```powershell
Get-Content logs\scheduler.log -Wait -Tail 50
```

### Eliminar Tarea
```powershell
Unregister-ScheduledTask -TaskName "FXConservativeTrading" -Confirm:$false
```

---

## 📊 Monitoreo

### Ver Logs del Scheduler
```powershell
# Ver últimas 100 líneas
Get-Content logs\scheduler.log -Tail 100

# Seguir logs en tiempo real
Get-Content logs\scheduler.log -Wait
```

### Ver Reportes Diarios
```powershell
# Listar reportes generados
Get-ChildItem logs\daily_report_*.md

# Ver reporte de hoy
Get-Content logs\daily_report_$(Get-Date -Format "yyyyMMdd").md
```

### Ver Métricas Actuales
```powershell
python scripts/main.py metrics --config config/config_optimized.yaml
```

---

## 🔍 Verificar que Funciona

### Test Inmediato
```powershell
# Ejecutar un ciclo de prueba
python scripts/auto_scheduler.py --config config/config_optimized.yaml --test
```

**Salida esperada**:
```
✅ TradingScheduler inicializado con equity: $100,000.00
🧪 MODO TEST - Ejecutando ciclo inmediato
🚀 Iniciando ciclo diario de trading...
   Sync: {'synced': 0}
   Resultado: {'opened': 0, 'signals': []}
🔄 Actualizando trailing stops...
   Resultado: {'updated_trailings': 2, 'moved_to_breakeven': 0}
📊 Generando reporte diario...
   Equity: $100,500.00
   Retorno: 0.50%
   Sharpe: 1.05
   DD: -0.02%
✅ Test completado
```

### Verificar Horarios
```powershell
# Ver próximas ejecuciones programadas
Get-ScheduledTask -TaskName "FXConservativeTrading" | Get-ScheduledTaskInfo
```

---

## ⚙️ Personalización de Horarios

Si quieres cambiar los horarios, edita `auto_scheduler.py`:

```python
def setup_schedule(self):
    # EJEMPLO: Cambiar hora del ciclo de trading
    schedule.every().day.at("22:05").do(self.execute_daily_cycle)  # UTC
    # Cambiar a: 21:05 UTC (16:05 NY) si quieres más temprano
    
    # EJEMPLO: Trailing stops cada 4 horas en vez de 6
    schedule.every(4).hours.do(self.update_trailings)
    
    # EJEMPLO: Reporte cada 12 horas
    schedule.every().day.at("11:00").do(self.generate_daily_report)
    schedule.every().day.at("23:00").do(self.generate_daily_report)
```

---

## 🛡️ Protecciones Implementadas

### 1. Detección de Mercado Cerrado
```python
# No opera sábados
# No opera domingos antes de 22:00 UTC
# No opera viernes después de 22:00 UTC
```

### 2. Horarios Seguros
```python
# Evita operar domingo antes de 23:00 UTC (baja liquidez)
# Evita operar viernes después de 20:00 UTC (pre-cierre)
```

### 3. Circuit Breaker del RiskMonitor
```python
# Si drawdown > 24% (2x límite), detiene trading automáticamente
# Si pérdida > 30% del capital inicial, detiene trading
```

### 4. Auto-Reintentos
```python
# Si falla una tarea, se reintenta automáticamente
# Hasta 3 reintentos con 5 minutos de espera
```

---

## 🚨 Resolución de Problemas

### Problema: La tarea no se inicia
**Solución**:
```powershell
# Verificar que Python está en el PATH
python --version

# Verificar permisos
Get-ScheduledTask -TaskName "FXConservativeTrading" | Select-Object -ExpandProperty Principal

# Reiniciar la tarea
Stop-ScheduledTask -TaskName "FXConservativeTrading"
Start-ScheduledTask -TaskName "FXConservativeTrading"
```

### Problema: No veo logs
**Solución**:
```powershell
# Verificar que el directorio logs existe
Test-Path logs

# Crear si no existe
New-Item -ItemType Directory -Path logs -Force

# Ver últimas líneas del log
Get-Content logs\scheduler.log -Tail 50
```

### Problema: "Circuit breaker activado"
**Solución**:
```
Esto es NORMAL si hay muchos errores de API consecutivos.
1. Verificar conexión a internet
2. Verificar que OANDA_TOKEN es válido
3. Esperar 10 minutos y se resetea automáticamente
```

### Problema: "STOP TRADING activado"
**Solución**:
```
El RiskMonitor detectó riesgo crítico (DD > 24%).
1. Revisar logs/daily_report*.md
2. Analizar qué causó las pérdidas
3. Decidir si continuar o pausar
4. Si continúas, el sistema se reactivará en el próximo ciclo
```

---

## 📈 Ejemplo de Día Típico

```
00:00 UTC - Actualización de trailing stops
01:00 UTC - Sincronización de transacciones
02:00 UTC - (no hay tareas)
03:00 UTC - Sincronización de transacciones
04:00 UTC - (no hay tareas)
05:00 UTC - Sincronización de transacciones
06:00 UTC - Actualización de trailing stops
...
22:05 UTC - 🚀 CICLO PRINCIPAL DE TRADING 🚀
           - Genera señales
           - Verifica riesgo
           - Envía órdenes si hay señales válidas
           - Actualiza logs
23:00 UTC - Generación de reporte diario
```

---

## 🎯 Recomendaciones

### Para Testing (1-2 semanas):
- ✅ Usar **Opción 1** (ejecución manual)
- ✅ Ejecutar con `--test` varias veces al día
- ✅ Revisar logs constantemente
- ✅ Validar que las señales son correctas

### Para Producción (3+ meses):
- ✅ Usar **Opción 2** (tarea programada)
- ✅ Revisar logs 1 vez al día
- ✅ Leer reportes diarios cada mañana
- ✅ Ajustar parámetros solo si es necesario

### Monitoreo Mínimo:
- 📅 **Diario**: Leer reporte (2 minutos)
- 📅 **Semanal**: Ejecutar `metrics` (5 minutos)
- 📅 **Mensual**: Análisis completo (30 minutos)

---

## ✅ Checklist de Puesta en Marcha

- [ ] Instalar schedule: `pip install schedule`
- [ ] Configurar variables de entorno (OANDA_TOKEN, OANDA_ACCOUNT, OANDA_ENV)
- [ ] Ejecutar test: `python scripts/auto_scheduler.py --test`
- [ ] Verificar que funciona correctamente
- [ ] (Opcional) Instalar como tarea programada
- [ ] Iniciar el scheduler
- [ ] Verificar logs después de 1 hora
- [ ] Verificar primer reporte diario
- [ ] Dejar correr y monitorear

---

**¡Ahora tu bot operará automáticamente 24/5 sin intervención manual! 🚀**
