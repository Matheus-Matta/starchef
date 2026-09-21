"""A pesagem vai para a COMANDA.

O cliente chega na balança com o cartão, passa o cartão, põe o prato — e o
valor entra na comanda dele. É o que faz o self-service por quilo funcionar de
verdade: hoje cada prato pesado vira um pedido avulso que alguém precisa pagar
na hora, o que serve para uma balança de balcão e não para quem vai pesar o
prato, sentar, pedir bebida e pagar na saída.

**O risco desta mudança é de dinheiro.** Se a balança continuar amarrada depois
da pesagem, o prato do próximo cliente cai na comanda do anterior: a pessoa vai
embora, outra chega, põe o prato sem passar o cartão — e paga o almoço de um
estranho. Por isso o vínculo expira na primeira pesagem E por tempo, o que vier
antes, e por isso a nota de pesagem imprime o número da comanda: é a única
barreira que não depende de o operador lembrar de nada.
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.printers.models import Scale
from apps.restaurants.models import Command


def _resolve_command(*, restaurant, reference):
    reference = str(reference or "").strip()
    if not reference:
        raise ValidationError("Passe o cartão da comanda na balança.")
    base = Command.objects.filter(restaurant=restaurant, is_active=True)
    command = base.filter(code=reference).first()
    if command is None and reference.isdigit():
        command = base.filter(number=int(reference)).first()
    if command is None:
        try:
            command = base.filter(pk=reference).first()
        except (ValueError, ValidationError):
            command = None
    if command is None:
        raise ValidationError(f"Comanda '{reference}' não encontrada neste restaurante.")
    return command


@transaction.atomic
def bind_command_to_scale(*, scale, reference, user=None):
    """Amarra a comanda à balança por um tempo curto (leitura do cartão)."""
    with tenant_context(scale.account):
        scale = Scale.objects.select_for_update().get(pk=scale.pk)
        command = _resolve_command(restaurant=scale.restaurant, reference=reference)
        janela = int(scale.command_binding_seconds or 60)
        scale.active_command = command
        scale.active_command_until = timezone.now() + timedelta(seconds=janela)
        scale.save(update_fields=["active_command", "active_command_until", "updated_at"])
        record_audit(
            action=AuditLog.ACTION_UPDATED,
            instance=scale,
            actor=user,
            metadata={
                "event": "scale_command_bound",
                "command": str(command.id),
                "command_number": command.number,
                "expires_at": scale.active_command_until.isoformat(),
            },
        )
        return scale


def release_command_binding(scale, *, save=True):
    """Solta o cartão. Chamado na pesagem e quando o vínculo vence."""
    scale.active_command = None
    scale.active_command_until = None
    if save:
        scale.save(update_fields=["active_command", "active_command_until", "updated_at"])
    return scale


@transaction.atomic
def consume_command_binding(scale, *, now=None):
    """Pega a comanda amarrada e JÁ solta o vínculo, sob lock.

    Consumir e soltar na mesma transação é o que impede a leitura estável
    repetida (a balança manda a mesma leitura mais de uma vez enquanto o peso
    não muda) de lançar dois itens na conta de quem já saiu.

    Devolve `None` quando não há vínculo válido — e no modo comanda isso é
    recusa, não queda para balcão.
    """
    now = now or timezone.now()
    scale = Scale.objects.select_for_update().get(pk=scale.pk)
    if not scale.active_command_id:
        return None
    if scale.active_command_until and scale.active_command_until < now:
        release_command_binding(scale)
        return None
    command = scale.active_command
    release_command_binding(scale)
    return command


@transaction.atomic
def weigh_into_command(*, scale, command, user, scale_reading):
    """Anota a pesagem NA COMANDA. Nenhum pedido é aberto.

    Antes, a primeira pesagem abria um pedido para o cartão — e era esse gesto
    que prendia a comanda a um pedido que talvez ninguém fosse pagar. Agora o
    peso vira uma anotação como qualquer outra, e o pedido só nasce no caixa.
    """
    from apps.orders.command_items import launch_item

    command = Command.objects.select_for_update().get(pk=command.pk)
    if scale_reading.order_item_id or scale_reading.command_item_id:
        raise ValidationError("Esta pesagem já foi lançada.")

    item = launch_item(
        command=command,
        product=scale.product,
        user=user,
        quantity=scale_reading.net_weight_kg,
        unit_price=scale.product.current_price,
    )
    # A leitura fica CONSUMIDA. Sem isto, a mesma pesagem poderia virar uma
    # segunda anotação — o cliente pagando duas vezes pelo mesmo corte.
    scale_reading.command_item = item
    scale_reading.save(update_fields=["command_item", "updated_at"])
    return item
