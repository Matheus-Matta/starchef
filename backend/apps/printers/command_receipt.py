"""A conferência da comanda — o papel que o cliente pede antes de pagar.

**Não é documento fiscal.** A nota é uma só, do pedido que cobrar a conta; isto
aqui é a resposta a "e a comanda 13, quanto deu?" numa mesa que vai pagar
junto. O cupom diz isso em letras, para ninguém guardar o papel errado.
"""
from django.core.exceptions import ValidationError

from apps.core.tenant import tenant_context
from apps.orders.command_billing import total_pendente
from apps.orders.command_items import open_items_of_command

TYPE_TABLE_BILL = "table_bill"


def register_command_receipt(*, command, user):
    """Enfileira a impressão da conferência. Devolve `(print_job, dados)`."""
    from apps.printers.services import register_command_bill_print

    with tenant_context(command.account):
        itens = list(
            open_items_of_command(command.pk).exclude(
                status__in=["cancelled", "comped"]
            )
        )
        if not itens:
            raise ValidationError(
                f"A comanda {command.number} não tem item pendente para conferir."
            )
        total = total_pendente(command.pk)
        job = register_command_bill_print(
            command=command, items=itens, total=total, user=user
        )
    return job, {"total": total, "items": itens}
