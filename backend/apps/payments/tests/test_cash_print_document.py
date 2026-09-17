"""Os comprovantes do caixa em texto, montados pelo servidor.

Quem poe no papel e o PDV — e ele quem enxerga a impressora do balcao —, mas o
conteudo sai daqui. O relatorio de fechamento e o documento que o operador
assina e o gerente confere: duas implementacoes divergiriam no primeiro ajuste
de regra, e a divergencia apareceria no papel assinado.
"""

import pytest

from apps.payments.models import CashMovement, CashRegister, CashStation

pytestmark = pytest.mark.django_db


@pytest.fixture
def station(account, restaurant, admin_user):
    return CashStation.all_objects.create(
        account=account,
        restaurant=restaurant,
        name="Balcao 01",
        code="BALCAO-01",
        created_by=admin_user,
        updated_by=admin_user,
    )


@pytest.fixture
def session(account, restaurant, branch, admin_user, station):
    return CashRegister.all_objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        cash_station=station,
        opened_by=admin_user,
        status=CashRegister.STATUS_OPEN,
        opening_amount="150.00",
        expected_amount="150.00",
        opened_terminal_label="Caixa 01",
        created_by=admin_user,
        updated_by=admin_user,
    )


def _document(client, session, **query):
    return client.get(
        f"/api/v1/cash-register/{session.id}/print-document/", query
    )


def test_abertura_traz_o_valor_e_o_caixa(admin_client, session):
    resposta = _document(admin_client, session, document="opening")

    assert resposta.status_code == 200
    texto = resposta.json()["text_content"]
    assert "COMPROVANTE DE ABERTURA DE CAIXA" in texto
    assert "Balcao 01" in texto
    assert "150.00" in texto
    # A assinatura e o que transforma o papel em comprovante.
    assert "Assinatura" in texto


def test_fechamento_separa_a_gaveta_das_outras_formas(
    admin_client, session, admin_user, account
):
    """O operador confere duas coisas diferentes, e o papel precisa separa-las.

    A gaveta e dinheiro fisico; as outras formas ele confere contra os
    comprovantes da maquininha e do PIX. Somar tudo numa linha so faria a
    divergencia de dinheiro desaparecer dentro do total do dia.
    """
    CashMovement.all_objects.create(
        account=account,
        restaurant=session.restaurant,
        branch=session.branch,
        cash_register=session,
        operator=admin_user,
        movement_type=CashMovement.TYPE_OPENING,
        amount="150.00",
        created_by=admin_user,
        updated_by=admin_user,
    )
    CashMovement.all_objects.create(
        account=account,
        restaurant=session.restaurant,
        branch=session.branch,
        cash_register=session,
        operator=admin_user,
        movement_type=CashMovement.TYPE_WITHDRAWAL,
        amount="40.00",
        reason="Deposito bancario",
        created_by=admin_user,
        updated_by=admin_user,
    )

    resposta = _document(admin_client, session, document="closing")

    assert resposta.status_code == 200
    texto = resposta.json()["text_content"]
    assert "RELATORIO DE FECHAMENTO DE CAIXA" in texto
    assert "MOVIMENTO DA GAVETA (DINHEIRO)" in texto
    assert "VENDAS POR FORMA DE PAGAMENTO" in texto
    assert "(+) Abertura (troco)" in texto
    assert "(-) Sangrias" in texto
    assert "40.00" in texto


def test_sangria_precisa_do_lancamento(admin_client, session):
    # Sem o movimento nao ha comprovante possivel: o valor, o motivo e o
    # destino sao dele.
    resposta = _document(admin_client, session, document="withdrawal")

    assert resposta.status_code == 400


def test_sangria_traz_motivo_destino_e_quem_autorizou(
    admin_client, session, admin_user, account
):
    movimento = CashMovement.all_objects.create(
        account=account,
        restaurant=session.restaurant,
        branch=session.branch,
        cash_register=session,
        operator=admin_user,
        movement_type=CashMovement.TYPE_WITHDRAWAL,
        amount="80.00",
        reason="Troco insuficiente no cofre",
        destination="Cofre da loja",
        created_by=admin_user,
        updated_by=admin_user,
    )

    resposta = _document(
        admin_client,
        session,
        document="withdrawal",
        movement=str(movimento.id),
        authorized_by="Senha de acoes do caixa",
    )

    assert resposta.status_code == 200
    texto = resposta.json()["text_content"]
    assert "COMPROVANTE DE SANGRIA DE CAIXA" in texto
    assert "Valor retirado" in texto
    assert "80.00" in texto
    assert "Troco insuficiente no cofre" in texto
    assert "Cofre da loja" in texto
    assert "Senha de acoes do caixa" in texto


def test_documento_invalido_e_recusado(admin_client, session):
    resposta = _document(admin_client, session, document="qualquer-coisa")

    assert resposta.status_code == 400


def test_lancamento_de_outra_sessao_nao_vira_comprovante_desta(
    admin_client, session, admin_user, account, restaurant, branch, station
):
    """Um comprovante que misturasse sessoes seria uma fraude assinada."""
    outra = CashRegister.all_objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        opened_by=admin_user,
        status=CashRegister.STATUS_CLOSED,
        opening_amount="0.00",
        created_by=admin_user,
        updated_by=admin_user,
    )
    alheio = CashMovement.all_objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        cash_register=outra,
        operator=admin_user,
        movement_type=CashMovement.TYPE_WITHDRAWAL,
        amount="999.00",
        created_by=admin_user,
        updated_by=admin_user,
    )

    resposta = _document(
        admin_client, session, document="withdrawal", movement=str(alheio.id)
    )

    assert resposta.status_code == 400
