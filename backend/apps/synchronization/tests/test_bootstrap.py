"""A carga total: manifesto, ordem, progresso e retomada."""
import pytest

from apps.menu.models import Product, ProductCategory
from apps.restaurants.models import Restaurant
from apps.synchronization.constants import Operation, RunStatus, RunType
from apps.synchronization.models import SyncEvent, SyncRun
from apps.synchronization.services import bootstrap
from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario(conta):
    r = Restaurant.objects.create(account=conta, legal_name="B LTDA", trade_name="B")
    c = ProductCategory.objects.create(account=conta, restaurant=r, name="Lanches")
    Product.objects.create(
        account=conta, restaurant=r, category=c, name="X", internal_code="X1",
        sale_price="10.00",
    )
    return r


def test_carga_nasce_pendente_com_cursor(como_nuvem, conta, no_loja, cenario):
    run = bootstrap.start_run(target_node=no_loja, run_type=RunType.BOOTSTRAP)
    assert run.status == RunStatus.PENDING
    assert run.account_id == conta.id
    # O cursor congela o "antes": tudo depois dele é reproduzido como incremental.
    assert run.snapshot_cursor >= 0


def test_duas_cargas_simultaneas_no_mesmo_no_sao_recusadas(como_nuvem, no_loja, cenario):
    bootstrap.start_run(target_node=no_loja)
    with pytest.raises(bootstrap.BootstrapBusy, match="ainda está em"):
        bootstrap.start_run(target_node=no_loja)


def test_cancelar_libera_para_uma_nova(como_nuvem, no_loja, cenario):
    primeira = bootstrap.start_run(target_node=no_loja)
    assert bootstrap.cancel_running(no_loja, motivo="rematrícula") == 1

    primeira.refresh_from_db()
    assert primeira.status == RunStatus.CANCELLED
    assert "rematrícula" in primeira.error
    bootstrap.start_run(target_node=no_loja)  # agora passa


def test_manifesto_conta_por_entidade(como_nuvem, no_loja, cenario):
    run = bootstrap.start_run(target_node=no_loja)
    manifesto = bootstrap.build_manifest(run)

    assert manifesto["restaurant"] >= 1
    assert manifesto["product"] >= 1
    run.refresh_from_db()
    assert run.status == RunStatus.PREPARING
    assert run.total_records == sum(manifesto.values())
    assert run.total_entities == len(manifesto)


def test_manifesto_essencial_e_menor_que_o_completo(como_nuvem, no_loja, cenario):
    essencial = bootstrap.build_manifest(
        bootstrap.start_run(target_node=no_loja, run_type=RunType.BOOTSTRAP)
    )
    bootstrap.cancel_running(no_loja)
    completo = bootstrap.build_manifest(
        bootstrap.start_run(target_node=no_loja, run_type=RunType.FULL)
    )
    assert set(essencial) < set(completo)


def test_carga_gera_eventos_de_snapshot(como_nuvem, no_loja, cenario):
    run = bootstrap.start_run(target_node=no_loja)
    bootstrap.build_manifest(run)
    SyncEvent.objects.all().delete()
    bootstrap.generate_events(run)

    eventos = SyncEvent.objects.filter(run=run)
    assert eventos.exists()
    assert all(e.operation == Operation.SNAPSHOT for e in eventos)
    run.refresh_from_db()
    assert run.status == RunStatus.VALIDATING
    assert run.processed_records > 0


def test_a_carga_so_leva_dados_da_propria_conta(como_nuvem, conta, outra_conta, no_loja, cenario):
    """O teste que impede a conta A de receber a loja da conta B."""
    Restaurant.objects.create(account=outra_conta, legal_name="V LTDA", trade_name="Vizinha")

    run = bootstrap.start_run(target_node=no_loja)
    bootstrap.build_manifest(run)
    SyncEvent.objects.all().delete()
    bootstrap.generate_events(run)

    nomes = {
        e.payload["fields"].get("trade_name")
        for e in SyncEvent.objects.filter(run=run, entity_type="restaurant")
    }
    assert "Vizinha" not in nomes
    assert all(e.account_id == conta.id for e in SyncEvent.objects.filter(run=run))


def test_ordem_topologica_poe_dependencia_antes(como_nuvem):
    ordem = [e.entity_type for e in registry.ordered()]
    assert ordem.index("account") < ordem.index("restaurant")
    assert ordem.index("restaurant") < ordem.index("product_category")
    assert ordem.index("product_category") < ordem.index("product")
    assert ordem.index("order") < ordem.index("order_item")


def test_finalizar_marca_concluida(como_nuvem, no_loja, cenario):
    run = bootstrap.start_run(target_node=no_loja)
    bootstrap.finish(run)
    run.refresh_from_db()
    assert run.status == RunStatus.COMPLETED
    assert run.completed_at is not None


def test_finalizar_com_erro_marca_falha(como_nuvem, no_loja, cenario):
    run = bootstrap.start_run(target_node=no_loja)
    bootstrap.finish(run, error="banco caiu no meio")
    run.refresh_from_db()
    assert run.status == RunStatus.FAILED
    assert "banco caiu" in run.error


def test_progresso_em_percentual(como_nuvem, no_loja, cenario):
    run = bootstrap.start_run(target_node=no_loja)
    run.total_records, run.processed_records = 200, 50
    assert run.progress_percent == 25
    run.total_records = 0
    assert run.progress_percent == 0  # sem total, não inventa número


def test_tarefa_de_carga_registra_a_falha_no_run(como_nuvem, no_loja, cenario, monkeypatch):
    """Falhar não pode sumir: o motivo fica gravado no SyncRun."""
    from apps.synchronization.tasks import bootstrap as tarefa

    run = bootstrap.start_run(target_node=no_loja)
    monkeypatch.setattr(
        bootstrap, "build_manifest", lambda _r: (_ for _ in ()).throw(RuntimeError("disco cheio"))
    )
    resultado = tarefa.run_bootstrap(str(run.id))

    assert "disco cheio" in resultado["erro"]
    run.refresh_from_db()
    assert run.status == RunStatus.FAILED
    assert "disco cheio" in run.error


def test_tarefa_com_carga_inexistente_nao_quebra(como_nuvem):
    import uuid

    from apps.synchronization.tasks import bootstrap as tarefa

    assert tarefa.run_bootstrap(str(uuid.uuid4())) == {"erro": "carga inexistente"}


def test_carga_registra_quem_iniciou(como_nuvem, no_loja, cenario):
    from django.contrib.auth import get_user_model

    usuario = get_user_model().objects.create_user("quem", "q@t.test", "senha-forte-123")
    run = bootstrap.start_run(
        target_node=no_loja, user=usuario, ip="10.0.0.9", reason="pedido do suporte"
    )
    assert run.initiated_by == usuario
    assert run.initiated_ip == "10.0.0.9"
    assert run.reason == "pedido do suporte"
    assert SyncRun.objects.filter(initiated_by=usuario).exists()
