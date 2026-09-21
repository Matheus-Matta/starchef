"""`production` existe — e a separação entre os dois mundos continua de pé.

O risco de abrir um segundo ambiente não é o ambiente novo funcionar: é a
proteção antiga deixar de funcionar sem ninguém notar. Enquanto só havia
`development`, "o valor é aceito" e "o valor é o NOSSO" eram a mesma pergunta
por acidente. Estes testes existem porque a segunda pergunta passou a precisar
de resposta própria.
"""
import pytest

from apps.synchronization.constants import (
    ENVIRONMENT_DEVELOPMENT,
    ENVIRONMENT_PRODUCTION,
    PROTOCOL_VERSION,
)
from apps.synchronization.models import SyncNode
from apps.synchronization.services import authentication, guard
from apps.synchronization.tests.conftest import TOKEN_DE_TESTE

pytestmark = pytest.mark.django_db


def _hello(no, ambiente):
    return {
        "node_id": str(no.id),
        "pair_id": str(no.pair_id),
        "account_id": str(no.account_id),
        "environment": ambiente,
        "protocol_version": PROTOCOL_VERSION,
    }


# ── o portão de valor ───────────────────────────────────────────────────────

def test_production_e_um_ambiente_valido(settings):
    settings.SYNC_ENVIRONMENT = ENVIRONMENT_PRODUCTION
    assert guard.ensure_environment() == ENVIRONMENT_PRODUCTION
    assert guard.is_production()


def test_valor_desconhecido_continua_recusado(settings):
    """`prod` não é `production`, e um typo não pode virar ambiente novo."""
    settings.SYNC_ENVIRONMENT = "prod"
    with pytest.raises(guard.SyncDisabled, match="prod"):
        guard.ensure_environment()

    settings.SYNC_ENVIRONMENT = ""
    with pytest.raises(guard.SyncDisabled, match="vazio"):
        guard.ensure_environment()


def test_as_duas_perguntas_sao_diferentes(settings):
    """`development` existe; numa instalação de produção, não é a nossa."""
    settings.SYNC_ENVIRONMENT = ENVIRONMENT_PRODUCTION

    assert guard.environment_is_allowed(ENVIRONMENT_DEVELOPMENT) is True
    assert guard.matches_environment(ENVIRONMENT_DEVELOPMENT) is False
    assert guard.matches_environment(ENVIRONMENT_PRODUCTION) is True


# ── o portão de identidade, que é o que protege de verdade ──────────────────

def test_loja_de_homologacao_nao_entra_na_nuvem_de_producao(
    settings, como_nuvem, no_loja
):
    """O teste que justifica ter separado as duas perguntas.

    Sem `matches_environment`, este cenário PASSARIA: o ambiente declarado é
    válido e bate com a ficha do nó. O que não bate é o mundo em que a nuvem
    está — e o resultado seria venda de teste no banco que vale.
    """
    settings.SYNC_ENVIRONMENT = ENVIRONMENT_PRODUCTION
    # A ficha e o HELLO concordam entre si: os dois dizem development.
    SyncNode.objects.filter(pk=no_loja.pk).update(environment=ENVIRONMENT_DEVELOPMENT)

    with pytest.raises(authentication.AuthenticationFailed, match="Ambiente incompatível"):
        authentication.authenticate(
            _hello(no_loja, ENVIRONMENT_DEVELOPMENT), raw_token=TOKEN_DE_TESTE
        )


def test_ficha_atrasada_recusa_e_diz_o_que_fazer(settings, como_nuvem, no_loja):
    """A loja já virou; a ficha na nuvem, não. É o meio da virada."""
    settings.SYNC_ENVIRONMENT = ENVIRONMENT_PRODUCTION
    SyncNode.objects.filter(pk=no_loja.pk).update(environment=ENVIRONMENT_DEVELOPMENT)

    with pytest.raises(authentication.AuthenticationFailed, match="sync_set_environment"):
        authentication.authenticate(
            _hello(no_loja, ENVIRONMENT_PRODUCTION), raw_token=TOKEN_DE_TESTE
        )


def test_com_os_dois_lados_em_producao_conecta(settings, como_nuvem, no_loja):
    """A virada completa: variável e ficha no mesmo mundo."""
    settings.SYNC_ENVIRONMENT = ENVIRONMENT_PRODUCTION
    SyncNode.objects.filter(pk=no_loja.pk).update(environment=ENVIRONMENT_PRODUCTION)
    no_loja.refresh_from_db()

    autenticado = authentication.authenticate(
        _hello(no_loja, ENVIRONMENT_PRODUCTION), raw_token=TOKEN_DE_TESTE
    )
    assert autenticado.pk == no_loja.pk


