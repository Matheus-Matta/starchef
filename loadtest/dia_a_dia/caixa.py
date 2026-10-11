"""O caixa: abre a sessão, fecha a conta da comanda e recebe.

O caminho é o do PDV desktop (`order_draft_materializer.dart`): a venda vive
no terminal até o fim. O servidor CALCULA o total sem gravar (`simular`), e a
conclusão é UM envio — pedido, comanda e recebimentos (`/orders/submit/`),
tudo com o UUID do terminal. O recebimento leva uma marca em `metadata` — é
por ela que a validação conta quantas vezes ele existe.
"""
import random
import time
import uuid
from datetime import datetime, timezone
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


def _recebimento(dados, valor, tipo, sessao):
    """O corpo de um recebimento, com a identidade (UUID + horário) dada aqui."""
    marca = f"sim:{uuid.uuid4().hex[:12]}"
    corpo = {"payment_method": dados["formas"][tipo], "amount": f"{valor:.2f}",
             "idempotency_key": marca, "metadata": {"sim_intencao": marca},
             "id": str(uuid.uuid4()),
             "client_updated_at": datetime.now(timezone.utc).isoformat()}
    if tipo == "cash":
        corpo["cash_register"] = sessao
    if tipo == "card":
        corpo["card_subtype"] = random.choice(["credit", "debit"])
    return corpo, {"marca": marca, "valor": f"{valor:.2f}", "tipo": tipo}


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
            venda = {"id": str(uuid.uuid4()), "order_type": "command",
                     "restaurant": dados["restaurante"], "items": [],
                     "commands": [comanda["id"]]}
            previa, origem, _ = gesto(terminal, "POST", "/orders/submit/",
                                      {**venda, "simular": True})
            conta.update(pedido=venda["id"], origem_abertura=origem)
            # Só o que o caixa viu: o lançado enquanto o cliente paga fica para a
            # próxima conta (como o PDV, `draft.anotacoesVistas`).
            venda["command_items"] = [str(item["command_item"]) for item in previa["order"].get("items", [])
                                      if item.get("command_item")]
            total = Decimal(str(previa["order"].get("total") or 0))
            conta["total"] = str(total)
            if total <= 0:
                registro.anomalia(terminal.nome, f"conta da comanda {comanda['numero']} com total {total}")
            else:
                tipo = random.choices(["pix", "card", "cash"], [5, 3, 2])[0]
                partes = [total] if random.random() < 0.8 else [
                    (total / 2).quantize(Decimal("0.01")), total - (total / 2).quantize(Decimal("0.01"))]
                montados = [_recebimento(dados, parte, tipo, sessao) for parte in partes]
                try:
                    _, origem, tentativas = gesto(terminal, "POST", "/orders/submit/", {
                        **venda, "kitchen": {"client_batch_serial": str(uuid.uuid4())},
                        "expected_total": str(total),
                        "payments": [corpo for corpo, _ in montados]})
                    for _, pagamento in montados:
                        pagamento.update(ok=True, origem=origem, tentativas=tentativas)
                except Falha as erro:
                    for _, pagamento in montados:
                        pagamento.update(ok=False, erro=f"{erro} {erro.corpo or ''}"[:200])
                conta["pagamentos"] = [pagamento for _, pagamento in montados]
                final, _ = terminal.chamar("GET", f"/orders/{venda['id']}/")
                conta.update(status=final.get("status"), pago=final.get("payment_status"),
                             total_final=str(final.get("total")))
                if final.get("status") not in PAGOS and final.get("payment_status") != "paid":
                    registro.anomalia(terminal.nome, f"pedido {venda['id']} terminou {final.get('status')}"
                                      f"/{final.get('payment_status')} depois de receber {total}")
        except Falha as erro:
            conta["erro"] = f"{erro} {erro.corpo or ''}"[:200]
            sobrou = True
        registro.anotar("pedidos", conta)
        salao.liberar(comanda["id"], ainda_tem_consumo=sobrou)
        time.sleep(random.uniform(3.0, 7.0))
