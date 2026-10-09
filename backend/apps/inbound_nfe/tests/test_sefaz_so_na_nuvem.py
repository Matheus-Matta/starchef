"""A loja sincronizada não fala com a SEFAZ: a nota de entrada desce da nuvem.

Com a nota de entrada no clone, loja e nuvem consultando a SEFAZ cada uma por
conta própria criariam a mesma nota duas vezes, com ids diferentes.
"""
import pytest

from apps.inbound_nfe.services import certificate
from apps.inbound_nfe.services.sefaz_na_nuvem import (
    SefazSoNaNuvem,
    esta_instalacao_fala_com_a_sefaz,
)


def test_loja_sincronizada_nao_abre_o_certificado_para_a_sefaz(settings):
    settings.SYNC_ENABLED = True
    settings.SYNC_NODE_TYPE = "local"

    with pytest.raises(SefazSoNaNuvem):
        certificate.get_pfx_bytes_and_password(account=None)


@pytest.mark.parametrize(
    ("ligada", "tipo", "fala"),
    [(True, "local", False), (True, "cloud", True), (False, "local", True), (False, "", True)],
)
def test_quem_fala_com_a_sefaz(settings, ligada, tipo, fala):
    settings.SYNC_ENABLED = ligada
    settings.SYNC_NODE_TYPE = tipo

    assert esta_instalacao_fala_com_a_sefaz() is fala


@pytest.mark.django_db
def test_agendador_da_loja_sincronizada_nao_consulta(settings, monkeypatch):
    from apps.inbound_nfe import tasks

    settings.SYNC_ENABLED = True
    settings.SYNC_NODE_TYPE = "local"
    chamou = []
    monkeypatch.setattr(tasks.sync_branch_inbound_nfe, "delay", lambda *a: chamou.append(a))

    tasks.sync_all_inbound_nfe()

    assert chamou == []
