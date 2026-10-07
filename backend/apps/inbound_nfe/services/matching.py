import difflib
from decimal import Decimal
from typing import Optional, Tuple
from apps.inbound_nfe.models import SupplierItemMapping, InboundNFeItem
from django.db.models import Q

from apps.core.tenant import tenant_context

from apps.menu.models import Ingredient, Product, RecipeItem

# Aprendizado que aponta para cadastro EXCLUÍDO não vale: religaria a nota nova
# a um produto/insumo que já não existe na tela (exclusão é só `deleted_at`).
_ALVO_VIVO = (Q(product__isnull=True) | Q(product__deleted_at__isnull=True)) & (
    Q(ingredient__isnull=True) | Q(ingredient__deleted_at__isnull=True)
)


def ean_valido(valor):
    """O EAN/GTIN da nota, só se for um código de verdade.

    A nota traz "SEM GTIN" para mercadoria sem código; casar por isso
    vincularia tudo que não tem código ao mesmo produto.
    """
    codigo = (valor or "").strip()
    return codigo if codigo.isdigit() and len(codigo) in (8, 12, 13, 14) else ""


def guardar_ean_da_nota(product, ean):
    """Vínculo manual ensina o EAN ao produto que ainda não tem nenhum.

    Nunca sobrescreve um EAN existente, e não grava o que outro produto da
    conta já usa: `ean` é único na conta, e o conflito derrubaria o vínculo.
    """
    codigo = ean_valido(ean)
    if not codigo or product.ean or product.gtin == codigo:
        return False
    em_uso = Product.all_objects.filter(
        account_id=product.account_id, ean=codigo, deleted_at__isnull=True,
    ).exclude(pk=product.pk).exists()
    if em_uso:
        return False
    product.ean = codigo
    product.save(update_fields=["ean", "updated_at"])
    return True


def attempt_matching(
    item: InboundNFeItem, supplier_cnpj: str, account
) -> Tuple[Optional[Ingredient], Optional[Product], Decimal, float]:
    """Ver `_attempt_matching`. Roda no contexto da conta da nota.

    Os managers daqui filtram pela conta do contexto e devolvem VAZIO sem ela.
    Numa requisição o middleware abre o contexto; na importação em segundo
    plano (sincronização com a SEFAZ) ninguém abria, e o aprendizado do
    fornecedor e o EAN nunca achavam nada.
    """
    with tenant_context(account):
        return _attempt_matching(item, supplier_cnpj, account)


def _attempt_matching(
    item: InboundNFeItem, supplier_cnpj: str, account
) -> Tuple[Optional[Ingredient], Optional[Product], Decimal, float]:
    """
    Tenta encontrar um Ingredient/Product compatível baseado nas regras da especificação:
    1. SupplierItemMapping (supplier_cnpj + supplier_code) -> confiança 1.0
    2. SupplierItemMapping (supplier_cnpj + supplier_ean)  -> confiança 1.0
    3. EAN do produto (`ean` ou `gtin`), sem ambiguidade   -> confiança 1.0
    4. Similaridade de descrição (Fuzzy Matching)         -> confiança baseada no score

    Retorna tupla: (Ingredient, Product, conversion_factor, confidence_score)
    """
    clean_cnpj = (supplier_cnpj or "").strip()

    # 1. Matching por supplier_cnpj + supplier_code
    if item.supplier_code and clean_cnpj:
        mapping = SupplierItemMapping.objects.filter(
            account=account,
            supplier_cnpj=clean_cnpj,
            supplier_code=item.supplier_code,
        ).filter(_ALVO_VIVO).first()

        if mapping:
            return mapping.ingredient, mapping.product, mapping.conversion_factor, 1.0

    # 2. Matching por supplier_cnpj + supplier_ean
    if item.ean and clean_cnpj:
        mapping = SupplierItemMapping.objects.filter(
            account=account,
            supplier_cnpj=clean_cnpj,
            supplier_ean=item.ean,
        ).filter(_ALVO_VIVO).first()

        if mapping:
            return mapping.ingredient, mapping.product, mapping.conversion_factor, 1.0

    # 3. EAN da nota igual ao do cadastro: é o MESMO produto, e vincula sozinho
    # (antes 0,95, que nunca passava do corte de 1,0). Procura em `ean`, que é
    # o campo usado pelo PDV, e no antigo `gtin`. Mais de um candidato não
    # vincula: estoque no produto errado é pior que um clique a mais.
    codigo = ean_valido(item.ean)
    if codigo:
        candidatos = list(
            Product.objects.filter(account=account, is_active=True)
            .filter(Q(ean=codigo) | Q(gtin=codigo))[:2]
        )
        product = candidatos[0] if len(candidatos) == 1 else None

        if product:
            # Tentar encontrar ingrediente primário vinculado via Recipe
            recipe_item = RecipeItem.objects.filter(
                recipe__product=product,
                recipe__is_active=True,
            ).select_related('ingredient').first()

            ingredient = recipe_item.ingredient if recipe_item else None
            return ingredient, product, Decimal('1'), 1.0

    # 4. Similaridade de descrição (Fuzzy Matching)
    if item.description:
        desc_clean = item.description.lower().strip()
        best_ingredient = None
        best_product = None
        best_score = 0.0

        # Comparar com ingredientes ativos
        for ingredient in Ingredient.objects.filter(account=account, is_active=True):
            score = difflib.SequenceMatcher(None, desc_clean, ingredient.name.lower().strip()).ratio()
            if score > best_score:
                best_score = score
                best_ingredient = ingredient
                best_product = None

        # Comparar também com produtos ativos
        for product in Product.objects.filter(account=account, is_active=True):
            score = difflib.SequenceMatcher(None, desc_clean, product.name.lower().strip()).ratio()
            if score > best_score:
                best_score = score
                best_product = product
                # Tentar achar ingrediente da receita
                recipe_item = RecipeItem.objects.filter(
                    recipe__product=product,
                    recipe__is_active=True,
                ).select_related('ingredient').first()
                best_ingredient = recipe_item.ingredient if recipe_item else None

        if best_score >= 0.6:
            return best_ingredient, best_product, Decimal('1'), round(best_score, 2)

    return None, None, Decimal('1'), 0.0


def apply_mapping_to_item(item: InboundNFeItem, supplier_cnpj: str):
    """
    Busca o mapeamento e aplica automaticamente no item se houver correspondência exata (1.0).
    """
    ingredient, product, conversion_factor, score = attempt_matching(
        item, supplier_cnpj, item.account
    )

    if score >= 1.0 and (product or ingredient):
        item.ingredient = ingredient
        item.product = product
        item.conversion_factor = conversion_factor
        item.save(update_fields=['ingredient', 'product', 'conversion_factor'])
