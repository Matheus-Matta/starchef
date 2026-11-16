"""Medição (não é teste de CI): o que travava a loja com 5 máquinas.

Rodar SÓ contra PostgreSQL — travas e índices só se comportam de verdade lá:

    POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55433 POSTGRES_PASSWORD=bench \
    POSTGRES_USER=starchef POSTGRES_DB=starchef_bench \
      pytest --ds=config.settings.test_postgres -s -p no:cacheprovider \
      apps/invoices/tests/bench_loja_sob_carga.py

O nome não casa com `test_*.py` de propósito: a suíte não o coleta.
"""
import statistics
import threading
import time
import uuid
from decimal import Decimal

import pytest
from django.db import connection, connections, transaction
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import FiscalProvider, register_provider
from apps.orders.models import Order, OrderItem
from apps.orders.services import add_order_item, create_order

SEFAZ_S = 1.0
CAIXAS = 5


@register_provider
class _SefazDeUmSegundo(FiscalProvider):
    name = "bench_sefaz_1s"
    transmits = True

    def emit(self, invoice, config):
        time.sleep(SEFAZ_S)
        invoice.provider = self.name
        invoice.status = Invoice.STATUS_ISSUED
        invoice.authorization_protocol = "135260000000001"
        return invoice

    def cancel(self, invoice, reason):
        invoice.status = Invoice.STATUS_CANCELLED
        return invoice

    def status(self, invoice):
        return invoice.status


def _pedidos(account, restaurant, branch, user, quantos):
    from apps.menu.models import Product

    with tenant_context(account):
        produto = Product.objects.create(
            account=account, restaurant=restaurant, branch=branch,
            name="X-Burger", internal_code=f"P{uuid.uuid4().hex[:6]}",
            sale_price=Decimal("25.00"),
        )
        pedidos = []
        for _ in range(quantos):
            pedido = create_order(restaurant=restaurant, branch=branch,
                                  order_type=Order.TYPE_COUNTER, user=user)
            add_order_item(order=pedido, product=produto, quantity=1, user=user)
            pedidos.append(pedido)
        return pedidos


@pytest.mark.django_db(transaction=True)
def test_cinco_caixas_emitindo_ao_mesmo_tempo(account, restaurant, branch, manager_user):
    from apps.invoices.services import emit_fiscal_invoice

    with tenant_context(account):
        FiscalConfig.objects.create(
            account=account, restaurant=restaurant, branch=branch,
            document_model=FiscalConfig.MODEL_NFCE, series=1, next_number=1,
            environment="2", cnpj="63201558000155", uf="RJ", provider=_SefazDeUmSegundo.name,
        )
    pedidos = _pedidos(account, restaurant, branch, manager_user, CAIXAS)

    tempos, espera_do_pdv, erros = {}, {}, []
    largada = threading.Barrier(CAIXAS + 2)  # os caixas, o PDV e esta thread

    def caixa(i, pedido):
        try:
            largada.wait()
            inicio = time.perf_counter()
            emit_fiscal_invoice(pedido, user=manager_user)
            tempos[i] = time.perf_counter() - inicio
        except Exception as exc:  # noqa: BLE001
            erros.append(exc)
        finally:
            connections.close_all()

    def pdv_pede_a_nota_do_primeiro():
        """O `/invoices/emit/` do PDV chega 0,3 s depois do pagamento."""
        try:
            largada.wait()
            time.sleep(0.3)
            inicio = time.perf_counter()
            with tenant_context(account), transaction.atomic():
                Order.all_objects.select_for_update().get(pk=pedidos[0].pk)
            espera_do_pdv["s"] = time.perf_counter() - inicio
        finally:
            connections.close_all()

    threads = [threading.Thread(target=caixa, args=(i, p)) for i, p in enumerate(pedidos)]
    threads.append(threading.Thread(target=pdv_pede_a_nota_do_primeiro))
    inicio = time.perf_counter()
    for t in threads:
        t.start()
    largada.wait()
    for t in threads:
        t.join()
    total = time.perf_counter() - inicio

    assert not erros, erros
    numeros = list(Invoice.all_objects.filter(order__in=pedidos).values_list("number", flat=True))
    print(f"\n[FISCAL] {CAIXAS} caixas, SEFAZ de {SEFAZ_S:.1f} s cada")
    print(f"[FISCAL] tempo total ............ {total:.2f} s")
    print(f"[FISCAL] cada caixa esperou ..... {', '.join(f'{tempos[i]:.2f}' for i in sorted(tempos))} s")
    print(f"[FISCAL] PDV esperou a trava .... {espera_do_pdv.get('s', -1):.2f} s")
    print(f"[FISCAL] números ................ {sorted(int(n) for n in numeros)}")
    assert len(set(numeros)) == CAIXAS  # nenhum número repetido


