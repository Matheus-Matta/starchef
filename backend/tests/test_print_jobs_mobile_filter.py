import pytest

from apps.printers.models import Printer, PrintJob
from conftest import _authenticated_client


@pytest.mark.django_db
def test_celular_filtra_a_fila_por_tipo_e_impressora_na_consulta(
    waiter_user, account, restaurant, branch
):
    """A fila acumula recibos que ninguém imprime; o filtro vai no servidor.

    Filtrar só no aparelho deixava a primeira página (a mais antiga) cheia de
    recibos, e a comanda nova nunca chegava ao celular do garçom.
    """
    base = {"account": account, "restaurant": restaurant, "branch": branch}
    cozinha = Printer.objects.create(**base, name="Cozinha", connection_type="network", host="10.0.0.5")
    caixa = Printer.objects.create(**base, name="Caixa", connection_type="network", host="10.0.0.6")
    for _ in range(3):
        PrintJob.objects.create(**base, printer=cozinha, job_type=PrintJob.TYPE_RECEIPT, status="pending")
    comanda = PrintJob.objects.create(
        **base, printer=cozinha, job_type=PrintJob.TYPE_KITCHEN, status="rendered"
    )
    PrintJob.objects.create(**base, printer=caixa, job_type=PrintJob.TYPE_KITCHEN, status="pending")

    response = _authenticated_client(waiter_user).get(
        "/api/v1/print-jobs/",
        {
            "restaurant": str(restaurant.id),
            "status__in": "pending,rendered",
            "job_type__in": "kitchen_ticket,bar_ticket,kitchen_cancellation",
            "printer__in": str(cozinha.id),
        },
    )

    assert response.status_code == 200, response.data
    assert [row["id"] for row in response.data["results"]] == [str(comanda.id)]
