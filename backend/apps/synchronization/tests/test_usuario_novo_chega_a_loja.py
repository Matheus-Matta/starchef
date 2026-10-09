"""O usuário criado na nuvem chega à loja — antes do perfil dele.

`auth.User` não tem conta: a outbox a descobre pelo PERFIL. Só que o usuário é
gravado ANTES do perfil (cadastro do painel, `ensure_tenant_user`, qualquer
`create_user` seguido do perfil), e nesse instante não há conta nenhuma — o
evento do usuário era descartado em silêncio. O perfil subia sozinho e, na
loja, ficava em "UserProfile.user aponta para User 6, que ainda não existe
aqui" até morrer. O garçom cadastrado na nuvem não entrava na loja.

Achado pela simulação do dia a dia (`loadtest/dia_a_dia`), com o par real.
"""
import pytest
from django.contrib.auth import get_user_model

from apps.synchronization.constants import Direction
from apps.synchronization.models import SyncEvent

pytestmark = pytest.mark.django_db


def test_gravar_o_perfil_registra_o_usuario_antes_dele(como_nuvem, conta, no_loja):
    from apps.accounts.models import Role, UserProfile
    from apps.core.tenant import tenant_context

    usuario = get_user_model().objects.create_user("garcom.novo", "g@t.test", "x")
    assert not SyncEvent.objects.filter(entity_type="user", entity_id=str(usuario.pk)).exists()

    with tenant_context(conta):
        papel = Role.all_objects.filter(account=conta).first()
        UserProfile.all_objects.create(user=usuario, account=conta, role=papel, is_active=True)

    eventos = list(
        SyncEvent.objects.filter(direction=Direction.OUTBOUND, target_node=no_loja,
                                 entity_type__in=["user", "user_profile"])
        .order_by("sequence").values_list("entity_type", "entity_id")
    )
    tipos = [tipo for tipo, _ in eventos]
    assert ("user", str(usuario.pk)) in eventos
    assert tipos.index("user") < tipos.index("user_profile")
