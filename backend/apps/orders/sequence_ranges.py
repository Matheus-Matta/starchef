"""A faixa de números de pedido que CADA NÓ entrega.

O terminal fala com dois backends: o da loja, que atende normalmente, e a
nuvem, que atende quando a loja cai. Os dois numeram pedido com
``Max(sequence) + 1`` sobre o mesmo restaurante — e enquanto a loja está fora
ela não enxerga o que a nuvem emitiu. Os dois entregam o mesmo número.

O modo de falhar é o pior possível: o número aparece igual nas duas bases, e
quando a sincronização junta as duas, dois pedidos diferentes têm o "pedido
17". A conferência de caixa do dia não fecha, e ninguém consegue dizer qual
dos dois é qual.

## O remédio é a faixa, e é o mesmo que o projeto já usa

`services/user_ids.py` resolveu exatamente isto para `auth.User`: a loja
numera a partir de um bilhão, a nuvem continua na faixa baixa, e as duas nunca
se encontram. Aqui a direção é invertida de propósito.

**A loja fica com a faixa baixa.** Ela é quem atende no dia a dia, e o número
do pedido é lido em voz alta — "pedido 42" cabe num cupom e na boca do
operador. A NUVEM é a exceção, e é ela que vai para a faixa alta.

E isso dá um efeito colateral que vale mais que o desempate: um pedido com
número acima de um milhão **é**, por definição, um pedido emitido enquanto a
loja estava fora. Quem conferir o caixa vê isso sem precisar de relatório.
"""
from django.conf import settings

#: Primeiro número que a NUVEM entrega a pedido emitido nela.
#:
#: `PositiveIntegerField` vai até 2.147.483.647, então sobram mais de um
#: bilhão de números de cada lado. Um restaurante precisaria de um milhão de
#: pedidos para a loja alcançar esta faixa — e nesse dia o problema é outro.
PRIMEIRO_NUMERO_DA_NUVEM = 1_000_000


def _tipo_do_no():
    return str(getattr(settings, "SYNC_NODE_TYPE", "") or "").strip().lower()


def _papel_gravado():
    """O papel deste nó SEGUNDO O BANCO, ou `None` se não há registro.

    O `SyncNode` com `is_self=True` é criado pelo provisionamento
    (`sync_provision_node` na nuvem, `sync_install_node` na loja) e o outro
    lado tem um registro que casa com ele. É conhecimento COMBINADO entre os
    dois; a variável de ambiente é configuração local de um só.

    Nunca derruba a venda: instalação sem sincronização, banco fora do ar ou
    tabela ainda não migrada devolvem `None`, e quem chama cai na variável.
    """
    try:
        from apps.synchronization.services.nodes import self_node_or_none

        no = self_node_or_none()
    except Exception:  # noqa: BLE001 — numerar pedido não depende da sincronização
        return None
    tipo = getattr(no, "node_type", "") or ""
    return tipo.strip().lower() or None


def e_a_nuvem():
    """Este backend é a nuvem?

    QUEM DECIDE É O REGISTRO DO NÓ, e a variável de ambiente só entra quando
    não há registro. A ordem importa, e custou: uma loja com
    `SYNC_NODE_TYPE=cloud` no `.env` passava a numerar na faixa alta, entregava
    os mesmos números que a nuvem entregava, e a sincronização juntava duas
    vendas diferentes com o mesmo "pedido 1.000.002". O sintoma que aparecia
    primeiro era outro — pedido nascendo com número de sete dígitos numa loja
    que nunca passou de três.

    Uma variável errada agora não muda a faixa: ela discorda do banco, o
    `manage.py check` acusa (W008), e a numeração continua certa enquanto
    ninguém arruma.

    Na dúvida (sem registro E sem variável), a resposta é NÃO: o padrão é a
    loja, que é o que quase toda instalação é.
    """
    gravado = _papel_gravado()
    if gravado:
        return gravado == "cloud"
    return _tipo_do_no() == "cloud"


def piso_da_faixa():
    """O menor número que este nó pode entregar."""
    return PRIMEIRO_NUMERO_DA_NUVEM if e_a_nuvem() else 1


def limites_da_faixa():
    """`(piso, teto)` da faixa deste nó. `teto` é `None` na nuvem, que não tem.

    A loja vai de 1 até um número abaixo do piso da nuvem; a nuvem vai do piso
    dela para cima.
    """
    if e_a_nuvem():
        return PRIMEIRO_NUMERO_DA_NUVEM, None
    return 1, PRIMEIRO_NUMERO_DA_NUVEM - 1


def proximo_numero(queryset, campo="sequence"):
    """O próximo número, a partir do maior JÁ USADO DENTRO DA FAIXA deste nó.

    O recorte pela faixa é o ponto todo, e errar nele é sutil nos dois
    sentidos:

    * sem recorte, a loja que recebe da nuvem um pedido 1.000.005 passaria a
      numerar a partir dele — abandonando a faixa dela e indo colidir com a
      nuvem no pedido seguinte;
    * recortando errado (zerando quando o máximo global está fora da faixa), a
      loja voltaria ao número 1 e colidiria com os PRÓPRIOS pedidos.

    Por isso o máximo é calculado no banco, já filtrado pela faixa.
    """
    from django.db.models import Max

    piso, teto = limites_da_faixa()
    na_faixa = queryset.filter(**{f"{campo}__gte": piso})
    if teto is not None:
        na_faixa = na_faixa.filter(**{f"{campo}__lte": teto})
    ultimo = na_faixa.aggregate(value=Max(campo))["value"]
    return (int(ultimo) + 1) if ultimo else piso
