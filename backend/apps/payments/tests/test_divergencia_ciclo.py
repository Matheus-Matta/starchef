"""Aberta → analisada → regularizada (ou cancelada), e só para a frente.

409 é conflito de estado (já foi regularizada); 400 é entrada errada (faltou o
protocolo). Trocar um pelo outro faz o PDV reenviar para sempre.
"""
import pytest

from apps.payments.discrepancy import SalesDiscrepancy
from apps.payments.tests.conftest import URL, corpo

pytestmark = pytest.mark.django_db


@pytest.fixture
def divergencia(api_client, sessao_de_caixa, forma):
    criada = api_client.post(URL, corpo(sessao_de_caixa(), (forma("PIX"), "350.00")), format="json")
    assert criada.status_code == 201, criada.content
    return f"{URL}{criada.data['id']}/"


def test_caminho_feliz_analisa_e_regulariza(api_client, divergencia):
    analisada = api_client.post(f"{divergencia}review/", {}, format="json")
    assert analisada.status_code == 200
    assert analisada.data["status"] == "reviewed" and analisada.data["reviewed_at"]

    nota = "Denúncia espontânea protocolo 2026/123, orientada pelo contador."
    feita = api_client.post(f"{divergencia}regularize/", {"note": nota}, format="json")

    assert feita.status_code == 200
    assert feita.data["status"] == "regularized"
    assert feita.data["regularization_note"] == nota


def test_regularizar_sem_descrever_e_400(api_client, divergencia):
    resposta = api_client.post(f"{divergencia}regularize/", {"note": "  "}, format="json")

    assert resposta.status_code == 400
    assert SalesDiscrepancy.all_objects.get().status == "open"


def test_regularizada_nao_volta_nem_cancela_409(api_client, divergencia):
    api_client.post(f"{divergencia}regularize/", {"note": "Feito."}, format="json")

    assert api_client.post(f"{divergencia}review/", {}, format="json").status_code == 409
    assert api_client.post(f"{divergencia}cancel/", {"reason": "engano"}, format="json").status_code == 409
    assert api_client.post(f"{divergencia}regularize/", {"note": "de novo"}, format="json").status_code == 409


def test_cancelar_exige_motivo_e_guarda_quem(api_client, divergencia, manager_user):
    assert api_client.post(f"{divergencia}cancel/", {}, format="json").status_code == 400

    cancelada = api_client.post(f"{divergencia}cancel/", {"reason": "Lançado em dobro."}, format="json")

    assert cancelada.status_code == 200
    linha = SalesDiscrepancy.all_objects.get()
    assert (linha.status, linha.cancel_reason, linha.cancelled_by_id) == (
        "cancelled", "Lançado em dobro.", manager_user.pk
    )


def test_operador_de_caixa_nao_decide(caixa_client, divergencia):
    for rota, dados in (("review/", {}), ("regularize/", {"note": "x"}), ("cancel/", {"reason": "x"})):
        assert caixa_client.post(f"{divergencia}{rota}", dados, format="json").status_code == 403
    assert SalesDiscrepancy.all_objects.get().status == "open"


def test_corpo_que_nao_e_objeto_e_400(api_client, divergencia):
    assert api_client.post(f"{divergencia}regularize/", ["x"], format="json").status_code == 400


@pytest.mark.django_db(transaction=True)
def test_dois_gerentes_ao_mesmo_tempo_so_um_decide(api_client, divergencia):
    """A trava é do banco e o estado é RELIDO depois dela: um regulariza, o
    outro recebe 409 — nunca os dois gravando por cima um do outro."""
    import threading
    from functools import partial

    from django.db import connection

    if connection.vendor != "postgresql":
        # No SQLite a segunda escrita espera o arquivo e pode sair 503 (banco
        # ocupado): a corrida que importa é a do Postgres, onde roda a nuvem.
        pytest.skip("A corrida só é real no Postgres.")

    respostas = []
    barreira = threading.Barrier(2)

    def agir(rota, dados):
        try:
            barreira.wait()
            respostas.append(api_client.post(f"{divergencia}{rota}", dados, format="json").status_code)
        finally:
            connection.close()

    linhas = [
        threading.Thread(target=partial(agir, "regularize/", {"note": "Feito pelo A."})),
        threading.Thread(target=partial(agir, "cancel/", {"reason": "Cancelado pelo B."})),
    ]
    for linha in linhas:
        linha.start()
    for linha in linhas:
        linha.join()

    assert sorted(respostas) == [200, 409]
    assert SalesDiscrepancy.all_objects.get().status in {"regularized", "cancelled"}
