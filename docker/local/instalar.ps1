# Gera um ambiente local de produção sem depender de arquivos .env de exemplo.
# Rode nesta pasta: powershell -ExecutionPolicy Bypass -File .\instalar.ps1
$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot
$envFile = Join-Path $PSScriptRoot '.env.local'
$compose = @('compose', '--env-file', '.env.local', '-f', 'docker-compose.local.yml')

function Novo-Segredo([int]$bytes) {
    $buffer = New-Object byte[] $bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    return [BitConverter]::ToString($buffer).Replace('-', '').ToLowerInvariant()
}

function Ler-Valor([string]$chave) {
    foreach ($linha in (Get-Content $envFile -ErrorAction SilentlyContinue)) {
        if ($linha -match "^\s*$([regex]::Escape($chave))=(.*)$") { return $Matches[1].Trim() }
    }
    return ''
}

function Gravar-Valor([string]$chave, [string]$valor) {
    $linhas = New-Object 'System.Collections.Generic.List[string]'
    foreach ($linha in (Get-Content $envFile -ErrorAction SilentlyContinue)) { $linhas.Add($linha) }
    $achou = $false
    for ($i = 0; $i -lt $linhas.Count; $i++) {
        if ($linhas[$i] -match "^\s*$([regex]::Escape($chave))=") { $linhas[$i] = "$chave=$valor"; $achou = $true }
    }
    if (-not $achou) { $linhas.Add("$chave=$valor") }
    [System.IO.File]::WriteAllLines($envFile, $linhas, [System.Text.UTF8Encoding]::new($false))
}

function Padrao([string]$chave, [string]$valor) {
    if (-not (Ler-Valor $chave)) { Gravar-Valor $chave $valor }
}

function Segredo-Se-Faltar([string]$chave, [int]$bytes) {
    if (-not (Ler-Valor $chave)) { Gravar-Valor $chave (Novo-Segredo $bytes) }
}

function Ip-Da-Loja {
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -match '^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)' -and $_.InterfaceAlias -notmatch 'vEthernet|WSL|Docker|Loopback' } |
        Select-Object -ExpandProperty IPAddress -First 1
}

if (-not (Test-Path $envFile)) {
    [System.IO.File]::WriteAllText($envFile, '', [System.Text.UTF8Encoding]::new($false))
    Write-Host 'Criado .env.local com configurações de produção.'
}

