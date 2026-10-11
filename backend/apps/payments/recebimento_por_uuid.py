"""O recebimento identificado pelo PDV: UUID + horário de quem lançou.

Loja e nuvem aceitam receber — o PDV escolhe o servidor e desvia quando um
cai. O que impede cobrar duas vezes é o DADO, e a única regra fixa é: **o UUID
nunca muda**.

* **UUID novo** → cria o recebimento com ESSE id. A sincronização junta as
  linhas pelo id: o mesmo recebimento enviado à loja e à nuvem é uma linha só.
* **UUID que já existe, horário mais novo** → vale o que chegou. Mudou só
  subtipo/referência: atualiza na linha. Mudou valor ou forma: desfaz os
  efeitos da versão anterior (gaveta, estado do pedido, estoque — o mesmo
  `cancel_payment` do estorno) e reaplica a nova NA MESMA LINHA, mesmo UUID.
* **UUID que já existe, horário igual ou mais velho** → ignorado: é o reenvio
  (rede caiu, fila do PDV) ou uma requisição atrasada.

Dois casos não são "versão nova do mesmo recebimento" e viram
`RecebimentoEmConflito` (409): o UUID num OUTRO pedido, e mudar o dinheiro de
um pedido com NFC-e já emitida — a nota saiu com os valores antigos e só se
corrige cancelando a nota.
"""
from datetime import timezone as dt_timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core import uuid_do_aparelho
from apps.core.numbers import parse_money
from apps.payments.models import Payment, PaymentMethod

CAMPO_DO_HORARIO = "client_updated_at"


class RecebimentoEmConflito(Exception):
    """O UUID não pode receber esta versão (outro pedido, ou nota já emitida)."""


def ler_id(valor):
    return uuid_do_aparelho.ler(valor, "recebimento")


def ler_horario(valor):
    if valor in (None, ""):
        return None
    momento = parse_datetime(str(valor))
    if momento is None:
        raise ValidationError("Horário do recebimento inválido.")
    # Sem fuso é UTC. Comparar um horário sem fuso com o gravado (com fuso)
    # estourava `TypeError` — um 500 que o PDV reenviaria para sempre.
    if timezone.is_naive(momento):
        momento = timezone.make_aware(momento, dt_timezone.utc)
    return momento


def conciliar(order, payment_id, *, payment_method_id, amount, metadata, client_updated_at, user):
    """`(recebimento, refazer)` para este UUID.

    `(None, False)`: UUID novo, segue a criação. `(p, False)`: nada mais a
    fazer, devolver `p`. `(p, True)`: a versão anterior foi desfeita e a nova
    deve ser reaplicada NESTA linha.
    """
    if payment_id is None:
        return None, False
    pagamento = (
        Payment.all_objects.select_for_update()
        .filter(pk=payment_id, account_id=order.account_id)
        .first()
    )
    if pagamento is None:
        return None, False
    if pagamento.order_id != order.pk:
        raise RecebimentoEmConflito(
            "Este recebimento pertence a outro pedido. Atualize a tela antes de receber de novo."
        )
    if not _mais_novo(client_updated_at, pagamento):
        _guardar_ignorado(pagamento, payment_method_id, amount, metadata, client_updated_at, user)
        return pagamento, False
    if not _dinheiro_mudou(pagamento, payment_method_id, amount):
        if pagamento.status == Payment.STATUS_APPROVED:
            _atualizar_detalhes(pagamento, metadata, client_updated_at)
            return pagamento, False
        return pagamento, True  # cancelado: a versão nova o reativa
    _sem_nota_emitida(order)
    if pagamento.status == Payment.STATUS_APPROVED:
        from apps.payments.services import cancel_payment

        cancel_payment(payment=pagamento, user=user)
    return pagamento, True


def marcar_horario(metadata, client_updated_at):
    if client_updated_at is not None:
        metadata[CAMPO_DO_HORARIO] = client_updated_at.isoformat()
    return metadata


