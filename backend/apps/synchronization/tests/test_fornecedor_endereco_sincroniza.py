"""O endereço do fornecedor (vindo da nota de entrada) sincroniza.

Campo novo não tem trava automática: sem isto, o fornecedor criado pela
importação na nuvem chegaria à loja sem endereço nem IE.
"""
import pytest

from apps.stock.models import Supplier
from apps.synchronization.catalog import registry
from apps.synchronization.services.serialization import serialize

pytestmark = pytest.mark.django_db


def test_endereco_e_ie_do_fornecedor_vao_no_payload(account):
    fornecedor = Supplier.all_objects.create(
        account=account, name="Rio Quality", tax_id="08969770000159",
        state_registration="86123456", street="AV BRASIL", number="1000",
        district="PENHA", city="RIO DE JANEIRO", state="RJ", zip_code="21012000",
    )

    payload = serialize(fornecedor, registry.require("stock_supplier"))

    for campo in ("state_registration", "street", "number", "district", "city", "state", "zip_code"):
        assert payload[campo] == getattr(fornecedor, campo)
