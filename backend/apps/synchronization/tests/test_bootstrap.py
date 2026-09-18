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


# ── o estado vivo do salão desce na carga ───────────────────────────────────
#
# Pedido e sessão de caixa nascem na loja e sobem. Mas uma loja que está
# ASSUMINDO a operação começa com o banco vazio — sem esta semeadura ela herda
# as mesas ocupadas sem nenhuma comanda para atender, e os terminais sem a
# sessão de caixa que já está aberta.
def test_pedido_aberto_desce_na_carga(como_nuvem, no_loja, cenario):
    from apps.synchronization.services.registry import registry

    entrada = registry.require("order")
    assert entrada.seed_to_local, "pedido aberto precisa descer na carga"
    assert entrada.flow == "local_to_cloud", (
        "a direção CONTÍNUA segue sendo só para cima; o que muda é a semeadura"
    )


def test_a_semeadura_nao_traz_o_historico(como_nuvem, no_loja):
    """Sem filtro, cada loja receberia todo pedido que a conta já teve."""
    from apps.synchronization.services.registry import registry

    for tipo in ("order", "order_item", "payment", "cash_register", "cash_movement"):
        entrada = registry.require(tipo)
        assert entrada.essential_filter, (
            f"{tipo} desceria na carga ESSENCIAL sem filtro — e essa carga "
            "existe para a loja abrir a porta, não para receber o histórico"
        )


def test_so_pedido_aberto_entra_no_manifesto(como_nuvem, no_loja, conta, cenario):
    from apps.orders.models import Order
    from apps.restaurants.models import Restaurant

    restaurante = Restaurant._base_manager.filter(account=conta).first()

    def pedido(status, numero):
        return Order.objects.create(account=conta, restaurant=restaurante,
                                    status=status, sequence=numero)

    aberto = pedido("open", 1)
    pedido("paid", 2)
    pedido("cancelled", 3)

    essencial = bootstrap.build_manifest(
        bootstrap.start_run(target_node=no_loja, run_type=RunType.BOOTSTRAP)
    )
    assert essencial.get("order") == 1, (
        f"na carga ESSENCIAL só o pedido aberto desce; vieram "
        f"{essencial.get('order')} — o aberto é {aberto.id}"
    )

    bootstrap.cancel_running(no_loja, motivo="troca de cenário no teste")
    completa = bootstrap.build_manifest(
        bootstrap.start_run(target_node=no_loja, run_type=RunType.FULL)
    )
    assert completa.get("order") == 3, (
        "'Sincronizar tudo' promete TODOS os dados da conta — o histórico "
        "inclusive"
    )


def test_caixa_fechado_nao_desce(como_nuvem, no_loja, conta, cenario):
    from django.contrib.auth import get_user_model

    from apps.payments.models import CashRegister, CashStation
    from apps.restaurants.models import Restaurant

    restaurante = Restaurant._base_manager.filter(account=conta).first()
    estacao = CashStation.objects.create(account=conta, restaurant=restaurante, name="Caixa 1")
    operador = get_user_model().objects.create_user("caixa1", "c@t.test", "x")

    def sessao(status):
        return CashRegister.objects.create(
            account=conta, restaurant=restaurante, cash_station=estacao,
            status=status, opened_by=operador,
        )

    sessao("open")
    sessao("closed")

    essencial = bootstrap.build_manifest(
        bootstrap.start_run(target_node=no_loja, run_type=RunType.BOOTSTRAP)
    )
    assert essencial.get("cash_register") == 1, (
        "na carga essencial, sessão encerrada é histórico, não estado vivo"
    )

    bootstrap.cancel_running(no_loja, motivo="troca de cenário no teste")
    completa = bootstrap.build_manifest(
        bootstrap.start_run(target_node=no_loja, run_type=RunType.FULL)
    )
    assert completa.get("cash_register") == 2, "'tudo' leva as duas sessões"
