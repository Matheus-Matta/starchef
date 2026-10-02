"""CNPJ na NFC-e: do checkout à nota, e o que o cliente pode mandar errado.

O destinatário é CPF OU CNPJ. O CNPJ pode ser o alfanumérico novo da Receita
(letras nas 12 primeiras posições, verificadores numéricos). Tudo o que chega
torto do cliente — máscara, minúscula, número no lugar de texto, lista, os dois
documentos juntos — tem de virar 400 com mensagem, nunca 500 nem nota errada.
"""
from decimal import Decimal

import pytest

from apps.core.tenant import tenant_context
from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import FocusNfeProvider, ManualFiscalProvider
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order

pytestmark = pytest.mark.django_db

CNPJ = "11222333000181"
CNPJ_ALFA = "12ABC34501DE35"
CPF = "52998224725"


@pytest.fixture
def pedido(contexto_tenant, restaurant, branch, manager_user, produto, sem_caixa_obrigatorio):
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
    add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
    pedido.refresh_from_db()
    return pedido


def _checkout(cliente, pedido, **corpo):
    return cliente.post(f"/api/v1/orders/{pedido.pk}/checkout/", corpo, format="json")


def _gravado(pedido):
    with tenant_context(pedido.account):
        pedido.refresh_from_db()
    return pedido.fiscal_customer_cpf, pedido.fiscal_customer_cnpj


@pytest.mark.parametrize("enviado, gravado", [
    (CNPJ, CNPJ),
    ("11.222.333/0001-81", CNPJ),
    (CNPJ_ALFA, CNPJ_ALFA),
    ("12.abc.345/01de-35", CNPJ_ALFA),
])
def test_cnpj_valido_e_gravado_normalizado(api_client, pedido, enviado, gravado):
    resposta = _checkout(api_client, pedido, fiscal_customer_cpf="", fiscal_customer_cnpj=enviado)

    assert resposta.status_code == 200, resposta.content
    assert _gravado(pedido) == ("", gravado)
    assert resposta.data["fiscal_customer_cnpj"] == gravado


@pytest.mark.parametrize("enviado", [
    "11222333000182",          # verificador errado
    "1122233300018A",          # letra no verificador
    "00000000000000",          # repetido
    "112223330001",            # curto
    "11222333000181999",       # comprido
    11222333000182,            # número JSON, verificador errado
    ["11222333000181"],        # lista
    {"cnpj": CNPJ},            # objeto
])
def test_cnpj_invalido_e_400_e_nao_grava(api_client, pedido, enviado):
    resposta = _checkout(api_client, pedido, fiscal_customer_cpf="", fiscal_customer_cnpj=enviado)

    assert resposta.status_code == 400, resposta.content
    assert _gravado(pedido) == ("", "")


def test_cnpj_como_numero_json_valido_e_aceito(api_client, pedido):
    """O cliente mandou número em vez de texto: o valor é o mesmo, a nota também."""
    assert _checkout(api_client, pedido, fiscal_customer_cnpj=11222333000181).status_code == 200
    assert _gravado(pedido)[1] == CNPJ


def test_cpf_e_cnpj_juntos_e_recusado(api_client, pedido):
    resposta = _checkout(api_client, pedido, fiscal_customer_cpf=CPF, fiscal_customer_cnpj=CNPJ)

    assert resposta.status_code == 400
    assert _gravado(pedido) == ("", "")


def test_trocar_de_cpf_para_cnpj_mandando_os_dois_campos(api_client, pedido):
    """É o que a web e o desktop fazem: o documento que sai vai vazio."""
    _checkout(api_client, pedido, fiscal_customer_cpf=CPF, fiscal_customer_cnpj="")
    resposta = _checkout(api_client, pedido, fiscal_customer_cpf="", fiscal_customer_cnpj=CNPJ)

    assert resposta.status_code == 200
    assert _gravado(pedido) == ("", CNPJ)


