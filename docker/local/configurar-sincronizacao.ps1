# Carregado por instalar.ps1; coleta os dados que identificam a loja na nuvem.
Gravar-Valor 'SYNC_ENABLED' 'true'
Gravar-Valor 'SYNC_AUTO_ENROLL' 'true'
foreach ($item in @(@('SYNC_CLOUD_API_URL','https://api.starchef.com.br'),
    @('SYNC_CLOUD_WSS_URL','wss://api.starchef.com.br/ws/sync/v1/'))) {
    if (-not (Ler-Valor $item[0])) {
        $valor = Read-Host "$($item[0]) [$($item[1])]"
        Gravar-Valor $item[0] $(if ($valor) { $valor.Trim() } else { $item[1] })
    }
}
$nome = Ler-Valor 'SYNC_NODE_NAME'
if (-not $nome -or $nome -in @('Loja StarChef','Loja Centro')) {
    $nome = Read-Host 'Nome da loja (como aparecerá na nuvem)'
    if (-not $nome) { throw 'O nome da loja é obrigatório para sincronizar.' }
    Gravar-Valor 'SYNC_NODE_NAME' $nome.Trim()
}
$uuid = '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
$conta = Ler-Valor 'SYNC_ACCOUNT_ID'
if ($conta -notmatch $uuid) {
    $conta = Read-Host 'UUID da conta StarChef na nuvem'
    if ($conta -notmatch $uuid) { throw 'Informe um UUID válido para a conta.' }
    Gravar-Valor 'SYNC_ACCOUNT_ID' $conta
}
$loja = Ler-Valor 'SYNC_STORE_ID'
if (-not $loja) {
    $loja = Read-Host 'UUID do restaurante/loja na nuvem (Enter para sincronizar a conta toda)'
    if ($loja -and $loja -notmatch $uuid) { throw 'Informe um UUID válido ou deixe vazio.' }
    if ($loja) { Gravar-Valor 'SYNC_STORE_ID' $loja }
}
foreach ($chave in @('SYNC_ENROLL_USERNAME','SYNC_ENROLL_PASSWORD')) {
    if (-not (Ler-Valor $chave)) {
        if ($chave -eq 'SYNC_ENROLL_PASSWORD') {
            $seguro = Read-Host $chave -AsSecureString
            $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro)
            try { $valor = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
            finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
        } else { $valor = Read-Host $chave }
        if (-not $valor) { throw "$chave é obrigatório para sincronizar." }
        Gravar-Valor $chave $valor
    }
}
$ticket = Ler-Valor 'SYNC_ENROLL_SECRET'
if ($ticket -notmatch '^sc-[0-9a-fA-F]{40}$') {
    Write-Host 'No Admin da nuvem, abra Sincronização > Bilhetes de matrícula > Adicionar.'
    Write-Host "Selecione a conta $conta, o restaurante (se aplicável) e use o nome '$nome'."
    Write-Host 'Salve, copie o código mostrado na confirmação e cole abaixo. Ele vale 30 minutos e uma matrícula.'
    $seguro = Read-Host 'Ticket de matrícula' -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro)
    try { $ticket = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    if ($ticket.Length -lt 24) { throw 'O ticket deve ter pelo menos 24 caracteres.' }
    Gravar-Valor 'SYNC_ENROLL_SECRET' $ticket
}
