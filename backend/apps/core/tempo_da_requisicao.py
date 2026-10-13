"""Quanto cada requisição custou no servidor, e em quê.

O caixa via 10 s para finalizar uma venda e ninguém sabia dizer de onde eles
vinham: CPU do Python, banco (na nuvem, ~6 ms de rede POR consulta) ou o
caminho até o servidor. Sem a medida, cada tentativa de otimizar era palpite.

Toda resposta leva `Server-Timing` (o DevTools do navegador o desenha, e o
`curl -I` o mostra), e a requisição acima de `REQUISICAO_LENTA_MS` vai para
o log com o mesmo detalhe:

    requisicao lenta POST /api/v1/orders/submit/ -> 201 em 2400 ms
    (banco 1900 ms em 111 consultas; aplicacao 500 ms)

Banco alto com muitas consultas = consulta repetida a cortar; banco alto com
poucas = banco longe ou lento; aplicação alta = CPU (Python ou a instância
sem crédito). O tempo do nginx (`rt` no log dele) menos o `total` daqui é o
caminho entre os dois.
"""
import logging
import time

from django.conf import settings
from django.db import connection

logger = logging.getLogger("starchef.tempo")


class TempoDaRequisicaoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        medida = {"consultas": 0, "banco": 0.0}

        def cronometro(execute, sql, params, many, context):
            inicio = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                medida["consultas"] += 1
                medida["banco"] += time.perf_counter() - inicio

        inicio = time.perf_counter()
        with connection.execute_wrapper(cronometro):
            response = self.get_response(request)
        total = (time.perf_counter() - inicio) * 1000
        banco = medida["banco"] * 1000
        aplicacao = max(total - banco, 0)
        response["Server-Timing"] = (
            f"app;dur={aplicacao:.0f}, "
            f'db;dur={banco:.0f};desc="{medida["consultas"]} consultas", '
            f"total;dur={total:.0f}"
        )
        if total >= getattr(settings, "REQUISICAO_LENTA_MS", 500):
            logger.warning(
                "requisicao lenta %s %s -> %s em %.0f ms (banco %.0f ms em %d consultas; aplicacao %.0f ms)",
                request.method, request.path, response.status_code, total, banco,
                medida["consultas"], aplicacao,
            )
        return response
