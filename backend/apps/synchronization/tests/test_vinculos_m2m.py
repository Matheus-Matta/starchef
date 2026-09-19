"""Vínculos ManyToMany: eles viajam, e esquecer um não passa em silêncio.

O defeito que originou este arquivo: `CashStation.operators` nunca sincronizou.
O caixa chegava na loja, a pessoa chegava, e a LIGAÇÃO entre os dois não —
então nenhum operador conseguia abrir caixa, com a tela mostrando o caixa e o
usuário ali, presentes. É o pior formato de falha: tudo que se olha parece
certo.

A causa tinha duas camadas, e a segunda é pior que a primeira:

1. o catálogo não declarava o campo, então ele não viajava;
2. mesmo declarado, o mecanismo lia e gravava o vínculo pelo manager PADRÃO do
   modelo-alvo — que num modelo de tenant é o `TenantManager`, e ele devolve
   `none()` sem conta no contexto. Fora de requisição (carga inicial, worker)
   não há conta: o vínculo serializaria vazio e apagaria o que existia do
   outro lado.
"""
import pytest
from django.contrib.auth import get_user_model

from apps.menu.models import Product, ProductCategory
from apps.payments.models import CashStation
from apps.restaurants.models import Restaurant
from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import apply, crypto, serialization
from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db

User = get_user_model()


def _evento(conta, origem, destino, *, entity_type, entity_id, fields, sequence=1,
            version=None):
    # A versão precisa ser MAIOR que a local, senão a resolução de conflito
    # ignora o evento — e com razão: sem fonte de versão explícita ela vem do
    # `updated_at` em microssegundos, que num registro recém-criado é enorme.
    version = version or 10
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
        entity_id=str(entity_id), operation=Operation.UPSERT, entity_version=version,
        payload=payload, payload_checksum=crypto.checksum(payload),
        status=EventStatus.RECEIVED,
    )


# ── a trava ─────────────────────────────────────────────────────────────────

def test_nenhum_vinculo_fica_sem_decisao():
    """A trava que impede o defeito de voltar.

    Um M2M é invisível para a checagem de model: a tabela de ligação é criada
    pelo Django e nunca aparece em `get_models()`. Sem esta varredura, campo
    novo entra sem ninguém decidir nada sobre ele.
    """
    from apps.synchronization.management.commands.sync_check_registry import (
        vinculos_sem_decisao,
    )

    faltando = vinculos_sem_decisao()
    assert faltando == [], (
        "vínculo sem decisão: "
        + ", ".join(f"{e}.{c} -> {alvo}" for e, c, alvo in faltando)
    )


def test_a_trava_reprova_um_vinculo_esquecido():
    """O teste acima só vale se a trava souber reprovar."""
    from apps.synchronization.management.commands.sync_check_registry import (
        vinculos_sem_decisao,
    )

    entrada = registry.get("cash_station")
    original = entrada.m2m_fields
    try:
        object.__setattr__(entrada, "m2m_fields", {})
        faltando = vinculos_sem_decisao()
        assert any(c == "operators" for _e, c, _a in faltando)
    finally:
        object.__setattr__(entrada, "m2m_fields", original)


def test_o_caixa_casa_o_operador_por_username_e_nao_por_id():
    """O id do usuário é inteiro sequencial e difere entre os dois bancos.

    Casar por ele ligaria o caixa à PESSOA ERRADA — um defeito que ninguém
    descobre olhando a tela, porque haveria um nome ali.
    """
    assert registry.get("cash_station").m2m_fields == {"operators": "username"}


# ── o vínculo viaja ─────────────────────────────────────────────────────────

def test_o_vinculo_do_caixa_entra_no_payload(como_nuvem, conta):
    restaurante = Restaurant.objects.create(
        account=conta, legal_name="R LTDA", trade_name="R"
    )
    joana = User.objects.create_user("joana", "joana@x.test", "senha-forte-123")
    caixa = CashStation.objects.create(
        account=conta, restaurant=restaurante, name="CAIXA 1"
    )
    caixa.operators.add(joana)

    dados = serialization.serialize(caixa, registry.get("cash_station"))
    assert dados["operators"] == ["joana"]


def test_aplicar_forma_o_vinculo_na_loja(como_loja, conta, no_nuvem, no_loja):
    """O caso do usuário, ponta a ponta: sem isto a loja não abre caixa."""
    restaurante = Restaurant.objects.create(
        account=conta, legal_name="R LTDA", trade_name="R"
    )
    User.objects.create_user("joana", "joana@x.test", "senha-forte-123")
    caixa = CashStation.objects.create(
        account=conta, restaurant=restaurante, name="CAIXA 1"
    )
    assert list(caixa.operators.all()) == []

    evento = _evento(
        conta, no_nuvem, no_loja, entity_type="cash_station", entity_id=caixa.id,
        fields={
            "account_id": str(conta.id),
            "restaurant_id": str(restaurante.id),
            "name": "CAIXA 1",
            "operators": ["joana"],
        },
        version=serialization.entity_version(caixa) + 1,
    )
    apply.apply_event(evento)

    assert list(caixa.operators.values_list("username", flat=True)) == ["joana"]


