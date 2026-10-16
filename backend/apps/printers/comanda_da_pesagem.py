"""O texto da comanda que sai na pesagem da Balança Rápida.

Cabeçalho com o que foi pesado (produto, preço do kg, peso e valor) e, abaixo,
as linhas que o atendente marca à mão — a lista do restaurante
(`Restaurant.linhas_da_comanda`)::

    COMANDA 17
    ------------------------------------------
    PRODUTO: Self-service Almoco
    PRECO KG:                         R$ 69,90
    PESO:                             0,452 kg
    VALOR:                            R$ 31,59
    ------------------------------------------
    Agua sem gas   ____________ [  ] [  ] [  ]

    Coca-Cola      ____________ [  ] [  ] [  ]

    ___________________________ [  ] [  ] [  ]

A largura é a do RECIBO DE VENDA (`LARGURA_CUPOM`, 42 colunas): em 32 a
comanda saía estreita no rolo de 80 mm. Entre um item e outro vai uma linha
vazia — colados, não sobrava espaço para escrever. O nome comprido é cortado,
nunca quebrado: uma linha que vira duas desalinha os quadrados de todas as de
baixo.
"""
from decimal import Decimal

from apps.restaurants.linhas_da_comanda import TIPO_BRANCO, TIPO_PRODUTO, TIPO_TEXTO

#: A mesma largura do recibo de venda (`services.LARGURA_CUPOM`), repetida
#: aqui porque `services` importa este módulo; o teste confere as duas.
LARGURA = 42
QUADRADOS = "[  ] [  ] [  ]"
# Nome + espaço + linha para escrever + espaço + quadrados = 42.
LARGURA_DO_NOME = 14
LINHA_PARA_ESCREVER = "_" * (LARGURA - LARGURA_DO_NOME - len(QUADRADOS) - 2)
LINHA_EM_BRANCO = "_" * (LARGURA - len(QUADRADOS) - 1)


def _cortar(texto, largura):
    texto = " ".join(str(texto or "").split())
    return texto if len(texto) <= largura else texto[: largura - 1].rstrip() + "."


def _reais(valor):
    inteiro, centavos = f"{Decimal(valor):,.2f}".split(".")
    return f"R$ {inteiro.replace(',', '.')},{centavos}"


def _quilos(valor):
    return f"{Decimal(valor):.3f}".replace(".", ",") + " kg"


def _campo(rotulo, valor):
    return rotulo + valor.rjust(LARGURA - len(rotulo))


def _linhas_de_item(restaurant):
    """Produtos e títulos na ordem configurada; as em branco sempre no fim.

    Produto apagado ou desativado depois de entrar na lista some do papel em
    silêncio: a pesagem não pode falhar por causa de um cadastro de bebida.
    """
    from apps.menu.models import Product

    configuradas = list(getattr(restaurant, "linhas_da_comanda", None) or [])
    ids = [linha.get("produto") for linha in configuradas if linha.get("tipo") == TIPO_PRODUTO]
    nomes = {
        str(pk): nome
        for pk, nome in Product.objects.filter(pk__in=ids, restaurant=restaurant, is_active=True)
        .values_list("pk", "name")
    }
    titulos = []
    for linha in configuradas:
        if linha.get("tipo") == TIPO_TEXTO:
            titulos.append(linha.get("nome"))
        elif linha.get("tipo") == TIPO_PRODUTO and linha.get("produto") in nomes:
            titulos.append(nomes[linha["produto"]])
    itens = [
        f"{_cortar(titulo, LARGURA_DO_NOME).ljust(LARGURA_DO_NOME)} {LINHA_PARA_ESCREVER} {QUADRADOS}"
        for titulo in titulos
        if titulo
    ]
    brancos = sum(1 for linha in configuradas if linha.get("tipo") == TIPO_BRANCO)
    todas = itens + [f"{LINHA_EM_BRANCO} {QUADRADOS}"] * brancos
    # Uma linha vazia ENTRE os itens: espaço para escrever e para a mão.
    return [linha for item in todas for linha in (item, "")][:-1]


def texto_da_comanda_da_pesagem(*, command, item):
    linhas = [
        # A primeira linha sai em letra alta (`_readableReceiptBytes` do PDV).
        f"COMANDA {command.number}",
        "-" * LARGURA,
        _cortar(f"PRODUTO: {item.product.name}", LARGURA),
        _campo("PRECO KG:", _reais(item.unit_price)),
        _campo("PESO:", _quilos(item.quantity)),
        _campo("VALOR:", _reais(item.total_price)),
    ]
    itens = _linhas_de_item(command.restaurant)
    if itens:
        linhas += ["-" * LARGURA, *itens]
    linhas += ["-" * LARGURA, "Leve esta comanda ao caixa."]
    return "\n".join(linhas)
