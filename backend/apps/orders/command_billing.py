"""Levar o consumo das comandas para o pedido que vai cobrar.

A comanda é um bloco de notas: ela anota e manda para a produção, sem pedido
nenhum. O pedido nasce no caixa, e é aqui que ele recebe o que os cartões
juntaram.

## Por que isto é em LOTE, e não um laço

A mesa grande que paga junto é o caso, não a exceção — e o requisito é aguentar
mais de duzentas comandas numa conta só. Um laço que abrisse um pedido por
cartão e movesse item por item faria milhares de `UPDATE` dentro de uma
transação, segurando trava em meia tabela enquanto o resto do salão espera.

Aqui são poucas consultas, independentemente de serem duas comandas ou
duzentas: uma trava, uma leitura dos pendentes, um `bulk_create`. O custo cresce
com a quantidade de ITENS, que é inevitável, e não com a de comandas.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.orders.models import CommandItem, OrderItem

#: Teto por chamada. Não é o limite do desenho — é o limite do GESTO: um caixa
#: que incluísse mil cartões de uma vez quase certamente errou a seleção, e uma
#: recusa clara é melhor que uma transação de minutos.
MAX_COMMANDS_POR_CONTA = 500


def lock_commands(command_ids):
    """Trava as comandas numa ordem estável, para dois caixas não se cruzarem.

    Ordenado por id de propósito: dois caixas fechando as mesmas mesas em
    ordens diferentes é o formato clássico de impasse no banco.
    """
    from apps.restaurants.models import Command

    ids = sorted({str(value) for value in command_ids if value})
    if not ids:
        return {}
    travadas = Command.objects.select_for_update().filter(pk__in=ids).order_by("pk")
    return {str(command.pk): command for command in travadas}


def pending_items_of(command_ids):
    """Os itens ainda PENDENTES destas comandas, numa consulta só."""
    return (
        CommandItem.objects.filter(
            command_id__in=list(command_ids),
            command_status=CommandItem.STATUS_PENDENTE,
        )
        .select_related("product")
        .order_by("command_id", "launched_at")
    )


def billable_items_of(command_ids):
    """O que há de fato A COBRAR nestas comandas.

    Pendente NÃO basta: um item cancelado ou de cortesia continua pendente na
    comanda mas não soma um centavo. Um cartão só com esses está livre na
    prática, e tratá-lo como ocupado prende a mesa e deixa o operador
    procurando uma conta que não existe.
    """
    return pending_items_of(command_ids).exclude(
        status__in=[CommandItem.STATUS_CANCELLED, CommandItem.STATUS_COMPED]
    )


def command_has_pending_items(command_id):
    """A comanda está EM USO?

    Em uso é ter o que COBRAR — não é um campo de estado, e não é a contagem
    de pendentes. Um cartão marcado como ocupado sem nada a receber não tem
    conta nenhuma, e deixá-lo entrar num pedido só produz uma venda presa a um
    cartão vazio.
    """
    return billable_items_of([command_id]).exists()


def attach_commands_to_order(*, order, command_ids, user):
    """Copia para o pedido o consumo pendente das comandas. Devolve os itens.

    Cada `CommandItem` pendente vira um `OrderItem` com `command_item`
    apontando de volta — é esse fio que, no encerramento do pedido, marca a
    anotação como concluída e esvazia o cartão.

    Repetir a chamada com a mesma comanda é inofensivo: a anotação que já tem
    item de pedido é ignorada, e a restrição no banco é quem garante isso
    mesmo com dois caixas ao mesmo tempo.
    """
    ids = [str(value) for value in dict.fromkeys(command_ids) if value]
    if not ids:
        raise ValidationError("Informe ao menos uma comanda para incluir na conta.")
    if len(ids) > MAX_COMMANDS_POR_CONTA:
        raise ValidationError(
            f"São {len(ids)} comandas numa conta só — o limite por inclusão é "
            f"{MAX_COMMANDS_POR_CONTA}. Divida a cobrança."
        )
    if order.is_locked:
        raise ValidationError("Este pedido já foi encerrado e não recebe comandas.")

    with tenant_context(order.account), transaction.atomic():
        comandas = lock_commands(ids)
        faltando = [i for i in ids if i not in comandas]
        if faltando:
            raise ValidationError("Uma das comandas não existe mais.")

        de_outro_restaurante = [
            c.number
            for c in comandas.values()
            if c.restaurant_id != order.restaurant_id
        ]
        if de_outro_restaurante:
            raise ValidationError(
                f"A comanda {de_outro_restaurante[0]} pertence a outro restaurante."
            )

        # RELER DEPOIS DA TRAVA. Conferir antes só dá a impressão de
        # impedir a corrida: entre a leitura e a escrita, outro caixa
        # cobra o mesmo cartão.
        # Só o que TEM VALOR entra na conta. O item cancelado ou de cortesia
        # continua pendente no cartão, mas levá-lo ao pedido acrescentaria uma
        # linha de R$ 0,00 que ninguém sabe explicar — ele é encerrado junto
        # com o cartão, na liberação.
        pendentes = list(billable_items_of(ids).select_for_update(of=("self",)))
        ja_cobrados = set(
            OrderItem.objects.filter(
                command_item_id__in=[p.pk for p in pendentes]
            ).values_list("command_item_id", flat=True)
        )
        novos = [p for p in pendentes if p.pk not in ja_cobrados]
        if not novos:
            vazias = [c.number for c in comandas.values()]
            raise ValidationError(
                f"Nada a cobrar: a comanda {vazias[0]} não tem item pendente."
                if len(vazias) == 1
                else "Nada a cobrar: nenhuma das comandas tem item pendente."
            )

        criados = OrderItem.objects.bulk_create(
            [_para_item_de_pedido(anotacao, order=order, user=user) for anotacao in novos]
        )
        # `bulk_create` não dispara signal, então o total do pedido não se
        # move sozinho: o caixa puxava quatro cartões e via R$ 0,00.
        #
        # Só não estourou antes porque o PDV fecha a conta (que recalcula)
        # antes de cobrar. Quem chamasse `attach-commands` e pagasse em
        # seguida — pela API, como o aplicativo faz — tentaria receber zero.
        from apps.orders.services import recalculate_order

        recalculate_order(order)

    return criados


def _para_item_de_pedido(anotacao, *, order, user):
    """O `OrderItem` que corresponde a esta anotação da comanda.

    O preço é COPIADO da anotação, nunca relido do cadastro: o cliente consumiu
    ao preço do momento do lançamento, e reler aqui faria a conta mudar porque
    o gerente reajustou o cardápio no meio do almoço.

    O estado de produção também vem junto. O prato já saiu da cozinha às 20h;
    o item que nasce no caixa às 22h não pode aparecer como pendente e mandar
    a picanha para o forno de novo.
    """
    return OrderItem(
        account=order.account,
        restaurant=order.restaurant,
        branch=order.branch,
        order=order,
        command_id=anotacao.command_id,
        command_item=anotacao,
        product_id=anotacao.product_id,
        quantity=anotacao.quantity,
        unit_price=anotacao.unit_price,
        total_price=anotacao.total_price,
        variations=anotacao.variations,
        customer_note=anotacao.customer_note,
        production_sector=anotacao.production_sector,
        status=anotacao.status,
        sent_to_kitchen_at=anotacao.sent_to_kitchen_at,
        preparation_started_at=anotacao.preparation_started_at,
        ready_at=anotacao.ready_at,
        delivered_at=anotacao.delivered_at,
        launched_by=anotacao.launched_by,
        created_by=user,
        updated_by=user,
    )


def conclude_items_of_order(order, *, when=None, billed=True):
    """Encerra na comanda tudo o que este pedido levou. Devolve quantos.

    Chamado quando o pedido TERMINA. `billed` diz POR QUE ele terminou, e essa
    distinção é o relatório: pago é VENDA, cancelado é PERDA. Um estado só para
    os dois obrigaria o fechamento do mês a adivinhar a diferença olhando o
    pedido — que pode nem existir mais.

    Nada é apagado, só marcado: é assim que o histórico do cartão sobrevive à
    reutilização, e é ele que responde "o que a comanda 13 consumiu no dia 20".
    """
    agora = when or timezone.now()
    destino = (
        CommandItem.STATUS_COBRADO if billed else CommandItem.STATUS_CANCELADO
    )
    ids = list(
        OrderItem.objects.filter(order_id=order.pk)
        .exclude(command_item__isnull=True)
        .values_list("command_item_id", flat=True)
    )
    if not ids:
        return 0
    return CommandItem.objects.filter(
        pk__in=ids, command_status=CommandItem.STATUS_PENDENTE
    ).update(
        command_status=destino,
        command_closed_at=agora,
        updated_at=agora,
    )


def total_pendente(command_id):
    """Quanto esta comanda tem a cobrar agora.

    Cancelado e cortesia continuam existindo na anotação, mas não somam.
    """
    return sum(
        (item.total_price for item in billable_items_of([command_id])),
        Decimal("0.00"),
    )


def detach_commands_from_order(*, order, command_ids, user):
    """Tira comandas da conta SEM cancelar nada. Devolve quantas anotações voltaram.

    É o desfazer do caixa: incluiu o cartão errado, ou o cliente resolveu pagar
    separado. As anotações voltam a PENDENTE e o cartão volta a ter o que
    cobrar — nada foi consumido a menos, e cancelar a conta inteira para
    corrigir uma inclusão seria caro demais para um engano de um toque.

    Só funciona enquanto o pedido está ABERTO: depois de pago ou cancelado as
    anotações já têm destino, e mexer nelas reescreveria o histórico.
    """
    ids = [str(value) for value in dict.fromkeys(command_ids) if value]
    if not ids:
        raise ValidationError("Informe a comanda a remover da conta.")
    if order.is_locked:
        raise ValidationError(
            "Este pedido já foi encerrado: as comandas dele não podem mais ser removidas."
        )

    with tenant_context(order.account), transaction.atomic():
        itens = list(
            OrderItem.objects.select_for_update(of=("self",)).filter(
                order_id=order.pk, command_id__in=ids
            )
        )
        if not itens:
            raise ValidationError("Nenhuma dessas comandas está nesta conta.")

        ja_produzidos = [i for i in itens if i.foi_para_a_producao]
        anotacoes = [i.command_item_id for i in itens if i.command_item_id]

        # O item de pedido é APAGADO, e não cancelado: ele era uma cópia da
        # anotação, e um cancelamento aqui contaria como perda no relatório
        # sem nada ter se perdido — o consumo continua vivo na comanda.
        OrderItem.objects.filter(pk__in=[i.pk for i in itens]).delete()

        CommandItem.objects.filter(pk__in=anotacoes).update(
            command_status=CommandItem.STATUS_PENDENTE,
            command_closed_at=None,
            updated_at=timezone.now(),
        )

        # A comanda volta a estar em uso: ela tem o que cobrar de novo.
        from apps.restaurants.models import Command

        Command.objects.filter(pk__in=ids, status=Command.STATUS_FREE).update(
            status=Command.STATUS_OCCUPIED, updated_at=timezone.now()
        )

    # Quem já foi para a produção volta para a comanda com o prato feito — o
    # cozinheiro não desfaz. Quem chamou decide se avisa o operador.
    return {"itens": len(anotacoes), "ja_produzidos": len(ja_produzidos)}
