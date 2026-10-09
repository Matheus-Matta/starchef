"""Prepara, NA NUVEM, o salão do dia a dia simulado.

Roda dentro do container da nuvem (`manage.py shell < preparar.py`), depois do
`seed_demo`. Tudo nasce na nuvem e chega à loja pela sincronização — que é a
primeira coisa que a simulação confere.

    5 garçons, 3 caixas (cada um com a SUA estação: o mesmo usuário em outra
    máquina é bloqueado), 2 balanças com produto por quilo e 40 comandas.

Imprime um JSON na última linha, que o orquestrador lê.
"""
import json
from decimal import Decimal

from apps.core.management.commands._demo_seed import ensure_demo_roles, ensure_tenant_user
from apps.core.tenant import tenant_context
from apps.menu.models import Product
from apps.payments.models import CashStation, PaymentMethod
from apps.printers.models import Scale
from apps.restaurants.models import Command, Restaurant

SENHA = "Senha12345!"

restaurante = Restaurant.all_objects.filter(trade_name__icontains="burger").first()
conta = restaurante.account
filial = restaurante.branches.first() if hasattr(restaurante, "branches") else None
papeis = ensure_demo_roles(conta, restaurante)


def usuario(nome, papel):
    return ensure_tenant_user(
        account=conta, username=nome, email=f"{nome}@sim.test", password=SENHA,
        restaurant=restaurante, branch=filial, role=papeis[papel],
    )


with tenant_context(conta):
    garcons = [usuario(f"sim.garcom{i}", "waiter").username for i in range(1, 6)]
    caixas = []
    for i in range(1, 4):
        operador = usuario(f"sim.caixa{i}", "manager")
        estacao, _ = CashStation.all_objects.update_or_create(
            account=conta, restaurant=restaurante, code=f"SIM-{i}",
            defaults={"name": f"PDV simulado {i}", "cash_limit": Decimal("100000"),
                      "is_active": True, "deleted_at": None},
        )
        estacao.operators.set([operador])
        caixas.append({"usuario": operador.username, "estacao": str(estacao.id)})

    modelo = Scale.all_objects.filter(restaurant=restaurante).exclude(product=None).first()
    balancas = [str(modelo.id)]
    segunda, _ = Scale.all_objects.update_or_create(
        account=conta, restaurant=restaurante, branch=modelo.branch, name="Balança 2 (simulada)",
        defaults={"protocol": modelo.protocol, "port": "COM4", "product": modelo.product,
                  "printer": modelo.printer,
                  "reading_max_age_seconds": 120, "is_active": True, "auto_print": False},
    )
    balancas.append(str(segunda.id))

    comandas = []
    for numero in range(501, 541):
        comanda = Command.all_objects.filter(restaurant=restaurante, number=numero).first()
        if comanda is None:
            comanda = Command(account=conta, restaurant=restaurante, branch=filial, number=numero)
            comanda.save()
        comandas.append({"id": str(comanda.id), "numero": numero, "codigo": comanda.code})

    produtos = [
        {"id": str(p.id), "nome": p.name}
        for p in Product.all_objects.filter(restaurants=restaurante, is_active=True,
                                            deleted_at__isnull=True)
        .exclude(pk=modelo.product_id)[:12]
    ]
    formas = {
        p.method_type: str(p.id)
        for p in PaymentMethod.all_objects.filter(restaurant=restaurante, is_active=True)
    }

print(json.dumps({
    "conta": str(conta.id), "restaurante": str(restaurante.id), "senha": SENHA,
    "garcons": garcons, "caixas": caixas, "balancas": balancas,
    "comandas": comandas, "produtos": produtos, "formas": formas,
}))
