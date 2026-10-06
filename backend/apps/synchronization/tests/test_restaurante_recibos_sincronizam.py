"""As duas chaves de recibo do restaurante chegam aos terminais da loja.

Campo novo não tem trava automática na sincronização: sem este teste, o
painel da nuvem desligaria o recibo e a loja continuaria imprimindo.
"""
import pytest

from apps.synchronization.catalog import registry
from apps.synchronization.services.serialization import serialize

pytestmark = pytest.mark.django_db


def test_chaves_de_recibo_do_restaurante_vao_no_payload(restaurant):
    restaurant.auto_print_receipt = False
    restaurant.print_cancellation_receipt = True
    restaurant.save(update_fields=["auto_print_receipt", "print_cancellation_receipt"])

    payload = serialize(restaurant, registry.require("restaurant"))

    assert payload["auto_print_receipt"] is False
    assert payload["print_cancellation_receipt"] is True


def test_padroes_recibo_ligado_e_cancelamento_desligado(restaurant):
    """Recibo automático era o único comportamento; o de cancelamento é novo."""
    assert restaurant.auto_print_receipt is True
    assert restaurant.print_cancellation_receipt is False
