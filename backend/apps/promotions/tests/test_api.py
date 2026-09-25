"""As rotas de promoção e cupom, pelo que elas devolvem a quem cadastra.

O foco aqui não é "o endpoint responde 200": é o que o operador consegue fazer
sem sair da tela. Salvar a regra com os produtos dentro no mesmo gesto, receber
a recusa ANTES de gravar duas regras para o mesmo produto, e conferir um cupom
sem consumi-lo.
"""

import uuid
from decimal import Decimal

import pytest

from apps.menu.models import Product, ProductCategory
from apps.promotions.models import DiscountTable, Promotion, PromotionProduct

pytestmark = pytest.mark.django_db


@pytest.fixture
def categoria(account, restaurant, branch):
    return ProductCategory.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Bebidas"
    )


@pytest.fixture
def produto(account, restaurant, branch, categoria):
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, category=categoria,
        name="Refrigerante", internal_code=f"R{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("20.00"),
    )


def _tabela(api_client, **campos):
    corpo = {"name": f"Tabela {uuid.uuid4().hex[:6]}", "is_enabled": True, **campos}
    resp = api_client.post("/api/v1/promotions/discount-tables/", corpo, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def test_tabela_nasce_ativa_e_diz_por_que(api_client):
    tabela = _tabela(api_client)
    # `is_active` e `status_label` são calculados: sem janela e ligada, vale.
    assert tabela["is_active"] is True
    assert tabela["status_label"] == "Ativa"
    assert tabela["rule_count"] == 0



def test_tabela_recusa_fim_antes_do_inicio(api_client):
    resp = api_client.post(
        "/api/v1/promotions/discount-tables/",
        {"name": "Invertida", "starts_at": "2026-10-10T18:00:00Z", "ends_at": "2026-10-10T09:00:00Z"},
        format="json",
    )
    assert resp.status_code == 400
    assert "depois do in" in str(resp.data)



def test_desligar_a_tabela_nao_exige_abrir_o_formulario(api_client):
    """`toggle` existe porque desligar promoção é urgente por natureza."""
    tabela = _tabela(api_client)
    resp = api_client.post(f"/api/v1/promotions/discount-tables/{tabela['id']}/toggle/", {}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["is_enabled"] is False
    assert resp.data["status_label"] == "Desligada"



def test_regra_grava_os_produtos_no_mesmo_salvamento(api_client, produto):
    """Produto e regra nascem juntos: regra vazia e ativa é o pior estado."""
    tabela = _tabela(api_client)
    resp = api_client.post(
        "/api/v1/promotions/rules/",
        {
            "table": tabela["id"],
            "name": "Refri no encarte",
            "position": 1,
            "target_type": "products",
            "discount_kind": "fixed",
            "discount_value": "0",
            "product_links": [
                {"product": str(produto.id), "promotional_price": "15.00", "compare_at_price": "30.00"},
            ],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert len(resp.data["product_links"]) == 1
    vinculo = resp.data["product_links"][0]
    # O preço CADASTRADO viaja junto para a tela poder mostrar, ao lado do
    # "de 30 por 15", que o produto está cadastrado a 20.
    assert vinculo["product_base_price"] == "20.00"
    assert vinculo["compare_at_price"] == "30.00"



def test_duas_regras_para_o_mesmo_produto_na_mesma_tabela_sao_recusadas(api_client, produto):
    """A segunda nunca venceria — ficaria ali, invisível, parecendo ativa."""
    tabela = _tabela(api_client)
    base = {
        "table": tabela["id"],
        "target_type": "products",
        "discount_kind": "percent",
        "discount_value": "10",
        "product_links": [{"product": str(produto.id)}],
    }
    primeira = api_client.post("/api/v1/promotions/rules/", {**base, "name": "Primeira", "position": 1}, format="json")
    assert primeira.status_code == 201, primeira.data

    segunda = api_client.post("/api/v1/promotions/rules/", {**base, "name": "Segunda", "position": 2}, format="json")
    assert segunda.status_code == 400
    # A mensagem NOMEIA a regra que já ocupa o produto: "já tem desconto" sem
    # dizer onde faria o operador procurar regra por regra.
    assert "Primeira" in str(segunda.data)



def test_percentual_acima_de_cem_e_recusado(api_client):
    tabela = _tabela(api_client)
    resp = api_client.post(
        "/api/v1/promotions/rules/",
        {"table": tabela["id"], "name": "Impossivel", "target_type": "all",
         "discount_kind": "percent", "discount_value": "120"},
        format="json",
    )
    assert resp.status_code == 400
    assert "100%" in str(resp.data)



def test_reordenar_troca_a_prioridade_sem_colidir(api_client, account, restaurant, branch):
    """Salvar uma a uma colidiria no meio: posição é única por tabela."""
    tabela = DiscountTable.objects.create(account=account, restaurant=restaurant, branch=branch, name="Ordem")
    regras = [
        Promotion.objects.create(account=account, table=tabela, name=f"R{n}", position=n, target_type="all")
        for n in (1, 2, 3)
    ]
    invertida = [str(regras[2].pk), str(regras[1].pk), str(regras[0].pk)]

    resp = api_client.post("/api/v1/promotions/rules/reorder/", {"ids": invertida}, format="json")
    assert resp.status_code == 200, resp.data

    for indice, identificador in enumerate(invertida, start=1):
        assert Promotion.all_objects.get(pk=identificador).position == indice



def test_produto_expoe_o_preco_de_agora_e_de_onde_ele_veio(api_client, account, produto, categoria):
    """O cadastro fica intacto e a leitura mostra o cobrado — com o motivo."""
    tabela = DiscountTable.objects.create(account=account, name="Encarte")
    regra = Promotion.objects.create(
        account=account, table=tabela, name="Refri", target_type="products", discount_kind="fixed",
    )
    PromotionProduct.objects.create(
        account=account, promotion=regra, product=produto,
        promotional_price=Decimal("15.00"), compare_at_price=Decimal("30.00"),
    )

    resp = api_client.get(f"/api/v1/menu/products/{produto.id}/")
    assert resp.status_code == 200, resp.data
    assert resp.data["sale_price"] == "20.00"
    assert resp.data["current_price"] == "15.00"
    assert resp.data["compare_at_price"] == "30.00"
    assert resp.data["promotion"]["table_name"] == "Encarte"
    # As colunas gravadas NÃO saem na API: dois caminhos para o mesmo número
    # deixariam o último que chegasse vencer, sem ordem definida.
    assert "base_price" not in resp.data
