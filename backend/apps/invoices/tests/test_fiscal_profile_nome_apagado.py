import pytest

from apps.invoices.models import FiscalProfile

URL = "/api/v1/fiscal/profiles/"
PERFIL = {"name": "CERVEJA_LONG_NECK_ST", "ncm": "22030000", "cfop": "5405"}


@pytest.fixture
def financeiro(account):
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])


@pytest.mark.django_db
def test_perfil_apagado_nao_impede_recriar_o_mesmo_nome(admin_client, financeiro):
    """Apagar é só marcar `deleted_at`. A regra de nome único contava o perfil
    apagado, e importar o CSV da Cobogó dava "valor duplicado" para um nome que
    não aparecia em lugar nenhum da tela."""
    criado = admin_client.post(URL, PERFIL, format="json")
    assert admin_client.delete(f"{URL}{criado.json()['id']}/").status_code == 204

    recriado = admin_client.post(URL, PERFIL, format="json")

    assert recriado.status_code == 201, recriado.json()
    assert FiscalProfile.all_objects.filter(name=PERFIL["name"]).count() == 2


@pytest.mark.django_db
def test_dois_perfis_ativos_com_o_mesmo_nome_continuam_proibidos(admin_client, financeiro):
    assert admin_client.post(URL, PERFIL, format="json").status_code == 201

    repetido = admin_client.post(URL, PERFIL, format="json")

    assert repetido.status_code in (400, 409)
    assert FiscalProfile.all_objects.filter(name=PERFIL["name"]).count() == 1
