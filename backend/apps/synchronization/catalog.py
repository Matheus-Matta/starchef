"""O catálogo: cada model do sistema e a decisão tomada sobre ele.

A ordem das entradas é a ordem de carga do plano (§14.4) — conta e lojas
primeiro, documentos fiscais e histórico por último. A ordem real usada na
carga é a topológica das `dependencies`; esta lista é a que um humano lê.

Mexeu num model do domínio? Ou ele entra aqui, ou entra em `EXCLUDED` com o
motivo (ver `decisions.py`). `manage.py sync_check_registry` não deixa passar
um terceiro caminho.
"""
from apps.synchronization.constants import ConflictResolution as CR
from apps.synchronization.services.registry import SyncEntry, registry

CLOUD, LOJA, VERSAO, MANUAL = CR.CLOUD_WINS, CR.LOCAL_WINS, CR.LAST_VERSION, CR.MANUAL


def _e(entity_type, model_label, **kwargs):
    return registry.register(SyncEntry(entity_type=entity_type, model_label=model_label, **kwargs))


# 1-2. Conta, empresa, lojas e configurações gerais. Descem da nuvem.
# `plan` sai do payload porque `accounts.Plan` está em `decisions.py` — a loja
# não opera planos. Mandar a chave estrangeira sem mandar o alvo tornava o
# evento da conta IMPOSSÍVEL de aplicar: ele falhava com "Plan … ainda não
# existe aqui", retentava e falhava de novo, para sempre. A conta ficava presa
# no esqueleto "(aguardando sincronização)", inativa — e conta inativa derruba
# o isolamento por tenant do backend inteiro.
#
# O campo é nulável, então a loja fica com `plan=None`, que é exatamente o que
# "a loja não opera planos" quer dizer.
_e("account", "accounts.Account", conflict_policy=CLOUD, flow="cloud_to_local",
   exclude_fields=("plan",))
# `cash_action_password` é o hash da senha de operação do caixa. O filtro
# global de segredos já o barrava; declarar aqui é o que torna isso uma DECISÃO
# em vez de um efeito colateral do nome do campo.
# O HASH da senha de ações do caixa viaja com o restaurante.
#
# Ela estava excluída, e a exclusão não protegia nada: o MESMO hash já sai do
# servidor por `/restaurants/{id}/cash-auth/`, que é como o PDV o guarda para
# verificar sem rede. O que a exclusão fazia era deixar a LOJA sem ele — e a
# loja é justamente quem precisa autorizar sangria e cancelamento quando a
# nuvem cai, que é a razão de ela existir.
#
# Mesmo argumento do hash da senha do usuário, algumas linhas abaixo: é PBKDF2
# autocontido, não usa a `SECRET_KEY`, e já É a forma protegida da senha.
#
# O texto puro continua sem existir em lugar nenhum: `set_cash_action_password`
# codifica antes de gravar.
_e("restaurant", "restaurants.Restaurant", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("account",), allow_fields=("cash_action_password",))
_e("branch", "restaurants.Branch", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("restaurant",))

