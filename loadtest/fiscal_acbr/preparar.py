"""Prepara, NA NUVEM, a emissão pela ACBrLib (roda em `manage.py shell`).

Desce para a loja pela sincronização — e é a loja que emite: a nuvem não
emite venda de conta com servidor de loja (docs/FISCAL_ACBRLIB.md).
"""
import json
from decimal import Decimal

from apps.core.management.commands._demo_seed import ensure_demo_roles, ensure_tenant_user

from apps.core.tenant import tenant_context
from apps.invoices.models import FiscalConfig
from apps.menu.models import Product
from apps.payments.models import CashStation, PaymentMethod
from apps.restaurants.models import Restaurant

restaurante = Restaurant.all_objects.filter(trade_name__icontains="burger").first()
restaurante.require_open_cash_register = False
restaurante.save()
with tenant_context(restaurante.account):
    config = FiscalConfig.all_objects.filter(restaurant=restaurante, deleted_at__isnull=True).first()
    config = config or FiscalConfig(account=restaurante.account, restaurant=restaurante)
    config.provider = FiscalConfig.PROVIDER_ACBRLIB
    config.offline_contingency = True
    config.document_model = FiscalConfig.MODEL_NFCE
    config.environment = FiscalConfig.ENV_HOMOLOGATION
    config.is_active = True
    config.series = 1
    config.cnpj, config.uf, config.ie, config.crt = "11222333000181", "SP", "123456789", "1"
    config.corporate_name = config.corporate_name or "Burger Palace LTDA"
    config.address_line, config.address_number, config.district = "Rua A", "10", "Centro"
    config.city, config.city_ibge, config.zip_code = "Sao Paulo", "3550308", "01001000"
    config.csc_id, config.csc_token = "000001", "CSC-DE-TESTE"
    config.certificate_ref, config.certificate_password = "/tmp/teste.pfx", "1234"
    config.save()
    produtos = [str(p) for p in Product.all_objects.filter(
        restaurants=restaurante, is_active=True, deleted_at__isnull=True,
        base_price__gt=0, pricing_unit="unit").values_list("id", flat=True)[:10]]
    papeis = ensure_demo_roles(restaurante.account, restaurante)
    caixas = []
    for i in range(1, 5):
        operador = ensure_tenant_user(
            account=restaurante.account, username=f"acbr.caixa{i}", email=f"acbr{i}@sim.test",
            password="Senha12345!", restaurant=restaurante, branch=None, role=papeis["manager"])
        estacao, _ = CashStation.all_objects.update_or_create(
            account=restaurante.account, restaurant=restaurante, code=f"ACBR-{i}",
            defaults={"name": f"PDV ACBr {i}", "cash_limit": Decimal("1000000"),
                      "is_active": True, "deleted_at": None})
        estacao.operators.set([operador])
        caixas.append({"usuario": operador.username, "estacao": str(estacao.id)})
    pix = PaymentMethod.all_objects.filter(restaurant=restaurante, method_type="pix").first()

print(json.dumps({"restaurante": str(restaurante.id), "config": str(config.id),
                  "produtos": produtos, "pix": str(pix.id), "caixas": caixas}))
