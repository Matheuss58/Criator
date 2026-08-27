$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $root "ai\venv"
$python = Join-Path $venv "Scripts\python.exe"

Write-Host "Preparando Criator local..." -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python 3.11 ou 3.12 nao foi encontrado. Instale pelo python.org e marque Add Python to PATH."
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  throw "FFmpeg nao foi encontrado no PATH. Instale o FFmpeg antes de continuar."
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  throw "Node.js nao foi encontrado. Instale a versao LTS antes de continuar."
}

if (-not (Test-Path $python)) {
  python -m venv $venv
}
& $python -m pip install --upgrade pip
& $python -m pip install -r (Join-Path $root "requirements.txt")
Push-Location (Join-Path $root "backend")
try { npm install } finally { Pop-Location }

Write-Host "Criator instalado. Execute .\start.ps1" -ForegroundColor Green
