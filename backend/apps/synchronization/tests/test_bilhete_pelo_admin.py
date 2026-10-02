"""Bilhete de matrícula emitido pelo Admin da nuvem — sem SSH no servidor.

O código aparece UMA vez, na confirmação; o banco guarda o hash. O admin de
uma conta só emite para a própria conta.
"""
import re
import uuid

import pytest
from django.contrib.auth import get_user_model

from apps.synchronization.models import SyncEnrollmentTicket
from apps.synchronization.services import crypto, enrollment

pytestmark = pytest.mark.django_db

ADICIONAR = "/admin/synchronization/syncenrollmentticket/add/"


@pytest.fixture
def superusuario(db):
    return get_user_model().objects.create_superuser("root", "root@starchef.test", "senha-de-teste-123")


def _emitir(client, **dados):
    return client.post(ADICIONAR, dados, follow=True)


def test_o_formulario_de_emissao_tem_os_campos_editaveis(client, superusuario):
    """Campo em `readonly_fields` some do formulário de ADIÇÃO: a conta, o
    restaurante e a identificação precisam ser digitáveis ao emitir."""
    client.force_login(superusuario)

    pagina = client.get(ADICIONAR).content.decode()

    for campo in ("account", "restaurant", "label"):
        assert f'name="{campo}"' in pagina, campo


def test_emite_mostra_o_codigo_uma_vez_e_guarda_so_o_hash(client, superusuario, conta):
    client.force_login(superusuario)

    resposta = _emitir(client, account=str(conta.id), label="Loja Centro")

    assert resposta.status_code == 200
    bilhete = SyncEnrollmentTicket.objects.get(label="Loja Centro")
    codigo = re.search(r"<code>(sc-[^<]+)</code>", resposta.content.decode()).group(1)
    assert bilhete.code_hash == crypto.hash_token(codigo)
    assert bilhete.utilizavel and bilhete.created_by == superusuario
    # A listagem depois disso não reexibe o código.
    assert codigo not in client.get("/admin/synchronization/syncenrollmentticket/").content.decode()


def test_restaurante_de_outra_conta_e_recusado(client, superusuario, conta, outra_conta):
    from apps.restaurants.models import Restaurant

    client.force_login(superusuario)
    alheio = Restaurant.all_objects.create(account=outra_conta, legal_name="X LTDA", trade_name="X")

    _emitir(client, account=str(conta.id), restaurant=str(alheio.id), label="Errado")

    assert not SyncEnrollmentTicket.objects.filter(label="Errado").exists()


def test_codigo_sc_inventado_e_recusado_e_nao_cai_no_segredo_legado(como_nuvem, conta):
    """`sc-` é o formato do bilhete: um código desses que não existe não pode
    escorregar para o segredo compartilhado antigo, que não tem uso único."""
    with pytest.raises(enrollment.EnrollmentRefused):
        enrollment._consumir_bilhete(f"sc-{uuid.uuid4().hex}", conta, "10.0.0.1")
