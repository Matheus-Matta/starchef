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
def test_a_LOJA_recusa_a_nuvem_mexer_na_nota_dela(tipo):
    """O §15 continua de pé — no lado que importa.

    A loja é a autora. A nuvem mandando uma versão da nota de volta é o caso
    que precisa de gente olhando, e não de uma sobrescrita silenciosa.
    """
    decisao = _decidir(tipo, recebedor=NodeType.LOCAL, remota=200, local=100)

    assert decisao == conflicts.CONFLITO


@pytest.mark.parametrize("tipo", ["invoice", "invoice_item"])
def test_evento_atrasado_da_loja_nao_desfaz_o_que_ja_subiu(tipo):
    """Entrega fora de ordem não pode reverter uma nota autorizada."""
    decisao = _decidir(tipo, recebedor=NodeType.CLOUD, remota=100, local=200)

    assert decisao == conflicts.IGNORAR


@pytest.mark.parametrize("tipo", ["invoice", "invoice_item"])
def test_a_queda_de_conexao_NAO_autoriza_a_nuvem_a_sobrescrever(tipo, monkeypatch):
    """A exceção da atualização perdida não vale para documento fiscal.

    Para o resto do catálogo, uma linha que a loja não tocou enquanto esteve
    fora aceita o que a nuvem traz — é o que faz o desvio para a nuvem valer.
    A nota não: o PDV nunca desvia o fiscal, então divergência aqui não nasceu
    de queda nenhuma.

    A proteção era amarrada à política `MANUAL`. Trocá-la por `LOJA` teria
    desligado isto em silêncio, e é este teste que prende o contrário.
    """
    from django.utils import timezone

    class _NoFalso:
        offline_since = timezone.now()

    monkeypatch.setattr(
        "apps.synchronization.services.nodes.self_node_or_none",
        lambda: _NoFalso(),
    )
    # Versão local ANTERIOR à queda: para qualquer outra entidade isto seria
    # "atualização que perdemos" e entraria.
    assert conflicts._so_perdemos_a_atualizacao(tipo, NodeType.LOCAL, 1) is False


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
    a atualização perdida e a adoção.

    Nomear a lista num teste é o que torna essa isenção uma decisão visível no
    diff, e não um efeito colateral de mexer no catálogo.
    """
    from apps.synchronization.constants import ENTIDADES_FISCAIS

    assert ENTIDADES_FISCAIS == frozenset({"invoice", "invoice_item"})