def _dinheiro_mudou(pagamento, payment_method_id, amount):
    recebido = Decimal(str((pagamento.metadata or {}).get("received_amount") or pagamento.amount))
    return (
        str(pagamento.payment_method_id) != str(payment_method_id)
        or recebido != parse_money(amount, field="amount")
    )


def _sem_nota_emitida(order):
    from apps.invoices.models import Invoice

    nota = Invoice.all_objects.filter(order_id=order.pk).first()
    if nota is not None and nota.status in (Invoice.STATUS_PENDING, Invoice.STATUS_ISSUED):
        raise RecebimentoEmConflito(
            "A NFC-e deste pedido já foi emitida com o recebimento anterior. "
            "Cancele a nota antes de alterar o valor ou a forma."
        )


def _mais_novo(client_updated_at, pagamento):
    if client_updated_at is None:
        return False
    gravado = ler_horario((pagamento.metadata or {}).get(CAMPO_DO_HORARIO))
    return gravado is None or client_updated_at > gravado


def _atualizar_detalhes(pagamento, metadata, client_updated_at):
    novos = dict(metadata or {})
    dados = dict(pagamento.metadata or {})
    if "reference" in novos:
        dados["reference"] = novos["reference"]
    subtipo = str(novos.get("card_subtype") or "").strip().lower()
    if (pagamento.payment_method.method_type == PaymentMethod.TYPE_CARD
            and subtipo in {Payment.CARD_DEBIT, Payment.CARD_CREDIT}):
        pagamento.card_subtype = subtipo
        dados["card_subtype"] = subtipo
    pagamento.metadata = marcar_horario(dados, client_updated_at)
    pagamento.save(update_fields=["card_subtype", "metadata", "updated_at"])


def _guardar_ignorado(pagamento, payment_method_id, amount, metadata, client_updated_at, user):
    """Ignorado, mas guardado no histórico (`SyncDiscard`): dá para recuperar."""
    from apps.synchronization.models import SyncDiscard
    from apps.synchronization.services import descartes

    gravado = ler_horario((pagamento.metadata or {}).get(CAMPO_DO_HORARIO))
    reenvio = client_updated_at is not None and gravado is not None and client_updated_at == gravado
    descartes.registrar(
        origem=SyncDiscard.ORIGEM_API,
        motivo=SyncDiscard.MOTIVO_REENVIO if reenvio else SyncDiscard.MOTIVO_VERSAO_MAIS_VELHA,
        entity_type="payment", entity_id=pagamento.pk, account_id=pagamento.account_id,
        dados={"order": pagamento.order_id, "payment_method": payment_method_id, "amount": amount,
               "metadata": metadata, CAMPO_DO_HORARIO: client_updated_at},
        versao_recebida=_micros(client_updated_at), versao_local=_micros(gravado), usuario=user,
    )


def _micros(momento):
    return int(momento.timestamp() * 1_000_000) if momento else 0


def guardar_reenvio_pela_chave(pagamento, payment_method_id, amount, metadata, user):
    """O reenvio reconhecido pela chave antiga (terminal sem UUID), no histórico."""
    from apps.synchronization.models import SyncDiscard
    from apps.synchronization.services import descartes

    descartes.registrar(
        origem=SyncDiscard.ORIGEM_API, motivo=SyncDiscard.MOTIVO_REENVIO,
        entity_type="payment", entity_id=pagamento.pk, account_id=pagamento.account_id,
        dados={"order": pagamento.order_id, "payment_method": payment_method_id,
               "amount": amount, "metadata": metadata,
               "idempotency_key": pagamento.idempotency_key},
        usuario=user,
    )


def chegou_no_mesmo_instante(order, payment_id, payment_method_id, amount, metadata, user):
    """O recebimento deste UUID que a sincronização gravou durante a inserção.

    `None` se não for esse o caso (outro UUID, outro pedido): aí o erro de
    integridade é de verdade e sobe.
    """
    if payment_id is None:
        return None
    existente = Payment.all_objects.filter(pk=payment_id, order_id=order.pk).first()
    if existente is not None:
        guardar_reenvio_pela_chave(existente, payment_method_id, amount, metadata, user)
    return existente
