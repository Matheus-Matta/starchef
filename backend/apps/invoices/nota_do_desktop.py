"""A NFC-e que o StarChef Desktop JÁ emitiu, guardada aqui — nunca emitida de novo.

O desktop assina e transmite com a ACBrLib dele, numa série só dele, e manda o
XML pronto (`POST /invoices/register/`). Tudo que é fato fiscal sai do XML;
do corpo só vem o pedido. O servidor confere o que dá para conferir sem a
SEFAZ: chave e DV, emitente, ambiente, série, total e, na autorizada, o
protocolo daquela mesma chave.

Exemplo: a venda sai em contingência às 20h e é registrada `pending`; às 21h o
desktop transmite e registra o MESMO pedido com o XML autorizado — a linha vira
`issued`. Reenviar qualquer um dos dois não muda nada, e a contingência que
chegar atrasada não desfaz a autorizada.

Quem manda nessa nota é o desktop: o servidor não a retransmite, recria,
consulta nem cancela (`recusar_se_do_desktop`). Só ele tem o XML assinado e a
situação dela na SEFAZ; a varredura de pendentes daqui a retransmitiria pelo
provedor da loja, em outra chave.
"""
import re

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.invoices.models import Invoice, InvoiceItem
from apps.invoices.nota_do_desktop_xml import NS, decimal, leitor, ler

PROVEDOR = "desktop"


class NotaEmConflito(Exception):
    """O XML está certo; o que o servidor já tem (ou o cadastro) diverge: 409."""


def do_desktop(invoice):
    return invoice is not None and invoice.provider == PROVEDOR


def recusar_se_do_desktop(invoice):
    if do_desktop(invoice):
        raise ValidationError(
            "Esta nota foi emitida no StarChef Desktop. Reenvio, consulta e cancelamento são feitos no terminal que a emitiu."
        )


def registrar(order, xml, *, user=None, terminal=""):
    """Grava (ou atualiza) a nota do pedido. Devolve `(nota, criada)`."""
    lida = ler(xml)
    with transaction.atomic(), tenant_context(order.account):
        order = type(order).objects.select_for_update().get(pk=order.pk)
        outra = Invoice.all_objects.filter(access_key=lida["chave"]).exclude(order=order).first()
        if outra is not None:
            raise NotaEmConflito("Esta chave de acesso já está registrada em outro pedido.")
        nota = Invoice.all_objects.select_for_update().filter(order=order).first()
        if nota is not None and nota.status == Invoice.STATUS_CANCELLED:
            raise NotaEmConflito("A nota deste pedido está cancelada.")
        if nota is not None and nota.access_key == lida["chave"] and do_desktop(nota):
            if nota.status == Invoice.STATUS_ISSUED or not lida["protocolo"]:
                return nota, False  # reenvio, ou contingência que chegou depois da autorizada
        elif nota is not None and nota.status != Invoice.STATUS_ERROR:
            raise NotaEmConflito("Este pedido já tem outra nota fiscal.")
        _conferir(order, lida)
        criada = nota is None
        nota = _gravar(nota, order, lida, user=user, terminal=terminal)
        record_audit(
            action=AuditLog.ACTION_CREATED if criada else AuditLog.ACTION_UPDATED, instance=nota, actor=user,
            metadata={"event": "desktop_invoice_registered", "access_key": nota.access_key, "status": nota.status},
        )
        return nota, criada


def registrar_cancelamento(order, dados, *, user=None):
    """O evento que o terminal já homologou na SEFAZ. Só depois disto o pedido pode ser cancelado aqui.

    Com `verificar`, só confere: o terminal pergunta ANTES de cancelar na SEFAZ.
    """
    dados = dados if isinstance(dados, dict) else {}
    protocolo, motivo = str(dados.get("protocolo") or "").strip(), str(dados.get("justificativa") or "").strip()
    verificar = dados.get("verificar") is True
    if not verificar and (not re.fullmatch(r"\d{10,20}", protocolo) or not 15 <= len(motivo) <= 255):
        raise ValidationError("Informe o protocolo do cancelamento e a justificativa (15 a 255 caracteres).")
    with transaction.atomic(), tenant_context(order.account):
        nota = Invoice.all_objects.select_for_update().filter(order=order).first()
        if not do_desktop(nota) or nota.access_key != str(dados.get("chave") or ""):
            raise NotaEmConflito("Este pedido não tem essa nota do desktop.")
        if nota.status == Invoice.STATUS_CANCELLED:
            return nota
        if nota.status != Invoice.STATUS_ISSUED:
            raise NotaEmConflito("Só uma nota autorizada pode ser cancelada.")
        if verificar:
            return nota
        nota.status, nota.error_message, nota.updated_by = Invoice.STATUS_CANCELLED, motivo, user
        nota.fiscal_payload = {**(nota.fiscal_payload or {}), "protocolo_cancelamento": protocolo}
        nota.save(update_fields=["status", "error_message", "updated_by", "fiscal_payload", "updated_at"])
        record_audit(action=AuditLog.ACTION_CANCELLED, instance=nota, actor=user, reason=motivo,
                     metadata={"event": "desktop_invoice_cancelled", "protocol": protocolo})
        return nota


