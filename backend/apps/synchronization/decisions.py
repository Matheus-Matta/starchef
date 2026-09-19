"""Os models que NÃO sincronizam, e por quê.

Existir aqui é uma decisão tomada, igual a existir no `catalog.py`. O que não
está em nenhum dos dois é um model novo cuja decisão ninguém tomou — e é
exatamente isso que `manage.py sync_check_registry` reprova no deploy.

Sem essa lista, a falha aparece meses depois: alguém cria um model, ninguém
percebe que ele ficou de fora, e a loja opera com um cadastro que a nuvem não
conhece.
"""

#: "app_label.ModelName" -> motivo da exclusão.
EXCLUDED = {
    # §14.5 — infraestrutura do próprio Django e da fila.
    "admin.LogEntry": "Log do /admin de cada instalação; não é dado de negócio.",
    "contenttypes.ContentType": "Tabela interna do Django, recriada por migration.",
    "auth.Permission": "Permissão do Django; o catálogo real é accounts.Permission.",
    "auth.Group": "Não usado — o agrupamento de acesso é accounts.Role.",
    "sessions.Session": "Sessão autenticada nunca sincroniza (§14.6).",
    "token_blacklist.OutstandingToken": "Token ativo é local por instalação.",
    "token_blacklist.BlacklistedToken": "Idem: revogação vale no nó que a emitiu.",
    # Tabelas da própria sincronização: sincronizá-las seria um laço.
    "synchronization.SyncNode": "Tabela interna da sincronização (§14.5).",
    "synchronization.SyncEvent": "Tabela interna da sincronização (§14.5).",
    "synchronization.SyncRun": "Tabela interna da sincronização (§14.5).",
    "synchronization.SyncConflict": "Tabela interna da sincronização (§14.5).",
    "synchronization.SyncFileTransfer": "Tabela interna da sincronização (§14.5).",
    "synchronization.SyncDirty": "Tabela interna da sincronização (§14.5)."
    ,
    # Credencial de matrícula. Sincronizá-la mandaria para a LOJA o hash do
    # bilhete de todas as outras — e o bilhete é justamente o que autoriza
    # uma instalação nova a existir.
    "synchronization.SyncEnrollmentTicket": "Credencial de matrícula; nasce e morre na nuvem.",
    # Plataforma/SaaS: vive só na nuvem, a loja não precisa nem pode alterar.
    "accounts.Plan": "Cadastro da plataforma; a loja não opera planos.",
    "accounts.Permission": (
        "Catálogo global provisionado por código nos dois lados (`code` é "
        "único): os bancos chegam ao mesmo conteúdo sozinhos. O que viaja é o "
        "VÍNCULO com o perfil, em `role.m2m_fields`."
    ),
    "accounts.Subscription": "Faturamento da conta, exclusivo da nuvem.",
    "accounts.GlobalSystemConfig": "Configuração global da plataforma.",
    "accounts.FirstAccessState": "Estado de onboarding, por instalação.",
    "accounts.PasswordResetRequest": "Token de recuperação, curto e por instalação.",
    "accounts.FocusNfeConfig": "Credencial de emissor: canal próprio, cifrado.",
    "accounts.CosmosConfig": "Credencial de integração: canal próprio, cifrado.",
    # Efêmero ou derivado: reconstruído no destino, não vale a banda.
    "notifications.Notification": "Aviso de tela, efêmero e por instalação.",
    "core.IdempotencyRecord": "Deduplicação de request HTTP: vale só no nó que atendeu.",
    "stock.StockEntry": "Documento de rascunho; o que vale é stock.StockMovement.",
    "stock.StockEntryItem": "Item de rascunho de entrada.",
    "stock.StockExit": "Documento de rascunho; o que vale é stock.StockMovement.",
    "stock.StockExitItem": "Item de rascunho de saída.",
    "stock.StockAllocation": "Reserva derivada do lote, recalculada no destino.",
    "stock.StockLot": "Derivado dos movimentos; recalculado a partir deles.",
    "stock.StockLabelTemplate": "Modelo de etiqueta local da impressora da loja.",
    # A captura fiscal de entrada e por no. Dois backends podem consultar a
    # mesma SEFAZ; replicar cursores, XML bruto e projecoes locais criaria
    # duplicidade e disputa de estado. O efeito duravel que viaja e o
    # stock.StockMovement, registrado no catalogo.
    "inbound_nfe.DFeGlobalConfig": "Configuracao e trava local do coletor SEFAZ.",
    "inbound_nfe.DFeSyncState": "Cursor NSU local do coletor SEFAZ.",
    "inbound_nfe.DFeDistributionDocument": "Documento bruto reobtido da SEFAZ por cada no.",
    "inbound_nfe.InboundNFe": "Projecao local do documento fiscal obtido da SEFAZ.",
    "inbound_nfe.InboundNFeItem": "Item da projecao local da NF-e de entrada.",
    "inbound_nfe.NFeEvent": "Evento fiscal reobtido da SEFAZ por cada no.",
    "inbound_nfe.NFeIssue": "Pendencia operacional local da importacao fiscal.",
    "inbound_nfe.NFeManifestation": "Fila local de manifestacao perante a SEFAZ.",
    "inbound_nfe.SupplierItemMapping": "Aprendizado local derivado da conciliacao da NF-e.",
    "stock.GoodsReceipt": "Projecao local do recebimento; o movimento de estoque e o livro sincronizado.",
    "stock.GoodsReceiptItem": "Detalhe local do recebimento fiscal.",
    "stock.InventoryLot": "Projecao FEFO local derivada do recebimento e dos movimentos.",
    # Patrimonio depende diretamente das projecoes fiscais locais acima. Ate
    # existir um contrato proprio, replica-lo deixaria FKs apontando para alvos
    # que deliberadamente nao viajam.
    "assets.Asset": "Registro operacional local ligado ao recebimento fiscal nao sincronizado.",
    "assets.AssetLocationHistory": "Historico local do patrimonio.",
    "assets.AssetDisposal": "Baixa local do patrimonio.",
}


def is_excluded(model_label):
    return model_label in EXCLUDED


def reason(model_label):
    return EXCLUDED.get(model_label, "")
