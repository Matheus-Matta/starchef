"""A etiqueta da Balança Rápida não volta para a fila dos PDVs.

Ela nasce reservada para a estação da balança, que imprime e confirma
(`mark-printed`). Com o servidor lento, a confirmação se perdia: em 5 minutos a
reserva vencia, o trabalho voltava para a fila e um PDV imprimia de novo — e de
novo, a cada confirmação perdida. Relato da loja: "a comanda 7 saiu umas 5
vezes seguidas". A etiqueta é DA estação; outro PC nem alcança a impressora
USB dela. Se faltar, quem resolve é o "Reimprimir".
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.printers.models import PrintJob

pytestmark = pytest.mark.django_db


def _trabalho(account, restaurant, branch, admin_user, payload):
    return PrintJob.all_objects.create(
        account=account, restaurant=restaurant, branch=branch, job_type=PrintJob.TYPE_WEIGH,
        status=PrintJob.STATUS_CLAIMED, payload=payload, created_by=admin_user, updated_by=admin_user,
    )


def _envelhecer(*jobs):
    PrintJob.all_objects.filter(pk__in=[j.pk for j in jobs]).update(
        updated_at=timezone.now() - timedelta(minutes=10))


def test_reservada_para_a_balanca_continua_dela(admin_client, account, restaurant, branch, admin_user):
    da_balanca = _trabalho(account, restaurant, branch, admin_user,
                           {"claimed_by_terminal": "balanca-1", "imprime_na_estacao": True})
    de_um_pdv = _trabalho(account, restaurant, branch, admin_user, {"claimed_by_terminal": "pdv-2"})
    _envelhecer(da_balanca, de_um_pdv)

    admin_client.get("/api/v1/print-jobs/", headers={"X-Terminal-Id": "pdv-3"})

    da_balanca.refresh_from_db()
    de_um_pdv.refresh_from_db()
    assert da_balanca.status == PrintJob.STATUS_CLAIMED
    assert de_um_pdv.status == PrintJob.STATUS_PENDING  # a regra antiga segue para os PDVs


def test_a_pesagem_que_a_estacao_imprime_nasce_marcada(admin_client, balanca, comandas):
    resposta = admin_client.post(
        f"/api/v1/scales/{balanca.id}/checkout-command/",
        {"comanda_automatica": True, "weight_kg": "0.400", "print": True, "imprime_aqui": True},
        format="json",
        headers={"X-Terminal-Id": "balanca-1"},
    )

    assert resposta.status_code == 201, resposta.data
    job = PrintJob.all_objects.get(pk=resposta.data["print_job"]["id"])
    assert job.status == PrintJob.STATUS_CLAIMED
    assert job.payload["imprime_na_estacao"] is True
