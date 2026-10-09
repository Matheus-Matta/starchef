"""O que faltava para a loja ser um clone: estoque detalhado, nota de entrada
e patrimônio.

Ficavam fora com o argumento de que eram rascunho, derivado ou "local da
loja". Com a loja e a nuvem atendendo, o que um lado registra o outro precisa
ver: a entrada lançada no painel da nuvem, o lote que a loja consumiu, a nota
que a nuvem baixou da SEFAZ.

A NOTA DE ENTRADA é baixada só pela nuvem quando há sincronização
(`inbound_nfe/services/sefaz_na_nuvem.py`): com os dois lados consultando a
SEFAZ, a mesma nota nasceria duas vezes, com ids diferentes. O documento bruto
da distribuição (`DFeDistributionDocument`) continua fora — ele é a fila de
processamento do coletor, e processá-lo de novo na loja criaria as notas em
dobro.

CICLO: o item da nota aponta o movimento de estoque que ele gerou, e o
movimento aponta o item. O movimento declara o item como dependência; o item
NÃO declara o movimento. Na carga, o item chega antes e espera o movimento
como dependência ausente — `retry.acordar_quem_espera_dependencia` o aplica
assim que o movimento entra.

Nada daqui entra na carga ESSENCIAL (a que abre a loja): são histórico e
documento, e quase tudo depende de insumo e lote, que também ficam fora dela.
Chegam no "sincronizar tudo" e, no dia a dia, evento a evento.
"""
from apps.synchronization.constants import ConflictResolution as CR
from apps.synchronization.services.registry import SyncEntry, registry

NUVEM, LOJA = CR.CLOUD_WINS, CR.LOCAL_WINS


def _e(entity_type, model_label, **kwargs):
    return registry.register(SyncEntry(entity_type=entity_type, model_label=model_label, **kwargs))


# Estoque: documentos e lotes.
_e("stock_label_template", "stock.StockLabelTemplate", conflict_policy=NUVEM,
   dependencies=("restaurant",))
_e("stock_entry", "stock.StockEntry", conflict_policy=LOJA,
   dependencies=("stock_location",), include_in_bootstrap=False)
_e("stock_entry_item", "stock.StockEntryItem", conflict_policy=LOJA,
   dependencies=("stock_entry", "ingredient", "stock_supplier"), include_in_bootstrap=False)
_e("stock_lot", "stock.StockLot", conflict_policy=LOJA,
   dependencies=("ingredient", "stock_location", "stock_entry_item"), include_in_bootstrap=False)
_e("stock_exit", "stock.StockExit", conflict_policy=LOJA,
   dependencies=("stock_location",), include_in_bootstrap=False)
_e("stock_exit_item", "stock.StockExitItem", conflict_policy=LOJA,
   dependencies=("stock_exit", "ingredient"), include_in_bootstrap=False)
_e("stock_allocation", "stock.StockAllocation", conflict_policy=LOJA,
   dependencies=("stock_exit_item", "stock_lot"), include_in_bootstrap=False)

# Nota de entrada (SEFAZ), baixada pela nuvem.
_e("inbound_nfe", "inbound_nfe.InboundNFe", conflict_policy=NUVEM,
   dependencies=("restaurant",), include_in_bootstrap=False)
_e("inbound_nfe_item", "inbound_nfe.InboundNFeItem", conflict_policy=NUVEM,
   dependencies=("inbound_nfe", "ingredient", "product"), include_in_bootstrap=False)
_e("nfe_event", "inbound_nfe.NFeEvent", conflict_policy=NUVEM,
   dependencies=("inbound_nfe",), include_in_bootstrap=False)
_e("nfe_issue", "inbound_nfe.NFeIssue", conflict_policy=NUVEM,
   dependencies=("inbound_nfe",), include_in_bootstrap=False)
_e("nfe_manifestation", "inbound_nfe.NFeManifestation", conflict_policy=NUVEM,
   dependencies=("inbound_nfe",), include_in_bootstrap=False)
_e("supplier_item_mapping", "inbound_nfe.SupplierItemMapping", conflict_policy=NUVEM,
   dependencies=("ingredient", "product"), include_in_bootstrap=False)

# Recebimento da mercadoria e lote de validade (FEFO).
_e("goods_receipt", "stock.GoodsReceipt", conflict_policy=LOJA,
   dependencies=("inbound_nfe", "stock_location"), include_in_bootstrap=False)
_e("goods_receipt_item", "stock.GoodsReceiptItem", conflict_policy=LOJA,
   dependencies=("goods_receipt", "inbound_nfe_item", "product"), include_in_bootstrap=False)
_e("inventory_lot", "stock.InventoryLot", conflict_policy=LOJA,
   dependencies=("product", "inbound_nfe", "goods_receipt", "goods_receipt_item",
                 "stock_location"), include_in_bootstrap=False)

# Patrimônio. O `qr_code_token` é a etiqueta colada no bem, não credencial: o
# filtro de segredos o barraria pelo nome, e sem ele o bem chega sem etiqueta
# e a chave única do token vazio recusa o segundo.
_e("asset", "assets.Asset", conflict_policy=LOJA,
   dependencies=("product", "inbound_nfe", "inbound_nfe_item", "goods_receipt",
                 "stock_location", "nfe_event"),
   allow_fields=("qr_code_token",), include_in_bootstrap=False)
_e("asset_location_history", "assets.AssetLocationHistory", conflict_policy=LOJA,
   dependencies=("asset", "stock_location"), include_in_bootstrap=False)
_e("asset_disposal", "assets.AssetDisposal", conflict_policy=LOJA,
   dependencies=("asset",), include_in_bootstrap=False)
