"""O perfil de acesso chega na loja COM as permissões dele.

Dois defeitos irmãos fecham aqui.

`accounts.Permission` estava no catálogo, mas é catálogo global sem conta — e o
outbox exige conta. Cada `sync_permissions` gerava dezenas de eventos
descartados na hora ("permission sem conta; evento descartado"), enchendo o log
de produção com ruído que escondia problema de verdade.

E o vínculo perfil→permissões nunca viajou, porque a serialização só olhava
campos concretos e ManyToMany não é um deles. O usuário sincronizava, o perfil
sincronizava, e o perfil chegava SEM PERMISSÃO NENHUMA.
"""
import uuid

import pytest

from apps.accounts.models import Permission, Role
from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import apply, crypto, serialization
from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db


@pytest.fixture
def permissoes(db):
    """`get_or_create` porque o catálogo JÁ EXISTE depois do `migrate`.

    É justamente a razão de `permission` não sincronizar: os dois bancos
    chegam ao mesmo conteúdo sozinhos, provisionados pelo mesmo código.
    """
    return [
        Permission.objects.get_or_create(code="orders.view",
                                         defaults={"name": "Ver pedidos"})[0],
        Permission.objects.get_or_create(code="cash.open",
                                         defaults={"name": "Abrir caixa"})[0],
    ]


def _evento_de_perfil(conta, origem, destino, *, role_id, codigos, versao=10**18,
                      sequencia=1):
    payload = {
        "schema_version": 1,
        "entity_type": "role",
        "entity_id": str(role_id),
        "entity_version": versao,
        "fields": {
            "account_id": str(conta.id),
            "code": "gerente",
            "name": "Gerente",
            "permissions": codigos,
        },
    }
    return SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino,
        direction=Direction.INBOUND, sequence=sequencia, entity_type="role",
        entity_id=str(role_id), operation=Operation.UPSERT, entity_version=versao,
        payload=payload, payload_checksum=crypto.checksum(payload),
        status=EventStatus.RECEIVED,
    )


# ── permission fora do catálogo ─────────────────────────────────────────────
def test_permission_nao_sincroniza_mais():
    assert registry.get("permission") is None, (
        "catálogo global sem conta: cada evento nascia e era descartado na hora"
    )


def test_a_decisao_esta_registrada():
    from apps.synchronization.decisions import EXCLUDED

    assert "accounts.Permission" in EXCLUDED


def test_role_nao_depende_mais_de_permission():
    assert "permission" not in registry.require("role").dependencies


# ── o vínculo viaja pela chave natural ──────────────────────────────────────
def test_o_perfil_serializa_as_permissoes_por_codigo(conta, permissoes):
    perfil = Role.objects.create(account=conta, code="gerente", name="Gerente")
    perfil.permissions.set(permissoes)

    dados = serialization.serialize(perfil, registry.require("role"))

    assert dados["permissions"] == ["cash.open", "orders.view"], (
        "por CÓDIGO e ordenado: o id é diferente em cada instalação, e a ordem "
        "estável impede o checksum de mudar à toa"
    )


def test_o_perfil_chega_com_as_permissoes(como_loja, conta, no_nuvem, no_loja, permissoes):
    """O caso que motivou tudo: antes, o perfil chegava vazio."""
    role_id = uuid.uuid4()
    evento = _evento_de_perfil(
        conta, no_nuvem, no_loja, role_id=role_id,
        codigos=["orders.view", "cash.open"],
    )

    assert apply.apply_event(evento) is True

    perfil = Role.all_objects.get(pk=role_id)
    assert sorted(perfil.permissions.values_list("code", flat=True)) == [
        "cash.open", "orders.view",
    ]


def test_codigo_desconhecido_e_ignorado_sem_derrubar_o_resto(
    como_loja, conta, no_nuvem, no_loja, permissoes
):
    """Uma nuvem mais nova pode conhecer permissão que esta loja ainda não tem.

    Recusar o evento inteiro deixaria o perfil sem vínculo NENHUM — pior que
    ficar com os que dão para resolver.
    """
    role_id = uuid.uuid4()
    evento = _evento_de_perfil(
        conta, no_nuvem, no_loja, role_id=role_id,
        codigos=["orders.view", "recurso.do.futuro"],
    )

    assert apply.apply_event(evento) is True

    perfil = Role.all_objects.get(pk=role_id)
    assert list(perfil.permissions.values_list("code", flat=True)) == ["orders.view"]


def test_o_vinculo_e_refeito_e_nao_acumulado(como_loja, conta, no_nuvem, no_loja, permissoes):
    """Remover uma permissão na nuvem tem de removê-la na loja."""
    role_id = uuid.uuid4()
    apply.apply_event(_evento_de_perfil(
        conta, no_nuvem, no_loja, role_id=role_id,
        codigos=["orders.view", "cash.open"], versao=10**18,
    ))

    apply.apply_event(_evento_de_perfil(
        conta, no_nuvem, no_loja, role_id=role_id,
        codigos=["orders.view"], versao=10**18 + 1, sequencia=2,
    ))

    perfil = Role.all_objects.get(pk=role_id)
    assert list(perfil.permissions.values_list("code", flat=True)) == ["orders.view"]
