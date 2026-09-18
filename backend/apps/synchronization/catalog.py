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
_e("restaurant", "restaurants.Restaurant", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("account",))
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
   exclude_fields=("csc_id", "csc_token", "certificate_ref"),
   # `local_fiscal_url` é o endereço do Comunicador NAQUELA máquina, como o IP
   # da impressora: a nuvem não tem como saber e não pode zerar o que o
   # técnico configurou na loja.
   local_only_fields=("local_fiscal_url",))

# 4. Funções, permissões e usuários. Sessão autenticada nunca sincroniza.
_e("permission", "accounts.Permission", conflict_policy=CLOUD, flow="cloud_to_local")
_e("role", "accounts.Role", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("account", "permission"))
_e("user", "auth.User", conflict_policy=CLOUD, flow="cloud_to_local",
   exclude_fields=("last_login",))
_e("user_profile", "accounts.UserProfile", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("user", "role", "restaurant"))

# 5. Terminais, caixas e operação.
_e("cash_station", "payments.CashStation", conflict_policy=CLOUD, dependencies=("restaurant",))
_e("pdv_terminal", "payments.PdvTerminal", conflict_policy=CLOUD, dependencies=("restaurant",))

# 6-7. Cardápio, preços e fichas técnicas.
_e("product_category", "menu.ProductCategory", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("restaurant",))
_e("product", "menu.Product", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("product_category",))
_e("product_variation", "menu.ProductVariation", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("product",))
_e("product_addon", "menu.ProductAddon", conflict_policy=CLOUD, flow="cloud_to_local",
   dependencies=("product",))
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
_e("scale", "printers.Scale", conflict_policy=CLOUD, dependencies=("restaurant",),
   local_only_fields=("port", "protocol", "agent_instance_id",
                      "agent_lease_expires_at"))
_e("kds_station", "kitchen.KdsStation", conflict_policy=CLOUD, dependencies=("restaurant",))
_e("kds_column", "kitchen.KdsColumn", conflict_policy=CLOUD, dependencies=("kds_station",))
_e("kds_item_position", "kitchen.KdsItemPosition", conflict_policy=LOJA,
   flow="local_to_cloud", dependencies=("kds_station", "kds_column", "order_item"),
   include_in_bootstrap=False)
_e("sla", "sla.ServiceLevelAgreement", conflict_policy=CLOUD, dependencies=("restaurant",),
   include_in_bootstrap=False)

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
   exclude_fields=("lot", "entry", "exit"))

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

_e("order", "orders.Order", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("restaurant", "table", "customer"),
   seed_to_local=True, essential_filter={"status__in": ABERTOS})
_e("order_batch", "orders.OrderBatch", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("order",),
   seed_to_local=True, essential_filter={"order__status__in": ABERTOS})
_e("order_item", "orders.OrderItem", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("order", "product"),
   seed_to_local=True, essential_filter={"order__status__in": ABERTOS})
_e("order_item_addon", "orders.OrderItemAddon", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("order_item", "product_addon"),
   seed_to_local=True, essential_filter={"item__order__status__in": ABERTOS})
_e("cash_register", "payments.CashRegister", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("restaurant", "cash_station"),
   seed_to_local=True, essential_filter={"status__in": CAIXA_VIVO})
# Movimento é imutável: a loja insere e nunca reescreve. Ele desce junto da
# sessão porque o saldo do caixa aberto é a soma deles — sem os movimentos, a
# sangria e o suprimento do turno sumiriam da conferência.
_e("cash_movement", "payments.CashMovement", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("cash_register",), immutable=True,
   seed_to_local=True, essential_filter={"cash_register__status__in": CAIXA_VIVO})
_e("payment", "payments.Payment", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("order", "payment_method", "cash_register"),
   seed_to_local=True, essential_filter={"order__status__in": ABERTOS})

# 15. Documentos fiscais. Conflito aqui nunca é resolvido em silêncio.
_e("invoice", "invoices.Invoice", conflict_policy=MANUAL, flow="local_to_cloud",
   dependencies=("order", "fiscal_profile"), include_in_bootstrap=False)
_e("invoice_item", "invoices.InvoiceItem", conflict_policy=MANUAL, flow="local_to_cloud",
   dependencies=("invoice",), include_in_bootstrap=False)

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
