# Sobe o StarChef da loja (Windows). Rode nesta pasta:
#   powershell -ExecutionPolicy Bypass -File .\instalar.ps1
#
# 1. Cria o .env.local a partir do exemplo (ou completa o que faltar nele).
# 2. Gera a chave do Django, a senha do banco e o segredo de matrícula.
# 3. Descobre o IP do servidor na rede da loja e pergunta se está certo.
# 4. Baixa as imagens e sobe tudo, esperando o backend ficar pronto.
#
# Rodar de novo é seguro: nada que já está preenchido é trocado. Trocar a
# senha do banco depois da primeira subida, aliás, quebraria o acesso a ele.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$envFile = ".env.local"
$compose = @("compose", "--env-file", $envFile, "-f", "docker-compose.local.yml")

function Novo-Segredo([int]$bytes) {
    $buffer = New-Object byte[] $bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return ([Convert]::ToBase64String($buffer) -replace '[+/=]', '')
}

function Ler-Valor([string[]]$linhas, [string]$chave) {
    foreach ($linha in $linhas) {
        if ($linha -match "^\s*$chave=(.*)$") { return $Matches[1].Trim() }
    }
    return $null
}

function Gravar-Valor([string]$chave, [string]$valor) {
    $linhas = [System.Collections.Generic.List[string]](Get-Content $envFile)
    $achou = $false
    for ($i = 0; $i -lt $linhas.Count; $i++) {
        if ($linhas[$i] -match "^\s*$chave=") { $linhas[$i] = "$chave=$valor"; $achou = $true }
    }
    if (-not $achou) { $linhas.Add("$chave=$valor") }
    # UTF-8 SEM BOM: o BOM grudaria na primeira chave do arquivo.
    [System.IO.File]::WriteAllLines((Join-Path $PSScriptRoot $envFile), $linhas, (New-Object System.Text.UTF8Encoding($false)))
}

function Ip-Da-Loja {
    $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -match '^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)' -and $_.InterfaceAlias -notmatch 'vEthernet|WSL|Docker|Loopback' } |
        Select-Object -ExpandProperty IPAddress
    return ($ips | Select-Object -First 1)
}

# ── Docker ───────────────────────────────────────────────────────────────────
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "O Docker nao esta rodando. Abra o Docker Desktop, espere ele ficar verde e rode de novo." -ForegroundColor Red
    exit 1
}

# ── .env.local ───────────────────────────────────────────────────────────────
if (-not (Test-Path $envFile)) {
    Copy-Item ".env.local.example" $envFile
    Write-Host "Criado $envFile a partir do exemplo."
}
$linhas = Get-Content $envFile

if (-not (Ler-Valor $linhas "STARCHEF_VERSION")) { Gravar-Valor "STARCHEF_VERSION" (Ler-Valor (Get-Content ".env.local.example") "STARCHEF_VERSION") }
if (-not (Ler-Valor $linhas "DJANGO_SECRET_KEY")) { Gravar-Valor "DJANGO_SECRET_KEY" (Novo-Segredo 48); Write-Host "Gerada a chave do Django." }
if (-not (Ler-Valor $linhas "POSTGRES_PASSWORD")) { Gravar-Valor "POSTGRES_PASSWORD" (Novo-Segredo 24); Write-Host "Gerada a senha do banco." }
if (-not (Ler-Valor $linhas "SYNC_ENROLL_SECRET")) { Gravar-Valor "SYNC_ENROLL_SECRET" (Novo-Segredo 32) }

# Loja sem sincronização cria a conta pelo primeiro acesso, e ele exige token.
if ((Ler-Valor (Get-Content $envFile) "SYNC_ENABLED") -ne "true" -and -not (Ler-Valor (Get-Content $envFile) "DJANGO_FIRST_ACCESS_TOKEN")) {
    $token = Novo-Segredo 18
    Gravar-Valor "DJANGO_FIRST_ACCESS_TOKEN" $token
}

$atual = Ler-Valor (Get-Content $envFile) "STORE_HOST"
if (-not $atual -or $atual -eq "192.168.0.10") {
    $sugerido = Ip-Da-Loja
    $resposta = Read-Host "IP deste servidor na rede da loja [$sugerido]"
    if ([string]::IsNullOrWhiteSpace($resposta)) { $resposta = $sugerido }
    if ([string]::IsNullOrWhiteSpace($resposta)) {
        Write-Host "Nao foi possivel descobrir o IP. Preencha STORE_HOST no $envFile e rode de novo." -ForegroundColor Red
        exit 1
    }
    Gravar-Valor "STORE_HOST" $resposta.Trim()
}

$valores = Get-Content $envFile
if ((Ler-Valor $valores "SYNC_ENABLED") -eq "true") {
    foreach ($chave in "SYNC_ACCOUNT_ID", "SYNC_ENROLL_USERNAME", "SYNC_ENROLL_PASSWORD") {
        if (-not (Ler-Valor $valores $chave) -and -not (Ler-Valor $valores "SYNC_AUTH_TOKEN")) {
            Write-Host "SYNC_ENABLED=true, mas $chave esta vazio no $envFile. Preencha e rode de novo." -ForegroundColor Red
            exit 1
        }
    }
}

# ── Subir ────────────────────────────────────────────────────────────────────
& docker @compose config --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "O $envFile tem algum valor invalido (veja acima)." -ForegroundColor Red; exit 1 }
& docker @compose pull
if ($LASTEXITCODE -ne 0) { exit 1 }
& docker @compose up -d
if ($LASTEXITCODE -ne 0) { exit 1 }

$hostLoja = Ler-Valor (Get-Content $envFile) "STORE_HOST"
$porta = Ler-Valor (Get-Content $envFile) "HTTP_PORT"
$base = if ($porta -and $porta -ne "80") { "http://${hostLoja}:$porta" } else { "http://$hostLoja" }

Write-Host "Esperando o backend ficar pronto (a primeira subida aplica as migrations e leva alguns minutos)..."
for ($i = 0; $i -lt 60; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "http://127.0.0.1:$(if ($porta) { $porta } else { 80 })/health/" | Out-Null
        Write-Host ""
        Write-Host "StarChef no ar." -ForegroundColor Green
        Write-Host "  Painel:       $base/"
        Write-Host "  API do PDV:   $base/api/v1"
        Write-Host "  Admin:        $base/admin/"
        $token = Ler-Valor (Get-Content $envFile) "DJANGO_FIRST_ACCESS_TOKEN"
        if ((Ler-Valor (Get-Content $envFile) "SYNC_ENABLED") -ne "true" -and $token) {
            Write-Host "  Primeiro acesso: abra o Admin e use o token $token para criar a conta e o administrador." -ForegroundColor Cyan
        }
        exit 0
    } catch { Start-Sleep -Seconds 10 }
}
Write-Host "O backend nao respondeu em 10 minutos. Veja o log: docker $($compose -join ' ') logs backend" -ForegroundColor Yellow
exit 1