# 3. Perfis fiscais e regras tributárias.
_e("fiscal_profile", "invoices.FiscalProfile", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("account",))
_e("fiscal_config", "invoices.FiscalConfig", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("restaurant",),
   # Segredo de emissão: o CSC vai por canal próprio, cifrado (ver a memória
   # "CSC no terminal"). Ele NUNCA viaja no payload de sincronização.
   # Estes nomes precisam EXISTIR no model — havia dois aqui
   # (`csc_token_homologation`, `csc_token_production`) que nunca existiram, e
   # a exclusão mirava no vazio. O CSC só estava protegido por acidente, porque
   # `csc_token` contém "token" e o filtro global o pegava. Um teste agora
   # recusa `exclude_fields` apontando para campo inexistente.
   # O SEGREDO DE EMISSÃO NÃO VIAJA. Estes oito abrem a assinatura da nota:
   # o certificado A1 em si, a senha dele e os tokens do provedor. O CSC vai
   # por canal próprio, cifrado (ver a memória "CSC no terminal").
   exclude_fields=("csc_id", "csc_token", "certificate_ref",
                   "certificate_file", "certificate_password",
                   "provider_token", "focus_token_production",
                   "focus_token_homologation", "focus_certificate_base64",
                   "focus_certificate_password"),
   # OS TRÊS ABAIXO NÃO SÃO SEGREDO, e o filtro global os barrava só porque o
   # nome contém "certificate" — um casamento por substring.
   #
   # O buraco era silencioso, e é o pior formato: `fiscal_config` DESCE da
   # nuvem para a loja, então uma tela da loja avisando "seu certificado vence
   # em 10 dias" nunca receberia a data, e ninguém saberia por quê.
   #
   # Nenhum dos três revela a chave privada ou a senha: é uma data, um CNPJ
   # (que já viaja em `restaurant.cnpj`) e o nome do titular. A liberação é
   # NOMINAL de propósito — campo a campo, aparecendo no diff —, e
   # `CAMPOS_PROIBIDOS` continua intacto para todo o resto.
   allow_fields=("certificate_valid_until", "certificate_cnpj",
                 "certificate_name"),
   # `local_fiscal_url` é o endereço do Comunicador NAQUELA máquina, como o IP
   # da impressora: a nuvem não tem como saber e não pode zerar o que o
   # técnico configurou na loja.
   local_only_fields=("local_fiscal_url",))

# 4. Funções, permissões e usuários. Sessão autenticada nunca sincroniza.
# `permission` NÃO sincroniza — ver `decisions.py`. É catálogo global
# provisionado por código nos dois lados, com `code` único: os dois bancos
# chegam ao mesmo conteúdo sozinhos. Sincronizá-lo gerava um evento por
# permissão que era descartado na hora por não ter conta ("permission sem
# conta; evento descartado"), enchendo o log a cada `sync_permissions`.
#
# O que precisa viajar é o VÍNCULO: sem `m2m_fields`, o perfil de acesso
# chegava na loja sem permissão nenhuma, porque a serialização só olhava
# campos concretos e ManyToMany não é um deles.
_e("role", "accounts.Role", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("account",), m2m_fields={"permissions": "code"})
# O HASH da senha viaja, e só ele entre os segredos. Sem isso a loja recebia os
# usuários com o campo vazio e ninguém entrava no backend local — derrubando a
# razão de ele existir, que é operar quando a nuvem cai.
#
# O hash do Django é autocontido (`algoritmo$iterações$salt$hash`) e NÃO usa a
# `SECRET_KEY`: ela assina sessão, CSRF e token de reset, nunca a senha. Por
# isso um hash gerado na nuvem confere na loja sem nenhum retrabalho.
#
# É um alargamento de superfície consciente: o banco da loja passa a ser
# material sensível. Mas um hash PBKDF2 já É a forma protegida da senha — é
# para isso que ele existe —, e a alternativa (login sempre contra a nuvem)
# apaga o login inteiro quando a internet cai.
#
# `last_login` fica de fora por outro motivo: é do nó onde a pessoa entrou.
# `groups` e `user_permissions` são o mecanismo de acesso do Django, que este
# projeto não usa: quem manda é `accounts.Role` + `accounts.Permission` (os dois
# estão em `decisions.py` como excluídos). Ficam declarados aqui em
# `exclude_fields` para a checagem de M2M não declarado passar por DECISÃO, e
# não por esquecimento — a diferença entre as duas é invisível no código sem
# isto escrito.
_e("user", "auth.User", conflict_policy=CLOUD, flow="cloud_to_local",
   exclude_fields=("last_login", "groups", "user_permissions"),
   allow_fields=("password",))
# `specific_permissions` é acesso de verdade: permissão dada a UMA pessoa além
# das do perfil dela. Sem viajar, quem recebeu uma permissão extra na nuvem
# simplesmente não a tem na loja — e o sintoma é "o sistema não deixa", sem
# nada que explique por quê.
_e("user_profile", "accounts.UserProfile", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("user", "role", "restaurant"),
   m2m_fields={"specific_permissions": "code"})

