"""Os atores do salão: garçom, balança e caixa.

Cada um repete o GESTO quando a rede falha, como a pessoa faz — e cada
repetição é uma chamada nova, com `Idempotency-Key` nova, igual ao PDV. A marca
da intenção (observação, peso, chave do recebimento) é a mesma em todas as
tentativas, e é ela que a validação conta no banco.
"""
import random
import time
import uuid
from decimal import Decimal

from cliente import Falha

TENTATIVAS = 4


def gesto(terminal, metodo, caminho, corpo=None):
    """A chamada, repetida pelo operador enquanto for falha de rede."""
    ultima = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resposta, origem = terminal.chamar(metodo, caminho, corpo)
            return resposta, origem, tentativa
        except Falha as erro:
            ultima = erro
            if not (erro.conectividade or (erro.status or 0) >= 500):
                raise
            time.sleep(1.5 * tentativa)
    raise ultima


def garcom(terminal, dados, salao, registro, parar):
    produtos = dados["produtos"]
    while not parar.is_set():
        comanda = salao.qualquer()
        for _ in range(random.randint(1, 3)):
            produto = random.choice(produtos)
            marca = f"sim:{uuid.uuid4().hex[:12]}"
            qtd = random.choice([1, 1, 1, 2, 3])
            item = {"marca": marca, "comanda": comanda["id"], "produto": produto["id"], "qtd": qtd}
            try:
                resposta, origem, tentativas = gesto(
                    terminal, "POST", f"/commands/{comanda['id']}/items/",
                    {"product": produto["id"], "quantity": qtd, "customer_note": marca},
                )
                item.update(ok=True, origem=origem, tentativas=tentativas)
                if str(resposta.get("product")) != produto["id"] or \
                        Decimal(str(resposta.get("quantity"))) != Decimal(qtd):
                    registro.anomalia(terminal.nome, f"item lançado volta diferente: {resposta}")
                salao.lancou(comanda["id"])
            except Falha as erro:
                item.update(ok=False, erro=f"{erro} {erro.corpo or ''}"[:200])
            registro.anotar("itens", item)
        time.sleep(random.uniform(1.0, 3.0))


def balanca(terminal, dados, salao, registro, parar, balanca_id, contador):
    """O peso é a marca da pesagem: o contador é COMPARTILHADO entre as duas
    balanças, então nenhum peso se repete na simulação."""
    while not parar.is_set():
        comanda = salao.qualquer()
        with contador["trava"]:
            contador["n"] += 1
            peso = (Decimal("0.200") + Decimal(contador["n"]) * Decimal("0.0013")).quantize(
                Decimal("0.001"))
        pesagem = {"comanda": comanda["id"], "peso": str(peso), "balanca": balanca_id}
        try:
            _, origem, tentativas = gesto(
                terminal, "POST", f"/scales/{balanca_id}/checkout-command/",
                {"command_code": comanda["codigo"] or str(comanda["numero"]), "weight_kg": str(peso)},
            )
            pesagem.update(ok=True, origem=origem, tentativas=tentativas)
            salao.lancou(comanda["id"])
        except Falha as erro:
            pesagem.update(ok=False, erro=f"{erro} {erro.corpo or ''}"[:200])
        registro.anotar("pesagens", pesagem)
        time.sleep(random.uniform(3.0, 6.0))
