"""O papel da Balança Rápida: cabeçalho da pesagem e linhas para marcar à mão.

O defeito que estes testes impedem é de LAYOUT: uma linha com mais de 32
colunas quebra no rolo de 58 mm, e os quadrados de todas as linhas de baixo
saem tortos — o atendente marca a bebida na linha errada.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.core.tenant import tenant_context
from apps.menu.models import Product, ProductCategory
from apps.printers.comanda_da_pesagem import LARGURA, QUADRADOS, texto_da_comanda_da_pesagem

pytestmark = pytest.mark.django_db


@pytest.fixture
def produtos(account, restaurant, branch):
    with tenant_context(account):
        categoria = ProductCategory.objects.create(
            account=account, restaurant=restaurant, branch=branch, name="Bebidas"
        )

        def criar(nome, **extra):
            return Product.objects.create(
                account=account, restaurant=restaurant, branch=branch, category=categoria,
                name=nome, internal_code=f"B{uuid.uuid4().hex[:6]}", sale_price=Decimal("6.00"),
                **extra,
            )

        yield criar


def _papel(account, restaurant):
    item = SimpleNamespace(
        product=SimpleNamespace(name="Self-service Almoço"),
        unit_price=Decimal("69.90"),
        quantity=Decimal("0.452"),
        total_price=Decimal("31.59"),
    )
    with tenant_context(account):
        return texto_da_comanda_da_pesagem(
            command=SimpleNamespace(number=17, restaurant=restaurant), item=item
        )


def test_o_cabecalho_traz_produto_preco_do_kg_peso_e_valor(account, restaurant):
    """É o que o caixa confere: sem o peso e o preço do kg o valor não se explica."""
    linhas = _papel(account, restaurant).splitlines()

    assert linhas[0] == "COMANDA 17"
    assert "PRODUTO: Self-service Almoço" in linhas
    assert "PRECO KG:" in linhas[3] and linhas[3].endswith("R$ 69,90")
    assert "PESO:" in linhas[4] and linhas[4].endswith("0,452 kg")
    assert "VALOR:" in linhas[5] and linhas[5].endswith("R$ 31,59")


def test_nome_comprido_e_cortado_e_os_quadrados_ficam_alinhados(account, restaurant, produtos):
    """Nome grande cortado, nunca quebrado; em branco sempre no fim."""
    longo = produtos("Refrigerante Coca-Cola Lata 350ml Zero Açúcar")
    curto = produtos("Água")
    restaurant.linhas_da_comanda = [
        {"tipo": "branco"},
        {"tipo": "produto", "produto": str(longo.pk)},
        {"tipo": "produto", "produto": str(curto.pk)},
    ]
    restaurant.save(update_fields=["linhas_da_comanda"])

    linhas = _papel(account, restaurant).splitlines()
    itens = [linha for linha in linhas if linha.endswith(QUADRADOS)]

    assert len(itens) == 3
    assert all(len(linha) == LARGURA for linha in itens)
    assert itens[0].startswith("Refrigerante.")
    assert itens[1].startswith("Água ")
    # Nome, espaço para escrever e os quadrados — a linha do item tem os três.
    assert "____" in itens[0]
    assert itens[2].startswith("_" * 20)
    assert all(len(linha) <= LARGURA for linha in linhas)


def test_produto_desativado_some_do_papel_sem_derrubar_a_pesagem(account, restaurant, produtos):
    """A pesagem não pode falhar por causa de um cadastro de bebida."""
    inativo = produtos("Suco antigo", is_active=False)
    restaurant.linhas_da_comanda = [
        {"tipo": "produto", "produto": str(inativo.pk)},
        {"tipo": "produto", "produto": str(uuid.uuid4())},
    ]
    restaurant.save(update_fields=["linhas_da_comanda"])

    papel = _papel(account, restaurant)

    assert QUADRADOS not in papel
    assert "Suco antigo" not in papel


def test_titulo_livre_sai_na_ordem_com_os_produtos(account, restaurant, produtos):
    """Produto e título livre na ordem configurada; em branco no fim."""
    agua = produtos("Água")
    restaurant.linhas_da_comanda = [
        {"tipo": "branco"},
        {"tipo": "texto", "nome": "Coca-Cola"},
        {"tipo": "produto", "produto": str(agua.pk)},
    ]
    restaurant.save(update_fields=["linhas_da_comanda"])

    itens = [linha for linha in _papel(account, restaurant).splitlines() if linha.endswith(QUADRADOS)]

    assert itens[0].startswith("Coca-Cola ")
    assert itens[1].startswith("Água ")
    assert itens[2].startswith("_" * 20)
    assert all(len(linha) == LARGURA for linha in itens)


def test_largura_do_recibo_de_venda_e_espaco_entre_os_itens(account, restaurant, produtos):
    """42 colunas, como o recibo de venda; uma linha vazia entre os itens.

    Em 32 colunas a comanda saía estreita no rolo de 80 mm, e os itens
    colados uns nos outros não davam espaço para escrever.
    """
    from apps.printers.services import LARGURA_CUPOM

    agua = produtos("Água")
    restaurant.linhas_da_comanda = [
        {"tipo": "produto", "produto": str(agua.pk)},
        {"tipo": "texto", "nome": "Coca-Cola"},
        {"tipo": "branco"},
    ]
    restaurant.save(update_fields=["linhas_da_comanda"])

    linhas = _papel(account, restaurant).splitlines()
    primeira = next(i for i, linha in enumerate(linhas) if linha.endswith(QUADRADOS))

    assert LARGURA == LARGURA_CUPOM
    assert all(len(linha) <= LARGURA for linha in linhas)
    assert linhas[primeira].startswith("Água")
    assert linhas[primeira + 1] == ""
    assert linhas[primeira + 2].startswith("Coca-Cola")
    assert linhas[primeira + 3] == ""
    assert linhas[primeira + 4].startswith("_" * 20)
