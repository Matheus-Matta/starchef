"""As triggers de verdade, contra um PostgreSQL de verdade.

Este arquivo INTEIRO é pulado no SQLite. Não é preguiça: a rede de segurança do
§11.2 é PL/pgSQL, e testá-la em qualquer outro banco seria testar o `skip`.

Para rodar:

    POSTGRES_HOST=localhost POSTGRES_DB=starchef_test USE_SQLITE_DATABASE=False \
      pytest apps/synchronization/tests/test_triggers_postgres.py

Ou, no compose da loja:

    docker compose -f docker/local/docker-compose.local.yml exec backend \
      pytest apps/synchronization/tests/test_triggers_postgres.py
"""
import pytest
from django.db import connection

from apps.restaurants.models import Restaurant
from apps.synchronization.models import SyncDirty, SyncEvent
from apps.synchronization.services import dirty, outbox, triggers

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="As triggers da rede de segurança só existem no PostgreSQL (§11.2).",
    ),
]


@pytest.fixture
def com_triggers(como_nuvem):
    triggers.install(log=lambda _m: None)
    yield
    triggers.uninstall(log=lambda _m: None)


def test_instalacao_cobre_todas_as_tabelas_do_catalogo(com_triggers):
    assert triggers.faltando() == []
    assert len(triggers.installed()) >= 20


def test_queryset_update_gera_marca(com_triggers, conta):
    """O buraco que os signals deixam: `update()` não passa por `post_save`."""
    restaurante = Restaurant.objects.create(account=conta, legal_name="P LTDA", trade_name="P")
    SyncDirty.objects.all().delete()
    SyncEvent.objects.all().delete()

    # Escrita em massa: nenhum signal dispara.
    Restaurant.all_objects.filter(pk=restaurante.pk).update(trade_name="P renomeado")

    marcas = SyncDirty.objects.filter(row_id=str(restaurante.pk))
    assert marcas.count() == 1
    assert marcas.first().operation == "UPDATE"


def test_bulk_create_gera_marca(com_triggers, conta):
    SyncDirty.objects.all().delete()
    Restaurant.objects.bulk_create([
        Restaurant(account=conta, legal_name=f"B{i} LTDA", trade_name=f"B{i}")
        for i in range(3)
    ])
    assert SyncDirty.objects.filter(table_name="restaurants_restaurant").count() == 3


def test_marca_vira_evento_pela_tarefa(com_triggers, conta, no_loja):
    restaurante = Restaurant.objects.create(account=conta, legal_name="Q LTDA", trade_name="Q")
    SyncDirty.objects.all().delete()
    SyncEvent.objects.all().delete()

    Restaurant.all_objects.filter(pk=restaurante.pk).update(trade_name="Q novo")
    convertidas, _ = dirty.process()

    assert convertidas == 1
    evento = SyncEvent.objects.get(entity_type="restaurant")
    assert evento.payload["fields"]["trade_name"] == "Q novo"


def test_aplicar_evento_remoto_nao_deixa_marca(com_triggers, conta):
    """`app.sync_apply` corta o laço também pelo lado da trigger.

    Sem isto, o eco voltaria pelo caminho que os signals não veem — e seria
    muito mais difícil de perceber.
    """
    SyncDirty.objects.all().delete()
    with outbox.applying_remote_event():
        Restaurant.objects.create(account=conta, legal_name="R LTDA", trade_name="R")
    assert SyncDirty.objects.count() == 0


def test_a_marca_volta_depois_do_bloco_de_aplicacao(com_triggers, conta):
    """`SET LOCAL` morre com a transação; a conexão do pool não fica marcada."""
    with outbox.applying_remote_event():
        Restaurant.objects.create(account=conta, legal_name="S LTDA", trade_name="S")

    SyncDirty.objects.all().delete()
    Restaurant.objects.create(account=conta, legal_name="T LTDA", trade_name="T")
    assert SyncDirty.objects.count() >= 1


def test_delete_gera_marca(com_triggers, conta):
    """Apaga uma FOLHA: o restaurante tem filhos com FK protegida."""
    from apps.payments.models import PaymentMethod

    restaurante = Restaurant.objects.create(account=conta, legal_name="U LTDA", trade_name="U")
    forma = PaymentMethod.all_objects.filter(restaurant=restaurante).first()
    assert forma is not None, "o signal do restaurante cria as formas padrão"

    SyncDirty.objects.all().delete()
    PaymentMethod.all_objects.filter(pk=forma.pk).delete()

    marca = SyncDirty.objects.filter(row_id=str(forma.pk)).first()
    assert marca is not None and marca.operation == "DELETE"


def test_desinstalar_remove_tudo(com_triggers):
    triggers.uninstall(log=lambda _m: None)
    assert triggers.installed() == set()
    triggers.install(log=lambda _m: None)  # repõe para o teardown da fixture
