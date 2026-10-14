"""O perfil Balança consegue fazer TUDO o que a tela da Balança Rápida faz.

O PDV abre direto na estação para esse perfil; se uma só das rotas que ela
chama recusasse o perfil, a tela abriria e travaria. Aqui cada chamada da tela
é feita com o perfil, na ordem da tela: carregar, pesar e lançar na comanda.
"""
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import UserProfile
from apps.accounts.role_catalog import CODE_SCALE, ensure_system_roles
from apps.core.tenant import tenant_context
from apps.menu.models import Product, ProductCategory
from apps.orders.models import CommandItem
from apps.printers.models import Printer, Scale
from apps.restaurants.models import Command, TableSector

pytestmark = pytest.mark.django_db


@pytest.fixture
def operador(account, restaurant, branch):
    user = User.objects.create_user(username="pesagem", password="x")
    UserProfile.objects.create(account=account, user=user, role=ensure_system_roles(account)[CODE_SCALE],
                               restaurant=restaurant, branch=branch)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@pytest.fixture
def estacao(account, restaurant, branch):
    with tenant_context(account):
        cat = ProductCategory.objects.create(account=account, restaurant=restaurant, branch=branch, name="Buffet")
        kg = Product.objects.create(account=account, restaurant=restaurant, branch=branch, category=cat,
                                    name="Prato por quilo", internal_code=f"K{uuid.uuid4().hex[:6]}",
                                    sale_price=Decimal("59.90"), pricing_unit=Product.PRICING_KG)
        setor = TableSector.objects.create(account=account, restaurant=restaurant, branch=branch, name="Balança")
        impressora = Printer.objects.create(account=account, restaurant=restaurant, branch=branch,
                                            name="Balança 1", sector=setor, is_active=True)
        balanca = Scale.objects.create(account=account, restaurant=restaurant, branch=branch, name="Buffet",
                                       product=kg, printer=impressora, weighing_mode=Scale.MODE_COMMAND)
        comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=17)
    return {"balanca": balanca, "comanda": comanda, "restaurante": restaurant}


def test_carrega_pesa_e_lanca_na_comanda_com_o_perfil_balanca(operador, estacao, account):
    restaurante = str(estacao["restaurante"].pk)
    for rota in ("/api/v1/restaurants/", "/api/v1/menu/products/", "/api/v1/scales/", "/api/v1/printers/"):
        resposta = operador.get(rota, {"restaurant": restaurante})
        assert resposta.status_code == 200, (rota, resposta.status_code, resposta.data)

    balanca = estacao["balanca"]
    leitura = operador.post("/api/v1/scales/readings/", {
        "scale": str(balanca.pk), "weight_kg": "0.450", "tare_kg": "0.000", "is_stable": True,
        "source": "agent", "for_checkout": True,
    }, format="json")
    assert leitura.status_code == 201, leitura.data

    lancamento = operador.post(f"/api/v1/scales/{balanca.pk}/checkout-command/", {
        "command_code": estacao["comanda"].code, "scale_reading": leitura.data["id"],
    }, format="json")
    assert lancamento.status_code in (200, 201), lancamento.data
    with tenant_context(account):
        assert CommandItem.objects.filter(command=estacao["comanda"]).exists()


def test_o_que_a_tela_faz_com_o_trabalho_de_impressao(operador, estacao, account):
    """Nota de pesagem: ler o trabalho e marcar como impresso."""
    from apps.printers.models import PrintJob

    with tenant_context(account):
        job = PrintJob.objects.create(account=account, restaurant=estacao["restaurante"],
                                      printer=estacao["balanca"].printer, job_type=PrintJob.TYPE_WEIGH,
                                      status=PrintJob.STATUS_RENDERED, payload={"text_content": "x"})
    assert operador.get(f"/api/v1/print-jobs/{job.pk}/").status_code == 200
    assert operador.post(f"/api/v1/print-jobs/{job.pk}/mark-printed/", {}, format="json").status_code == 200


def test_a_etiqueta_nasce_reservada_para_a_estacao_que_imprime_ela_mesma(operador, estacao, account):
    """A Balança Rápida imprime a própria etiqueta, e nenhum outro PC a pega.

    Antes o trabalho nascia `pending` e QUALQUER PDV do restaurante podia
    reservá-lo. Com a impressora USB/serial ligada no PC da balança, outro PC
    reservava, tentava a porta dele (que não tem a impressora) e a etiqueta
    não saía. Com `imprime_aqui`, ela nasce reservada para o terminal da
    balança, fora da lista que os agentes dos PDVs consultam.
    """
    from apps.printers.models import PrintJob

    balanca = estacao["balanca"]
    lancamento = operador.post(
        f"/api/v1/scales/{balanca.pk}/checkout-command/",
        {"command_code": estacao["comanda"].code, "weight_kg": "0.450", "print": True,
         "imprime_aqui": True},
        format="json", HTTP_X_TERMINAL_ID="pc-balanca-1",
    )
    assert lancamento.status_code == 201, lancamento.data
    job = lancamento.data["print_job"]
    assert job["status"] == PrintJob.STATUS_CLAIMED
    assert job["payload"]["claimed_by_terminal"] == "pc-balanca-1"

    pendentes = operador.get("/api/v1/print-jobs/", {
        "restaurant": str(estacao["restaurante"].pk),
        "status__in": "scheduled,pending,rendered"})
    assert job["id"] not in {j["id"] for j in pendentes.data["results"]}

    impresso = operador.post(f"/api/v1/print-jobs/{job['id']}/mark-printed/", {}, format="json")
    assert impresso.status_code == 200, impresso.data
    with tenant_context(account):
        assert PrintJob.objects.get(pk=job["id"]).status == PrintJob.STATUS_PRINTED


def test_sem_imprime_aqui_a_etiqueta_segue_para_os_agentes(operador, estacao):
    balanca = estacao["balanca"]
    lancamento = operador.post(
        f"/api/v1/scales/{balanca.pk}/checkout-command/",
        {"command_code": estacao["comanda"].code, "weight_kg": "0.450", "print": True},
        format="json",
    )
    assert lancamento.status_code == 201, lancamento.data
    assert lancamento.data["print_job"]["status"] == "pending"


def test_a_estacao_devolve_a_etiqueta_que_nao_conseguiu_imprimir(operador, estacao):
    balanca = estacao["balanca"]
    job = operador.post(
        f"/api/v1/scales/{balanca.pk}/checkout-command/",
        {"command_code": estacao["comanda"].code, "weight_kg": "0.450", "print": True,
         "imprime_aqui": True},
        format="json", HTTP_X_TERMINAL_ID="pc-balanca-1",
    ).data["print_job"]

    devolvida = operador.post(f"/api/v1/print-jobs/{job['id']}/release/", {}, format="json")

    assert devolvida.status_code == 200, devolvida.data
    assert devolvida.data["released"] is True
