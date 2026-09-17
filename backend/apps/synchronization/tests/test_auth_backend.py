"""O acesso ao /admin da loja pela credencial de matrícula.

Este arquivo testa principalmente o que o backend RECUSA. Ele é uma porta a
mais para o /admin, então o que importa não é o caminho feliz — é ter certeza
de que ela não abre na nuvem, fora de development, ou com a sincronização
desligada.
"""
import pytest
from django.contrib.auth import authenticate, get_user_model

pytestmark = pytest.mark.django_db
Usuario = get_user_model()

USUARIO = "stardev"
SENHA = "senha-da-matricula-de-teste"


@pytest.fixture
def credenciais(settings):
    settings.SYNC_ENROLL_USERNAME = USUARIO
    settings.SYNC_ENROLL_PASSWORD = SENHA
    return settings


# ── o que ele PERMITE ───────────────────────────────────────────────────────
def test_na_loja_a_credencial_de_matricula_entra(como_loja, credenciais):
    usuario = authenticate(username=USUARIO, password=SENHA)

    assert usuario is not None
    assert usuario.username == USUARIO
    assert usuario.is_staff and usuario.is_superuser


def test_o_usuario_criado_nao_tem_senha_utilizavel(como_loja, credenciais):
    """Não pode virar uma segunda porta pelo ModelBackend."""
    authenticate(username=USUARIO, password=SENHA)

    usuario = Usuario.objects.get(username=USUARIO)
    assert not usuario.has_usable_password()


def test_entrar_duas_vezes_nao_duplica_usuario(como_loja, credenciais):
    authenticate(username=USUARIO, password=SENHA)
    authenticate(username=USUARIO, password=SENHA)
    assert Usuario.objects.filter(username=USUARIO).count() == 1


def test_o_login_do_admin_aceita(client, como_loja, credenciais):
    """O caminho de verdade: o formulário do /admin."""
    assert client.login(username=USUARIO, password=SENHA) is True


# ── o que ele RECUSA ────────────────────────────────────────────────────────
def test_na_NUVEM_nunca_entra(como_nuvem, credenciais):
    """A trava mais importante: é lá que moram os dados de todas as contas."""
    assert authenticate(username=USUARIO, password=SENHA) is None
    assert not Usuario.objects.filter(username=USUARIO).exists()


def test_fora_de_development_nunca_entra(settings, como_loja, credenciais):
    settings.SYNC_ENVIRONMENT = "production"
    assert authenticate(username=USUARIO, password=SENHA) is None


def test_com_a_sincronizacao_desligada_nunca_entra(settings, como_loja, credenciais):
    settings.SYNC_ENABLED = False
    assert authenticate(username=USUARIO, password=SENHA) is None


def test_sem_credencial_configurada_nao_ha_o_que_comparar(settings, como_loja):
    settings.SYNC_ENROLL_USERNAME = ""
    settings.SYNC_ENROLL_PASSWORD = ""
    assert authenticate(username="", password="") is None
    assert authenticate(username="qualquer", password="coisa") is None


def test_senha_errada_nao_entra(como_loja, credenciais):
    assert authenticate(username=USUARIO, password="chute") is None


def test_usuario_errado_nao_entra(como_loja, credenciais):
    assert authenticate(username="outro", password=SENHA) is None


def test_usuario_vindo_da_nuvem_sem_staff_nao_e_promovido(como_loja, credenciais):
    """Quem veio da sincronização manda; o acesso é recusado, não elevado."""
    Usuario.objects.create_user(USUARIO, "x@t.test", "outra-senha", is_staff=False)

    assert authenticate(username=USUARIO, password=SENHA) is None
    assert not Usuario.objects.get(username=USUARIO).is_staff


def test_a_sessao_cai_quando_a_trava_muda(settings, como_loja, credenciais):
    """Desligar a sincronização derruba quem entrou por aqui."""
    from apps.synchronization.auth_backend import LocalConsoleBackend

    usuario = authenticate(username=USUARIO, password=SENHA)
    backend = LocalConsoleBackend()
    assert backend.get_user(usuario.pk) is not None

    settings.SYNC_ENABLED = False
    assert backend.get_user(usuario.pk) is None


def test_o_modelbackend_continua_sendo_o_caminho_normal(como_loja, credenciais):
    """Quem tem usuário no banco entra por ele, sem passar por aqui."""
    Usuario.objects.create_user("gerente", "g@t.test", "senha-forte-123")
    usuario = authenticate(username="gerente", password="senha-forte-123")
    assert usuario is not None and usuario.username == "gerente"


def test_o_usuario_local_nao_vira_evento_de_sincronizacao(como_loja, credenciais):
    """`user` é cloud_to_local: a loja nunca empurra usuário para a nuvem."""
    from apps.synchronization.models import SyncEvent

    antes = SyncEvent.objects.filter(entity_type="user").count()
    authenticate(username=USUARIO, password=SENHA)
    assert SyncEvent.objects.filter(entity_type="user").count() == antes
