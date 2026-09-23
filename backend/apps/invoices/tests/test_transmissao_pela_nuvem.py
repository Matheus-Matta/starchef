"""A loja monta a nota; a nuvem transmite. E falhar ali não condena o documento.

O ponto mais delicado deste caminho não é a transmissão — é a CLASSIFICAÇÃO da
falha. Não conseguir falar com a nuvem não diz nada sobre a validade do
documento: a nota fica pendente e volta na retransmissão. Se virasse rejeição,
uma nota perfeitamente boa seria marcada como recusada por causa de um cabo de
rede — e recusa não é retentada nunca mais.

É a mesma regra que `contingency.py` já protege num nível acima: só
indisponibilidade autoriza tentar de novo.
"""
from unittest.mock import patch

import pytest
import requests

from apps.invoices import relay_client
from apps.invoices.providers import FiscalConfigurationError, FiscalUnavailable


pytestmark = pytest.mark.django_db


class _Resposta:
    def __init__(self, status_code, corpo):
        self.status_code = status_code
        self._corpo = corpo
        self.content = b"x" if corpo is not None else b""

    def json(self):
        return self._corpo


@pytest.fixture(autouse=True)
def _no_desta_loja(monkeypatch):
    """A identidade do nó, que vai no cabeçalho junto do token."""

    class _No:
        id = "11111111-1111-4111-8111-111111111111"

    monkeypatch.setattr(
        "apps.synchronization.services.nodes.self_node", lambda: _No()
    )


@pytest.fixture
def como_loja(settings):
    settings.FISCAL_TRANSMIT_VIA_CLOUD = True
    settings.SYNC_NODE_TYPE = "local"
    settings.SYNC_CLOUD_API_URL = "https://api.starchef.com.br"
    settings.SYNC_AUTH_TOKEN = "token-do-no"
    return settings


# ── quem delega ─────────────────────────────────────────────────────────────
def test_a_loja_delega(como_loja):
    assert relay_client.deve_delegar(None) is True


def test_a_NUVEM_nao_delega(como_loja):
    """Ela é o destino. Delegar seria pedir a si mesma."""
    como_loja.SYNC_NODE_TYPE = "cloud"

    assert relay_client.deve_delegar(None) is False


def test_instalacao_UNICA_nao_delega(como_loja):
    """Sem endereço de nuvem não há a quem pedir — e o segredo está nela mesma."""
    como_loja.SYNC_CLOUD_API_URL = ""

    assert relay_client.deve_delegar(None) is False


def test_dá_para_DESLIGAR_a_delegação(como_loja):
    como_loja.FISCAL_TRANSMIT_VIA_CLOUD = False

    assert relay_client.deve_delegar(None) is False


# ── o caminho feliz ─────────────────────────────────────────────────────────
def test_a_resposta_do_provedor_volta_CRUA(como_loja):
    """Quem interpreta é a loja: é lá que a nota recebe chave e protocolo."""
    resposta = _Resposta(200, {"status_code": 200, "data": {"status": "autorizado"}})

    with patch("requests.post", return_value=resposta):
        codigo, dados = relay_client.executar(
            None, operacao="transmit", reference="ref-1", document_model="65",
            payload={"a": 1},
        )

    assert codigo == 200
    assert dados == {"status": "autorizado"}


def test_a_rejeicao_do_provedor_CHEGA_como_rejeicao(como_loja):
    """A nuvem transmitiu e a SEFAZ recusou: isso não é indisponibilidade.

    O código do provedor precisa atravessar o relé intacto, senão a loja
    trataria uma recusa definitiva como algo a tentar de novo para sempre.
    """
    resposta = _Resposta(200, {"status_code": 422, "data": {"status": "erro_autorizacao"}})

    with patch("requests.post", return_value=resposta):
        codigo, dados = relay_client.executar(
            None, operacao="transmit", reference="ref-1", document_model="65",
        )

    assert codigo == 422


# ── e o que importa mesmo: como a falha é classificada ──────────────────────
def test_nuvem_INALCANCAVEL_e_indisponibilidade(como_loja):
    """Cabo de rede não condena documento nenhum."""
    with patch("requests.post", side_effect=requests.ConnectionError("sem rota")):
        with pytest.raises(FiscalUnavailable):
            relay_client.executar(
                None, operacao="transmit", reference="ref-1", document_model="65",
            )


@pytest.mark.parametrize("codigo", [500, 502, 503, 429])
def test_nuvem_com_problema_e_indisponibilidade(como_loja, codigo):
    with patch("requests.post", return_value=_Resposta(codigo, {})):
        with pytest.raises(FiscalUnavailable):
            relay_client.executar(
                None, operacao="transmit", reference="ref-1", document_model="65",
            )


def test_nuvem_RECUSANDO_transmitir_tambem_e_indisponibilidade(como_loja):
    """409 é a nuvem dizendo que NÃO transmitiu — nunca chegou ao provedor.

    Sem configuração fiscal lá, ou nó errado. O documento continua intacto, e
    tratá-lo como recusado marcaria como inválida uma nota que ninguém leu.
    """
    resposta = _Resposta(409, {"detail": "Nenhuma configuração fiscal ativa"})

    with patch("requests.post", return_value=resposta):
        with pytest.raises(FiscalUnavailable):
            relay_client.executar(
                None, operacao="transmit", reference="ref-1", document_model="65",
            )


def test_identidade_RECUSADA_e_configuracao_e_nao_se_retenta(como_loja):
    """403 não melhora tentando de novo: é credencial, e alguém tem de agir."""
    with patch("requests.post", return_value=_Resposta(403, {})):
        with pytest.raises(FiscalConfigurationError):
            relay_client.executar(
                None, operacao="transmit", reference="ref-1", document_model="65",
            )


def test_loja_SEM_token_do_no_e_configuracao(como_loja):
    como_loja.SYNC_AUTH_TOKEN = ""

    with pytest.raises(FiscalConfigurationError):
        relay_client.executar(
            None, operacao="transmit", reference="ref-1", document_model="65",
        )


def test_o_pedido_leva_O_ID_DO_NO_junto_do_token(como_loja):
    """Sem ele a nuvem devolve 401, e a nota fica pendente para sempre.

    `NodeTokenAuthentication` precisa do id em cabeçalho próprio — o token
    sozinho exigiria varrer todos os nós comparando hash. O primeiro relé que
    eu escrevi mandava só o `Authorization`, e o sintoma era o pior possível:
    parecia rede instável.
    """
    capturado = {}

    def _post(url, **kwargs):
        capturado.update(kwargs.get("headers") or {})
        return _Resposta(200, {"status_code": 200, "data": {}})

    with patch("requests.post", side_effect=_post):
        relay_client.executar(
            None, operacao="transmit", reference="ref-1", document_model="65",
        )

    assert capturado["Authorization"] == "Bearer token-do-no"
    assert capturado["X-Sync-Node-Id"] == "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize("codigo", [401, 403])
def test_identidade_recusada_NAO_e_indisponibilidade(como_loja, codigo):
    """Repetir não conserta credencial — e a nota não pode ficar em espera."""
    with patch("requests.post", return_value=_Resposta(codigo, {})):
        with pytest.raises(FiscalConfigurationError):
            relay_client.executar(
                None, operacao="transmit", reference="ref-1", document_model="65",
            )
