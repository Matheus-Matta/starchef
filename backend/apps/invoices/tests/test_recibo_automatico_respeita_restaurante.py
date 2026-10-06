"""O recibo que o SERVIDOR imprime sozinho também obedece ao restaurante.

O pagamento sem terminal identificado (o PDV desviando para a nuvem, uma
integração) é impresso pelo próprio servidor (`print_sale_documents`). Esse
caminho ignorava `auto_print_receipt`: a loja desligava o recibo no painel e
ele continuava saindo. O DANFE da NFC-e não depende da chave.
"""
import pytest

from apps.invoices.models import Invoice
from apps.invoices.tests.test_auto_issue_on_payment import (  # noqa: F401 — fixtures
    _AutoIssueProvider,
    _no_cash_register_required,
    _pay,
    cash_method,
    fiscal_config,
    order,
    printer,
    product,
)
from apps.printers.models import PrintJob

pytestmark = pytest.mark.django_db

# Os parâmetros abaixo SÃO as fixtures importadas (o pytest casa pelo nome);
# por isso o F811 de "redefinição" nas assinaturas é esperado.


def test_recibo_desligado_nao_sai_mas_o_danfe_sai(
    django_capture_on_commit_callbacks, restaurant, order, cash_method, manager_user,  # noqa: F811
    printer, fiscal_config,  # noqa: F811
):
    restaurant.auto_print_receipt = False
    restaurant.save(update_fields=["auto_print_receipt"])

    with django_capture_on_commit_callbacks(execute=True):
        _pay(order, cash_method, manager_user)

    assert Invoice.all_objects.get(order=order).status == Invoice.STATUS_ISSUED
    tipos = [job.job_type for job in PrintJob.all_objects.filter(order=order)]
    assert tipos == [PrintJob.TYPE_FISCAL]


def test_recibo_ligado_continua_saindo(
    django_capture_on_commit_callbacks, order, cash_method, manager_user, printer,  # noqa: F811
):
    with django_capture_on_commit_callbacks(execute=True):
        _pay(order, cash_method, manager_user)

    tipos = [job.job_type for job in PrintJob.all_objects.filter(order=order)]
    assert tipos == [PrintJob.TYPE_RECEIPT]
