"""O que cada ator QUIS fazer e o que o servidor respondeu.

A validação final compara isto com os dois bancos. Sem o registro da intenção
não dá para separar "o garçom lançou duas vezes" de "o sistema duplicou": cada
intenção tem uma marca única (a observação do item, o peso exato da pesagem, a
chave do recebimento) e é por ela que se conta o que existe no banco.
"""
import random
import threading
from collections import Counter


class Registro:
    def __init__(self):
        self._trava = threading.Lock()
        self.itens = []       # lançamentos do garçom
        self.pesagens = []    # pesagens da balança
        self.pedidos = []     # contas fechadas no caixa
        self.anomalias = []   # resposta errada do servidor
        self.eventos = []     # quedas simuladas, em ordem
        self.contagem = Counter()

    def anotar(self, lista, registro):
        with self._trava:
            getattr(self, lista).append(registro)

    def anomalia(self, ator, texto):
        with self._trava:
            self.anomalias.append(f"[{ator}] {texto}")

    def contar(self, chave, n=1):
        with self._trava:
            self.contagem[chave] += n


class Salao:
    """As comandas, e quem está cobrando qual. Uma comanda em cobrança não é
    sorteada por outro caixa — mas o garçom PODE lançar nela, como no salão."""

    def __init__(self, comandas):
        self.comandas = comandas
        self._trava = threading.Lock()
        self._cobrando = set()
        self._com_consumo = set()

    def qualquer(self):
        return random.choice(self.comandas)

    def lancou(self, comanda_id):
        with self._trava:
            self._com_consumo.add(comanda_id)

    def reservar_para_cobrar(self):
        with self._trava:
            livres = [c for c in self.comandas
                      if c["id"] in self._com_consumo and c["id"] not in self._cobrando]
            if not livres:
                return None
            comanda = random.choice(livres)
            self._cobrando.add(comanda["id"])
            self._com_consumo.discard(comanda["id"])
            return comanda

    def liberar(self, comanda_id, *, ainda_tem_consumo=False):
        with self._trava:
            self._cobrando.discard(comanda_id)
            if ainda_tem_consumo:
                self._com_consumo.add(comanda_id)