def test_mandar_so_o_cnpj_com_cpf_gravado_e_recusado(api_client, pedido):
    """Contrato: quem troca de documento manda os dois. Mandar só um, com o outro
    gravado, é ambíguo — o servidor recusa em vez de adivinhar qual vale."""
    _checkout(api_client, pedido, fiscal_customer_cpf=CPF)

    resposta = _checkout(api_client, pedido, fiscal_customer_cnpj=CNPJ)

    assert resposta.status_code == 400
    assert _gravado(pedido) == (CPF, "")


def test_limpar_o_cnpj(api_client, pedido):
    _checkout(api_client, pedido, fiscal_customer_cpf="", fiscal_customer_cnpj=CNPJ)

    assert _checkout(api_client, pedido, fiscal_customer_cpf="", fiscal_customer_cnpj="").status_code == 200
    assert _gravado(pedido) == ("", "")


@pytest.fixture
def emitivel(pedido, account, restaurant, branch):
    FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch, provider=ManualFiscalProvider.name,
        cnpj="11222333000181", uf="SP", environment=FiscalConfig.ENV_HOMOLOGATION, series=1, next_number=1,
        corporate_name="Loja Teste LTDA",
    )
    return pedido


def test_nota_leva_o_cnpj_alfanumerico_ate_a_focus_e_ao_danfe(api_client, emitivel, manager_user):
    from apps.invoices.services import _danfe_nfce_text, emit_fiscal_invoice

    _checkout(api_client, emitivel, fiscal_customer_cpf="", fiscal_customer_cnpj="12.abc.345/01de-35")
    with tenant_context(emitivel.account):
        emitivel.refresh_from_db()
        emit_fiscal_invoice(emitivel, user=manager_user)
        nota = Invoice.all_objects.get(order=emitivel)
        payload = FocusNfeProvider()._build_payload(nota, nota.fiscal_config if hasattr(nota, "fiscal_config") else FiscalConfig.objects.get(restaurant=emitivel.restaurant))
        danfe = _danfe_nfce_text(nota, FiscalConfig.objects.get(restaurant=emitivel.restaurant))

    assert nota.recipient_cnpj == CNPJ_ALFA
    assert not nota.recipient_cpf
    assert payload["cnpj_destinatario"] == CNPJ_ALFA
    assert "cpf_destinatario" not in payload
    assert f"CNPJ: {CNPJ_ALFA}" in danfe


def test_emitir_com_cnpj_invalido_e_recusado_sem_criar_nota(emitivel, manager_user):
    from django.core.exceptions import ValidationError

    from apps.invoices.services import emit_fiscal_invoice

    with tenant_context(emitivel.account):
        with pytest.raises(ValidationError):
            emit_fiscal_invoice(emitivel, cnpj="11222333000182", user=manager_user)
        assert not Invoice.all_objects.filter(order=emitivel).exists()


@pytest.mark.parametrize("campo", ["cpf", "cnpj"])
def test_emitir_com_documento_em_lista_e_recusado(emitivel, manager_user, campo):
    from django.core.exceptions import ValidationError

    from apps.invoices.services import emit_fiscal_invoice

    with tenant_context(emitivel.account):
        with pytest.raises(ValidationError):
            emit_fiscal_invoice(emitivel, user=manager_user, **{campo: [CPF if campo == "cpf" else CNPJ]})
        assert not Invoice.all_objects.filter(order=emitivel).exists()


@pytest.mark.parametrize("campo", ["fiscal_customer_cpf", "fiscal_customer_cnpj"])
def test_documento_em_lista_e_400(api_client, pedido, campo):
    """`["52998224725"]` passava: virava texto e perdia os colchetes."""
    valor = [CPF] if campo == "fiscal_customer_cpf" else [CNPJ]

    assert _checkout(api_client, pedido, **{campo: valor}).status_code == 400
    assert _gravado(pedido) == ("", "")


def test_valor_total_nao_muda_com_documento(api_client, pedido):
    """Identificar o destinatário não mexe em dinheiro."""
    antes = Decimal(_checkout(api_client, pedido, fiscal_customer_cpf="").data["total"])
    depois = Decimal(_checkout(api_client, pedido, fiscal_customer_cpf="", fiscal_customer_cnpj=CNPJ).data["total"])

    assert antes == depois
