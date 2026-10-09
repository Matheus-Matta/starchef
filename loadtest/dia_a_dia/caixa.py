"""O caixa: abre a sessão, fecha a conta da comanda e recebe.

O caminho é o do PDV desktop (`order_draft_materializer.dart` e
`home_page_payment.dart`): cria o pedido do tipo comanda, puxa as anotações
pendentes do cartão (`attach-commands`), lê o total que o SERVIDOR calculou e
recebe. O recebimento leva a chave da intenção no corpo e uma marca em
`metadata` — é por ela que a validação conta quantas vezes ele existe.
"""
import random
import time
import uuid
from decimal import Decimal

from atores import gesto
from cliente import Falha

PAGOS = {"paid", "closed", "completed", "finished"}


def abrir_caixa(terminal, estacao, registro):
    """O caixa nunca desvia para a nuvem: com a loja fora, espera."""
    while True:
        try:
            resposta, _ = terminal.chamar(
                "POST", "/cash-register/open/", {"cash_station": estacao, "opening_amount": "100.00"}
            )
            return resposta["id"]
        except Falha as erro:
            if erro.status == 409:
                sessao = (erro.corpo or {}).get("session") or {}
                if sessao.get("id"):
                    return sessao["id"]
                atual, _ = terminal.chamar("GET", "/cash-register/current/")
                return atual.get("id")
            if (erro.status or 0) >= 500:
                registro.anomalia(terminal.nome, f"abrir caixa: {erro} {erro.corpo}")
            elif not erro.conectividade:
                registro.anomalia(terminal.nome, f"abrir caixa: {erro} {erro.corpo}")
                raise
            time.sleep(3)


def _receber(terminal, dados, pedido_id, valor, tipo, sessao):
    marca = f"sim:{uuid.uuid4().hex[:12]}"
    corpo = {"payment_method": dados["formas"][tipo], "amount": f"{valor:.2f}",
             "idempotency_key": marca, "metadata": {"sim_intencao": marca}}
    if tipo == "cash":
        corpo["cash_register"] = sessao
    if tipo == "card":
        corpo["card_subtype"] = random.choice(["credit", "debit"])
    pagamento = {"marca": marca, "valor": f"{valor:.2f}", "tipo": tipo}
    try:
        _, origem, tentativas = gesto(terminal, "POST", f"/orders/{pedido_id}/pay/", corpo)
        pagamento.update(ok=True, origem=origem, tentativas=tentativas)
    except Falha as erro:
        pagamento.update(ok=False, erro=f"{erro} {erro.corpo or ''}"[:200])
    return pagamento


def caixa(terminal, dados, salao, registro, parar, estacao):
    sessao = abrir_caixa(terminal, estacao, registro)
    while not parar.is_set():
        comanda = salao.reservar_para_cobrar()
        if comanda is None:
            time.sleep(2)
            continue
        conta = {"comanda": comanda["id"], "numero": comanda["numero"], "pagamentos": []}
        sobrou = False
        try:
            pedido, origem, _ = gesto(terminal, "POST", "/orders/",
                                      {"order_type": "command", "restaurant": dados["restaurante"]})
            conta.update(pedido=pedido["id"], origem_abertura=origem)
            pedido, _, _ = gesto(terminal, "POST", f"/orders/{pedido['id']}/attach-commands/",
                                 {"commands": [comanda["id"]]})
            total = Decimal(str(pedido.get("total") or 0))
            conta["total"] = str(total)
            if total <= 0:
                registro.anomalia(terminal.nome, f"conta da comanda {comanda['numero']} com total {total}")
            else:
                tipo = random.choices(["pix", "card", "cash"], [5, 3, 2])[0]
                partes = [total] if random.random() < 0.8 else [
                    (total / 2).quantize(Decimal("0.01")), total - (total / 2).quantize(Decimal("0.01"))]
                for parte in partes:
                    conta["pagamentos"].append(_receber(terminal, dados, pedido["id"], parte, tipo, sessao))
                final, _ = terminal.chamar("GET", f"/orders/{pedido['id']}/")
                conta.update(status=final.get("status"), pago=final.get("payment_status"),
                             total_final=str(final.get("total")))
                if final.get("status") not in PAGOS and final.get("payment_status") != "paid":
                    registro.anomalia(terminal.nome, f"pedido {pedido['id']} terminou {final.get('status')}"
                                      f"/{final.get('payment_status')} depois de receber {total}")
        except Falha as erro:
            conta["erro"] = f"{erro} {erro.corpo or ''}"[:200]
            sobrou = True
        registro.anotar("pedidos", conta)
        salao.liberar(comanda["id"], ainda_tem_consumo=sobrou)
        time.sleep(random.uniform(3.0, 7.0))
