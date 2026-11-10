"""O transporte Redis do kombu aceita o redis-py que está instalado.

Achado em produção na v3.1.11: o `kombu` não tinha trava, a imagem nova puxou
o 5.7.0 — que exige redis-py >= 6.1 — e o `redis` está travado em 5.0. O worker
e o beat morriam no boot com `VersionMismatch` e nenhuma tarefa rodava (notas,
sincronização, lançamentos em massa). O CI não viu porque nenhum teste abre o
canal do Redis: este chama exatamente o ponto onde o worker quebrou, sem rede.
"""
from types import SimpleNamespace

from kombu.transport.redis import Channel


def test_o_worker_consegue_abrir_o_canal_do_redis_com_as_versoes_travadas():
    canal = SimpleNamespace(global_keyprefix=None)

    Channel._get_client(canal)  # levanta VersionMismatch se kombu e redis brigarem
