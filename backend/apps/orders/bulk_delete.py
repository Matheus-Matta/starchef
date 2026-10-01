"""Excluir vários pedidos — só os que não deixaram rastro fiscal nem de caixa.

Excluir é a exclusão lógica (`deleted_at`): o pedido some das listas e dos
relatórios. Por isso a trava: pedido com nota fiscal (emitida, pendente ou
cancelada — documento fiscal é registro, mesmo cancelado) ou com pagamento
aprovado é VENDA, e venda se cancela, não se apaga. Sumir com ela faria o caixa
e o relatório fiscal não baterem com o que a SEFAZ e a gaveta registraram.

Sobra o que é lixo de operação: pedido aberto vazio, rascunho esquecido,
pedido cancelado que nunca foi pago nem gerou nota.
"""
from django.db import transaction

#: Teto por chamada, o mesmo do cancelamento em massa.
MAXIMO = 500


def motivo_para_manter(pedido):
    """Por que este pedido NÃO pode ser excluído, ou `None` se pode."""
    from apps.payments.models import Payment

    if getattr(pedido, "invoice", None) is not None:
        return "tem nota fiscal — cancele o pedido em vez de excluir"
    if pedido.payments.filter(status=Payment.STATUS_APPROVED).exists():
        return "tem pagamento recebido — cancele o pedido em vez de excluir"
    return None


def excluir_em_massa(pedidos, *, user):
    resultado = {"deleted": 0, "skipped": []}
    for pedido in sorted(pedidos, key=lambda p: str(p.pk)):
        motivo = motivo_para_manter(pedido)
        if motivo:
            resultado["skipped"].append({"id": str(pedido.pk), "sequence": pedido.sequence, "reason": motivo})
            continue
        with transaction.atomic():
            pedido.updated_by = user
            pedido.save(update_fields=["updated_by", "updated_at"])
            pedido.delete()
        resultado["deleted"] += 1
    return resultado
