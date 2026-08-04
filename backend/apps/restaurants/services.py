"""Serviços de domínio dos cadastros base (restaurantes/mesas/comandas)."""
from django.db.models import Max
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.restaurants.models import Branch, Command

# Campos espelhados do Restaurant pra Branch. O produto trata o cadastro de
# restaurante como sendo a própria filial (não há mais de uma filial por
# restaurante na prática), então mantemos uma única Branch por Restaurant
# sincronizada automaticamente — é ela que sustenta FiscalConfig/FiscalProfile
# (únicas coisas no sistema que ainda exigem uma Branch de verdade).
_MIRRORED_RESTAURANT_FIELDS = (
    "state_registration",
    "phone",
    "email",
    "address",
    "city",
    "state",
    "zip_code",
    "default_service_fee_percent",
    "require_open_cash_register",
    "stock_deduction_timing",
    "print_settings",
    "fiscal_settings",
    "is_active",
    "deleted_at",
)


def sync_branch_for_restaurant(restaurant):
    """Garante uma única Branch por Restaurant, espelhando os campos em comum.

    Chamado pelo signal `post_save` de Restaurant (cobre criar/editar/deletar
    — soft-delete passa por `save()`, ver `TenantBaseModel.delete()`) e pelo
    comando `sync_restaurant_branches` (backfill de restaurantes já
    existentes). `all_objects`/`.first()` em vez de `get_or_create` pra não
    quebrar se algum dado antigo tiver mais de uma branch pro restaurante —
    nesse caso só atualiza a primeira, nunca cria uma segunda.
    """
    defaults = {
        "account": restaurant.account,
        "name": restaurant.trade_name,
        "cnpj": restaurant.cnpj or "",
        **{field: getattr(restaurant, field) for field in _MIRRORED_RESTAURANT_FIELDS},
    }
    branch = Branch.all_objects.filter(restaurant=restaurant).order_by("created_at").first()
    if branch is None:
        return Branch.objects.create(restaurant=restaurant, **defaults)
    # `.update()` não passa pelo `save()`, então `updated_at` (auto_now) não se
    # atualiza sozinho — seta explícito pra não ficar com timestamp parado.
    Branch.all_objects.filter(pk=branch.pk).update(updated_at=timezone.now(), **defaults)
    return branch


def next_command_number(restaurant):
    """Próximo número de comanda do restaurante (max+1), escopo por restaurante.

    Espelha `apps.orders.services.next_order_sequence`. Usa `all_objects` para
    considerar também comandas inativas/soft-deleted e não repetir números.
    """
    with tenant_context(restaurant.account):
        last = Command.all_objects.filter(restaurant=restaurant).aggregate(value=Max("number"))["value"] or 0
        return last + 1


def default_command_code(number):
    """Código escaneável padrão a partir do número (zero-padded, ex.: 1 -> "0001")."""
    return f"{int(number):04d}"
