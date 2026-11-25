"""`POST /invoices/register/`: a NFC-e que o StarChef Desktop já emitiu."""
import uuid
from decimal import Decimal
from unittest import mock

import pytest

from apps.invoices.models import FiscalConfig, Invoice, InvoiceItem
from apps.invoices.nota_do_desktop_xml import _dv
from apps.invoices.tests.quitacao import quitar_pedido
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db
URL = "/api/v1/invoices/register/"
CNPJ = "11222333000181"


def montar(*, total="25.00", serie="50", numero="7", tp_emis="1", amb="2", cnpj=CNPJ, protocolo=True, cstat="100",
           cnf="87654321", chave_do_protocolo=None, antes=""):
    corpo = f"332611{cnpj}65{serie:0>3}{numero:0>9}{tp_emis}{cnf}"
    chave = corpo + _dv(corpo)
    prot = (f'<protNFe versao="4.00"><infProt><tpAmb>{amb}</tpAmb><chNFe>{chave_do_protocolo or chave}</chNFe>'
            f"<dhRecbto>2026-11-24T20:00:05-03:00</dhRecbto><nProt>135260000000042</nProt><cStat>{cstat}</cStat></infProt></protNFe>")
    nota = (
        f'<NFe xmlns="http://www.portalfiscal.inf.br/nfe"><infNFe Id="NFe{chave}" versao="4.00"><ide><cNF>{cnf}</cNF><mod>65</mod>'
        f"<serie>{serie}</serie><nNF>{numero}</nNF><dhEmi>2026-11-24T20:00:00-03:00</dhEmi><tpEmis>{tp_emis}</tpEmis><tpAmb>{amb}</tpAmb></ide>"
        f"<emit><CNPJ>{cnpj}</CNPJ><xNome>LOJA LTDA</xNome><CRT>1</CRT></emit><dest><CPF>52998224725</CPF><xNome>CLIENTE</xNome></dest>"
        f'<det nItem="1"><prod><cProd>P1</cProd><xProd>X-Burger</xProd><NCM>21069090</NCM><CFOP>5102</CFOP><uCom>UN</uCom><qCom>1.0000</qCom>'
        f"<vUnCom>{total}</vUnCom><vProd>{total}</vProd></prod><imposto><vTotTrib>1.00</vTotTrib><ICMS><ICMSSN102><orig>0</orig><CSOSN>102</CSOSN>"
        f"</ICMSSN102></ICMS><PIS><PISOutr><CST>49</CST></PISOutr></PIS></imposto></det><total><ICMSTot><vProd>{total}</vProd><vDesc>0.00</vDesc>"
        f"<vNF>{total}</vNF><vTotTrib>1.00</vTotTrib></ICMSTot></total></infNFe><infNFeSupl><qrCode>https://qr?p={chave}</qrCode>"
        f"<urlChave>www.nfce.fazenda.rj.gov.br</urlChave></infNFeSupl><Signature xmlns=\"http://www.w3.org/2000/09/xmldsig#\"><SignedInfo><Reference>"
        f"<DigestValue>abc=</DigestValue></Reference></SignedInfo><SignatureValue>xyz=</SignatureValue></Signature></NFe>"
    )
    return chave, antes + f'<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">{nota}{prot if protocolo else ""}</nfeProc>'


@pytest.fixture
def pedido(account, restaurant, branch, manager_user):
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch, provider="manual", environment="2", cnpj="11.222.333/0001-81",
        corporate_name="Loja", series=1, cloud_series=2, crt="1",
    )
    produto = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="X-Burger", internal_code="P1", sale_price=Decimal("25.00"))
    order = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    add_order_item(order=order, product=produto, quantity=1, user=manager_user)
    quitar_pedido(order)
    order.refresh_from_db()
    Order.objects.filter(pk=order.pk).update(service_fee=0, total=Decimal("25.00"))
    return order


def enviar(client, pedido, xml, **extra):
    return client.post(URL, {"order": str(pedido.pk), "xml": xml, **extra}, format="json")


def test_autorizada_fica_gravada_com_tudo_do_xml(api_client, pedido):
    chave, xml = montar()
    r = enviar(api_client, pedido, xml)
    assert r.status_code == 201, r.data
    nota = Invoice.all_objects.get(order=pedido)
    assert (nota.status, nota.provider, nota.access_key, nota.series, nota.number) == ("issued", "desktop", chave, 50, "7")
    assert (nota.authorization_protocol, nota.recipient_cpf, nota.total_amount) == ("135260000000042", "52998224725", Decimal("25.00"))
    assert nota.xml_content == xml and nota.authorized_at and nota.consult_url.startswith("https://")
    item = InvoiceItem.all_objects.get(invoice=nota)
    assert (item.csosn, item.ncm, item.product.internal_code, item.total_price) == ("102", "21069090", "P1", Decimal("25.00"))
    assert r.data["fiscal_state"] == "authorized"
    assert nota.fiscal_payload["terminal_prints"] is True


def test_reenvio_nao_duplica_nem_muda(api_client, pedido):
    _, xml = montar()
    enviar(api_client, pedido, xml)
    r = enviar(api_client, pedido, xml)
    assert r.status_code == 200
    assert Invoice.all_objects.filter(order=pedido).count() == 1
    assert InvoiceItem.all_objects.filter(invoice__order=pedido).count() == 1


