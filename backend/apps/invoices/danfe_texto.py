"""DANFE NFC-e em texto monoespaçado, para a impressora térmica.

Saiu de `invoices/services.py` (que passava de 1800 linhas). O agente local de
impressão manda bytes ESC/POS puros para impressoras de rede/serial; só a via
de spool do Windows renderiza o HTML (`danfe_nfce.html`). Os dois têm o MESMO
conteúdo.
"""
import textwrap
from decimal import Decimal

from django.utils import timezone

from apps.invoices import lei_da_transparencia
from apps.invoices.fiscal import format_access_key
from apps.invoices.models import FiscalConfig, Invoice

# A MESMA largura do recibo de venda (`printers.services.LARGURA_CUPOM`), e
# pelo mesmo motivo: varias termicas genericas de 80mm so cabem 42~47
# caracteres reais por linha na fonte A, e o excedente NAO TRUNCA — ele quebra
# para a linha de baixo. Com 48, o ultimo caractere do valor e o ultimo traco
# do separador caiam sozinhos numa linha nova, e o cupom fiscal saia picotado.
#
# O recibo ja tinha aprendido isso e baixado para 42; o DANFE ficou para tras.
# A constante e repetida aqui em vez de importada porque `invoices.services` e
# `printers.services` se importam em ciclo (por isso os imports locais dentro
# das funcoes) — mudar uma sem a outra e o erro que este comentario evita.
_DANFE_WIDTH = 42


def _danfe_decimal(value, places=2):
    return f"{Decimal(value):.{places}f}".replace(".", ",")


def _danfe_linha_valor(rotulo, valor, *, places=2):
    quantia = _danfe_decimal(valor, places)
    largura_rotulo = _DANFE_WIDTH - len(quantia) - 1
    rotulo = str(rotulo)[:largura_rotulo]
    return f"{rotulo:<{largura_rotulo}} {quantia}"


def _danfe_center_wrapped(value):
    return [line.center(_DANFE_WIDTH) for line in textwrap.wrap(str(value), _DANFE_WIDTH) or [""]]


def _danfe_payment_label(payment):
    label = payment.payment_method.name.upper()
    if payment.card_subtype:
        label += f" - {payment.get_card_subtype_display().upper()}"
    return label