$defaults = [ordered]@{
    POSTGRES_DB='starchef_local'; POSTGRES_USER='starchef'; DJANGO_ENV='production'
    DJANGO_SETTINGS_MODULE='config.settings.production'; DJANGO_DEBUG='false'
    USE_SQLITE_DATABASE='false'; USE_LOCAL_MEMORY_SERVICES='false'
    POSTGRES_HOST='postgres'; POSTGRES_PORT='5432'; REDIS_URL='redis://redis:6379/0'
    CELERY_BROKER_URL='redis://redis:6379/1'; CELERY_RESULT_BACKEND='redis://redis:6379/2'
    DJANGO_SECURE_SSL_REDIRECT='false'; DJANGO_SESSION_COOKIE_SECURE='false'
    DJANGO_CSRF_COOKIE_SECURE='false'; DJANGO_AUTH_COOKIE_SECURE='false'
    SYNC_ENVIRONMENT='production'; SYNC_AUTO_ENROLL='true'
    SYNC_NODE_TYPE='local'; SYNC_ENROLL_ENV_PATH='/app/sync/credentials.env'
    SYNC_STALE_NEVER_SEEN_DAYS='7'; SYNC_STALE_SILENT_DAYS='30'
    FISCAL_TRANSMIT_VIA_CLOUD='true'; FISCAL_RELAY_TIMEOUT='45'
    HTTP_PORT='80'; HTTP_BIND='0.0.0.0'; BACKEND_PORT='8000'; BACKEND_BIND='0.0.0.0'
    GUNICORN_WORKERS='3'; CELERY_CONCURRENCY='2'; POSTGRES_POOL='true'
    POSTGRES_POOL_MIN='2'; POSTGRES_POOL_MAX='8'; POSTGRES_POOL_TIMEOUT='10'
    POSTGRES_CONN_HEALTH_CHECKS='false'; SYNC_BATCH_MAX_EVENTS='200'
    SYNC_BATCH_MAX_BYTES='1048576'; SYNC_RETENTION_DAYS='30'; SYNC_INTERVAL='2'
    SYNC_HEARTBEAT='20'; SYNC_FILE_MAX_BYTES='67108864'; SENTRY_ENVIRONMENT='production'
    SENTRY_TRACES_SAMPLE_RATE='0.1'; SENTRY_SEND_PII='false'; POSTGRES_MEM_LIMIT='1g'
    POSTGRES_CELERY_CONN_MAX_AGE='60'; POSTGRES_CONN_MAX_AGE='60'
    DJANGO_EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend'; DJANGO_EMAIL_HOST='localhost'
    DJANGO_EMAIL_PORT='587'; DJANGO_EMAIL_USE_TLS='true'; DJANGO_EMAIL_USE_SSL='false'
    PASSWORD_RESET_TIMEOUT_MINUTES='30'; DJANGO_AUTH_COOKIE_SAMESITE='Lax'
    DJANGO_JWT_AUTH_COOKIE='sc_access'; DJANGO_JWT_AUTH_REFRESH_COOKIE='sc_refresh'
    DJANGO_STOREFRONT_JWT_AUTH_COOKIE='sf_access'; DJANGO_STOREFRONT_JWT_REFRESH_COOKIE='sf_refresh'
    FOCUS_NFE_PRODUCTION_URL='https://api.focusnfe.com.br'
    FOCUS_NFE_HOMOLOGATION_URL='https://homologacao.focusnfe.com.br'
    FOCUS_NFE_TIMEOUT_SECONDS='30'; FOCUS_NFE_AUTO_SYNC='true'; FOCUS_NFE_COMPANY_DRY_RUN='false'
    IMAGE_UPLOAD_MAX_BYTES='8388608'; RLS_ENABLED='false'
    REDIS_MEM_LIMIT='256m'; REDIS_MAXMEMORY='192mb'; BACKEND_MEM_LIMIT='1g'
    CELERY_WORKER_MEM_LIMIT='768m'; CELERY_BEAT_MEM_LIMIT='256m'; SYNC_WORKER_MEM_LIMIT='512m'
    FRONTEND_MEM_LIMIT='256m'; PROXY_MEM_LIMIT='128m'
}
foreach ($chave in $defaults.Keys) { Padrao $chave $defaults[$chave] }
Gravar-Valor 'SYNC_ENABLED' 'true'

foreach ($chave in @('STORE_HOST','DJANGO_ALLOWED_HOSTS','DJANGO_CORS_ALLOWED_ORIGINS','DJANGO_CSRF_TRUSTED_ORIGINS',
    'SYNC_ACCOUNT_ID','SYNC_STORE_ID','SYNC_ENROLL_USERNAME','SYNC_ENROLL_PASSWORD','SYNC_NODE_ID','SYNC_PAIR_ID',
    'SYNC_PEER_NODE_ID','SYNC_AUTH_TOKEN','SYNC_ENCRYPTION_KEY','SYNC_ENCRYPTION_KEY_ID','SYNC_CLOUD_API_URL',
    'SYNC_CLOUD_WSS_URL','SYNC_ENROLL_SECRET','SYNC_NODE_NAME','AWS_STORAGE_BUCKET_NAME',
    'AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_S3_ENDPOINT_URL','AWS_S3_CUSTOM_DOMAIN','SENTRY_DSN',
    'DJANGO_EMAIL_HOST_USER','DJANGO_EMAIL_HOST_PASSWORD','DJANGO_DEFAULT_FROM_EMAIL','DJANGO_AUTH_COOKIE_DOMAIN',
    'FOCUS_NFE_MASTER_TOKEN','FOCUS_NFE_WEBHOOK_URL','FOCUS_NFE_WEBHOOK_AUTHORIZATION',
    'FOCUS_NFE_WEBHOOK_AUTHORIZATION_HEADER','FRONTEND_URL')) {
    Padrao $chave ''
}
Padrao 'DJANGO_DEFAULT_FROM_EMAIL' 'StarChef <no-reply@localhost>'
Padrao 'AWS_S3_REGION_NAME' 'auto'
Padrao 'AWS_QUERYSTRING_AUTH' 'false'

