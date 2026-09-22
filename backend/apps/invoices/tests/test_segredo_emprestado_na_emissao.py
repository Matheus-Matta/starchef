"""Quem CONSOME o segredo emprestado — e todos precisam consultá-lo.

`emission_secrets.segredos_de` resolve; estes são os quatro pontos que o usam.
Um leitor esquecido não aparece como erro: aparece como recusa, dita pelo
provedor, com o segredo na mão. Foi o que aconteceu com o pré-voo.
"""
import pytest

from apps.invoices.models import FiscalConfig

from .emprestimo import PACOTE, config_sem_segredo, nuvem_devolve


pytestmark = pytest.mark.django_db


@pytest.fixture
def config(account, restaurant, branch):
    return config_sem_segredo(account, restaurant, branch)


@pytest.fixture
def nuvem_responde(monkeypatch, config):
    pacote = {**PACOTE, "fiscal_config_id": str(config.id)}
    nuvem_devolve(monkeypatch, pacote)
    return pacote


def test_o_pacote_da_nuvem_LEVA_o_token_do_provedor(account, restaurant, branch):
    """Ele faltava, e sem ele o pacote não emitia nada.

    A loja abria o envelope com o certificado e o CSC na mão e ainda ouvia
    "empresa ainda sem token para o ambiente selecionado".
    """
    from apps.synchronization.constants import NodeType
    from apps.synchronization.models import SyncNode
    from apps.synchronization.services import credentials

    FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        document_model=FiscalConfig.MODEL_NFCE, series=1, next_number=1,
        environment=FiscalConfig.ENV_HOMOLOGATION, cnpj="63201558000155", uf="RJ",
        focus_token_homologation="TOKEN-DA-NUVEM", csc_id="1", csc_token="CSC",
    )
    no = SyncNode.objects.create(
        account=account, restaurant=restaurant, node_type=NodeType.LOCAL,
        name="Loja de teste",
    )

    pacote = credentials.montar_pacote(no)

    assert pacote["focus_token_homologation"] == "TOKEN-DA-NUVEM"


def test_o_PROVEDOR_usa_o_token_emprestado(config, nuvem_responde):
    """O teste que fecha o buraco: o resolvedor existir não basta.

    Os testes acima provam `segredos_de`. Este prova que a Focus o CONSULTA —
    sem ele, voltar `_token` a ler direto do `FiscalConfig` passaria
    despercebido, que é exatamente o defeito original.
    """
    from apps.invoices.providers import FocusNfeProvider

    assert FocusNfeProvider._token(config) == "TOKEN-HOMOLOGACAO"


def test_sem_token_em_lugar_nenhum_o_provedor_RECUSA(config, monkeypatch):
    """A recusa continua sendo a de sempre, com o motivo certo."""
    from apps.invoices.providers import FiscalConfigurationError, FocusNfeProvider

    monkeypatch.setattr(
        "apps.synchronization.services.credentials_client.obter",
        lambda **kwargs: None,
    )

    with pytest.raises(FiscalConfigurationError) as falha:
        FocusNfeProvider._token(config)

    assert "sem token para o ambiente selecionado" in str(falha.value)


def test_o_PRE_VOO_enxerga_o_CSC_emprestado(config, nuvem_responde):
    """O buraco que sobrou do primeiro conserto.

    `_token` e o QR já consultavam o empréstimo, mas `unavailable_reason` lia
    o CSC direto do model e recusava com "ID do CSC: obrigatorio para emitir
    NFC-e" — com o CSC na mão. A emissão parava ANTES de chegar ao provedor,
    então nenhum dos testes anteriores pegava.
    """
    from apps.invoices.focus import company_payload_missing_fields

    faltando = {issue["field"] for issue in company_payload_missing_fields(config)}

    assert "csc_id" not in faltando, "o pré-voo ignorou o CSC emprestado"
    assert "csc_token" not in faltando


def test_o_payload_da_empresa_LEVA_o_certificado_emprestado(config, nuvem_responde):
    """Cadastrar a empresa na Focus a partir da loja também precisa dele."""
    from apps.invoices.focus import build_focus_company_payload

    payload = build_focus_company_payload(config)

    assert payload["arquivo_certificado_base64"] == "Y2VydGlmaWNhZG8="
    assert payload["senha_certificado"] == "senha-do-a1"