def test_vinculo_para_modelo_de_TENANT_tambem_viaja(como_nuvem, conta):
    """O caso que o manager padrão quebrava em silêncio.

    `Product.restaurants` aponta para um modelo de tenant. Lido pelo
    `_default_manager` fora de requisição, o `TenantManager` devolve `none()`
    e o vínculo serializa VAZIO — o payload afirma "não pertence a loja
    nenhuma" e aplicar isso do outro lado apaga o que havia.

    Este teste roda sem conta no contexto de propósito: é exatamente a
    condição da carga inicial e do worker.
    """
    from apps.core.tenant import clear_current_account

    restaurante = Restaurant.objects.create(
        account=conta, legal_name="R LTDA", trade_name="R"
    )
    categoria = ProductCategory.objects.create(
        account=conta, restaurant=restaurante, name="Bebidas"
    )
    produto = Product.objects.create(
        account=conta, restaurant=restaurante, category=categoria,
        name="Suco", sale_price=10,
    )
    produto.restaurants.add(restaurante)

    clear_current_account()
    dados = serialization.serialize(produto, registry.get("product"))

    assert dados["restaurants"] == [str(restaurante.id)], (
        "sem conta no contexto o vínculo serializou vazio — é a carga inicial "
        "apagando relação em vez de sincronizá-la"
    )


def test_remover_o_vinculo_na_nuvem_remove_na_loja(como_loja, conta, no_nuvem, no_loja):
    """Tirar alguém do caixa na nuvem tem de tirar na loja.

    Este caso passa pelo caminho fácil: `auth.User` não é modelo de tenant, e
    o manager padrão dele enxerga tudo. Está aqui como regressão do comporta-
    mento, não como prova do defeito — quem prova aquilo é o teste seguinte.
    """
    restaurante = Restaurant.objects.create(
        account=conta, legal_name="R LTDA", trade_name="R"
    )
    joana = User.objects.create_user("joana", "joana@x.test", "senha-forte-123")
    pedro = User.objects.create_user("pedro", "pedro@x.test", "senha-forte-123")
    caixa = CashStation.objects.create(
        account=conta, restaurant=restaurante, name="CAIXA 1"
    )
    caixa.operators.add(joana, pedro)

    evento = _evento(
        conta, no_nuvem, no_loja, entity_type="cash_station", entity_id=caixa.id,
        fields={
            "account_id": str(conta.id),
            "restaurant_id": str(restaurante.id),
            "name": "CAIXA 1",
            "operators": ["joana"],
        },
        version=serialization.entity_version(caixa) + 1,
    )
    apply.apply_event(evento)

    assert list(caixa.operators.values_list("username", flat=True)) == ["joana"], (
        "pedro perdeu o acesso na nuvem e continuou com ele na loja"
    )


def test_remover_vinculo_de_modelo_de_TENANT_tambem_remove(
    como_loja, conta, no_nuvem, no_loja
):
    """O caso que `relacao.set()` errava — e errava para MAIS, não para menos.

    Para saber o que remover, `set()` pergunta ao manager padrão do alvo o que
    já existe. Num modelo de tenant, sem conta no contexto, a resposta é
    "nada": ele conclui que não há o que tirar e só adiciona. Um produto
    retirado de uma loja na nuvem continuaria à venda naquela loja para
    sempre, sem erro em lugar nenhum.
    """
    from apps.core.tenant import clear_current_account

    loja_a = Restaurant.objects.create(account=conta, legal_name="A LTDA", trade_name="A")
    loja_b = Restaurant.objects.create(account=conta, legal_name="B LTDA", trade_name="B")
    categoria = ProductCategory.objects.create(
        account=conta, restaurant=loja_a, name="Bebidas"
    )
    produto = Product.objects.create(
        account=conta, restaurant=loja_a, category=categoria,
        name="Suco", sale_price=10,
    )
    produto.restaurants.add(loja_a, loja_b)

    evento = _evento(
        conta, no_nuvem, no_loja, entity_type="product", entity_id=produto.id,
        fields={
            "account_id": str(conta.id),
            "restaurant_id": str(loja_a.id),
            "category_id": str(categoria.id),
            "name": "Suco",
            "sale_price": "10.00",
            "restaurants": [str(loja_a.id)],
        },
        version=serialization.entity_version(produto) + 1,
    )
    clear_current_account()
    apply.apply_event(evento)

    ligados = sorted(
        str(x) for x in produto.restaurants.through._base_manager.filter(
            product_id=produto.pk
        ).values_list("restaurant_id", flat=True)
    )
    assert ligados == [str(loja_a.id)], (
        "o produto saiu da loja B na nuvem e continuou à venda nela aqui"
    )
