"""Perfil das rotas que o PDV, o KDS e o painel mais chamam (não é teste de CI).

Para cada rota: tempo mediano, consultas ao banco e as funções do projeto que
mais gastam CPU (cProfile). Mede o custo POR REQUISIÇÃO dentro do Python —
o que a carga de rede não separa.

    pytest -s -p no:cacheprovider apps/core/tests/bench_rotas_quentes.py

O nome não casa com `test_*.py`: a suíte não o coleta.
"""
import cProfile
import io
import pstats
import statistics
import time
import uuid

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

VOLTAS = 5


def _cliente(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def _perfil(chamar):
    """As funções com mais tempo PRÓPRIO (onde a CPU realmente fica)."""
    perfil = cProfile.Profile()
    perfil.enable()
    chamar()
    perfil.disable()
    stats = pstats.Stats(perfil, stream=io.StringIO())
    linhas = []
    for (arquivo, linha, funcao), (_cc, nc, tt, ct, _callers) in stats.stats.items():
        curto = arquivo.replace("\\", "/")
        for marca in ("site-packages/", "/backend/"):
            if marca in curto:
                curto = curto.split(marca)[-1]
        linhas.append((tt, ct, nc, f"{curto}:{linha} {funcao}"))
    linhas.sort(reverse=True)
    return linhas[:12], stats.total_tt


@pytest.mark.django_db
def test_rotas_quentes():
    from django.contrib.auth import get_user_model

    from apps.core.management.commands._demo_defaults import DEFAULT_USERNAME
    from apps.restaurants.models import Restaurant

    call_command("seed_demo", skip_tenant_2=True, stdout=io.StringIO())
    admin = get_user_model().objects.get(username=DEFAULT_USERNAME)
    restaurante = Restaurant.all_objects.filter(account=admin.profile.account).order_by("created_at").first()
    r = str(restaurante.pk)
    cliente = _cliente(admin)
    hoje = time.strftime("%Y-%m-%d")

    rotas = [
        ("PDV catálogo: produtos", "get", "/api/v1/menu/products/", {"restaurant": r, "page_size": 100, "is_active": True}),
        ("PDV catálogo: categorias", "get", "/api/v1/menu/categories/", {"page_size": 100, "is_active": True}),
        ("PDV catálogo: mesas", "get", "/api/v1/tables/", {"restaurant": r, "page_size": 300}),
        ("PDV catálogo: comandas", "get", "/api/v1/commands/", {"restaurant": r, "page_size": 300, "is_active": True}),
        ("PDV catálogo: formas pgto", "get", "/api/v1/payments/methods/",
         {"restaurant": r, "is_active": True, "page_size": 100, "ordering": "-uso,name"}),
        ("PDV: fila de impressão", "get", "/api/v1/print-jobs/", {"restaurant": r}),
        ("PDV: pedidos abertos", "get", "/api/v1/orders/", {"restaurant": r, "page_size": 50}),
        ("KDS: itens do dia", "get", "/api/v1/kitchen/items/",
         {"ordering": "sent_to_kitchen_at", "page_size": 100, "launched_after": hoje, "launched_before": hoje}),
        ("Painel: resumo do topo", "get", "/api/v1/reports/dashboard/", {"resumo": 1}),
        ("Painel: dashboard inteiro", "get", "/api/v1/reports/dashboard/", {}),
    ]

    print(f"\n{'rota':32} {'status':>6} {'ms (mediana)':>13} {'consultas':>10} {'KB':>7}")
    resultados = []
    for nome, metodo, url, params in rotas:
        def chamar(metodo=metodo, url=url, params=params):
            return getattr(cliente, metodo)(url, params, HTTP_X_RESTAURANT_ID=r)
        chamar()  # aquece cache de rota, de serializer, etc.
        tempos = []
        for _ in range(VOLTAS):
            with CaptureQueriesContext(connection) as consultas:
                inicio = time.perf_counter()
                resposta = chamar()
                tempos.append((time.perf_counter() - inicio) * 1000)
        ms = statistics.median(tempos)
        print(f"{nome:32} {resposta.status_code:>6} {ms:>13.1f} {len(consultas):>10} {len(resposta.content) / 1024:>7.1f}")
        resultados.append((ms, nome, chamar, consultas))

    # A venda inteira, como o PDV manda no "Concluir".
    from apps.menu.models import Product
    from apps.payments.models import PaymentMethod

    restaurante.require_open_cash_register = False
    restaurante.save(update_fields=["require_open_cash_register"])
    produto = Product.all_objects.filter(restaurant=restaurante, is_active=True).first()
    forma = PaymentMethod.all_objects.filter(restaurant=restaurante, is_active=True).first()

    def vender(itens=8):
        corpo = {
            "id": str(uuid.uuid4()), "order_type": "counter", "restaurant": r,
            "items": [{"id": str(uuid.uuid4()), "product": str(produto.pk), "quantity": 1} for _ in range(itens)],
            "payments": [{"id": str(uuid.uuid4()), "payment_method": str(forma.pk),
                          "amount": str(produto.sale_price * itens), "client_updated_at": "2026-11-15T12:00:00Z"}],
        }
        return cliente.post("/api/v1/orders/submit/", corpo, format="json", HTTP_X_RESTAURANT_ID=r)

    primeira = vender()
    print("venda:", primeira.status_code, primeira.content[:400])
    tempos = []
    for _ in range(VOLTAS):
        with CaptureQueriesContext(connection) as consultas:
            inicio = time.perf_counter()
            resposta = vender()
            tempos.append((time.perf_counter() - inicio) * 1000)
    ms = statistics.median(tempos)
    print(f"{'PDV: venda de 8 itens':32} {resposta.status_code:>6} {ms:>13.1f} {len(consultas):>10} "
          f"{len(resposta.content) / 1024:>7.1f}")
    resultados.append((ms, "PDV: venda de 8 itens", vender, consultas))

    print("\n=== Onde o Python gasta, nas 5 rotas mais caras ===")
    for ms, nome, chamar, consultas in sorted(resultados, key=lambda x: x[0], reverse=True)[:5]:
        linhas, _ = _perfil(chamar)
        print(f"\n--- {nome} ({ms:.0f} ms, {len(consultas)} consultas)")
        for tt, _ct, nc, onde in linhas:
            print(f"   {tt * 1000:6.1f} ms próprio {nc:>7}x  {onde}")
        repetidas = {}
        for q in consultas.captured_queries:
            chave = q["sql"].split(" WHERE ")[0][:110]
            repetidas[chave] = repetidas.get(chave, 0) + 1
        top = sorted(repetidas.items(), key=lambda x: -x[1])[:3]
        for sql, vezes in top:
            if vezes > 2:
                print(f"   consulta repetida {vezes}x: {sql}")


@pytest.mark.django_db
def test_custo_por_item_da_venda():
    from django.contrib.auth import get_user_model

    from apps.core.management.commands._demo_defaults import DEFAULT_USERNAME
    from apps.menu.models import Product
    from apps.payments.models import PaymentMethod
    from apps.restaurants.models import Restaurant

    call_command("seed_demo", skip_tenant_2=True, skip_orders=True, stdout=io.StringIO())
    admin = get_user_model().objects.get(username=DEFAULT_USERNAME)
    restaurante = Restaurant.all_objects.filter(account=admin.profile.account).order_by("created_at").first()
    restaurante.require_open_cash_register = False
    restaurante.save(update_fields=["require_open_cash_register"])
    r = str(restaurante.pk)
    cliente = _cliente(admin)
    produtos = list(Product.all_objects.filter(restaurant=restaurante, is_active=True)
                    .exclude(pricing_unit=Product.PRICING_KG)[:20])
    forma = PaymentMethod.all_objects.filter(restaurant=restaurante, is_active=True,
                                          method_type=PaymentMethod.TYPE_CASH).first()

    def vender(itens):
        escolhidos = [produtos[i % len(produtos)] for i in range(itens)]
        corpo = {
            "id": str(uuid.uuid4()), "order_type": "counter", "restaurant": r,
            "items": [{"id": str(uuid.uuid4()), "product": str(p.pk), "quantity": 1} for p in escolhidos],
            "payments": [{"id": str(uuid.uuid4()), "payment_method": str(forma.pk),
                          "amount": str(sum(p.sale_price for p in escolhidos)),
                          "client_updated_at": "2026-11-15T12:00:00Z"}],
        }
        with CaptureQueriesContext(connection) as consultas:
            inicio = time.perf_counter()
            resposta = cliente.post("/api/v1/orders/submit/", corpo, format="json", HTTP_X_RESTAURANT_ID=r)
            ms = (time.perf_counter() - inicio) * 1000
        assert resposta.status_code == 201, resposta.content[:300]
        return ms, consultas

    vender(1)
    medidas = {n: vender(n) for n in (1, 5, 20)}
    print()
    for n, (ms, consultas) in medidas.items():
        print(f"[VENDA] {n:>2} itens: {len(consultas):>4} consultas  {ms:7.1f} ms")
    por_item = (len(medidas[20][1]) - len(medidas[1][1])) / 19
    print(f"[VENDA] consultas por item a mais: {por_item:.1f}")
    repetidas = {}
    for q in medidas[20][1].captured_queries:
        sql = q["sql"]
        chave = (sql.split(" WHERE ")[0] if sql.startswith("SELECT") else sql[:60])[:140]
        repetidas[chave] = repetidas.get(chave, 0) + 1
    for sql, vezes in sorted(repetidas.items(), key=lambda x: -x[1])[:14]:
        print(f"[VENDA] {vezes:>3}x {sql}")