@pytest.mark.django_db(transaction=True)  # CREATE INDEX com trigger pendente não roda numa transação
def test_consulta_do_quadro_do_kds_com_historico(account, restaurant, branch, manager_user):
    """3 meses de itens prontos esquecidos no quadro + 30 itens de hoje."""
    from apps.kitchen.views import KitchenItemFilter, _ACTIVE_ITEM_STATUSES

    HISTORICO = 60_000
    [pedido] = _pedidos(account, restaurant, branch, manager_user, 1)
    modelo = OrderItem.all_objects.filter(order=pedido).first()

    def copia():
        import copy

        item = copy.copy(modelo)
        item.pk = None
        item.id = None
        item.status = OrderItem.STATUS_READY
        return item

    for _ in range(HISTORICO // 5000):
        OrderItem.all_objects.bulk_create([copia() for _ in range(5000)], batch_size=5000)
    with connection.cursor() as cur:
        cur.execute(
            f"UPDATE {OrderItem._meta.db_table} SET launched_at = now() - (random() * 90 + 1) * interval '1 day' "
            "WHERE order_id = %s", [pedido.pk],
        )
        OrderItem.all_objects.bulk_create([copia() for _ in range(30)])  # hoje
        cur.execute("ANALYZE " + OrderItem._meta.db_table)

    hoje = timezone.localdate()
    base = OrderItem.all_objects.filter(account=account, status__in=_ACTIVE_ITEM_STATUSES)
    antigo = base.filter(launched_at__date__gte=hoje, launched_at__date__lte=hoje)
    filtro = KitchenItemFilter({"launched_after": hoje.isoformat(), "launched_before": hoje.isoformat()},
                               queryset=base)
    novo = filtro.qs

    def medir(qs, voltas=15):
        amostras = []
        for _ in range(voltas):
            inicio = time.perf_counter()
            ids = list(qs.values_list("id", flat=True))
            amostras.append((time.perf_counter() - inicio) * 1000)
        return statistics.median(amostras), len(ids)

    def plano(qs):
        sql, params = qs.values_list("id", flat=True).query.sql_with_params()
        with connection.cursor() as cur:
            cur.execute("EXPLAIN " + sql, params)
            return " | ".join(linha[0].strip() for linha in cur.fetchall()[:2])

    with connection.cursor() as cur:
        cur.execute("DROP INDEX IF EXISTS orders_item_kds_idx")
    ms_antigo, n_antigo = medir(antigo)
    plano_antigo = plano(antigo)
    with connection.cursor() as cur:
        cur.execute(f"CREATE INDEX orders_item_kds_idx ON {OrderItem._meta.db_table} (account_id, status, launched_at)")
        cur.execute("ANALYZE " + OrderItem._meta.db_table)
    ms_novo, n_novo = medir(novo)
    plano_novo = plano(novo)

    print(f"\n[KDS] {HISTORICO} itens de histórico, 30 de hoje")
    print(f"[KDS] antes: {ms_antigo:7.2f} ms  ({n_antigo} itens)  plano: {plano_antigo}")
    print(f"[KDS] depois: {ms_novo:6.2f} ms  ({n_novo} itens)  plano: {plano_novo}")
    assert n_antigo == n_novo == 30
