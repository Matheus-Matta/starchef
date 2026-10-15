"""Total por forma de pagamento e total geral de uma sessão de caixa.

Soma os valores JÁ gravados de cada recebimento (regra do dinheiro: total de
vários é soma de valores arredondados), em `Decimal`. A tela não soma: o que o
gerente confere contra a maquininha e o extrato do banco sai daqui.
"""
from decimal import Decimal


def totais_por_forma(sales):
    """`sales` é a lista do `CashRegisterSerializer.get_sales`."""
    por_forma = {}
    total = Decimal("0.00")
    for venda in sales:
        valor = Decimal(str(venda.get("amount") or 0))
        troco = Decimal(str(venda.get("change_amount") or 0))
        chave = venda.get("payment_method")
        linha = por_forma.setdefault(chave, {
            "payment_method": chave,
            "payment_method_name": venda.get("payment_method_name") or "",
            "method_type": venda.get("method_type") or "",
            "count": 0,
            "amount": Decimal("0.00"),
            "change": Decimal("0.00"),
        })
        linha["count"] += 1
        linha["amount"] += valor
        linha["change"] += troco
        total += valor
    linhas = sorted(por_forma.values(), key=lambda linha: (-linha["amount"], linha["payment_method_name"]))
    return {
        "payment_totals": [
            {**linha, "amount": str(linha["amount"]), "change": str(linha["change"])} for linha in linhas
        ],
        "payments_total": str(total),
        "payments_count": len(sales),
    }