def _danfe_nfce_text(invoice, config):
    """Renderiza o DANFE NFC-e em texto monoespaçado 48 colunas.

    Mesmo conteudo do template HTML (`danfe_nfce.html`) — necessario porque o
    agente local de impressao so consegue mandar bytes ESC/POS puros pra
    impressoras de rede/serial; so a via de spool do Windows renderiza HTML.
    """
    lines = []
    name = (
        ((config.trade_name or config.corporate_name) if config else "")
        or invoice.emitter_name
        or "RAZAO SOCIAL"
    )
    lines.append(name.center(_DANFE_WIDTH)[:_DANFE_WIDTH])
    cnpj = invoice.emitter_cnpj or "__.___.___/____-__"
    ie = f" IE: {config.ie}" if config and config.ie else ""
    lines.append(f"CNPJ: {cnpj}{ie}".center(_DANFE_WIDTH)[:_DANFE_WIDTH])
    if config and (config.address_line or config.city):
        address = config.address_line
        if config.address_number:
            address += f", {config.address_number}"
        if config.district:
            address += f" - {config.district}"
        if config.city:
            address += f" - {config.city}/{config.uf}"
        if config.zip_code:
            address += f" - CEP {config.zip_code}"
        lines.extend(_danfe_center_wrapped(address))
    lines.append("-" * _DANFE_WIDTH)
    lines.append("DOCUMENTO AUXILIAR DA NOTA FISCAL DE".center(_DANFE_WIDTH))
    lines.append("CONSUMIDOR ELETRONICA".center(_DANFE_WIDTH))
    if invoice.environment == FiscalConfig.ENV_HOMOLOGATION:
        lines.append("-" * _DANFE_WIDTH)
        lines.append("SEM VALOR FISCAL - HOMOLOGACAO".center(_DANFE_WIDTH))
    if invoice.emission_type == Invoice.EMISSION_CONTINGENCY:
        lines.append("-" * _DANFE_WIDTH)
        lines.append("EMITIDA EM CONTINGENCIA".center(_DANFE_WIDTH))
        lines.append("TRANSMITIR QUANDO A CONEXAO VOLTAR".center(_DANFE_WIDTH))
    lines.append("-" * _DANFE_WIDTH)

    lines.append("COD DESCRICAO   QTD UN VL UNIT VL TOTAL")
    for item in invoice.items.all():
        description = f"{item.code or '-'} {item.description}"
        lines.extend(textwrap.wrap(description, _DANFE_WIDTH) or [description[:_DANFE_WIDTH]])
        detail = f"{_danfe_decimal(item.quantity, 3)} {item.unit.upper()} x {_danfe_decimal(item.unit_price)}"
        lines.append(_danfe_linha_valor(f"  {detail}", item.total_price))

    lines.append("-" * _DANFE_WIDTH)
    lines.append(_danfe_linha_valor("QTD. TOTAL DE ITENS", invoice.items.count(), places=0))
    lines.append(_danfe_linha_valor("VALOR TOTAL R$", invoice.total_amount))
    if invoice.discount_total:
        lines.append(_danfe_linha_valor("DESCONTO R$", invoice.discount_total))
    # Sempre, mesmo zerada: é a Lei 12.741 (ver `lei_da_transparencia.py`).
    lines.append(_danfe_linha_valor(lei_da_transparencia.ROTULO, invoice.tax_approx_total or 0))
    lines.append(lei_da_transparencia.FONTE)
    lines.append("-" * _DANFE_WIDTH)

    lines.append("FORMA DE PAGAMENTO" + "VALOR PAGO".rjust(_DANFE_WIDTH - len("FORMA DE PAGAMENTO")))
    payments = invoice.order.payments.select_related("payment_method").filter(status="approved").order_by("created_at")
    if payments.exists():
        for payment in payments:
            lines.append(_danfe_linha_valor(_danfe_payment_label(payment), payment.amount))
            if payment.change_amount:
                lines.append(_danfe_linha_valor("TROCO", payment.change_amount))
    else:
        lines.append(_danfe_linha_valor("NAO INFORMADO", invoice.total_amount))
    lines.append("-" * _DANFE_WIDTH)

    lines.append("Via Consumidor".center(_DANFE_WIDTH))
    lines.append("Consulte pela Chave de Acesso em".center(_DANFE_WIDTH))
    consult_url = invoice.consult_url or (config.portal_url if config else "") or "(portal da SEFAZ da UF)"
    lines.extend(_danfe_center_wrapped(consult_url))
    lines.extend(_danfe_center_wrapped(format_access_key(invoice.access_key)))
    lines.append(f"NFC-e n. {invoice.number}  Serie {invoice.series}".center(_DANFE_WIDTH)[:_DANFE_WIDTH])
    if invoice.issued_at:
        lines.append(f"Emissao: {timezone.localtime(invoice.issued_at):%d/%m/%Y %H:%M:%S}".center(_DANFE_WIDTH))

    if invoice.authorization_protocol:
        lines.extend(_danfe_center_wrapped(f"PROTOCOLO DE AUTORIZACAO: {invoice.authorization_protocol}"))
        if invoice.authorized_at:
            lines.append(
                f"DATA DE AUTORIZACAO: {timezone.localtime(invoice.authorized_at):%d/%m/%Y %H:%M:%S}".center(
                    _DANFE_WIDTH
                )
            )
    else:
        lines.append("AGUARDANDO AUTORIZACAO".center(_DANFE_WIDTH))
        lines.extend(_danfe_center_wrapped("(protocolo sera preenchido apos transmissao a SEFAZ)"))
    lines.append("-" * _DANFE_WIDTH)

    if invoice.recipient_cpf:
        lines.extend(_danfe_center_wrapped(f"CONSUMIDOR - CPF: {invoice.recipient_cpf}"))
    elif invoice.recipient_cnpj:
        lines.extend(_danfe_center_wrapped(f"CONSUMIDOR - CNPJ: {invoice.recipient_cnpj}"))
    else:
        lines.append("CONSUMIDOR NAO IDENTIFICADO".center(_DANFE_WIDTH))
    if invoice.recipient_name:
        lines.extend(_danfe_center_wrapped(invoice.recipient_name.upper()))
    lines.append("-" * _DANFE_WIDTH)
    return "\n".join(lines)
