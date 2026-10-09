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
    "imports.ImportJob": "Fila de processamento da importação, local ao nó que a recebeu; o que ela grava sincroniza pelos próprios models.",
    # O COLETOR da SEFAZ: so a nuvem consulta quando ha sincronizacao
    # (`inbound_nfe/services/sefaz_na_nuvem.py`). A nota, os itens, eventos e
    # manifestacoes viajam (`catalog_clone.py`); o cursor, a trava e a fila
    # bruta sao do coletor e nao tem uso na loja.
    "inbound_nfe.DFeGlobalConfig": "Configuracao e trava local do coletor SEFAZ.",
    "inbound_nfe.DFeSyncState": "Cursor NSU local do coletor SEFAZ.",
    "inbound_nfe.DFeDistributionDocument": "Fila bruta do coletor da SEFAZ (so a nuvem coleta); reprocessa-la na loja criaria as notas em dobro.",
}


def is_excluded(model_label):
    return model_label in EXCLUDED


def reason(model_label):
    return EXCLUDED.get(model_label, "")
