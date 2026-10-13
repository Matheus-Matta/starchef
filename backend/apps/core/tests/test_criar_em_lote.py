"""Criar em lote faz o mesmo que criar um a um — só que numa gravação.

`bulk_create` não dispara `post_save`, e é por ele que a sincronização e os
avisos de tempo real nascem (AGENTS.md: "QuerySet.update() não dispara
signal"). `criar_em_lote` grava de uma vez e dispara o `post_save` de cada
registro, então TODO receptor roda como num `save()`.
"""
from unittest import mock

import pytest
from django.db.models.signals import post_save

from apps.core.lote import atualizar_em_lote, criar_em_lote
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db


def _auditoria(account, n):
    return AuditLog(account=account, action=AuditLog.ACTION_CREATED, entity="Teste",
                    object_id=str(n), changes={}, metadata={})


def test_grava_tudo_numa_insercao_e_avisa_cada_um(account, django_assert_num_queries):
    recebidos = []

    def receptor(sender, instance, created, **kwargs):
        recebidos.append((sender, instance.object_id, created))

    post_save.connect(receptor, sender=AuditLog, dispatch_uid="teste-lote")
    try:
        with django_assert_num_queries(1):
            criados = criar_em_lote(AuditLog, [_auditoria(account, n) for n in range(5)])
    finally:
        post_save.disconnect(dispatch_uid="teste-lote", sender=AuditLog)

    assert len(criados) == 5
    assert AuditLog.all_objects.filter(entity="Teste").count() == 5
    assert recebidos == [(AuditLog, str(n), True) for n in range(5)]
    assert all(not obj._state.adding for obj in criados)


def test_lista_vazia_nao_vai_ao_banco(django_assert_num_queries):
    with django_assert_num_queries(0):
        assert criar_em_lote(AuditLog, []) == []


def test_preenche_criado_em_e_atualizado_em(account):
    (obj,) = criar_em_lote(AuditLog, [_auditoria(account, 1)])
    assert obj.created_at is not None and obj.updated_at is not None


def test_a_sincronizacao_recebe_cada_registro(account):
    with mock.patch("apps.synchronization.signals._registrar") as registrar, \
            mock.patch("apps.synchronization.signals._sincronizavel", return_value=True):
        criar_em_lote(AuditLog, [_auditoria(account, n) for n in range(3)])
    assert registrar.call_count == 3


def test_atualizar_em_lote_e_um_update_so_com_o_post_save_de_cada(account, django_assert_num_queries):
    objetos = criar_em_lote(AuditLog, [_auditoria(account, n) for n in range(4)])
    for objeto in objetos:
        objeto.reason = "revisado"
    recebidos = []

    def receptor(sender, instance, created, update_fields, **kwargs):
        recebidos.append((created, update_fields))

    post_save.connect(receptor, sender=AuditLog, dispatch_uid="teste-atualizar")
    try:
        with django_assert_num_queries(1):
            atualizar_em_lote(AuditLog, objetos, ["reason", "updated_at"])
    finally:
        post_save.disconnect(dispatch_uid="teste-atualizar", sender=AuditLog)

    assert AuditLog.all_objects.filter(entity="Teste", reason="revisado").count() == 4
    assert recebidos == [(False, frozenset({"reason", "updated_at"}))] * 4