def _conferir(order, lida):
    from apps.invoices.acbrlib.emitente import Emitente
    from apps.invoices.services import _resolve_fiscal_config

    config = _resolve_fiscal_config(order.restaurant, order.branch)
    if config is None:
        raise NotaEmConflito("O restaurante não possui configuração fiscal ativa.")
    if re.sub(r"[^0-9A-Z]", "", str(Emitente(config).cnpj).upper()) != lida["cnpj"]:
        raise NotaEmConflito("O emitente da nota não é este restaurante.")
    if lida["tpAmb"] != config.environment:
        raise NotaEmConflito("O ambiente da nota (produção/homologação) não é o do cadastro fiscal.")
    if int(lida["serie"]) in {config.series, config.cloud_series}:
        raise NotaEmConflito("A série da nota é usada pelo servidor: o terminal precisa de uma série própria.")
    if lida["total"] != order.total:
        raise NotaEmConflito(f"O total da nota ({lida['total']}) difere do total do pedido ({order.total}).")


def _gravar(nota, order, lida, *, user, terminal):
    nota = nota or Invoice(account=order.account, restaurant=order.restaurant, branch=order.branch, order=order, created_by=user)
    texto, autorizada = lida["texto"], bool(lida["protocolo"])
    campos = {
        "phase": Invoice.PHASE_FISCAL, "status": Invoice.STATUS_ISSUED if autorizada else Invoice.STATUS_PENDING,
        "provider": PROVEDOR, "provider_reference": lida["chave"], "document_model": lida["mod"],
        "series": int(lida["serie"]), "number": lida["nNF"], "environment": lida["tpAmb"], "crt": lida["crt"],
        "emission_type": Invoice.EMISSION_CONTINGENCY if lida["tpEmis"] == "9" else Invoice.EMISSION_NORMAL,
        "access_key": lida["chave"], "emitter_cnpj": lida["cnpj"], "emitter_name": texto("emit/xNome")[:180],
        "recipient_cpf": texto("dest/CPF"), "recipient_cnpj": texto("dest/CNPJ"), "recipient_name": texto("dest/xNome")[:180],
        "products_total": decimal(texto("total/ICMSTot/vProd")), "discount_total": decimal(texto("total/ICMSTot/vDesc")),
        "tax_approx_total": decimal(texto("total/ICMSTot/vTotTrib")), "total_amount": lida["total"],
        "qr_code_data": lida["qr"], "consult_url": _url(lida["url"]), "authorization_protocol": lida["protocolo"],
        "authorized_at": lida["autorizada_em"], "digest_value": lida["digest"][:64], "xml_content": lida["xml"],
        "error_message": "", "issued_at": parse_datetime(lida["dhEmi"]), "updated_by": user,
        # `terminal_prints`: o DANFE é do desktop, nunca do agente automático.
        "fiscal_payload": {"origem": PROVEDOR, "terminal": str(terminal)[:120], "cNF": lida["cNF"], "terminal_prints": True},
    }
    for campo, valor in campos.items():
        setattr(nota, campo, valor)
    nota.save()
    nota.items.all().delete()
    InvoiceItem.objects.bulk_create([_item(nota, det, user) for det in lida["itens"]])
    return nota


def _item(nota, det, user):
    from apps.menu.models import Product

    texto = leitor(det)
    icms = leitor(det.find(f"{NS}imposto/{NS}ICMS/*"))
    pis = leitor(det.find(f"{NS}imposto/{NS}PIS/*"))
    cofins = leitor(det.find(f"{NS}imposto/{NS}COFINS/*"))
    bruto, desconto = decimal(texto("prod/vProd")), decimal(texto("prod/vDesc"))
    codigo = texto("prod/cProd")
    return InvoiceItem(
        account=nota.account, restaurant=nota.restaurant, branch=nota.branch, created_by=user, updated_by=user,
        invoice=nota, line_number=int(det.get("nItem") or 1), code=codigo[:60], description=texto("prod/xProd")[:180],
        product=Product.all_objects.filter(account=nota.account, internal_code=codigo, deleted_at__isnull=True).first(),
        ncm=texto("prod/NCM"), cest=texto("prod/CEST"), cfop=texto("prod/CFOP"), unit=texto("prod/uCom")[:6] or "UN",
        quantity=decimal(texto("prod/qCom"), "0.001"), unit_price=decimal(texto("prod/vUnCom")), discount=desconto,
        total_price=bruto - desconto + decimal(texto("prod/vOutro")), origem=icms("orig") or "0", csosn=icms("CSOSN"),
        cst_icms=icms("CST"), icms_base=decimal(icms("vBC")), icms_rate=decimal(icms("pICMS")), icms_value=decimal(icms("vICMS")),
        pis_cst=pis("CST") or "49", pis_rate=decimal(pis("pPIS")), pis_value=decimal(pis("vPIS")),
        cofins_cst=cofins("CST") or "49", cofins_rate=decimal(cofins("pCOFINS")), cofins_value=decimal(cofins("vCOFINS")),
        approx_tax_value=decimal(texto("imposto/vTotTrib")),
    )


def _url(valor):
    if not valor or len(valor) > 190:
        return ""
    return valor if valor.startswith(("http://", "https://")) else f"https://{valor}"
