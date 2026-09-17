"""Fixtures da sincronização: um par LOCAL/CLOUD pronto para exercitar o fluxo.

Os testes daqui rodam com `SYNC_ENABLED=True` (os demais rodam com ela
desligada, ver `config/settings/test.py`), e cada teste escolhe o papel da
instalação com `como_nuvem` / `como_loja`.
"""
import uuid

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import Account
from apps.synchronization.constants import ENVIRONMENT_DEVELOPMENT, NodeStatus, NodeType
from apps.synchronization.models import SyncNode
from apps.synchronization.services import crypto, nodes

User = get_user_model()

TOKEN_DE_TESTE = "token-de-teste-com-tamanho-suficiente-para-parecer-real"
CHAVE_DE_TESTE = crypto.generate_key()


@pytest.fixture(autouse=True)
def _sync_ligado(settings):
    settings.SYNC_ENABLED = True
    settings.SYNC_ENVIRONMENT = ENVIRONMENT_DEVELOPMENT
    settings.SYNC_ENCRYPTION_KEY = CHAVE_DE_TESTE
    nodes.invalidate_cache()
    yield
    nodes.invalidate_cache()


@pytest.fixture
def conta(db):
    # `slug` é único: deixá-lo em branco faz a segunda conta do teste colidir
    # com a primeira em "" e o erro aparecer longe daqui.
    return Account.objects.create(name="Conta Sincronizada", slug="conta-sync", is_active=True)


@pytest.fixture
def outra_conta(db):
    return Account.objects.create(name="Conta Vizinha", slug="conta-vizinha", is_active=True)


@pytest.fixture
def par_id():
    return uuid.uuid4()


@pytest.fixture
def no_nuvem(conta, par_id):
    return SyncNode.objects.create(
        pair_id=par_id,
        account=conta,
        node_type=NodeType.CLOUD,
        environment=ENVIRONMENT_DEVELOPMENT,
        name="Nuvem de testes",
        status=NodeStatus.ACTIVE,
        is_self=False,
        encryption_key_id="dev-key-01",
    )


@pytest.fixture
def no_loja(conta, par_id, no_nuvem):
    no = SyncNode.objects.create(
        pair_id=par_id,
        account=conta,
        node_type=NodeType.LOCAL,
        environment=ENVIRONMENT_DEVELOPMENT,
        name="Loja de testes",
        status=NodeStatus.ACTIVE,
        credential_hash=crypto.hash_token(TOKEN_DE_TESTE),
        secret_fingerprint=crypto.fingerprint(CHAVE_DE_TESTE),
        encryption_key_id="dev-key-01",
        peer=no_nuvem,
        is_self=False,
    )
    return no


@pytest.fixture
def como_nuvem(settings, no_nuvem, no_loja):
    """Esta instalação É a nuvem: o nó CLOUD vira `is_self`."""
    settings.SYNC_NODE_TYPE = "cloud"
    settings.SYNC_NODE_ID = str(no_nuvem.id)
    no_nuvem.is_self = True
    no_nuvem.save(update_fields=["is_self"])
    nodes.invalidate_cache()
    return no_nuvem


@pytest.fixture
def como_loja(settings, no_nuvem, no_loja):
    """Esta instalação É a loja: o nó LOCAL vira `is_self`."""
    settings.SYNC_NODE_TYPE = "local"
    settings.SYNC_NODE_ID = str(no_loja.id)
    settings.SYNC_AUTH_TOKEN = TOKEN_DE_TESTE
    settings.SYNC_CLOUD_WSS_URL = "wss://dev-sync.local/ws/sync/v1/"
    no_loja.is_self = True
    no_loja.save(update_fields=["is_self"])
    nodes.invalidate_cache()
    return no_loja
