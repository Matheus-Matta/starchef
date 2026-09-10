"""
Invalidação do cache público.

O cardápio público é cacheado, então toda alteração que o cliente final
enxerga precisa derrubar aquele cache — senão o restaurante muda um preço e o
site continua vendendo pelo valor antigo por mais cinco minutos. É um erro
caro: quem paga a diferença é o restaurante.

Os sinais cobrem exatamente o que aparece no payload público: página
publicada, produto, preço, variação, adicional, categoria, disponibilidade,
horário, zona de entrega, forma de pagamento, dados do restaurante, tema e
domínio.
"""
import logging

from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from apps.menu.models import Menu, MenuItem, Product, ProductAddon, ProductCategory, ProductVariation
from apps.payments.models import PaymentMethod
from apps.restaurants.models import Branch, DeliveryZone, Restaurant
from apps.storefront.models import MenuDomain, MenuPage, MenuSite
from apps.storefront.services.cache import invalidate_domain, invalidate_for_instance, schedule_invalidation

logger = logging.getLogger("storefront.provisioning")

# Models cujo `restaurant_id` (ou a conta, quando o registro é compartilhado)
# aponta para os sites que precisam ser invalidados.
CATALOG_MODELS = (
    Product,
    ProductVariation,
    ProductAddon,
    ProductCategory,
    Menu,
    MenuItem,
    Branch,
    DeliveryZone,
    PaymentMethod,
    MenuSite,
    MenuPage,
)


def invalidate_from_catalog_change(sender, instance, **kwargs):
    """Handler único para todos os models de catálogo.

    É uma função de módulo, e não uma closure criada dentro do laço: o
    dispatcher do Django guarda os receivers por referência fraca, e uma função
    local morreria assim que o laço terminasse — os sinais simplesmente não
    disparariam, e o cache público nunca seria invalidado.
    """
    invalidate_for_instance(instance, reason=f"{kwargs.get('signal_name', 'change')}:{sender._meta.label_lower}")


for _model in CATALOG_MODELS:
    post_save.connect(
        invalidate_from_catalog_change,
        sender=_model,
        dispatch_uid=f"storefront_cache_save_{_model._meta.label_lower}",
    )
    post_delete.connect(
        invalidate_from_catalog_change,
        sender=_model,
        dispatch_uid=f"storefront_cache_delete_{_model._meta.label_lower}",
    )


@receiver(post_save, sender=Restaurant, dispatch_uid="storefront_cache_restaurant")
def invalidate_on_restaurant_change(sender, instance, **kwargs):
    """O restaurante não tem `restaurant_id`; ele *é* o restaurante."""
    schedule_invalidation(instance.id, reason="save:restaurants.restaurant")


@receiver(post_save, sender=Restaurant, dispatch_uid="storefront_provision_restaurant")
def provision_site_for_new_restaurant(sender, instance, created, **kwargs):
    """Restaurante novo em conta com E-commerce já nasce com cardápio no ar.

    Roda em `on_commit` porque o site referencia o restaurante: agendar depois
    do commit garante que a linha existe quando a criação acontecer, e evita
    que uma falha no provisionamento derrube o cadastro do restaurante — que é
    a operação que o usuário de fato pediu.

    Se o módulo for habilitado só depois, este sinal já passou; nesse caso o
    site sai por `POST /api/v1/storefront/sites/provision/` ou pelo comando
    `manage.py provision_storefronts`.
    """
    if not created or instance.deleted_at is not None:
        return

    from apps.storefront.services.provisioning import account_has_storefront, ensure_site

    if not account_has_storefront(instance.account):
        return

    def _provision():
        try:
            ensure_site(instance)
        except Exception:  # noqa: BLE001 - site é acessório; cadastro não pode falhar por causa dele
            logger.exception("Falha ao provisionar o storefront", extra={"restaurant": str(instance.id)})

    transaction.on_commit(_provision)


@receiver(m2m_changed, sender=Product.restaurants.through, dispatch_uid="storefront_cache_product_restaurants")
def invalidate_on_product_restaurants(sender, instance, action, pk_set, **kwargs):
    """Vincular/desvincular um produto de um restaurante muda o que o site lista.

    Sem este sinal, tirar um produto de uma unidade não o tirava do cardápio
    público dela até o TTL expirar — o cliente continuaria pedindo algo que a
    loja não vende mais.
    """
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    if isinstance(instance, Product):
        for restaurant_id in pk_set or []:
            schedule_invalidation(restaurant_id, reason="m2m:product.restaurants")
        invalidate_for_instance(instance, reason="m2m:product.restaurants")
    else:
        schedule_invalidation(getattr(instance, "id", None), reason="m2m:restaurant.products")


@receiver(post_save, sender=MenuDomain, dispatch_uid="storefront_cache_domain_save")
@receiver(post_delete, sender=MenuDomain, dispatch_uid="storefront_cache_domain_delete")
def invalidate_on_domain_change(sender, instance, **kwargs):
    """O mapa hostname → site tem cache próprio, com chave por hostname."""
    invalidate_domain(instance.hostname)
    invalidate_for_instance(instance, reason="domain")
