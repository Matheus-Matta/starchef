"""Os cupons que o caixa vê como sugestão no pagamento.

Os 5 mais usados primeiro (o cliente costuma trazer o da campanha do mês) e,
enquanto o operador digita, a busca pelo código. Só cupom VIGENTE: sugerir um
vencido ou desligado faria o caixa tocar num botão para ouvir uma recusa.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.orders.models import Order
from apps.promotions.models import Coupon, CouponRedemption

pytestmark = pytest.mark.django_db
ROTA = "/api/v1/promotions/coupons/"


@pytest.fixture
def cupons(account, restaurant):
    agora = timezone.now()
    with tenant_context(account):
        def cupom(codigo, usos, **extra):
            c = Coupon.objects.create(account=account, code=codigo, discount_value=Decimal("10"), **extra)
            for n in range(usos):
                pedido = Order.objects.create(account=account, restaurant=restaurant, sequence=1000 + hash(codigo) % 900 * 10 + n)
                CouponRedemption.objects.create(account=account, restaurant=restaurant, coupon=c, order=pedido)
            return c

        cupom("NATAL10", 3)
        cupom("BEMVINDO", 5)
        cupom("FRETE", 1)
        cupom("VENCIDO", 9, ends_at=agora - timedelta(days=1))
        cupom("DESLIGADO", 9, is_enabled=False)
        cupom("FUTURO", 9, starts_at=agora + timedelta(days=1))


def test_mais_usados_primeiro_e_so_vigentes(cupons, api_client):
    resposta = api_client.get(ROTA, {"vigentes": 1, "ordering": "-total_resgates", "page_size": 5})

    assert resposta.status_code == 200, resposta.data
    assert [c["code"] for c in resposta.data["results"]] == ["BEMVINDO", "NATAL10", "FRETE"]


def test_busca_pelo_que_foi_digitado(cupons, api_client):
    resposta = api_client.get(ROTA, {"vigentes": 1, "search": "nat"})

    assert [c["code"] for c in resposta.data["results"]] == ["NATAL10"]


def test_sem_o_filtro_o_cadastro_continua_vendo_todos(cupons, api_client):
    assert api_client.get(ROTA, {"page_size": 50}).data["count"] == 6
