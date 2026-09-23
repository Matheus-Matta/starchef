"""Lado NUVEM: só três portas, e só a empresa da própria loja.

A tentação, ao construir isto, é relayar `(método, caminho, corpo)` e deixar a
loja endereçar o provedor. Seria entregar a chave mestra por outro buraco: o
mesmo token que emite nota também faz `DELETE /v2/empresas/{id}`, e aí uma
loja poderia apagar o cadastro fiscal de qualquer restaurante da conta.

Por isso existem três operações nomeadas e o caminho é montado do lado da
nuvem. Estes testes prendem as duas fronteiras: o que se pode pedir, e em nome
de quem.
"""
from unittest.mock import patch

import pytest

from apps.synchronization.constants import NodeType
from apps.synchronization.services import fiscal_relay


pytestmark = pytest.mark.django_db


@pytest.fixture
def config_fiscal(account, restaurant, branch):
    from apps.invoices.models import FiscalConfig

    return FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        document_model=FiscalConfig.MODEL_NFCE, series=1, next_number=1,
        environment=FiscalConfig.ENV_HOMOLOGATION,
        provider=FiscalConfig.PROVIDER_FOCUS_NFE,
        cnpj="63201558000155", uf="RJ",
    )


@pytest.fixture
def no_loja(account, restaurant, config_fiscal):
    from apps.synchronization.models import SyncNode

    return SyncNode.objects.create(
        account=account, restaurant=restaurant,
        node_type=NodeType.LOCAL, name="Loja de teste",
    )


@pytest.fixture
def no_nuvem(account):
    from apps.synchronization.models import SyncNode

    return SyncNode.objects.create(
        account=account, node_type=NodeType.CLOUD, name="Nuvem de teste",
    )


def test_a_nuvem_transmite_pela_loja(no_loja):
    """O caminho feliz: a resposta do provedor volta como veio."""
    with patch(
        "apps.invoices.providers.FocusNfeProvider.relay_execute",
        return_value=(200, {"status": "autorizado"}),
    ) as chamada:
        codigo, dados = fiscal_relay.executar(
            no_loja, operacao="transmit", reference="ref-1",
            document_model="65", payload={"a": 1},
        )

    assert (codigo, dados) == (200, {"status": "autorizado"})
    assert chamada.call_args.kwargs["operacao"] == "transmit"


def test_o_no_da_NUVEM_nao_transmite(no_nuvem):
    """Um nó de nuvem pedindo isto é sinal de token usado no lugar errado."""
    with pytest.raises(fiscal_relay.RelayRecusado):
        fiscal_relay.executar(
            no_nuvem, operacao="transmit", reference="ref-1", document_model="65",
        )


@pytest.mark.parametrize(
    "operacao", ["delete_company", "empresas", "", "GET", "listar"],
)
def test_so_as_TRES_operacoes_nomeadas_passam(no_loja, operacao):
    """A fronteira que impede o relé de virar proxy para `/v2/empresas`."""
    with pytest.raises(fiscal_relay.RelayRecusado):
        fiscal_relay.executar(
            no_loja, operacao=operacao, reference="ref-1", document_model="65",
        )


def test_loja_SEM_configuracao_fiscal_e_recusada(account, restaurant):
    """Sem cadastro não há empresa em nome de quem transmitir."""
    from apps.synchronization.models import SyncNode

    orfao = SyncNode.objects.create(
        account=account, restaurant=restaurant,
        node_type=NodeType.LOCAL, name="Loja sem fiscal",
    )

    with pytest.raises(fiscal_relay.RelayRecusado):
        fiscal_relay.executar(
            orfao, operacao="transmit", reference="ref-1", document_model="65",
        )


def test_a_configuracao_usada_e_a_do_NO_e_nao_a_que_o_corpo_pedir(no_loja, config_fiscal):
    """Uma loja transmite como a própria empresa, ou não transmite.

    O corpo do pedido não escolhe emitente — seria assinar a nota com o
    certificado do cliente errado.
    """
    with patch(
        "apps.invoices.providers.FocusNfeProvider.relay_execute",
        return_value=(200, {}),
    ) as chamada:
        fiscal_relay.executar(
            no_loja, operacao="transmit", reference="ref-1",
            document_model="65", payload={"fiscal_config_id": "outro-qualquer"},
        )

    assert chamada.call_args.args[0].pk == config_fiscal.pk