def test_contingencia_vira_autorizada_e_nao_volta(api_client, pedido):
    _, assinada = montar(tp_emis="9", protocolo=False)
    _, autorizada = montar(tp_emis="9")
    r = enviar(api_client, pedido, assinada)
    assert r.status_code == 201 and r.data["fiscal_state"] == "contingency_pending"
    assert enviar(api_client, pedido, autorizada).data["fiscal_state"] == "authorized"
    assert enviar(api_client, pedido, assinada).data["fiscal_state"] == "authorized"  # atrasada
    nota = Invoice.all_objects.get(order=pedido)
    assert nota.emission_type == "9" and "protNFe" in nota.xml_content


def test_contingencia_substituida_por_outra_chave_e_conflito(api_client, pedido):
    enviar(api_client, pedido, montar(tp_emis="9", protocolo=False)[1])
    r = enviar(api_client, pedido, montar(cnf="11112222")[1])
    assert r.status_code == 409


@pytest.mark.parametrize(("campos", "codigo"), [
    ({"protocolo": False}, 400),  # normal sem protocolo: não foi autorizada
    ({"cstat": "778"}, 400),
    ({"chave_do_protocolo": "3" * 44}, 400),
    ({"antes": '<!DOCTYPE a [<!ENTITY b "c">]>'}, 400),
    ({"cnpj": "99888777000166"}, 409),  # outra empresa
    ({"amb": "1"}, 409),
    ({"serie": "1"}, 409), ({"serie": "2"}, 409),  # séries do servidor
    ({"total": "24.99"}, 409),
])
def test_o_que_nao_confere_e_recusado_sem_gravar(api_client, pedido, campos, codigo):
    r = enviar(api_client, pedido, montar(**campos)[1])
    assert r.status_code == codigo, r.data
    assert not Invoice.all_objects.filter(order=pedido).exists()


def test_xml_editado_depois_de_assinado_e_recusado(api_client, pedido):
    chave, xml = montar()
    for trocado in (xml.replace("<nNF>7<", "<nNF>8<"), xml.replace(f"NFe{chave}", "NFe" + chave[:-1] + str((int(chave[-1]) + 1) % 10)),
                    xml.replace("SignatureValue", "Outro"), "<a", "", None, 123, "x" * 600_000):
        assert enviar(api_client, pedido, trocado).status_code == 400
    assert not Invoice.all_objects.filter(order=pedido).exists()


def test_chave_ja_usada_em_outro_pedido(api_client, pedido, restaurant, branch, manager_user):
    _, xml = montar()
    enviar(api_client, pedido, xml)
    outro = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    Order.objects.filter(pk=outro.pk).update(total=Decimal("25.00"))
    assert enviar(api_client, outro, xml).status_code == 409


def test_pedido_que_o_servidor_ja_emitiu_nao_e_trocado(api_client, pedido):
    Invoice.objects.create(account=pedido.account, restaurant=pedido.restaurant, branch=pedido.branch, order=pedido,
                           status=Invoice.STATUS_ISSUED, provider="focus_nfe", access_key="1" * 44)
    assert enviar(api_client, pedido, montar()[1]).status_code == 409
    assert Invoice.all_objects.get(order=pedido).provider == "focus_nfe"


def test_pedido_de_outra_conta_nao_existe(api_client, pedido):
    r = api_client.post(URL, {"order": str(uuid.uuid4()), "xml": montar()[1]}, format="json")
    assert r.status_code == 404
    assert api_client.post(URL, {"order": "lixo", "xml": "x"}, format="json").status_code in (400, 404)


def test_o_servidor_nao_mexe_na_nota_do_desktop(api_client, pedido):
    from apps.invoices.services import reprocess_pending_fiscal_invoices

    enviar(api_client, pedido, montar(tp_emis="9", protocolo=False)[1])
    nota = Invoice.all_objects.get(order=pedido)
    FiscalConfig.objects.update(provider=FiscalConfig.PROVIDER_FOCUS_NFE)
    with mock.patch("apps.invoices.providers.FocusNfeProvider.emit", side_effect=AssertionError("retransmitiu")):
        assert reprocess_pending_fiscal_invoices() == (0, 0)
        for acao in ("resend", "recreate", "refresh-status", "cancel"):
            r = api_client.post(f"/api/v1/invoices/{nota.pk}/{acao}/", {"reason": "teste de cancelamento"}, format="json")
            assert r.status_code in (400, 409), (acao, r.status_code, r.data)
            assert "Desktop" in str(r.data)
        # pedir a nota devolve ESTA, sem emitir outra
        r = api_client.post("/api/v1/invoices/emit/", {"order": str(pedido.pk)}, format="json")
    assert r.status_code == 200 and r.data["access_key"] == nota.access_key
    nota.refresh_from_db()
    assert nota.status == Invoice.STATUS_PENDING


def test_caixa_comum_registra_e_anonimo_nao(api_client, pedido, manager_user):
    from rest_framework.test import APIClient

    assert APIClient().post(URL, {"order": str(pedido.pk), "xml": montar()[1]}, format="json").status_code == 401
    from apps.accounts.models import Role

    perfil = manager_user.profile
    perfil.role = Role.all_objects.get(account=perfil.account, code="cashier")
    perfil.save()
    assert enviar(api_client, pedido, montar()[1]).status_code == 201
