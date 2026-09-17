"""As rotas HTTP de arquivo: autenticação por nó e isolamento entre nós."""
import hashlib
import uuid

import pytest
from rest_framework.test import APIClient

from apps.synchronization.constants import NodeStatus
from apps.synchronization.models.transfer import TransferStatus
from apps.synchronization.tests.conftest import TOKEN_DE_TESTE

pytestmark = pytest.mark.django_db

CONTEUDO = b"binario-de-teste-" * 500
CHECKSUM = hashlib.sha256(CONTEUDO).hexdigest()


def _cliente(no, token=TOKEN_DE_TESTE):
    cliente = APIClient()
    cliente.credentials(
        HTTP_AUTHORIZATION=f"Bearer {token}", HTTP_X_SYNC_NODE_ID=str(no.id)
    )
    return cliente


def _corpo(caminho="produtos/api.jpg", total=None):
    return {
        "direction": "upload",
        "entity_type": "image",
        "entity_id": str(uuid.uuid4()),
        "field_name": "file",
        "storage_path": caminho,
        "total_bytes": total or len(CONTEUDO),
        "checksum": CHECKSUM,
        "content_type": "image/jpeg",
    }


def test_fluxo_completo_pela_api(como_nuvem, no_loja, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    cliente = _cliente(no_loja)

    abertura = cliente.post("/api/v1/sync/files/", _corpo(), format="json")
    assert abertura.status_code == 201
    transfer_id, offset = abertura.json()["id"], abertura.json()["offset"]
    assert offset == 0

    pedaco = 2048
    while offset < len(CONTEUDO):
        resposta = cliente.put(
            f"/api/v1/sync/files/{transfer_id}/chunk/",
            data=CONTEUDO[offset:offset + pedaco],
            content_type="application/octet-stream",
            HTTP_X_SYNC_OFFSET=str(offset),
        )
        assert resposta.status_code == 200
        offset = resposta.json()["offset"]

    fim = cliente.post(f"/api/v1/sync/files/{transfer_id}/complete/", {}, format="json")
    assert fim.status_code == 200
    assert fim.json()["status"] == TransferStatus.COMPLETED
    assert (tmp_path / "produtos" / "api.jpg").read_bytes() == CONTEUDO


def test_sem_token_de_no_nao_entra(como_nuvem, no_loja):
    assert APIClient().post("/api/v1/sync/files/", _corpo(), format="json").status_code in (401, 403)


def test_token_errado_nao_entra(como_nuvem, no_loja):
    resposta = _cliente(no_loja, token="chute").post(
        "/api/v1/sync/files/", _corpo(), format="json"
    )
    assert resposta.status_code == 401


def test_no_revogado_nao_transfere(como_nuvem, no_loja):
    no_loja.status = NodeStatus.REVOKED
    no_loja.is_active = False
    no_loja.save()
    resposta = _cliente(no_loja).post("/api/v1/sync/files/", _corpo(), format="json")
    assert resposta.status_code == 401


def test_offset_fora_de_ordem_devolve_409_com_o_esperado(como_nuvem, no_loja, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    cliente = _cliente(no_loja)
    transfer_id = cliente.post("/api/v1/sync/files/", _corpo(), format="json").json()["id"]

    resposta = cliente.put(
        f"/api/v1/sync/files/{transfer_id}/chunk/",
        data=CONTEUDO[:100], content_type="application/octet-stream",
        HTTP_X_SYNC_OFFSET="9999",
    )
    assert resposta.status_code == 409
    # A resposta diz de onde continuar, em vez de só reclamar. O cabeçalho é o
    # contrato estável: o corpo passa pelo envelope de erro da API.
    assert resposta["X-Sync-Expected-Offset"] == "0"
    assert resposta.json()["error"]["expected_offset"] == 0


def test_no_nao_ve_transferencia_de_outro(como_nuvem, conta, outra_conta, no_loja, settings, tmp_path):
    from apps.synchronization.constants import NodeType
    from apps.synchronization.models import SyncNode
    from apps.synchronization.services import crypto

    settings.MEDIA_ROOT = str(tmp_path)
    transfer_id = _cliente(no_loja).post(
        "/api/v1/sync/files/", _corpo(), format="json"
    ).json()["id"]

    outro_token = "token-do-vizinho-com-tamanho-suficiente-aqui"
    vizinho = SyncNode.objects.create(
        pair_id=uuid.uuid4(), account=outra_conta, node_type=NodeType.LOCAL,
        name="Loja vizinha", status=NodeStatus.ACTIVE,
        credential_hash=crypto.hash_token(outro_token),
    )

    resposta = _cliente(vizinho, token=outro_token).get(f"/api/v1/sync/files/{transfer_id}/")
    # 404 e não 403: confirmar que o id existe já entrega informação.
    assert resposta.status_code == 404


def test_travessia_de_diretorio_pela_api_e_400(como_nuvem, no_loja):
    resposta = _cliente(no_loja).post(
        "/api/v1/sync/files/", _corpo(caminho="../../etc/passwd"), format="json"
    )
    assert resposta.status_code == 400


def test_checksum_malformado_e_recusado_no_serializer(como_nuvem, no_loja):
    corpo = _corpo()
    corpo["checksum"] = "nao-e-um-sha256"
    assert _cliente(no_loja).post("/api/v1/sync/files/", corpo, format="json").status_code == 400


def test_download_serve_a_partir_do_offset(como_nuvem, no_loja, settings, tmp_path):
    """O outro sentido: a loja puxa o binário que o evento anunciou."""
    settings.MEDIA_ROOT = str(tmp_path)
    destino = tmp_path / "produtos"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "baixar.jpg").write_bytes(CONTEUDO)

    cliente = _cliente(no_loja)
    corpo = _corpo(caminho="produtos/baixar.jpg")
    corpo["direction"] = "download"
    transfer_id = cliente.post("/api/v1/sync/files/", corpo, format="json").json()["id"]

    inteiro = cliente.get(f"/api/v1/sync/files/{transfer_id}/download/")
    assert inteiro.status_code == 200
    assert inteiro["X-Sync-Total-Bytes"] == str(len(CONTEUDO))
    assert inteiro["X-Sync-Checksum"] == CHECKSUM
    assert inteiro["X-Sync-Complete"] == "1"
    assert b"".join(inteiro.streaming_content if inteiro.streaming else [inteiro.content]) == CONTEUDO


def test_download_retoma_do_meio(como_nuvem, no_loja, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    (tmp_path / "produtos").mkdir(parents=True, exist_ok=True)
    (tmp_path / "produtos" / "meio.jpg").write_bytes(CONTEUDO)

    cliente = _cliente(no_loja)
    corpo = _corpo(caminho="produtos/meio.jpg")
    corpo["direction"] = "download"
    transfer_id = cliente.post("/api/v1/sync/files/", corpo, format="json").json()["id"]

    metade = len(CONTEUDO) // 2
    resposta = cliente.get(f"/api/v1/sync/files/{transfer_id}/download/?offset={metade}")
    assert resposta.status_code == 200
    assert resposta["X-Sync-Offset"] == str(metade)
    assert resposta.content == CONTEUDO[metade:]


def test_download_de_arquivo_inexistente_e_404(como_nuvem, no_loja, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    cliente = _cliente(no_loja)
    corpo = _corpo(caminho="produtos/nao-existe.jpg")
    corpo["direction"] = "download"
    transfer_id = cliente.post("/api/v1/sync/files/", corpo, format="json").json()["id"]

    assert cliente.get(f"/api/v1/sync/files/{transfer_id}/download/").status_code == 404


def test_download_com_offset_invalido_e_400(como_nuvem, no_loja, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    (tmp_path / "produtos").mkdir(parents=True, exist_ok=True)
    (tmp_path / "produtos" / "ok.jpg").write_bytes(CONTEUDO)

    cliente = _cliente(no_loja)
    corpo = _corpo(caminho="produtos/ok.jpg")
    corpo["direction"] = "download"
    transfer_id = cliente.post("/api/v1/sync/files/", corpo, format="json").json()["id"]

    assert cliente.get(
        f"/api/v1/sync/files/{transfer_id}/download/?offset=abc"
    ).status_code == 400


def test_download_alem_do_fim_devolve_vazio(como_nuvem, no_loja, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    (tmp_path / "produtos").mkdir(parents=True, exist_ok=True)
    (tmp_path / "produtos" / "fim.jpg").write_bytes(CONTEUDO)

    cliente = _cliente(no_loja)
    corpo = _corpo(caminho="produtos/fim.jpg")
    corpo["direction"] = "download"
    transfer_id = cliente.post("/api/v1/sync/files/", corpo, format="json").json()["id"]

    resposta = cliente.get(f"/api/v1/sync/files/{transfer_id}/download/?offset=999999")
    assert resposta.status_code == 200
    assert resposta.content == b""
    assert resposta["X-Sync-Complete"] == "1"
