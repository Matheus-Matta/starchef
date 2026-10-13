# Carregado por instalar.ps1: põe a ACBrLib (lib + Schemas da NF-e) em acbr\libs.
#
# A lib é conferida pelo SHA-256 ANTES de ir para acbr\libs: uma página de
# erro, um download pela metade ou uma lib trocada viram aviso, nunca uma lib
# carregada pelo emissor que assina as notas da empresa (docs/FISCAL_ACBRLIB.md).
#
# Nunca derruba a instalação: sem a lib a loja sobe igual, e o caixa lê
# "ACBrLib não instalada" com a providência quando o provedor for ACBrLib.
Padrao 'ACBRLIB_PACOTE_URL' 'https://www.mediafire.com/file/hd3t2w7uqc2r6b3/acbr-fiscal-linux-x64.tar.gz/file'
Padrao 'ACBRLIB_SO_SHA256' 'deec61a921b830516ad3d7f5833aee7cb69603391eb497e649296ecc5522b3f0'
$acbrLibs = Join-Path $PSScriptRoot 'acbr/libs'
New-Item -ItemType Directory -Force -Path $acbrLibs | Out-Null

function Sha256-De([string]$arquivo) { (Get-FileHash $arquivo -Algorithm SHA256).Hash.ToLowerInvariant() }

function Acbrlib-Instalada {
    $so = Join-Path $acbrLibs 'libacbrnfe64.so'
    (Test-Path $so) -and (Test-Path (Join-Path $acbrLibs 'Schemas')) -and
        ((Sha256-De $so) -eq (Ler-Valor 'ACBRLIB_SO_SHA256'))
}

# O link direto do MediaFire muda a cada visita: ele é lido da página do arquivo.
function Link-Direto([string]$url) {
    if ($url -notmatch 'mediafire\.com/file/') { return $url }
    $pagina = (Invoke-WebRequest -UseBasicParsing -UserAgent 'Mozilla/5.0' $url).Content
    $achado = [regex]::Match($pagina, 'https://download\d*\.mediafire\.com/[^"'' ]+')
    if ($achado.Success) { return $achado.Value }
    return ''
}

function Instalar-Acbrlib {
    $url = Ler-Valor 'ACBRLIB_PACOTE_URL'
    if (-not $url) { Write-Host 'ACBrLib: sem ACBRLIB_PACOTE_URL; copie a lib para acbr\libs à mão.'; return }
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("acbrlib-" + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        Write-Host 'ACBrLib: baixando o pacote...'
        $direto = Link-Direto $url
        if (-not $direto) { throw 'link de download não encontrado na página' }
        $pacote = Join-Path $tmp 'pacote.tar.gz'
        Invoke-WebRequest -UseBasicParsing -UserAgent 'Mozilla/5.0' -OutFile $pacote $direto
        # tar.exe vem no Windows 10 (1803+) e abre .tar.gz.
        & tar.exe -xzf $pacote -C $tmp
        if ($LASTEXITCODE -ne 0) { throw 'o arquivo baixado não é um .tar.gz' }
        $so = Get-ChildItem -Path $tmp -Recurse -Filter 'libacbrnfe64.so' | Select-Object -First 1
        if (-not $so -or (Sha256-De $so.FullName) -ne (Ler-Valor 'ACBRLIB_SO_SHA256')) {
            Write-Host 'ACBrLib: a lib baixada não confere com ACBRLIB_SO_SHA256. Nada foi instalado.' -ForegroundColor Yellow
            return
        }
        # O ACBrLib.ini do comunicador lê os .xsd direto em /app/libs/Schemas.
        $origem = Join-Path $so.DirectoryName 'Schemas/NFe'
        if (-not (Test-Path $origem)) { $origem = Join-Path $so.DirectoryName 'Schemas' }
        $destino = Join-Path $acbrLibs 'Schemas'
        New-Item -ItemType Directory -Force -Path $destino | Out-Null
        Copy-Item $so.FullName (Join-Path $acbrLibs 'libacbrnfe64.so') -Force
        Copy-Item (Join-Path $origem '*.xsd') $destino -Force
        $total = (Get-ChildItem $destino -Filter '*.xsd').Count
        Write-Host "ACBrLib instalada em acbr\libs ($total Schemas)." -ForegroundColor Green
    } catch {
        Write-Host "ACBrLib: não consegui instalar ($($_.Exception.Message)). A loja sobe sem emissor; copie a lib para acbr\libs depois." -ForegroundColor Yellow
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

if (-not (Acbrlib-Instalada)) { Instalar-Acbrlib }
