# Script para configurar el Trading Bot como Tarea Programada de Windows
# Ejecutar como Administrador en PowerShell

# Parámetros de configuración
$TaskName = "FXConservativeTrading"
$ScriptPath = "$PSScriptRoot\auto_scheduler.py"
$WorkingDirectory = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$LogPath = "$WorkingDirectory\logs\scheduler.log"

# Verificar que el script existe
if (-not (Test-Path $ScriptPath)) {
    Write-Error "❌ No se encuentra auto_scheduler.py en: $ScriptPath"
    exit 1
}

Write-Host "🔧 Configurando Trading Bot como Tarea Programada..." -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuración:" -ForegroundColor Yellow
Write-Host "  - Tarea: $TaskName"
Write-Host "  - Script: $ScriptPath"
Write-Host "  - Directorio: $WorkingDirectory"
Write-Host "  - Logs: $LogPath"
Write-Host ""

# Crear directorio de logs si no existe
if (-not (Test-Path "$WorkingDirectory\logs")) {
    New-Item -ItemType Directory -Path "$WorkingDirectory\logs" -Force | Out-Null
}

# Definir la acción (ejecutar el script Python)
$Action = New-ScheduledTaskAction `
    -Execute "python" `
    -Argument "`"$ScriptPath`" --config config/config_optimized.yaml" `
    -WorkingDirectory $WorkingDirectory

# Definir el trigger (iniciar al arranque del sistema y ejecutar continuamente)
$Trigger = New-ScheduledTaskTrigger -AtStartup

# Configuración adicional
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5)

# Solicitar credenciales del usuario
Write-Host "🔐 Ingrese las credenciales para ejecutar la tarea:" -ForegroundColor Yellow
Write-Host "   (Use su usuario de Windows actual)" -ForegroundColor Gray
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType ServiceAccount `
    -RunLevel Highest

# Eliminar tarea existente si existe
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($ExistingTask) {
    Write-Host "⚠️  Eliminando tarea existente..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Registrar la nueva tarea
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "Trading Bot FX Conservative - Ejecución automática con scheduler" `
        -ErrorAction Stop
    
    Write-Host ""
    Write-Host "✅ Tarea programada creada exitosamente!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📋 Comandos útiles:" -ForegroundColor Cyan
    Write-Host "   Iniciar tarea:  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
    Write-Host "   Detener tarea:  Stop-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
    Write-Host "   Ver estado:     Get-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
    Write-Host "   Ver logs:       Get-Content '$LogPath' -Wait" -ForegroundColor White
    Write-Host "   Eliminar tarea: Unregister-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
    Write-Host ""
    Write-Host "⚠️  IMPORTANTE: La tarea se iniciará automáticamente al reiniciar Windows" -ForegroundColor Yellow
    Write-Host "   Para iniciarla ahora, ejecute: Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow
    Write-Host ""
    
} catch {
    Write-Error "❌ Error al crear la tarea programada: $_"
    exit 1
}
