"""Adoção: a linha que o destino criou sozinho cede lugar à identidade da origem.

O caso real: aplicar um `restaurant` da nuvem dispara, na loja, o signal que
cria a Branch espelho — com UUID local. O evento `branch` da nuvem chega com o
MESMO (restaurante, nome) e outro UUID, e o índice único recusa. Sem adoção, o
evento tenta até morrer e as duas pontas ficam divergentes para sempre.
"""
import uuid

import pytest

from apps.restaurants.models import Branch, Restaurant
from apps.synchronization.constants import Direction, EventStatus, NodeType, Operation
from apps.synchronization.models import SyncConflict, SyncEvent
from apps.synchronization.services import adoption, apply, crypto

pytestmark = pytest.mark.django_db


def _evento(conta, origem, destino, *, entity_type, entity_id, fields, sequence=1, version=10):
    payload = {
        "schema_version": 1, "entity_type": entity_type, "entity_id": str(entity_id),
        "entity_version": version, "origin_node_id": str(origem.id), "fields": fields,
    }
    return SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino, direction=Direction.INBOUND,
        sequence=sequence, entity_type=entity_type, entity_id=str(entity_id),
        operation=Operation.UPSERT, entity_version=version, payload=payload,
        payload_checksum=crypto.checksum(payload), status=EventStatus.RECEIVED,
    )


def test_branch_criada_por_signal_cede_lugar(como_loja, conta, no_nuvem, no_loja):
    restaurante_id = uuid.uuid4()
    apply.apply_event(_evento(
        conta, no_nuvem, no_loja, entity_type="restaurant", entity_id=restaurante_id,
        fields={"account_id": str(conta.id), "legal_name": "A LTDA",
                "trade_name": "Rest A", "is_active": True}))

    # O signal do domínio criou a Branch espelho, com UUID local.
    local = Branch.all_objects.get(restaurant_id=restaurante_id)
    id_da_nuvem = uuid.uuid4()
    assert local.pk != id_da_nuvem

    aplicou = apply.apply_event(_evento(
        conta, no_nuvem, no_loja, entity_type="branch", entity_id=id_da_nuvem,
        fields={"account_id": str(conta.id), "restaurant_id": str(restaurante_id),
                "name": "Rest A"}, sequence=2))

    assert aplicou is True
    assert Branch.all_objects.filter(restaurant_id=restaurante_id).count() == 1
    # E agora ela tem a identidade da NUVEM — que é o ponto.
    assert Branch.all_objects.get(restaurant_id=restaurante_id).pk == id_da_nuvem


def test_nao_adota_linha_que_ja_veio_da_sincronizacao(como_loja, conta, no_nuvem, no_loja):
    """Adotar uma linha já sincronizada seria apagar um registro do outro lado."""
    restaurante_id, primeira = uuid.uuid4(), uuid.uuid4()
    apply.apply_event(_evento(
        conta, no_nuvem, no_loja, entity_type="restaurant", entity_id=restaurante_id,
        fields={"account_id": str(conta.id), "legal_name": "B LTDA",
                "trade_name": "Rest B", "is_active": True}))
    apply.apply_event(_evento(
        conta, no_nuvem, no_loja, entity_type="branch", entity_id=primeira,
        fields={"account_id": str(conta.id), "restaurant_id": str(restaurante_id),
                "name": "Rest B"}, sequence=2))
    assert Branch.all_objects.filter(pk=primeira).exists()

    # Outro evento, mesma chave única, id diferente: agora NÃO pode adotar.
    segunda = uuid.uuid4()
    aplicou = apply.apply_event(_evento(
        conta, no_nuvem, no_loja, entity_type="branch", entity_id=segunda,
        fields={"account_id": str(conta.id), "restaurant_id": str(restaurante_id),
                "name": "Rest B"}, sequence=3))

    assert aplicou is False
    assert Branch.all_objects.filter(pk=primeira).exists()  # a de antes continua lá
    assert not Branch.all_objects.filter(pk=segunda).exists()
    assert SyncConflict.objects.filter(entity_type="branch").exists()


def test_colisao_insoluvel_vira_conflito_e_sai_da_fila(como_loja, conta, no_nuvem, no_loja):
    """Retentar colisão de chave única é bater na parede até morrer."""
    restaurante_id, primeira = uuid.uuid4(), uuid.uuid4()
    apply.apply_event(_evento(
        conta, no_nuvem, no_loja, entity_type="restaurant", entity_id=restaurante_id,
        fields={"account_id": str(conta.id), "legal_name": "C LTDA",
                "trade_name": "Rest C", "is_active": True}))
    apply.apply_event(_evento(
        conta, no_nuvem, no_loja, entity_type="branch", entity_id=primeira,
        fields={"account_id": str(conta.id), "restaurant_id": str(restaurante_id),
                "name": "Rest C"}, sequence=2))

    evento = _evento(
        conta, no_nuvem, no_loja, entity_type="branch", entity_id=uuid.uuid4(),
        fields={"account_id": str(conta.id), "restaurant_id": str(restaurante_id),
                "name": "Rest C"}, sequence=3)
    apply.apply_event(evento)
    evento.refresh_from_db()

    assert evento.status == EventStatus.APPLIED  # saiu da fila
    assert evento.status != EventStatus.FAILED   # não fica retentando
    assert "UNIQUE" in evento.last_error or "unique" in evento.last_error.lower()


def test_a_nuvem_nao_adota_registro_que_nasceu_na_loja(como_nuvem, conta, no_nuvem, no_loja):
    """`order` é LOCAL_WINS: a loja manda. A nuvem nunca apaga por conta própria."""
    assert adoption.origin_is_authority("product", NodeType.LOCAL) is True
    assert adoption.origin_is_authority("product", NodeType.CLOUD) is False
    assert adoption.origin_is_authority("order", NodeType.CLOUD) is True
    assert adoption.origin_is_authority("order", NodeType.LOCAL) is False
    # Documento fiscal nunca adota, em sentido nenhum — e agora por ser
    # FISCAL, não por ser MANUAL. A nota virou LOCAL_WINS para a nuvem aceitar
    # as atualizações dela; sem a trava por entidade, isso teria autorizado a
    # nuvem a APAGAR uma nota dela para dar lugar à da loja.
    assert adoption.origin_is_authority("invoice", NodeType.LOCAL) is False
    assert adoption.origin_is_authority("invoice", NodeType.CLOUD) is False


def test_chave_unica_e_lida_do_model(como_loja):
    conjuntos = adoption.unique_field_sets(Branch)
    assert any("restaurant_id" in campos and "name" in campos for campos in conjuntos)
    # Campo unique simples também entra (Restaurant.cnpj).
    assert ("cnpj",) in adoption.unique_field_sets(Restaurant)
