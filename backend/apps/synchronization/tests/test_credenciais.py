"""O canal do segredo de emissão: emprestado, cifrado, e nunca no disco.

O que este canal substitui: o certificado A1 da empresa viajava dentro do
payload de sincronização. O tráfego é cifrado, mas `SyncEvent.payload` é um
JSONField em TEXTO PURO gravado nos DOIS bancos — a cifra protege o cabo, não o
disco. O segredo ficava legível na tabela de eventos da nuvem, na de cada loja,
e em todo backup dos dois, para sempre.
"""
import pytest
from django.urls import reverse

from apps.invoices.models import FiscalConfig
from apps.synchronization.services import credentials, credentials_client
from apps.synchronization.tests.conftest import TOKEN_DE_TESTE

pytestmark = pytest.mark.django_db

CERTIFICADO = "Y2VydGlmaWNhZG8tZmFsc28="
SENHA = "senha-do-certificado"


@pytest.fixture
def config_fiscal(conta, db):
    from apps.restaurants.models import Branch, Restaurant

    restaurante = Restaurant.objects.create(
        account=conta, legal_name="Loja LTDA", trade_name="Loja"
    )
    filial = Branch.objects.create(account=conta, restaurant=restaurante, name="Matriz")
    return FiscalConfig.objects.create(
        account=conta, restaurant=restaurante, branch=filial, is_active=True,
        provider=FiscalConfig.PROVIDER_FOCUS_NFE,
        csc_id="000001", csc_token="CSC-SECRETO",
        focus_certificate_base64=CERTIFICADO, focus_certificate_password=SENHA,
    )


# ── o pacote ────────────────────────────────────────────────────────────────
def test_o_pacote_leva_certificado_csc_e_senha(como_nuvem, no_loja, config_fiscal):
    pacote = credentials.montar_pacote(no_loja)

    assert pacote["certificate_base64"] == CERTIFICADO
    assert pacote["certificate_password"] == SENHA
    assert pacote["csc_token"] == "CSC-SECRETO"


def test_no_de_nuvem_nao_recebe_credencial(como_nuvem, no_nuvem, config_fiscal):
    """A nuvem não pede credencial a ninguém; um nó CLOUD pedindo é sinal ruim."""
    with pytest.raises(credentials.CredentialsUnavailable, match="loja"):
        credentials.montar_pacote(no_nuvem)


def test_sem_configuracao_fiscal_recusa_com_motivo(como_nuvem, no_loja):
    with pytest.raises(credentials.CredentialsUnavailable, match="configuração fiscal"):
        credentials.montar_pacote(no_loja)


# ── o envelope ──────────────────────────────────────────────────────────────
def test_o_envelope_abre_no_no_de_destino(como_nuvem, no_loja, config_fiscal):
    pacote = credentials.montar_pacote(no_loja)
    envelope = credentials.cifrar_para(no_loja, pacote)

    assert CERTIFICADO not in envelope["ciphertext"], "o segredo não pode sair em claro"
    assert credentials.abrir(envelope, no_loja.id) == pacote


def test_o_envelope_de_outra_loja_nao_abre_aqui(como_nuvem, no_loja, no_nuvem,
                                                config_fiscal):
    """O id do nó é dado associado do GCM: um envelope capturado não serve em
    outra loja, mesmo com a chave do ambiente correta."""
    envelope = credentials.cifrar_para(no_loja, credentials.montar_pacote(no_loja))

    with pytest.raises(Exception):
        credentials.abrir(envelope, no_nuvem.id)


def test_checksum_adulterado_e_recusado(como_nuvem, no_loja, config_fiscal):
    envelope = credentials.cifrar_para(no_loja, credentials.montar_pacote(no_loja))
    envelope["checksum"] = "0" * 64

    with pytest.raises(credentials.CredentialsUnavailable, match="[Cc]hecksum"):
        credentials.abrir(envelope, no_loja.id)


def test_sem_chave_do_ambiente_recusa_em_vez_de_mandar_em_claro(
    como_nuvem, no_loja, config_fiscal, settings
):
    settings.SYNC_ENCRYPTION_KEY = ""
    with pytest.raises(credentials.CredentialsUnavailable, match="em claro"):
        credentials.cifrar_para(no_loja, {"x": 1})


# ── a rota ──────────────────────────────────────────────────────────────────
def test_a_rota_entrega_ao_no_autenticado(client, como_nuvem, no_loja, config_fiscal):
    resposta = client.post(
        reverse("sync-credentials"),
        HTTP_AUTHORIZATION=f"Bearer {TOKEN_DE_TESTE}",
        HTTP_X_SYNC_NODE_ID=str(no_loja.id),
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["node_id"] == str(no_loja.id)
    aberto = credentials.abrir(corpo["envelope"], no_loja.id)
    assert aberto["certificate_base64"] == CERTIFICADO


def test_a_rota_recusa_sem_token(client, como_nuvem, no_loja, config_fiscal):
    resposta = client.post(
        reverse("sync-credentials"), HTTP_X_SYNC_NODE_ID=str(no_loja.id)
    )
    assert resposta.status_code in (401, 403)


def test_a_rota_recusa_token_errado(client, como_nuvem, no_loja, config_fiscal):
    resposta = client.post(
        reverse("sync-credentials"),
        HTTP_AUTHORIZATION="Bearer token-de-outra-pessoa-com-tamanho-parecido",
        HTTP_X_SYNC_NODE_ID=str(no_loja.id),
    )
    assert resposta.status_code in (401, 403)


def test_a_rota_nao_aceita_get(client, como_nuvem, no_loja, config_fiscal):
    """Entregar credencial é ato auditável, não leitura de recurso."""
    resposta = client.get(
        reverse("sync-credentials"),
        HTTP_AUTHORIZATION=f"Bearer {TOKEN_DE_TESTE}",
        HTTP_X_SYNC_NODE_ID=str(no_loja.id),
    )
    assert resposta.status_code == 405


# ── o cache da loja ─────────────────────────────────────────────────────────
def test_o_cache_e_so_de_memoria_e_esquecivel():
    credentials_client._CACHE["pacote"] = {"certificate_base64": "x"}
    credentials_client._CACHE["expira_em"] = 1e12

    credentials_client.esquecer()

    assert credentials_client._CACHE["pacote"] is None


def test_falha_ao_buscar_devolve_none_e_nao_derruba_a_venda(settings):
    """Quem chama está no caminho de uma venda: exceção aqui vira caixa parado."""
    settings.SYNC_CLOUD_API_URL = ""
    credentials_client.esquecer()

    assert credentials_client.obter() is None
