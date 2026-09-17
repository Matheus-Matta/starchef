"""Aplicação de evento: idempotência, ordem e conflito (§23.2, §23.3)."""
import uuid

import pytest

from apps.restaurants.models import Branch, Restaurant
from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncConflict, SyncEvent
from apps.synchronization.services import apply, crypto

pytestmark = pytest.mark.django_db


def _evento(conta, origem, destino, *, entity_type, entity_id, fields,
            sequence=1, operation=Operation.UPSERT, version=10):
    payload = {
        "schema_version": 1,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "entity_version": version,
        "origin_node_id": str(origem.id),
        "fields": fields,
    }
    return SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino,
        direction=Direction.INBOUND, sequence=sequence, entity_type=entity_type,
        entity_id=str(entity_id), operation=operation, entity_version=version,
        payload=payload, payload_checksum=crypto.checksum(payload),
        status=EventStatus.RECEIVED,
    )


def test_aplica_registro_novo(como_loja, conta, no_nuvem, no_loja):
    restaurante_id = uuid.uuid4()
    evento = _evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                     entity_id=restaurante_id,
                     fields={"account_id": str(conta.id), "legal_name": "Nova LTDA",
                             "trade_name": "Nova", "is_active": True})

    assert apply.apply_event(evento) is True
    assert Restaurant.all_objects.get(pk=restaurante_id).trade_name == "Nova"
    evento.refresh_from_db()
    assert evento.status == EventStatus.APPLIED


def test_mesmo_evento_duas_vezes_aplica_uma_vez(como_loja, conta, no_nuvem, no_loja):
    restaurante_id = uuid.uuid4()
    evento = _evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                     entity_id=restaurante_id,
                     fields={"account_id": str(conta.id), "legal_name": "X LTDA",
                             "trade_name": "X", "is_active": True})
    apply.apply_event(evento)
    evento.refresh_from_db()

    # Segunda passada: não reaplica e não duplica.
    assert apply.apply_event(evento) is False
    assert Restaurant.all_objects.filter(pk=restaurante_id).count() == 1


def test_evento_repetido_nao_gera_registro_duplicado(como_loja, conta, no_nuvem, no_loja):
    restaurante_id = uuid.uuid4()
    campos = {"account_id": str(conta.id), "legal_name": "Y LTDA",
              "trade_name": "Y", "is_active": True}
    primeiro = _evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                       entity_id=restaurante_id, fields=campos, sequence=1)
    apply.apply_event(primeiro)

    # Reenvio depois de timeout: mesmo entity_id, sequência nova.
    segundo = _evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                      entity_id=restaurante_id, fields=campos, sequence=2, version=10)
    apply.apply_event(segundo)
    assert Restaurant.all_objects.filter(pk=restaurante_id).count() == 1


def test_dependencia_faltando_vira_retentativa_nao_perda(como_loja, conta, no_nuvem, no_loja):
    """Filial antes do restaurante: falha retentável, o evento continua lá."""
    evento = _evento(conta, no_nuvem, no_loja, entity_type="branch",
                     entity_id=uuid.uuid4(),
                     fields={"account_id": str(conta.id),
                             "restaurant_id": str(uuid.uuid4()),
                             "name": "Filial órfã"})

    assert apply.apply_event(evento) is False
    evento.refresh_from_db()
    assert evento.status == EventStatus.FAILED
    assert evento.next_attempt_at is not None
    assert "ainda não existe aqui" in evento.last_error
    assert evento.payload["fields"]["name"] == "Filial órfã"


def test_ordem_correta_aplica_os_dois(como_loja, conta, no_nuvem, no_loja):
    restaurante_id, filial_id = uuid.uuid4(), uuid.uuid4()
    apply.apply_event(_evento(
        conta, no_nuvem, no_loja, entity_type="restaurant", entity_id=restaurante_id,
        fields={"account_id": str(conta.id), "legal_name": "Z LTDA",
                "trade_name": "Z", "is_active": True}, sequence=1))
    apply.apply_event(_evento(
        conta, no_nuvem, no_loja, entity_type="branch", entity_id=filial_id,
        fields={"account_id": str(conta.id), "restaurant_id": str(restaurante_id),
                "name": "Matriz"}, sequence=2))

    assert Branch.all_objects.filter(pk=filial_id).exists()


def test_versao_mais_antiga_e_ignorada(como_loja, conta, no_nuvem, no_loja):
    restaurante_id = uuid.uuid4()
    apply.apply_event(_evento(
        conta, no_nuvem, no_loja, entity_type="restaurant", entity_id=restaurante_id,
        fields={"account_id": str(conta.id), "legal_name": "Atual LTDA",
                "trade_name": "Atual", "is_active": True}, version=10**18))

    atrasado = _evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                       entity_id=restaurante_id,
                       fields={"account_id": str(conta.id), "legal_name": "Velha LTDA",
                               "trade_name": "Velha", "is_active": True},
                       sequence=2, version=1)
    apply.apply_event(atrasado)
    assert Restaurant.all_objects.get(pk=restaurante_id).trade_name == "Atual"


def test_entidade_desconhecida_nao_derruba_nada(como_loja, conta, no_nuvem, no_loja):
    evento = _evento(conta, no_nuvem, no_loja, entity_type="entidade_do_futuro",
                     entity_id=uuid.uuid4(), fields={"x": 1})
    assert apply.apply_event(evento) is False
    evento.refresh_from_db()
    assert evento.status == EventStatus.APPLIED
    assert "não registrada" in evento.last_error


