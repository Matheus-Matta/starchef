"""O usuário sincronizado consegue ENTRAR no backend local.

Sem isso, a loja recebia os usuários com o campo `password` vazio e ninguém
conseguia autenticar — o que apaga a razão de o backend local existir, que é
operar quando a nuvem cai.

E pior que não funcionar: `has_usable_password()` responde True para string
vazia (ela só não começa com `!`), então o usuário AFIRMAVA ter senha válida
enquanto nenhuma senha do mundo conferia.
"""
import pytest
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import check_password, make_password

from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import apply, crypto, serialization
from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db
Usuario = get_user_model()
SENHA = "senha-real-do-operador"


def _evento_de_usuario(conta, origem, destino, *, user_id, username, hash_senha,
                       sequencia=1):
    payload = {
        "schema_version": 1,
        "entity_type": "user",
        "entity_id": str(user_id),
        "entity_version": 10**18,
        "fields": {
            "username": username,
            "email": f"{username}@loja.test",
            "password": hash_senha,
            "is_active": True,
            "is_staff": False,
            "is_superuser": False,
            "first_name": "",
            "last_name": "",
            "date_joined": "2026-01-01T00:00:00+00:00",
        },
    }
    return SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino,
        direction=Direction.INBOUND, sequence=sequencia, entity_type="user",
        entity_id=str(user_id), operation=Operation.UPSERT, entity_version=10**18,
        payload=payload, payload_checksum=crypto.checksum(payload),
        status=EventStatus.RECEIVED,
    )


# ── o hash viaja ────────────────────────────────────────────────────────────
def test_o_hash_da_senha_esta_no_payload(conta):
    usuario = Usuario.objects.create_user("operador", "o@t.test", SENHA)

    dados = serialization.serialize(usuario, registry.require("user"))

    assert dados["password"] == usuario.password
    assert SENHA not in str(dados), "o hash viaja; a senha em claro, nunca"


def test_last_login_continua_fora():
    """É do nó onde a pessoa entrou, não da instalação que recebe."""
    assert "last_login" in registry.require("user").exclude_fields


def test_nenhum_outro_segredo_foi_liberado_junto():
    assert registry.require("user").allow_fields == ("password",)


# ── e o login funciona do outro lado ────────────────────────────────────────
def test_o_usuario_sincronizado_consegue_entrar(como_loja, conta, no_nuvem, no_loja):
    """O teste que fecha o caso: autenticação de verdade, ponta a ponta."""
    hash_da_nuvem = make_password(SENHA)
    evento = _evento_de_usuario(
        conta, no_nuvem, no_loja, user_id=9001,
        username="operador", hash_senha=hash_da_nuvem,
    )

    assert apply.apply_event(evento) is True
    assert authenticate(username="operador", password=SENHA) is not None


def test_o_hash_confere_mesmo_com_outra_secret_key(como_loja, conta, no_nuvem, no_loja,
                                                   settings):
    """A `SECRET_KEY` assina sessão, CSRF e reset — nunca a senha.

    Era a dúvida que levantou o assunto: se o hash dependesse dela, a loja
    nunca leria uma senha gerada na nuvem.
    """
    hash_da_nuvem = make_password(SENHA)
    settings.SECRET_KEY = "uma-secret-key-completamente-diferente-na-loja"

    assert check_password(SENHA, hash_da_nuvem) is True


# ── e sem hash, a verdade ───────────────────────────────────────────────────
def test_sem_hash_a_senha_nasce_inutilizavel_e_nao_vazia(como_loja, conta, no_nuvem,
                                                         no_loja):
    """Vazia MENTE: `has_usable_password()` responde True para string vazia."""
    # `auth.User` tem PK INTEIRO, não UUID.
    user_id = 9002
    evento = _evento_de_usuario(
        conta, no_nuvem, no_loja, user_id=user_id,
        username="sem_senha", hash_senha="",
    )
    del evento.payload["fields"]["password"]
    evento.save(update_fields=["payload"])

    apply.apply_event(evento)

    usuario = Usuario.objects.get(pk=user_id)
    assert usuario.has_usable_password() is False, (
        "sem hash, a senha tem de se declarar inutilizável em vez de fingir"
    )
    assert authenticate(username="sem_senha", password="qualquer") is None


