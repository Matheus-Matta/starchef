"""Sincronizacao incremental usada pelo Caixa Principal offline-first.

O PDV desktop guarda a operacao inteira em SQLite e reconcilia com o backend
em segundo plano. Depois de horas offline, rebaixar a base completa a cada
reconexao e caro e desnecessario: `?updated_after=` devolve so o que mudou.

`?include_deleted=1` existe pelo motivo oposto — sem ele, um produto removido
na retaguarda apenas sumiria da listagem, e a copia local continuaria vendavel
no caixa. Ele so tem efeito acompanhado de `updated_after`, para nao mudar o
comportamento de nenhuma listagem normal da aplicacao.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from apps.menu.models import Product


@pytest.fixture
def authenticated_client(api_client, manager_user):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")
    return api_client


def _ids(response):
    return {item["id"] for item in response.data["results"]}


@pytest.mark.django_db
def test_updated_after_devolve_apenas_o_que_mudou(authenticated_client, product, account, restaurant, branch, category):
    antigo = timezone.now() - timedelta(hours=2)
    Product.objects.filter(pk=product.pk).update(updated_at=antigo)

    novo = Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        category=category,
        name="Refrigerante",
        internal_code="RF001",
        sale_price=Decimal("8.00"),
    )

    marca = (timezone.now() - timedelta(hours=1)).isoformat()
    response = authenticated_client.get("/api/v1/menu/products/", {"updated_after": marca})

    assert response.status_code == 200
    assert _ids(response) == {str(novo.pk)}


@pytest.mark.django_db
def test_sem_updated_after_a_listagem_continua_completa(authenticated_client, product):
    response = authenticated_client.get("/api/v1/menu/products/")

    assert response.status_code == 200
    assert str(product.pk) in _ids(response)


@pytest.mark.django_db
def test_updated_after_invalido_nao_nega_dados_ao_caixa(authenticated_client, product):
    # Melhor devolver a listagem completa do que deixar o caixa sem cardapio
    # por causa de um parametro malformado.
    response = authenticated_client.get("/api/v1/menu/products/", {"updated_after": "ontem"})

    assert response.status_code == 200
    assert str(product.pk) in _ids(response)


@pytest.mark.django_db
def test_include_deleted_revela_a_exclusao_para_o_delta_sync(authenticated_client, product):
    product.deleted_at = timezone.now()
    product.save(update_fields=["deleted_at"])

    marca = (timezone.now() - timedelta(hours=1)).isoformat()
    incremental = authenticated_client.get(
        "/api/v1/menu/products/",
        {"updated_after": marca, "include_deleted": "1"},
    )

    assert incremental.status_code == 200
    encontrados = {item["id"]: item for item in incremental.data["results"]}
    assert str(product.pk) in encontrados
    assert encontrados[str(product.pk)]["deleted_at"] is not None


@pytest.mark.django_db
def test_include_deleted_sozinho_nao_muda_a_listagem_normal(authenticated_client, product):
    product.deleted_at = timezone.now()
    product.save(update_fields=["deleted_at"])

    response = authenticated_client.get("/api/v1/menu/products/", {"include_deleted": "1"})

    assert response.status_code == 200
    assert str(product.pk) not in _ids(response)