def test_dado_fiscal_divergente_vira_conflito(como_loja, conta, no_nuvem, no_loja, settings):
    """Nota fiscal nunca é resolvida em silêncio por last-write-wins (§15)."""
    from apps.synchronization.services import conflicts

    decisao = conflicts.decide(
        "invoice", local_version=5, remote_version=9,
        receiving_node_type="LOCAL", local_exists=True,
    )
    assert decisao == conflicts.CONFLITO


def test_conflito_registrado_guarda_as_duas_versoes(como_loja, conta, no_nuvem, no_loja):
    from apps.synchronization.services import conflicts

    evento = _evento(conta, no_nuvem, no_loja, entity_type="invoice",
                     entity_id=uuid.uuid4(), fields={"numero": "999"})
    conflicts.register(evento, local_instance=None, remote_payload={"numero": "999"},
                       local_version=5, remote_version=9)

    conflito = SyncConflict.objects.get(entity_type="invoice")
    assert conflito.local_version == 5 and conflito.remote_version == 9
    assert conflito.remote_payload == {"numero": "999"}


def _mais_nova_que(instancia):
    """Uma versão acima da do registro local.

    `entity_version` usa o `updated_at` em microssegundos quando o model não
    tem `sync_version`. Passar um número pequeno aqui faria o evento ser
    descartado por ser "mais velho" — e o teste passaria pelo motivo errado.
    """
    from apps.synchronization.services import serialization

    return serialization.entity_version(instancia) + 1_000_000


# ── UUID que já existe: atualiza, não estoura ───────────────────────────────
def test_uuid_ja_existente_atualiza_em_vez_de_inserir(como_loja, conta, no_nuvem, no_loja):
    """Gravar por cima é a resposta certa; erro de chave duplicada não é."""
    restaurante = Restaurant.objects.create(
        account=conta, legal_name="Antiga LTDA", trade_name="Antiga"
    )
    evento = _evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                     entity_id=restaurante.id,
                     fields={"account_id": str(conta.id), "legal_name": "Nova Razao LTDA",
                             "trade_name": "Nova", "is_active": True},
                     version=_mais_nova_que(restaurante))

    assert apply.apply_event(evento) is True
    restaurante.refresh_from_db()
    assert restaurante.trade_name == "Nova"
    # Pelo manager CRU: `Restaurant.objects` é escopado por tenant e nem
    # enxerga esta linha — é justamente essa cegueira que fazia a aplicação
    # tentar inserir um UUID que o banco já tinha.
    assert Restaurant._base_manager.filter(pk=restaurante.id).count() == 1
    assert not SyncConflict.objects.exists()


def test_linha_invisivel_ao_manager_padrao_ainda_e_encontrada(como_loja, conta, no_nuvem, no_loja):
    """O caso que quebrava: existe no banco, não aparece na consulta filtrada.

    Sem isso a aplicação tenta INSERT num UUID que o banco já tem e o evento
    morre como conflito — quando o dado só precisava ser atualizado.
    """
    restaurante = Restaurant.objects.create(
        account=conta, legal_name="Oculta LTDA", trade_name="Oculta"
    )
    assert apply._encontrar(Restaurant, restaurante.id) is not None

    # Simula o manager padrão não enxergando a linha (escopo de tenant, soft
    # delete, conta inativa — todos acontecem neste projeto).
    vazio = Restaurant._default_manager.none()
    original = Restaurant._default_manager.filter
    try:
        Restaurant._default_manager.filter = lambda *a, **k: vazio
        encontrado = apply._encontrar(Restaurant, restaurante.id)
    finally:
        Restaurant._default_manager.filter = original

    assert encontrado is not None and encontrado.pk == restaurante.id


# ── sem mudanças: não grava ─────────────────────────────────────────────────
def test_payload_identico_nao_grava_nada(como_loja, conta, no_nuvem, no_loja):
    """Reaplicar o mesmo dado não pode mexer no `updated_at` nem gerar eco."""
    restaurante = Restaurant.objects.create(
        account=conta, legal_name="Igual LTDA", trade_name="Igual"
    )
    carimbo = restaurante.updated_at

    evento = _evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                     entity_id=restaurante.id,
                     fields={"account_id": str(conta.id), "legal_name": "Igual LTDA",
                             "trade_name": "Igual", "is_active": True},
                     version=_mais_nova_que(restaurante))

    assert apply.apply_event(evento) is False, "nada mudou: não havia o que gravar"
    restaurante.refresh_from_db()
    assert restaurante.updated_at == carimbo
    # E o evento continua encerrado, não retentável.
    evento.refresh_from_db()
    assert evento.status == EventStatus.APPLIED


def test_uma_unica_diferenca_ja_manda_gravar(como_loja, conta, no_nuvem, no_loja):
    restaurante = Restaurant.objects.create(
        account=conta, legal_name="Base LTDA", trade_name="Base"
    )
    evento = _evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                     entity_id=restaurante.id,
                     fields={"account_id": str(conta.id), "legal_name": "Base LTDA",
                             "trade_name": "Base Nova", "is_active": True},
                     version=_mais_nova_que(restaurante))

    assert apply.apply_event(evento) is True
    restaurante.refresh_from_db()
    assert restaurante.trade_name == "Base Nova"


def test_uuid_como_texto_nao_conta_como_mudanca(como_loja, conta, no_nuvem, no_loja):
    """O payload traz `account_id` em str; a instância guarda UUID."""
    assert apply._igual(conta.id, str(conta.id)) is True
    assert apply._igual(None, None) is True
    assert apply._igual(None, "algo") is False
    assert apply._igual("a", "b") is False
