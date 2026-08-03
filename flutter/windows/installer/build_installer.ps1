# Compila o instalador Windows (Inno Setup) usando a versao do pubspec.yaml
# como unica fonte de verdade — starchef_pdv.iss recebe /DAppVersion no lugar
# de manter a versao hardcoded em dois arquivos.
#
# Uso:
#   flutter build windows --release
#   .\windows\installer\build_installer.ps1
#
# Requer o Inno Setup 6 instalado (ISCC.exe no PATH ou no caminho padrao).

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$pubspecPath = Join-Path $repoRoot "pubspec.yaml"

$versionLine = Select-String -Path $pubspecPath -Pattern '^version:\s*(\S+)' | Select-Object -First 1
if (-not $versionLine) {
    throw "Nao foi possivel achar a linha 'version:' em $pubspecPath"
}
# pubspec usa build-name+build-number (ex.: 1.0.0+1); o instalador so quer o build-name.
$fullVersion = $versionLine.Matches[0].Groups[1].Value
$appVersion = $fullVersion.Split("+")[0]

Write-Host "Versao lida do pubspec.yaml: $fullVersion (instalador usara $appVersion)"

$iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
if (-not $iscc) {
    $defaultPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $defaultPath) {
        $iscc = Get-Item $defaultPath
    } else {
        throw "ISCC.exe (Inno Setup) nao encontrado no PATH nem em '$defaultPath'."
    }
}

$issPath = Join-Path $PSScriptRoot "starchef_pdv.iss"
& $iscc.Source "/DAppVersion=$appVersion" $issPath
if ($LASTEXITCODE -ne 0) {
    throw "ISCC.exe falhou com codigo $LASTEXITCODE"
}

Write-Host "Instalador gerado em artifacts\StarChef-PDV-Setup-$appVersion-offline.exe"
