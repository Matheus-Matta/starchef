"""A loja emite com o segredo EMPRESTADO — e não fica com ele.

O segredo de emissão (token do provedor, CSC, certificado A1) não desce pela
sincronização, e o motivo está em `services/credentials.py`: o evento é gravado
em `SyncEvent.payload`, texto puro, nos dois bancos e em todo backup dos dois,
para sempre. A cifra protege o cabo, não o disco.

O canal certo existia inteiro — endpoint, cliente, envelope AES-GCM amarrado ao
id do nó, cache só em memória — e ninguém o chamava. A emissão lia direto do
`FiscalConfig` da loja, que vem sem esses campos, e recusava.

O que estes testes prendem é a propriedade que dá sentido a tudo: o empréstimo
serve a emissão e **não é gravado**. Se um dia alguém "otimizar" salvando o
pacote no `FiscalConfig`, o segredo volta a morar num computador dentro do
restaurante — e revogar o token do nó deixa de apagá-lo de lá.
"""
import pytest

from apps.invoices.emission_secrets import segredos_de
from apps.invoices.models import FiscalConfig

from .emprestimo import PACOTE, config_sem_segredo, nuvem_devolve


pytestmark = pytest.mark.django_db


@pytest.fixture
def config(account, restaurant, branch):
    return config_sem_segredo(account, restaurant, branch)


@pytest.fixture
def nuvem_responde(monkeypatch, config):
    """A nuvem devolve o pacote desta configuração."""
    pacote = {**PACOTE, "fiscal_config_id": str(config.id)}
    nuvem_devolve(monkeypatch, pacote)
    return pacote


def test_sem_nada_gravado_a_loja_USA_o_que_a_nuvem_empresta(config, nuvem_responde):
    """O defeito: a emissão recusava com o segredo disponível na nuvem."""
    segredos = segredos_de(config)

    assert segredos.csc_token == "CSC-DA-NUVEM"
    assert segredos.token_do_provedor(FiscalConfig.ENV_HOMOLOGATION) == "TOKEN-HOMOLOGACAO"
    assert segredos.certificate_password == "senha-do-a1"


def test_o_ambiente_escolhe_QUAL_token(config, nuvem_responde):
    """Usar o token de produção em homologação não dá erro de credencial.

    Dá nota de verdade — emitida contra a SEFAZ real, num teste.
    """
    segredos = segredos_de(config)

    assert segredos.token_do_provedor(FiscalConfig.ENV_PRODUCTION) == "TOKEN-PRODUCAO"


def test_o_que_a_LOJA_tem_gravado_tem_precedencia(config, nuvem_responde):
    """Instalação provisionada à mão continua funcionando igual."""
    config.csc_token = "CSC-DA-LOJA"
    config.save(update_fields=["csc_token", "updated_at"])

    assert segredos_de(config).csc_token == "CSC-DA-LOJA"


def test_o_emprestimo_NAO_e_gravado_no_banco(config, nuvem_responde):
    """A propriedade que dá sentido ao canal inteiro.

    Persistir resolveria a leitura casual e não o que importa: o segredo
    passaria a morar num computador dentro do restaurante, e revogar o token
    do nó não o apagaria de lá.
    """
    segredos_de(config)

    config.refresh_from_db()
    assert config.csc_token == ""
    assert config.focus_token_homologation == ""
    assert config.certificate_password == ""


def test_a_loja_COMPLETA_nao_vai_a_nuvem(config, monkeypatch):
    """Uma chamada de rede por venda seria o preço errado a pagar."""
    chamou = []
    monkeypatch.setattr(
        "apps.synchronization.services.credentials_client.obter",
        lambda **kwargs: chamou.append(1) or {},
    )
    config.csc_id = "000001"
    config.csc_token = "CSC-LOCAL"
    config.focus_token_homologation = "TOKEN-LOCAL"
    config.save(update_fields=["csc_id", "csc_token", "focus_token_homologation", "updated_at"])

    segredos_de(config)

    assert chamou == []


def test_pacote_de_OUTRA_configuracao_e_ignorado(config, monkeypatch):
    """Assinaria a nota com o certificado do cliente errado."""
    monkeypatch.setattr(
        "apps.synchronization.services.credentials_client.obter",
        lambda **kwargs: {**PACOTE, "fiscal_config_id": "00000000-0000-4000-8000-000000000000"},
    )

    assert segredos_de(config).csc_token == ""


def test_nuvem_fora_do_ar_NAO_derruba_a_venda(config, monkeypatch):
    """Quem chama está no caminho de uma venda.

    Sem o empréstimo a emissão recusa com o motivo de sempre, dito pelo
    provedor — e não com uma exceção subindo até o caixa.
    """
    monkeypatch.setattr(
        "apps.synchronization.services.credentials_client.obter",
        lambda **kwargs: None,
    )

    assert segredos_de(config).csc_token == ""