# 5. Terminais, caixas e operação.
# `operators` é o vínculo operador <-> caixa, e sem ele a loja NÃO ABRE CAIXA:
# a abertura recusa com "O operador não está vinculado a este caixa". O caixa
# chegava (o registro sincroniza), a pessoa chegava (o usuário sincroniza) e a
# ligação entre os dois não — que é o pior formato de falha, porque tudo que
# se olha na tela parece presente.
#
# A chave natural é o `username` porque o id do usuário é um inteiro
# sequencial: ele NÃO é o mesmo nos dois bancos, e casar por ele ligaria o
# caixa à pessoa errada.
_e("cash_station", "payments.CashStation", conflict_policy=CLOUD, dependencies=("restaurant", "user"),
   m2m_fields={"operators": "username"})
_e("pdv_terminal", "payments.PdvTerminal", conflict_policy=CLOUD, dependencies=("restaurant",))

# 6-7. Cardápio, preços e fichas técnicas.
_e("product_category", "menu.ProductCategory", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("restaurant",))
# `restaurants` decide em QUAIS lojas o produto existe. Sem viajar, o produto
# desce e não aparece em loja nenhuma.
_e("product", "menu.Product", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("product_category", "restaurant"),
   m2m_fields={"restaurants": "id"})
_e("product_unit_conversion", "menu.ProductUnitConversion", conflict_policy=CLOUD,
   flow="cloud_to_local", dependencies=("product",))
_e("product_variation", "menu.ProductVariation", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("product",))
_e("product_addon", "menu.ProductAddon", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("product",),
   m2m_fields={"products": "id"})
_e("ingredient", "menu.Ingredient", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("restaurant",), include_in_bootstrap=False)
_e("recipe", "menu.Recipe", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("product",), include_in_bootstrap=False)
_e("recipe_item", "menu.RecipeItem", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("recipe", "ingredient"), include_in_bootstrap=False)
_e("menu_catalog", "menu.Menu", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("restaurant",), include_in_bootstrap=False)
_e("menu_item", "menu.MenuItem", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("menu_catalog", "product"), include_in_bootstrap=False)

# 8-9. Impressoras, balanças e periféricos. `local_only_fields` protege o que
# só a loja sabe: o IP da impressora e a porta da balança mudam na loja.
# Os nomes aqui precisam EXISTIR no model. Estavam errados: protegiam
# `ip_address`, `is_online`, `last_seen_at` e `serial_port`, que nunca
# existiram nestes models — enquanto `host` e `endpoint`, o endereço REAL da
# impressora, viajavam e eram sobrescritos pela nuvem a cada sincronização.
# Exatamente o que o comentário abaixo jurava impedir.
_e("printer", "printers.Printer", conflict_policy=CLOUD, dependencies=("restaurant",),
   local_only_fields=("host", "port", "endpoint"))
# Na balança, além do endereço, a posse do agente: `agent_instance_id` e
# `agent_lease_expires_at` dizem QUAL processo daquela loja está segurando a
# balança agora. A nuvem não tem como saber e sobrescrever derruba a leitura.
# `active_command`/`active_command_until` NÃO viajam: eles são o cartão que
# está encostado NAQUELA balança, agora. Sincronizá-los deixaria o sync
# ressuscitar na loja o cartão de um cliente que já foi embora — e o prato do
# próximo cairia na conta dele. `weighing_mode` e `command_binding_seconds`
# são configuração e sincronizam normalmente.
_e("scale", "printers.Scale", conflict_policy=CLOUD, dependencies=("restaurant",),
   exclude_fields=("active_command", "active_command_until"),
   local_only_fields=("port", "protocol", "agent_instance_id",
                      "agent_lease_expires_at"))
_e("kds_station", "kitchen.KdsStation", conflict_policy=CLOUD, dependencies=("restaurant",))
_e("kds_column", "kitchen.KdsColumn", conflict_policy=CLOUD, dependencies=("kds_station",))
_e("kds_item_position", "kitchen.KdsItemPosition", conflict_policy=LOJA,
   flow="local_to_cloud", dependencies=("kds_station", "kds_column", "order_item"),
   include_in_bootstrap=False)
# Os três M2M são o ESCOPO do acordo: sem eles o SLA desce valendo para nada.
_e("sla", "sla.ServiceLevelAgreement", conflict_policy=CLOUD,
   dependencies=("restaurant", "kds_station", "kds_column"),
   include_in_bootstrap=False,
   m2m_fields={"restaurants": "id", "stations": "id", "columns": "id"})

