# Libera a porta do Caixa Principal no Firewall do Windows.
#
# Por que isto existe: o PDV abre uma porta na rede da loja para os caixas
# secundários e o app do garçom. O Windows bloqueia conexões de entrada por
# padrão — e em rede classificada como "Pública" bloqueia sem nem perguntar.
# O sintoma aparece do outro lado ("não foi possível alcançar o caixa"), o que
# manda o suporte procurar no lugar errado.
#
# Uso: clique com o botão direito -> "Executar com o PowerShell".
# O script pede elevação sozinho (a regra de firewall exige administrador).
#
#   .\liberar_firewall.ps1              # porta padrão (47832)
#   .\liberar_firewall.ps1 -Port 50000  # se você mudou a porta no PDV

param(
    [int]$Port = 47832,
    # O instalador roda este script e ESPERA ele terminar: sem isto, a pausa
    # do fim deixaria a instalação parada para sempre em uma janela oculta.
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"
$nome = "StarChef PDV - Caixa Principal"

$identidade = [Security.Principal.WindowsIdentity]::GetCurrent()
$ehAdmin = (New-Object Security.Principal.WindowsPrincipal($identidade)).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $ehAdmin) {
    Write-Host "Pedindo permissao de administrador..."
    try {
        Start-Process powershell.exe -Verb RunAs -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", "`"$PSCommandPath`"", "-Port", $Port,
            $(if ($NoPause) { "-NoPause" } else { "" })
        ).Where({ $_ -ne "" })
    } catch {
        $recado = "A porta $Port continua BLOQUEADA no firewall: os outros caixas e o app do garcom nao vao conseguir conectar neste computador.`n`n" +
                  "Para liberar depois: Menu Iniciar -> StarChef PDV -> 'Liberar Caixa Principal no Firewall' (e aceite o pedido de administrador)."
        Write-Warning $recado
        # Durante a instalacao este script roda oculto: sem a caixa de dialogo,
        # recusar o pedido de administrador falharia em silencio e o problema
        # so apareceria do outro lado, no celular do garcom.
        try {
            (New-Object -ComObject Wscript.Shell).Popup($recado, 0, "StarChef PDV - firewall nao liberado", 48) | Out-Null
        } catch {
            # Sem shell grafico (execucao automatizada): o aviso de texto basta.
        }
        exit 1
    }
    exit 0
}

# Regra por PORTA, não por programa: o mesmo PDV roda instalado ou pela versão
# portátil (.zip), em caminhos diferentes, e uma regra amarrada ao caminho
# silenciosamente deixaria de valer depois de uma atualização.
Get-NetFirewallRule -DisplayName $nome -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule -ErrorAction SilentlyContinue

New-NetFirewallRule -DisplayName $nome `
    -Description "Permite que caixas secundarios e o app do garcom conectem no Caixa Principal (StarChef)." `
    -Direction Inbound -Protocol TCP -LocalPort $Port `
    -Action Allow -Profile Any | Out-Null

Write-Host ""
Write-Host "Pronto: porta TCP $Port liberada para a rede local." -ForegroundColor Green
Write-Host ""

$perfil = Get-NetConnectionProfile | Where-Object { $_.IPv4Connectivity -eq "Internet" }
if ($perfil | Where-Object { $_.NetworkCategory -eq "Public" }) {
    Write-Warning "A rede desta maquina esta como PUBLICA. Recomendado mudar para PARTICULAR:"
    Write-Warning "Configuracoes -> Rede e Internet -> (sua conexao) -> Tipo de perfil de rede -> Rede particular."
}

Write-Host "Confira se o PDV esta escutando com:  netstat -ano | findstr $Port"
if (-not $NoPause) {
    Write-Host "Pressione ENTER para fechar."
    Read-Host | Out-Null
}
