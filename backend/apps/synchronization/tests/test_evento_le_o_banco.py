"""O evento leva o que está NO BANCO, não a cópia velha que estava na memória.

Achado no par Docker (`loadtest/dia_a_dia`): a tarefa que libera a rodada da
cozinha tinha o pedido na memória de ANTES do pagamento e salvou só
`updated_at`. O banco ficou certo (pago), mas o evento era montado da cópia
velha: "aberto/pendente" com versão NOVA. A loja aplicou — era o mais novo — e
o pedido pago voltou a ficar em aberto lá.
"""
import pytest

from apps.synchronization.models import SyncEvent
from apps.synchronization.tests.test_versao_mais_nova_vence import grupo  # noqa: F401 — fixture

pytestmark = pytest.mark.django_db


def test_save_parcial_de_copia_velha_manda_o_que_esta_no_banco(como_loja, grupo):  # noqa: F811
    velha = type(grupo)._base_manager.get(pk=grupo.pk)  # lida ANTES da mudança
    grupo.name = "Pago"
    grupo.save()

    velha.save(update_fields=["updated_at"])  # só toca o horário

    ultimo = SyncEvent.objects.filter(entity_type="customer_group",
                                      entity_id=str(grupo.pk)).order_by("-sequence").first()
    assert ultimo.payload["fields"]["name"] == "Pago"