# 10. Salão.
_e("table_sector", "restaurants.TableSector", conflict_policy=CLOUD, dependencies=("restaurant",))
_e("table", "restaurants.Table", conflict_policy=CLOUD, dependencies=("table_sector",))
_e("command", "restaurants.Command", conflict_policy=LOJA, dependencies=("restaurant",))
_e("delivery_zone", "restaurants.DeliveryZone", conflict_policy=CLOUD, dependencies=("restaurant",),
   include_in_bootstrap=False)
_e("deliveryman", "restaurants.Deliveryman", conflict_policy=CLOUD, dependencies=("restaurant",),
   include_in_bootstrap=False)

# 11. Clientes: os dois lados cadastram, então vence a maior versão e o empate
# vai para revisão.
_e("customer", "customers.Customer", conflict_policy=VERSAO, dependencies=("account",))
_e("customer_address", "customers.CustomerAddress", conflict_policy=VERSAO,
   dependencies=("customer",))

# 12. Estoque. Movimento é imutável: o destino insere e nunca reescreve.
_e("stock_location", "stock.StockLocation", conflict_policy=CLOUD, dependencies=("restaurant",))
_e("stock_supplier", "stock.Supplier", conflict_policy=CLOUD, dependencies=("account",),
   include_in_bootstrap=False)
# `default_label_template` sai do payload: `StockLabelTemplate` é modelo de
# etiqueta da impressora daquela loja e não sincroniza. Mandar a chave sem o
# alvo travaria o evento em "ainda não existe aqui", para sempre.
_e("stock_settings", "stock.StockSettings", conflict_policy=CLOUD,
   dependencies=("restaurant",), exclude_fields=("default_label_template",))
# `lot`, `entry` e `exit` saem do payload. Os três apontam para modelos que
# `decisions.py` exclui de propósito — lote é derivado dos próprios movimentos,
# e entrada/saída são documentos de rascunho. Como o movimento sobe para a
# NUVEM, mandar essas chaves fazia a nuvem falhar ao aplicar e o movimento de
# estoque da loja nunca chegar lá. Os três aceitam nulo, e o que importa —
# produto, local e quantidade — continua viajando.
_e("stock_movement", "stock.StockMovement", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("stock_location", "product"), include_in_bootstrap=False, immutable=True,
   exclude_fields=("lot", "entry", "exit", "nfe", "nfe_item", "receipt",
                   "receipt_item", "inventory_lot"))

# 13-14. Pedidos, vendas e pagamentos. Nascem na loja e sobem.
_e("payment_method", "payments.PaymentMethod", conflict_policy=CLOUD, dependencies=("restaurant",))
# Estas entidades nascem na loja e sobem no dia a dia (`local_to_cloud`), mas
# uma loja que está ASSUMINDO a operação começa com o banco vazio: sem descer,
# ela herda as mesas ocupadas sem nenhuma comanda para atender e os terminais
# sem a sessão de caixa que já está em turno. `seed_to_local` abre essa exceção.
#
# `essential_filter` separa as duas cargas:
#   • "Dados essenciais" leva só o que está ABERTO — o suficiente para atender.
#   • "Sincronizar tudo" traz o histórico inteiro da conta, sem filtro.
ABERTOS = ["open", "awaiting_payment"]
CAIXA_VIVO = ["pending_opening", "open", "blocked",
              "pending_manager_approval", "pending_closing"]

