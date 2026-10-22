"""A fila do PDV vem filtrada pelas impressoras do terminal (`printer__in`).

O PDV pedia os 100 trabalhos pendentes do restaurante inteiro e descartava os
de impressora com impressão automática desligada — de novo a cada consulta:
6.000 linhas de log em 50 minutos. Agora ele pede só as impressoras dele, e
das manuais só a nota de pesagem. Se o servidor ignorasse o filtro, o PDV
voltaria a receber tudo sem ninguém perceber.
"""
import pytest

from apps.printers.models import Printer, PrintJob

pytestmark = pytest.mark.django_db


def _impressora(account, restaurant, branch, nome):
    return Printer.objects.create(account=account, restaurant=restaurant, branch=branch, name=nome)


def _trabalho(account, restaurant, branch, admin_user, printer, job_type):
    return PrintJob.all_objects.create(
        account=account, restaurant=restaurant, branch=branch, printer=printer, job_type=job_type,
        status=PrintJob.STATUS_PENDING, payload={}, created_by=admin_user, updated_by=admin_user,
    )


def test_printer_in_e_job_type_trazem_so_o_que_o_terminal_imprime(
    admin_client, account, restaurant, branch, admin_user,
):
    cozinha = _impressora(account, restaurant, branch, "Cozinha")
    caixa = _impressora(account, restaurant, branch, "Caixa")
    outra = _impressora(account, restaurant, branch, "Outra estação")
    da_cozinha = _trabalho(account, restaurant, branch, admin_user, cozinha, PrintJob.TYPE_KITCHEN)
    pesagem_no_caixa = _trabalho(account, restaurant, branch, admin_user, caixa, PrintJob.TYPE_WEIGH)
    _trabalho(account, restaurant, branch, admin_user, caixa, PrintJob.TYPE_RECEIPT)
    _trabalho(account, restaurant, branch, admin_user, outra, PrintJob.TYPE_KITCHEN)
    _trabalho(account, restaurant, branch, admin_user, None, PrintJob.TYPE_RECEIPT)

    def ids(**query):
        resposta = admin_client.get("/api/v1/print-jobs/", {
            "restaurant": str(restaurant.id), "status__in": "scheduled,pending,rendered", **query,
        })
        assert resposta.status_code == 200
        return {item["id"] for item in resposta.json()["results"]}

    assert ids(printer__in=str(cozinha.id)) == {str(da_cozinha.id)}
    assert ids(printer__in=str(caixa.id), job_type=PrintJob.TYPE_WEIGH) == {str(pesagem_no_caixa.id)}
