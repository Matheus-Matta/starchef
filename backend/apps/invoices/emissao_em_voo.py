"""A nota "em voo": transmissão à SEFAZ em curso, fora de qualquer transação.

`emit_fiscal_invoice` grava a nota como `pending` com a marca `EM_VOO` antes de
chamar o provedor, e só então transmite — sem lock. Quem chega no meio
(reprocessamento, consulta, reenvio, cancelamento, o `/invoices/emit/` do PDV)
lê a marca e espera, em vez de transmitir de novo ou travar a linha.
"""
from datetime import datetime, timedelta

from django.utils import timezone

from apps.invoices.emissao_da_loja import avancar_contador
from apps.invoices.models import Invoice

#: O mesmo valor de `services.AWAITING_AUTHORIZATION`; repetido para não
#: importar `services` daqui (ele importa este módulo).
_AGUARDANDO_AUTORIZACAO = "authorization"

#: Marca da nota cuja transmissão está em curso (`fiscal_payload`), com o
#: instante em que começou. O reprocessamento não mexe nela antes de
#: `EM_VOO_PRAZO`: consultar o provedor no meio da transmissão leria "não
#: existe" e mandaria transmitir de novo.
EM_VOO = "emitindo_desde"
EM_VOO_PRAZO = timedelta(minutes=5)


def _marcar_em_voo(invoice, config, contador, number):
    """Grava a nota como `pending` em transmissão e reserva o número.

    Só o BANCO vê a marca: em memória a nota volta ao estado de antes, e a
    transmissão segue exatamente como seguia — o provedor e o tratamento da
    resposta leem `status` e `fiscal_payload`.
    """
    status_antes = invoice.status
    payload_antes = dict(invoice.fiscal_payload or {})
    invoice.status = Invoice.STATUS_PENDING
    invoice.fiscal_payload = {
        **payload_antes,
        "awaiting": _AGUARDANDO_AUTORIZACAO,
        EM_VOO: timezone.now().isoformat(),
    }
    invoice.save(update_fields=["status", "fiscal_payload", "updated_at"])
    avancar_contador(config, contador, number)
    invoice.status = status_antes
    invoice.fiscal_payload = payload_antes


def em_voo_recente(invoice, agora=None):
    """A transmissão desta nota começou há menos de `EM_VOO_PRAZO`?"""
    inicio = (invoice.fiscal_payload or {}).get(EM_VOO)
    if not inicio:
        return False
    try:
        inicio = datetime.fromisoformat(inicio)
    except (TypeError, ValueError):
        return False
    return (agora or timezone.now()) - inicio < EM_VOO_PRAZO


def _preservar_marcas_do_voo(invoice):
    """Traz o que outra requisição gravou na nota DURANTE a transmissão.

    O `/invoices/emit/` do terminal acha a nota em andamento e grava nela
    `terminal_prints` (quem imprime o DANFE). A gravação final escreve o
    `fiscal_payload` inteiro, e sem isto apagaria a marca: o agente local
    imprimiria uma via e o terminal outra.
    """
    no_banco = (
        Invoice.all_objects.select_for_update()
        .filter(pk=invoice.pk).values_list("fiscal_payload", flat=True).first()
    ) or {}
    if "terminal_prints" in no_banco and "terminal_prints" not in (invoice.fiscal_payload or {}):
        invoice.fiscal_payload = {**(invoice.fiscal_payload or {}),
                                  "terminal_prints": no_banco["terminal_prints"]}
