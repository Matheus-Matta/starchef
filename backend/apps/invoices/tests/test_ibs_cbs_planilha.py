"""A planilha de perfis fiscais com IBS/CBS: exportar, mexer no Excel, importar.

A planilha usa as colunas do formulário (`resources.js`), então as colunas de
IBS/CBS entram nela sozinhas. O defeito que este arquivo impede é o do Excel:
ele lê CST e cClassTrib como número e apaga o zero à esquerda. `000` volta
como `0` e `000001` como `1`, e sem a correção TODA linha reimportada era
recusada ("CST 0 não é suportado").
"""
from unittest import mock

import pytest

from apps.core.tenant import tenant_context
from apps.imports.services import run_import
from apps.invoices.models import FiscalProfile

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def financeiro(account):
    """Perfil fiscal é do módulo financeiro: sem ele a rota responde 403."""
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])


def _importar(cliente, linhas):
    with mock.patch("apps.imports.tasks.run_import_task.delay"):
        resposta = cliente.post("/api/v1/imports/", {
            "endpoint": "/fiscal/profiles/", "key": "name", "rows": linhas,
        }, format="json")
    assert resposta.status_code == 202, resposta.data
    return run_import(resposta.data["id"])


def test_reimportar_planilha_aberta_no_excel_devolve_os_zeros(admin_client, account):
    with tenant_context(account):
        FiscalProfile.objects.create(account=account, name="Refrigerante", ncm="22021000")

    job = _importar(admin_client, [
        {"name": "Refrigerante", "ibs_cbs_cst": "0", "ibs_cbs_cclass_trib": "1"},
        {"name": "Prato reduzido", "ncm": "21069090", "ibs_cbs_cst": "200",
         "ibs_cbs_cclass_trib": "200003", "ibs_cbs_reducao": 60},
    ])

    assert job.errors == []
    assert (job.created_count, job.updated_count) == (1, 1)
    with tenant_context(account):
        refri = FiscalProfile.objects.get(name="Refrigerante")
        prato = FiscalProfile.objects.get(name="Prato reduzido")
    assert (refri.ibs_cbs_cst, refri.ibs_cbs_cclass_trib) == ("000", "000001")
    assert (prato.ibs_cbs_cst, prato.ibs_cbs_reducao) == ("200", 60)


def test_planilha_com_regra_impossivel_aponta_a_linha(admin_client, account):
    """Completar zeros não vira aceitar qualquer coisa: o cClassTrib de outro
    CST continua recusado, e a mensagem diz qual linha corrigir."""
    job = _importar(admin_client, [
        {"name": "Cerveja", "ibs_cbs_cst": "0", "ibs_cbs_cclass_trib": "200003"},
    ])

    assert len(job.errors) == 1 and job.errors[0].startswith("Linha 2:")
    assert "200003" in job.errors[0]
