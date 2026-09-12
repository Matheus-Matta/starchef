# Sobe um backend DEDICADO ao teste de carga: banco proprio e throttle desligado.
#
# Nunca aponte a suite para o banco de desenvolvimento normal: ela cria dezenas
# de milhares de registros de proposito e deixa lixo intencional para tras.
param(
    [string]$Port = "8001",
    [string]$Database = "db_loadtest.sqlite3"
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $raiz

$env:DJANGO_ENV = "development"
# Postgres quando POSTGRES_HOST ja estiver no ambiente. SQLite serializa a
# escrita e devolve "database is locked" (500) sob concorrencia — bom para
# conhecer o teto do ambiente de dev, ruim para medir o codigo.
if ($env:POSTGRES_HOST) {
    $env:USE_SQLITE_DATABASE = "False"
    Write-Host "Banco: Postgres em $($env:POSTGRES_HOST)"
} else {
    $env:USE_SQLITE_DATABASE = "True"
    $env:SQLITE_DB_NAME = $Database
    Write-Host "Banco: SQLite $Database (perfis pesado/extremo pedem Postgres)"
}
# Sem isto o teste mede o throttle do DRF, nao o sistema.
$env:THROTTLE_RATE_ANON = "1000000/min"
$env:THROTTLE_RATE_USER = "10000000/hour"
$env:THROTTLE_RATE_LOGIN = "100000/min"
$env:THROTTLE_RATE_TOKEN_REFRESH = "100000/min"
$env:THROTTLE_RATE_DEVICE_POLL = "1000000/min"
$env:THROTTLE_RATE_CASH_APPROVAL = "1000000/min"
$env:THROTTLE_RATE_PASSWORD_RESET = "100000/min"

Write-Host "Porta: $Port"
& "$raiz\.venv\Scripts\python.exe" "$raiz\backend\manage.py" migrate --noinput
& "$raiz\.venv\Scripts\python.exe" "$raiz\backend\manage.py" runserver "0.0.0.0:$Port" --noreload