Segredo-Se-Faltar POSTGRES_PASSWORD 32
Segredo-Se-Faltar DJANGO_SECRET_KEY 48
Segredo-Se-Faltar DJANGO_FIRST_ACCESS_TOKEN 24
Segredo-Se-Faltar SYNC_METRICS_TOKEN 32

if (-not (Ler-Valor 'STARCHEF_VERSION')) {
    $versao = Read-Host 'Versão da imagem StarChef [latest]'
    Padrao 'STARCHEF_VERSION' $(if ($versao) { $versao.Trim() } else { 'latest' })
}

$atual = Ler-Valor 'STORE_HOST'
if (-not $atual -or $atual -eq '192.168.0.10') {
    $sugerido = Ip-Da-Loja
    $resposta = Read-Host "IP/nome deste servidor na rede da loja [$sugerido]"
    if (-not $resposta) { $resposta = $sugerido }
    if (-not $resposta) { throw 'Informe o IP/nome do servidor em STORE_HOST.' }
    Gravar-Valor 'STORE_HOST' $resposta.Trim()
}

$hostLoja = Ler-Valor 'STORE_HOST'
$porta = Ler-Valor 'HTTP_PORT'
$origens = "http://${hostLoja},http://${hostLoja}:$porta,http://localhost,http://localhost:$porta"
Gravar-Valor 'DJANGO_ALLOWED_HOSTS' "localhost,127.0.0.1,backend,proxy,$hostLoja"
Gravar-Valor 'DJANGO_CORS_ALLOWED_ORIGINS' $origens
Gravar-Valor 'DJANGO_CSRF_TRUSTED_ORIGINS' $origens
Padrao 'FRONTEND_URL' "http://$hostLoja"

. (Join-Path $PSScriptRoot 'configurar-sincronizacao.ps1')

Write-Host ''
Write-Host 'Guarde estas chaves em local seguro:'
foreach ($chave in @('POSTGRES_USER','POSTGRES_DB','POSTGRES_PASSWORD','DJANGO_SECRET_KEY',
    'DJANGO_FIRST_ACCESS_TOKEN','SYNC_METRICS_TOKEN')) {
    Write-Host "  ${chave}=$(Ler-Valor $chave)"
}
Write-Host ''

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host '.env.local foi criado, mas o Docker não está rodando. Abra o Docker e rode novamente.' -ForegroundColor Red
    exit 1
}
& docker @compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'docker compose config encontrou um valor inválido.' }
& docker @compose pull
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& docker @compose up -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$base = if ($porta -eq '80') { "http://$hostLoja" } else { "http://${hostLoja}:$porta" }
Write-Host 'Esperando o backend ficar pronto (a primeira subida pode levar alguns minutos)...'
for ($i = 0; $i -lt 60; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "http://127.0.0.1:$porta/health/" | Out-Null
        Write-Host "StarChef no ar: $base/ (API $base/api/v1, Admin $base/admin/)" -ForegroundColor Green
        Write-Host "Token do primeiro acesso: $(Ler-Valor 'DJANGO_FIRST_ACCESS_TOKEN')" -ForegroundColor Cyan
        Write-Host "Sincronização: $(Ler-Valor 'SYNC_NODE_NAME') ($(Ler-Valor 'SYNC_ACCOUNT_ID'))" -ForegroundColor Cyan
        exit 0
    } catch { Start-Sleep -Seconds 10 }
}
Write-Host 'O backend não respondeu em 10 minutos. Consulte os logs do serviço backend.' -ForegroundColor Yellow
exit 1
