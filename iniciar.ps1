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

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backend'; npm start" -WindowStyle Normal
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$frontend'; python -m http.server 8080" -WindowStyle Normal

Start-Sleep -Seconds 3
Start-Process "http://localhost:8080/index.html"

Write-Host "Frontend: http://localhost:8080/index.html" -ForegroundColor Green
Write-Host "Backend:  http://localhost:5001" -ForegroundColor Green
Write-Host "Feche as janelas do PowerShell para parar os servidores." -ForegroundColor Yellow
