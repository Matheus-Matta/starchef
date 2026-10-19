"""A SEFAZ já tem uma nota AUTORIZADA com o nosso número (rejeições 613/539).

"Chave de Acesso difere da existente em BD": série e número já foram
autorizados, com outra chave, e a SEFAZ manda a chave dela entre colchetes.
Reenviar a mesma nota repete a recusa para sempre. Há dois casos, e a chave
existente diz qual é — pelo `cNF`, que cada nota nossa mantém em TODAS as
tentativas (normal, contingência, reenvio):

* **mesmo cNF: é desta nota.** Uma tentativa anterior (tempo esgotado, ou a
  normal que a contingência substituiu) foi autorizada. A nota passa a ser
  ELA: consulta e adota chave e protocolo. Reemitir em outro número daria duas
  notas para a mesma venda.
* **cNF diferente: é de outro emissor** — outro servidor com o mesmo CNPJ e
  série (loja e um ambiente de teste com bancos separados), ou o contador
  voltado para trás. O número está queimado: a nota é refeita no próximo
  número livre, cNF novo, e reenviada — e, se o seguinte também for de outro
  emissor, segue andando até `TENTATIVAS_DE_NUMERO`. Andar UM por tentativa
  deixava o operador reenviando e recebendo 613 a cada clique com o contador
  alguns números atrás. Fica registrado em `numero_ja_usado_na_sefaz` por que
  ela pulou.

Só a ACBrLib: na Focus quem numera é a Focus.
"""
import logging
import re

from django.db import transaction
from django.utils import timezone

from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers_erros import FiscalRejection

logger = logging.getLogger(__name__)

CODIGOS = ("613", "539")
#: Quantos números a nota anda numa emissão quando outro emissor ocupa a série.
#: O teto existe: um contador muito atrás é cadastro a corrigir, não laço.
TENTATIVAS_DE_NUMERO = 10
_CHAVE = re.compile(r"(?<!\d)(\d{44})(?!\d)")


def chave_existente(erro):
    """A chave que a SEFAZ já tem, se a recusa é de número já usado."""
    texto = str(erro)
    if not any(re.search(rf"(?<!\d){codigo}(?!\d)", texto) for codigo in CODIGOS):
        return None
    achada = _CHAVE.search(texto)
    return achada.group(1) if achada else None


def _cnf_da_chave(chave):
    return chave[35:43]


def emitir(provider, invoice, config):
    """`provider.emit`, resolvendo a recusa de número já usado na SEFAZ."""
    try:
        return provider.emit(invoice, config)
    except FiscalRejection as erro:
        chave = chave_existente(erro) if provider.name == FiscalConfig.PROVIDER_ACBRLIB else None
        if chave is None:
            raise
        if _cnf_da_chave(chave) == str((invoice.fiscal_payload or {}).get("cNF", "")):
            return _adotar(provider, invoice, config, chave, erro)
        return _reemitir_no_proximo_numero(provider, invoice, config, chave)


def _adotar(provider, invoice, config, chave, erro):
    from apps.invoices.contingencia_offline import _qr_da_normal

    invoice.access_key = chave
    provider.status(invoice)
    if invoice.status != Invoice.STATUS_ISSUED:
        raise erro
    descartada = invoice.xml_content if invoice.emission_type == Invoice.EMISSION_CONTINGENCY else ""
    invoice.emission_type = Invoice.EMISSION_NORMAL
    if descartada and invoice.xml_content == descartada:
        invoice.xml_content = ""
    invoice.error_message = ""
    invoice.qr_code_data = _qr_da_normal(invoice, config)
    logger.info("Nota %s: o número %s já estava autorizado com o mesmo cNF; adotada %s.",
                invoice.pk, invoice.number, chave)


def _reemitir_no_proximo_numero(provider, invoice, config, chave):
    tentativa = 0
    while True:
        tentativa += 1
        travada = _trocar_de_numero(invoice, config, chave)
        try:
            return provider.emit(invoice, travada)
        except FiscalRejection as erro:
            proxima = chave_existente(erro)
            if proxima is None or tentativa == TENTATIVAS_DE_NUMERO:
                raise
            chave = proxima


def _trocar_de_numero(invoice, config, chave):
    from apps.invoices.emissao_da_loja import avancar_contador, serie_desta_emissao
    from apps.invoices.services import _proximo_numero_livre, _refresh_emission_for_retry

    numero_queimado = invoice.number
    with transaction.atomic():
        travada = FiscalConfig.objects.select_for_update().get(pk=config.pk)
        serie, contador = serie_desta_emissao(invoice.order, travada)
        numero = _proximo_numero_livre(travada, serie, contador)
        # O próprio número queimado está gravado nesta nota, então a busca já o
        # pula; o `max` é a garantia para a nota que ainda não foi salva.
        numero = max(numero, int(numero_queimado) + 1)
        avancar_contador(travada, contador, numero)
    payload = dict(invoice.fiscal_payload or {})
    payload.pop("cNF", None)
    payload.pop("chave_normal", None)
    payload["numero_ja_usado_na_sefaz"] = {
        "numero": numero_queimado, "chave": chave, "em": timezone.now().isoformat(),
    }
    invoice.fiscal_payload = payload
    invoice.number = str(numero)
    invoice.emission_type = Invoice.EMISSION_NORMAL
    invoice.xml_content = ""
    invoice.error_message = ""
    _refresh_emission_for_retry(invoice, travada)  # chave e QR do número novo, cNF novo
    logger.warning("Nota %s: a SEFAZ já tem o número %s (%s); reemitida como %s.",
                   invoice.pk, numero_queimado, chave, numero)
    return travada
