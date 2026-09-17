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
_e("account", "accounts.Account", conflict_policy=CLOUD, flow="cloud_to_local")
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
   exclude_fields=("csc_token_homologation", "csc_token_production"))

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
_e("printer", "printers.Printer", conflict_policy=CLOUD, dependencies=("restaurant",),
   local_only_fields=("ip_address", "port", "is_online", "last_seen_at"))
_e("scale", "printers.Scale", conflict_policy=CLOUD, dependencies=("restaurant",),
   local_only_fields=("ip_address", "port", "serial_port", "is_online", "last_seen_at"))
_e("kds_station", "kitchen.KdsStation", conflict_policy=CLOUD, dependencies=("restaurant",))
_e("kds_column", "kitchen.KdsColumn", conflict_policy=CLOUD, dependencies=("kds_station",))
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
_e("stock_settings", "stock.StockSettings", conflict_policy=CLOUD, dependencies=("restaurant",))
_e("stock_movement", "stock.StockMovement", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("stock_location", "product"), include_in_bootstrap=False, immutable=True)

# 13-14. Pedidos, vendas e pagamentos. Nascem na loja e sobem.
_e("payment_method", "payments.PaymentMethod", conflict_policy=CLOUD, dependencies=("restaurant",))
_e("order", "orders.Order", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("restaurant", "table", "customer"), include_in_bootstrap=False)
_e("order_batch", "orders.OrderBatch", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("order",), include_in_bootstrap=False)
_e("order_item", "orders.OrderItem", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("order", "product"), include_in_bootstrap=False)
_e("order_item_addon", "orders.OrderItemAddon", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("order_item", "product_addon"), include_in_bootstrap=False)
_e("cash_register", "payments.CashRegister", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("restaurant", "cash_station"), include_in_bootstrap=False)
_e("cash_movement", "payments.CashMovement", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("cash_register",), include_in_bootstrap=False, immutable=True)
_e("payment", "payments.Payment", conflict_policy=LOJA, flow="local_to_cloud",
   dependencies=("order", "payment_method", "cash_register"), include_in_bootstrap=False)

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