# ── A VENDA VIAJA NOS DOIS SENTIDOS ────────────────────────────────────────
#
# Estas entidades eram de mão única (`local_to_cloud`), e estava certo: só a
# loja atendia, então a venda nascia lá e subia para a nuvem ver. Não havia
# caminho de volta porque não havia venda nascendo na nuvem.
#
# Deixou de ser verdade. O terminal agora desvia para a nuvem quando a loja
# está comprovadamente fora (`CloudFallback` nos dois PDVs), e o que ele grava
# lá precisa DESCER quando a loja voltar. Sem isto o evento nem é gerado — o
# portão de `outbox._deve_gerar` recusa na origem —, e a venda fica presa na
# nuvem para sempre: o salão volta e nunca vê aquele pedido.
#
# O conflito não fica mais frouxo por causa disso. Os dois nós nunca escrevem o
# mesmo registro ao mesmo tempo (quando a nuvem escreve, a loja está fora), e
# as faixas de numeração (`orders/sequence_ranges.py`) garantem que os
# registros dos dois lados não colidem em número. `LOJA` continua sendo o
# desempate quando as versões empatam.
#
# Fiscal e caixa NÃO entram aqui, e não é esquecimento: eles não desviam
# (`CloudFallback.caminhosQueNuncaDesviam`), então não há o que descer.
_e("order", "orders.Order", conflict_policy=LOJA, flow="both",
   dependencies=("restaurant", "table", "customer"),
   seed_to_local=True, essential_filter={"status__in": ABERTOS})
_e("order_batch", "orders.OrderBatch", conflict_policy=LOJA, flow="both",
   dependencies=("order",),
   seed_to_local=True, essential_filter={"order__status__in": ABERTOS})
_e("order_item", "orders.OrderItem", conflict_policy=LOJA, flow="both",
   # `command` é a comanda de onde o item veio, copiada no lançamento: um
   # pedido que paga 200 cartões responde "quais estão nesta conta" sem visitar
   # 200 anotações.
   dependencies=("order", "product", "command"),
   seed_to_local=True, essential_filter={"order__status__in": ABERTOS})
_e("order_item_addon", "orders.OrderItemAddon", conflict_policy=LOJA, flow="both",
   dependencies=("order_item", "product_addon"),
   seed_to_local=True, essential_filter={"item__order__status__in": ABERTOS})
# A COMANDA COMO BLOCO DE NOTAS. Ela anota o consumo sem pedido nenhum, e o
# pedido só nasce no caixa — então a anotação precisa descer na carga
# essencial por conta própria: uma loja que assume a operação herda cartões
# com consumo em aberto, e sem isto o garçom encontra a mesa vazia.
#
# Só o PENDENTE desce. O histórico do cartão fica na nuvem: ele é grande (todo
# almoço de todo cliente) e a loja não precisa dele para atender.
PENDENTE_NA_COMANDA = {"command_status": "pending"}

# ORDEM DE CARGA: `command_batch` depende de `command`; `command_item` das
# duas. Errar a ordem não quebra teste nenhum — quebra a carga inicial de uma
# loja nova, com "ainda não existe aqui" em retentativa eterna.
_e("command_batch", "orders.CommandBatch", conflict_policy=LOJA, flow="both",
   dependencies=("command",),
   seed_to_local=True,
   essential_filter={"items__command_status": "pending"})
_e("command_item", "orders.CommandItem", conflict_policy=LOJA, flow="both",
   # `table` é o retrato de onde o item foi consumido, e a comanda anda pelo
   # salão: a dependência é real, não decorativa.
   dependencies=("command", "product", "command_batch", "table"),
   seed_to_local=True, essential_filter=PENDENTE_NA_COMANDA)
# A CHAVE DE IDEMPOTÊNCIA ATRAVESSA OS NÓS.
#
# Ela já foi excluída daqui, com a razão "vale só no nó que atendeu" — e era
# verdade enquanto UM nó atendia. Deixou de ser: quando a loja cai, o terminal
# desvia para a nuvem, e o mesmo gesto pode ser tentado nos dois lugares.
#
# Sem isto, a loja volta, a fila do terminal reenvia a operação que a NUVEM já
# executou, e a loja não reconhece a chave — porque nunca a viu. Vira uma
# segunda venda, um segundo pagamento, um segundo envio à cozinha.
#
# A impressão digital (`request_fingerprint`) é método + caminho + corpo: ela é
# IDÊNTICA nos dois nós, e é o que faz a mesma chave reconhecer a mesma
# operação do outro lado.
#
# `immutable` porque o registro nasce pronto e nunca muda: ele é a resposta já
# produzida. Reescrevê-lo seria trocar a resposta de uma operação encerrada.
_e("idempotency_record", "core.IdempotencyRecord", conflict_policy=LOJA,
   flow="bidirectional", dependencies=("account",), immutable=True,
   # Não desce na carga inicial: uma loja nova não tem operação pendente para
   # deduplicar, e o histórico de chaves é grande e sem uso lá.
   seed_to_local=False)
