"""Aplicativo do garcom: fila propria + cache do Caixa Principal.

Duas regras do app real sao verificadas aqui, porque sao as que evitam erro
caro em campo:

1. leitura sem principal vem do cache, **marcada** como cache — e falha quando
   nao ha cache, em vez de fingir que esta tudo bem;
2. a sessao de caixa NUNCA vem do cache: sem principal, dinheiro nao aparece
   como forma de pagamento.
"""
import time

from .. import result as verdicts
from .terminal import WAITER, PrincipalDown, Terminal

MAX_CACHE = 120
CACHE_STALE_MINUTES = 30


class PrincipalCache:
    """Ultimas respostas confirmadas pelo principal, por rota+filtro."""

    def __init__(self, limite=MAX_CACHE):
        self.entradas = {}
        self.limite = limite
        self.hits = 0
        self.misses = 0

    def store(self, chave, valor):
        if len(self.entradas) >= self.limite:
            self.entradas.pop(next(iter(self.entradas)), None)
        self.entradas[chave] = (time.time(), valor)

    def read(self, chave):
        registro = self.entradas.get(chave)
        if registro is None:
            self.misses += 1
            return None
        gravado_em, valor = registro
        self.hits += 1
        marcado = dict(valor) if isinstance(valor, dict) else {"results": valor}
        marcado["_from_cache"] = True
        marcado["_cached_at"] = gravado_em
        marcado["_stale"] = (time.time() - gravado_em) > CACHE_STALE_MINUTES * 60
        return marcado


class WaiterTerminal(Terminal):
    """Um aparelho de garcom. So fala com o Caixa Principal."""

    def __init__(self, ctx, suite, session, name, principal):
        super().__init__(ctx, suite, session, name, role=WAITER, upstream=principal)
        self.cache = PrincipalCache()
        self.leituras_negadas = 0
        self.dinheiro_bloqueado = 0

    def read(self, path):
        """Leitura pelo principal, com cache quando ele estiver fora."""
        if self.upstream is None or not self.upstream.online:
            do_cache = self.cache.read(path)
            if do_cache is None:
                self.leituras_negadas += 1
            return do_cache
        inicio = time.time()
        resposta = self.session.get(path)
        self.ctx.record(
            self.suite, "garcom:leitura", "GET", path, resposta,
            expectation=verdicts.ACCEPT, case="leitura_pelo_principal", started=inicio,
        )
        if resposta.status == 200:
            corpo = resposta.json()
            self.cache.store(path, corpo)
            return corpo
        return None

    def cash_session_available(self):
        """A sessao de caixa nunca vem do cache — e a regra que evita o pior erro."""
        if self.upstream is None or not self.upstream.online:
            self.dinheiro_bloqueado += 1
            return False
        return bool(self.upstream.cash_register)

    def execute(self, operation, force_queue=False):
        try:
            return super().execute(operation, force_queue=force_queue)
        except PrincipalDown:
            self.outbox.enqueue(operation)
            return None

    def summary(self):
        base = super().summary()
        base.update({
            "cache_hits": self.cache.hits,
            "cache_misses": self.cache.misses,
            "leituras_negadas_sem_cache": self.leituras_negadas,
            "dinheiro_bloqueado_sem_principal": self.dinheiro_bloqueado,
        })
        return base
