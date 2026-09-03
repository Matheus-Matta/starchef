import difflib
from decimal import Decimal
from typing import Optional, Tuple
from apps.inbound_nfe.models import SupplierItemMapping, InboundNFeItem
from apps.menu.models import Ingredient, Product, RecipeItem


def attempt_matching(
    item: InboundNFeItem, supplier_cnpj: str, account
) -> Tuple[Optional[Ingredient], Optional[Product], Decimal, float]:
    """
    Tenta encontrar um Ingredient/Product compatível baseado nas regras da especificação:
    1. SupplierItemMapping (supplier_cnpj + supplier_code) -> confiança 1.0
    2. SupplierItemMapping (supplier_cnpj + supplier_ean)  -> confiança 1.0
    3. Product.gtin (EAN cadastrado no sistema)           -> confiança 0.95
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
        ).first()

        if mapping:
            return mapping.ingredient, mapping.product, mapping.conversion_factor, 1.0

    # 2. Matching por supplier_cnpj + supplier_ean
    if item.ean and clean_cnpj:
        mapping = SupplierItemMapping.objects.filter(
            account=account,
            supplier_cnpj=clean_cnpj,
            supplier_ean=item.ean,
        ).first()

        if mapping:
            return mapping.ingredient, mapping.product, mapping.conversion_factor, 1.0

    # 3. Matching por Product.gtin
    if item.ean:
        product = Product.objects.filter(
            account=account,
            gtin=item.ean,
            is_active=True,
        ).first()

        if product:
            # Tentar encontrar ingrediente primário vinculado via Recipe
            recipe_item = RecipeItem.objects.filter(
                recipe__product=product,
                recipe__is_active=True,
            ).select_related('ingredient').first()

            ingredient = recipe_item.ingredient if recipe_item else None
            return ingredient, product, Decimal('1'), 0.95

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