_e("cash_register", "payments.CashRegister", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("restaurant", "cash_station"),
   seed_to_local=True, essential_filter={"status__in": CAIXA_VIVO})
# O movimento de caixa NÃO é append-only, e dizer que era custava dinheiro.
#
# Ele foi declarado `immutable=True` com a frase "a loja insere e nunca
# reescreve". A frase descreve um livro-razão; o model não é um. Ele tem ciclo
# de vida:
#
#     pending  ──(o gerente aprova a sangria)──►  approved
#     approved ──(o recebimento é cancelado)───►  cancelled
#
# Com `immutable`, o destino insere e nunca atualiza: as duas setas morriam na
# chegada. E o saldo é `Sum(amount)` sobre `status="approved"`, então o efeito
# era aritmético — **a nuvem fechava o turno com um valor diferente do da
# loja, sempre para o mesmo lado**: a sangria aprovada continuava `pending` lá
# (dinheiro a mais na conferência) e a venda estornada continuava `approved`
# (dinheiro a mais de novo).
#
# O que protege contra reescrita não é o `immutable`, é a ordem de versão:
# `conflicts.decide` IGNORA um evento cuja versão seja anterior à local, e a
# entidade é de mão única (`local_to_cloud`), então a nuvem nunca empurra nada
# para baixo. Um evento atrasado não ressuscita um movimento cancelado — há
# teste para isso em `test_movimento_de_caixa_sincroniza.py`.
#
# Ele desce junto da sessão porque o saldo do caixa aberto é a soma deles —
# sem os movimentos, a sangria e o suprimento do turno sumiriam da conferência.
_e("cash_movement", "payments.CashMovement", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("cash_register",),
   seed_to_local=True, essential_filter={"cash_register__status__in": CAIXA_VIVO})
_e("payment", "payments.Payment", conflict_policy=LOJA, flow="both",
   dependencies=("order", "payment_method", "cash_register"),
   seed_to_local=True, essential_filter={"order__status__in": ABERTOS})

# 15. Documentos fiscais. Conflito aqui nunca é resolvido em silêncio.
# A NOTA dos pedidos abertos desce junto com eles, e a razão é mais forte que
# imprimir o DANFE: é NÃO EMITIR DUAS VEZES. Se a loja assume um pedido que já
# teve NFC-e emitida na nuvem e não sabe disso, ela emite outra — e documento
# fiscal em duplicidade não se apaga, só se cancela, um a um, dentro do prazo.
#
# `MANUAL` continua valendo: a nota entra na semeadura porque ainda não existe
# na loja, mas uma divergência posterior vira SyncConflict para uma pessoa
# decidir. Documento fiscal nunca se resolve em silêncio (§15).
_e("invoice", "invoices.Invoice", conflict_policy=MANUAL, flow="local_to_cloud",
   dependencies=("order", "fiscal_profile"),
   seed_to_local=True, essential_filter={"order__status__in": ABERTOS})
_e("invoice_item", "invoices.InvoiceItem", conflict_policy=MANUAL, flow="local_to_cloud",
   dependencies=("invoice",),
   seed_to_local=True, essential_filter={"invoice__order__status__in": ABERTOS})

# 16. Produção e periféricos em uso.
_e("print_job", "printers.PrintJob", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("printer",), include_in_bootstrap=False)
_e("scale_reading", "printers.ScaleReading", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("scale",), include_in_bootstrap=False, immutable=True)

# 17. Auditoria: append-only.
_e("audit_log", "core.AuditLog", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("account",), include_in_bootstrap=False, immutable=True)
_e("command_log", "restaurants.CommandMovementLog", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("command",), include_in_bootstrap=False, immutable=True)

# 18. Metadados de anexo. O binário vai por HTTPS em chunks (ver services/files.py).
_e("image", "images.Image", conflict_policy=CLOUD, dependencies=("account",),
   include_in_bootstrap=False)
_e("product_image", "images.ProductImage", conflict_policy=CLOUD,
   dependencies=("image", "product"), include_in_bootstrap=False)
