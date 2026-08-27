$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

Write-Host "Iniciando Criator..." -ForegroundColor Cyan

function Stop-Port {
  param([int]$Port)
  $lines = netstat -ano | Select-String ":$Port"
  foreach ($line in $lines) {
    $parts = ($line.ToString() -split "\s+") | Where-Object { $_ }
    $pidValue = $parts[-1]
    if ($pidValue -match "^\d+$") {
      Stop-Process -Id ([int]$pidValue) -Force -ErrorAction SilentlyContinue
    }
  }
}

Stop-Port 5001
Stop-Port 8080
Start-Sleep -Seconds 1

# Set Demucs as optional
$env:CRIATOR_DEMUCS_REQUIRED = "0"
$env:CRIATOR_ENABLE_STEMS = "0"
$env:CRIATOR_ENABLE_DEEP_VISION = "0"

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backend'; npm start" -WindowStyle Normal
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$frontend'; python -m http.server 8080" -WindowStyle Normal

Start-Sleep -Seconds 3
Start-Process "http://localhost:8080/index.html"

Write-Host "Frontend: http://localhost:8080/index.html" -ForegroundColor Green
Write-Host "Backend:  http://localhost:5001" -ForegroundColor Green
Write-Host "Feche as janelas do PowerShell para parar os servidores." -ForegroundColor Yellow
Write-Host ""
Write-Host "NOTA: Demucs está desativado por padrão (CRIATOR_DEMUCS_REQUIRED=0)" -ForegroundColor Cyan
Write-Host "Para ativar, modifique o arquivo start.ps1 ou defina a variável de ambiente" -ForegroundColor Cyan
