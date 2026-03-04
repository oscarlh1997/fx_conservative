# FX Conservative (Alpaca - Acciones)

Proyecto de trading conservador conectado a Alpaca para operar acciones USA.

## Requisitos

- Python (recomendado 3.10+)
- Cuenta de Alpaca (paper o live)

Instalar dependencias:

```powershell
py -m pip install -r requirements.txt
```

Configurar variables de entorno (PowerShell):

```powershell
$env:ALPACA_API_KEY="TU_KEY"
$env:ALPACA_SECRET_KEY="TU_SECRET"
$env:ALPACA_PAPER="true"   # "true" (paper) o "false" (live)
```

## Configuracion

- Config principal: `config/config.yaml`
- `pairs`: lista de simbolos (ej: SPY, QQQ, IWM)
- `daily_alignment_hour`: hora de cierre en NY (acciones suele ser 16)

## Ejecutar

Un ciclo (hace sync de cierres y luego evalua entradas):

```powershell
py scripts/main.py run-once --config config/config.yaml
```

Modo daemon (espera al cierre diario y ejecuta):

```powershell
py scripts/main.py daemon --config config/config.yaml
```

Actualizar trailing:

```powershell
py scripts/main.py update-trailing --config config/config.yaml
```

## Tests

```powershell
py -m pytest -q
```

