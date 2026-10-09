"""A nota emitida na loja chega à nuvem — e as atualizações dela também.

Uma nota fiscal não nasce pronta. Ela nasce, na melhor das hipóteses,
`pending`; vira `issued` quando a SEFAZ autoriza, e nesse instante ganha o
protocolo, a chave definitiva, o XML e a URL do DANFE. Quando algo dá errado,
nasce `error` e só depois — configurado o token, corrigido o perfil — é
reenviada e autorizada.

Com `conflict_policy=MANUAL`, só a PRIMEIRA chegada era aplicada na nuvem: a
linha ainda não existia lá, então não havia o que conflitar. Toda alteração
seguinte caía em `_decidir_versao_nova`, que devolve CONFLITO para MANUAL —
e a nuvem guardava para sempre o primeiro retrato, quase sempre o de erro.

Do lado da loja nada aparecia: o evento era reconhecido, a fila zerava. O
prejuízo ficava só na nuvem, em conflitos que ninguém abria.
"""
import pytest

from apps.synchronization.constants import NodeType
from apps.synchronization.services import conflicts


pytestmark = pytest.mark.django_db


def _decidir(entity_type, *, recebedor, remota, local, existe=True):
    return conflicts.decide(
        entity_type,
        local_version=local,
        remote_version=remota,
        receiving_node_type=recebedor,
        local_exists=existe,
        local_instance=None,
    )


@pytest.mark.parametrize("tipo", ["invoice", "invoice_item"])
def test_a_nuvem_APLICA_a_atualizacao_que_a_loja_manda(tipo):
    """O defeito: a autorização da SEFAZ nunca chegava à nuvem."""
    decisao = _decidir(tipo, recebedor=NodeType.CLOUD, remota=200, local=100)

    assert decisao == conflicts.APLICAR


@pytest.mark.parametrize("tipo", ["invoice", "invoice_item"])
def test_a_primeira_chegada_tambem_aplica(tipo):
    """Isto já funcionava, e continua: sem linha local não há o que conflitar."""
    decisao = _decidir(
        tipo, recebedor=NodeType.CLOUD, remota=100, local=0, existe=False
    )

    assert decisao == conflicts.APLICAR


@pytest.mark.parametrize("tipo", ["invoice", "invoice_item"])
def test_a_LOJA_aplica_a_nota_mais_nova_que_vem_da_nuvem(tipo):
    """A nota emitida na nuvem (pagamento com a loja fora) precisa descer.

    Antes a loja recusava e abria conflito: ela via o pedido pago e sem nota,
    e o operador emitia a segunda NFC-e da mesma venda. A versão só anda para
    a frente (`error` → `pending` → `issued`): a mais nova é a certa.
    """
    decisao = _decidir(tipo, recebedor=NodeType.LOCAL, remota=200, local=100)

    assert decisao == conflicts.APLICAR


@pytest.mark.parametrize("tipo", ["invoice", "invoice_item"])
def test_evento_atrasado_da_loja_nao_desfaz_o_que_ja_subiu(tipo):
    """Entrega fora de ordem não pode reverter uma nota autorizada."""
    decisao = _decidir(tipo, recebedor=NodeType.CLOUD, remota=100, local=200)

    assert decisao == conflicts.IGNORAR


@pytest.mark.parametrize("tipo", ["invoice", "invoice_item"])
def test_a_nota_nunca_e_tratada_como_esqueleto(tipo):
    """Uma nota local sem história de sincronização NÃO aceita versão mais velha.

    O esqueleto (a conta criada na matrícula) aceita o dado verdadeiro mesmo
    "mais velho". A nota não: para documento fiscal a versão decide sempre.
    """
    class _Nota:
        pk = "nota-local"

    assert conflicts._linha_local_nunca_sincronizou(tipo, _Nota()) is False


@pytest.mark.parametrize("tipo", ["invoice", "invoice_item"])
def test_a_nuvem_NUNCA_apaga_uma_nota_para_dar_lugar_a_outra(tipo):
    """A adoção apaga a linha local. No fiscal isso não existe.

    `LOCAL_WINS` torna a loja autoridade sobre a nota — e `origin_is_authority`
    lia a política para decidir se podia apagar a duplicata do outro lado. A
    troca de `MANUAL` para `LOJA` teria ligado isso sozinha: uma colisão de
    chave única e a nuvem descartaria uma nota dela. Documento fiscal em
    duplicidade se cancela, um a um, dentro do prazo — não se apaga.
    """
    from apps.synchronization.services import adoption

    assert adoption.origin_is_authority(tipo, NodeType.CLOUD) is False
    assert adoption.origin_is_authority(tipo, NodeType.LOCAL) is False


def test_a_lista_de_entidades_fiscais_e_esta_e_nenhuma_outra():
    """Uma entrada a mais aqui isenta a entidade de DUAS regras de uma vez:
    o esqueleto e a adoção.

    Nomear a lista num teste é o que torna essa isenção uma decisão visível no
    diff, e não um efeito colateral de mexer no catálogo.
    """
    from apps.synchronization.constants import ENTIDADES_FISCAIS

    assert ENTIDADES_FISCAIS == frozenset({"invoice", "invoice_item"})