def test_development_continua_funcionando_como_antes(como_nuvem, no_loja):
    """Abrir `production` não pode mexer em quem está em homologação hoje."""
    autenticado = authentication.authenticate(
        _hello(no_loja, ENVIRONMENT_DEVELOPMENT), raw_token=TOKEN_DE_TESTE
    )
    assert autenticado.pk == no_loja.pk


# ── o que o provisionamento grava ───────────────────────────────────────────

def test_no_provisionado_nasce_no_ambiente_da_instalacao(settings, como_nuvem, conta):
    """Gravar `development` literal fazia todo nó nascer em homologação.

    Numa nuvem de produção, o nó só descobriria isso no primeiro HELLO —
    recusado por ambiente incompatível, com a ficha errada desde o nascimento.
    """
    from apps.synchronization.services import provisioning

    settings.SYNC_ENVIRONMENT = ENVIRONMENT_PRODUCTION
    no, pacote = provisioning.provision_local_node(
        account=conta, restaurant=None, name="Loja Nova",
        endpoint="wss://nuvem/ws/", cloud_endpoint="wss://nuvem/ws/",
    )

    assert no.environment == ENVIRONMENT_PRODUCTION
    assert pacote.get("SYNC_ENVIRONMENT", ENVIRONMENT_PRODUCTION) == ENVIRONMENT_PRODUCTION


# ── o nome do nó ────────────────────────────────────────────────────────────

def test_a_matricula_inicial_usa_o_nome_do_env(como_nuvem, conta):
    """`SYNC_NODE_NAME` manda desde a PRIMEIRA matrícula, não só na segunda.

    A corrente é: `.env` da loja -> autostart -> POST /enroll/ -> `enroll()` ->
    `provision_local_node(name=...)` -> `SyncNode.name`. Qualquer elo que caia
    no padrão faz a loja aparecer como "Servidor da loja" no Admin da nuvem.
    """
    from django.contrib.auth import get_user_model

    from apps.synchronization.services import enrollment

    User = get_user_model()
    root = User.objects.create_superuser("root3", "root3@starchef.test", "senha-de-teste-123")

    no, _env, _run = enrollment.enroll(
        username=root.username, password="senha-de-teste-123",
        account_id=str(conta.id),
        enrollment_secret="segredo-de-matricula-com-tamanho-ok",
        node_name="Loja Cobogó", cloud_wss_url="wss://nuvem/ws/",
    )

    assert no.name == "Loja Cobogó"


def test_o_pacote_leva_o_nome_de_volta_para_a_loja(como_nuvem, conta):
    """A ficha que a LOJA grava de si precisa ter o mesmo nome que a da nuvem.

    Sem o nome no pacote, o lado de cá caía em "Servidor da loja": o Admin da
    nuvem dizia "Loja Cobogó" e o da loja dizia outra coisa, para o mesmo nó.
    """
    from django.contrib.auth import get_user_model

    from apps.synchronization.services import enrollment

    User = get_user_model()
    root = User.objects.create_superuser("root4", "root4@starchef.test", "senha-de-teste-123")
    segredo = "segredo-de-matricula-com-tamanho-ok"

    _no, envelope, _run = enrollment.enroll(
        username=root.username, password="senha-de-teste-123",
        account_id=str(conta.id), enrollment_secret=segredo,
        node_name="Loja Cobogó", cloud_wss_url="wss://nuvem/ws/",
    )

    pacote = enrollment.decifrar(envelope, segredo)
    assert pacote["SYNC_NODE_NAME"] == "Loja Cobogó"


def test_rematricular_renomeia_o_no(como_nuvem, conta):
    """`SYNC_NODE_NAME` é a fonte do nome, inclusive na segunda vez.

    Sem isto, trocar o nome no `.env` da loja e rematricular não mudava nada:
    a nuvem continuava listando o nome antigo, e quem procurasse a loja no
    Admin procuraria por um nome que só existe no arquivo dela.
    """
    from django.contrib.auth import get_user_model

    from apps.synchronization.services import enrollment

    User = get_user_model()
    root = User.objects.create_superuser("root2", "root2@starchef.test", "senha-de-teste-123")
    comum = {
        "username": root.username, "password": "senha-de-teste-123",
        "account_id": str(conta.id),
        "enrollment_secret": "segredo-de-matricula-com-tamanho-ok",
        "cloud_wss_url": "wss://nuvem/ws/",
    }

    no, _env, _run = enrollment.enroll(node_name="Loja Centro", **comum)
    assert no.name == "Loja Centro"

    mesmo, _env2, _run2 = enrollment.enroll(
        node_name="Loja Cobogó", existing_node_id=str(no.id), **comum
    )
    assert mesmo.pk == no.pk, "rematrícula não pode criar um segundo nó"
    mesmo.refresh_from_db()
    assert mesmo.name == "Loja Cobogó"