# ── e a senha chega mesmo num usuário que já existe aqui ───────────────────
#
# `auth.User` não tem `updated_at` nem `sync_version`, então `entity_version`
# devolve 1 dos dois lados — sempre. E o resolvedor tratava "versão igual" como
# "já apliquei, ignore": depois do primeiro apply, NENHUM evento de usuário
# voltava a ser aplicado. A nuvem podia mandar o hash para sempre que a loja
# descartaria, e o operador continuaria sem conseguir entrar.
#: Entidades sem fonte de versão que já foram examinadas e são seguras.
#:
#: `user` NÃO é segura — é o defeito descrito acima, tratado por conteúdo.
#:
#: `idempotency_record` é: ele nunca PREEXISTE no nó que recebe. O registro
#: nasce no nó que atendeu a operação, e chega ao outro como linha nova — com
#: `local_version=0` contra `remote_version=1`, que a decisão aplica. A
#: armadilha de "versão igual = já apliquei" precisa dos dois lados terem a
#: linha, e aqui só um tem. Se ela já existir, `immutable=True` a preserva,
#: que é exatamente o certo: a resposta de uma operação encerrada não se
#: reescreve.
SEM_FONTE_DE_VERSAO_EXAMINADAS = {"user", "idempotency_record"}


def test_toda_entidade_sem_fonte_de_versao_foi_examinada():
    """Se uma nova aparecer, ela herda o problema — e este teste avisa.

    Sem `updated_at` nem `sync_version`, `entity_version` devolve 1 dos dois
    lados. O resolvedor lê "versão igual" como "já apliquei, ignore", e o
    evento nunca mais é aplicado depois da primeira vez.
    """
    sem_versao = {
        e.entity_type for e in registry.entries.values()
        if "sync_version" not in {c.name for c in e.model._meta.concrete_fields}
        and "updated_at" not in {c.name for c in e.model._meta.concrete_fields}
    }
    novas = sem_versao - SEM_FONTE_DE_VERSAO_EXAMINADAS
    assert not novas, (
        f"entidade nova sem `updated_at`: {sorted(novas)}. Confira se ela "
        "também precisa que o CONTEÚDO decida, e não a versão — e acrescente "
        "aqui com a razão."
    )


def test_a_senha_chega_num_usuario_que_ja_existe(como_loja, conta, no_nuvem, no_loja):
    """O caso exato da produção: 8 usuários, 0 com senha utilizável."""
    existente = Usuario.objects.create(username="operador2", email="o2@t.test")
    existente.set_unusable_password()
    existente.save()

    hash_da_nuvem = make_password(SENHA)
    evento = _evento_de_usuario(
        conta, no_nuvem, no_loja, user_id=existente.pk,
        username="operador2", hash_senha=hash_da_nuvem,
    )

    assert apply.apply_event(evento) is True, (
        "versão constante não pode significar 'já apliquei'"
    )
    assert authenticate(username="operador2", password=SENHA) is not None


def test_reaplicar_o_mesmo_usuario_identico_nao_grava(como_loja, conta, no_nuvem, no_loja):
    """Deixar passar pela versão não pode virar escrita à toa: quem decide é o
    conteúdo, e conteúdo igual não gera gravação."""
    hash_da_nuvem = make_password(SENHA)
    primeiro = _evento_de_usuario(
        conta, no_nuvem, no_loja, user_id=9003, username="op3",
        hash_senha=hash_da_nuvem,
    )
    assert apply.apply_event(primeiro) is True

    segundo = _evento_de_usuario(
        conta, no_nuvem, no_loja, user_id=9003, username="op3",
        hash_senha=hash_da_nuvem, sequencia=2,
    )

    assert apply.apply_event(segundo) is False, "nada mudou: não havia o que gravar"
