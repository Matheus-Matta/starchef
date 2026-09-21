"""O pool de conexões não pode atravessar o `fork()` do Celery.

`DatabaseWrapper._connection_pools` é atributo de CLASSE: existe um pool por
processo, e o `fork()` copia esse objeto para cada filho. Só que
`ConnectionPool` abre conexões com THREADS de fundo, e `fork()` não copia
thread nenhuma além da que chamou. No filho o pool fica sem quem o abasteça:
todo pedido espera por um trabalhador que nunca vai rodar e estoura em
`PoolTimeout: couldn't get a connection after 10.00 sec`.

Foi o que derrubou os workers em produção — tarefas "terminando" em 10,003s
sem ter tocado no banco. E é invisível em teste de unidade, porque ninguém
bifurca num teste. Por isso o que se afirma aqui é a DECISÃO: sob Celery, sem
pool.
"""
import sys
import weakref

import pytest

from config.settings.base import _e_celery, build_database_settings


@pytest.fixture
def pool_ligado(monkeypatch):
    """O pool PEDIDO pela instalação.

    Explícito porque `config/settings/test_postgres.py` faz
    `os.environ.setdefault("POSTGRES_POOL", "False")` no import, e isso vale
    para a sessão inteira: depender do ambiente faria estes testes passarem ou
    falharem conforme a ORDEM em que a suíte roda.
    """
    monkeypatch.setenv("POSTGRES_POOL", "True")


@pytest.fixture
def como_celery(monkeypatch, pool_ligado):
    monkeypatch.setattr(sys, "argv", ["/usr/local/bin/celery", "-A", "config", "worker"])


@pytest.fixture
def como_gunicorn(monkeypatch, pool_ligado):
    monkeypatch.setattr(sys, "argv", ["/usr/local/bin/gunicorn", "config.asgi:application"])


def _opcoes(settings_do_banco):
    return settings_do_banco["DATABASES"]["default"]


def test_worker_celery_nao_usa_pool(como_celery):
    """O defeito que isto existe para impedir."""
    banco = _opcoes(build_database_settings(False))

    assert "pool" not in banco["OPTIONS"], (
        "o pool herdado no fork trava o worker em PoolTimeout"
    )


def test_sem_pool_o_worker_ganha_conexao_PERSISTENTE(como_celery):
    """Não é abrir e fechar a cada tarefa.

    Cada filho do prefork atende UMA tarefa por vez, então uma conexão por
    processo é o desenho certo — e é o que `CONN_MAX_AGE` dá. Zero aqui faria
    o worker reabrir conexão a cada tarefa, que sob o ritmo do beat é pior que
    o problema original.
    """
    banco = _opcoes(build_database_settings(False))

    assert banco["CONN_MAX_AGE"] > 0


def test_o_servidor_web_CONTINUA_com_pool(como_gunicorn):
    """A regra que não pode cair junto.

    O pool foi feito para o ASGI, que é thread por request: sem ele, quatro
    workers estouraram os 100 `max_connections` do Postgres em minutos.
    """
    banco = _opcoes(build_database_settings(False))

    assert banco["OPTIONS"].get("pool"), "o servidor web perdeu o pool"
    assert banco["CONN_MAX_AGE"] == 0, "pool e conexão persistente não convivem"


def test_quem_e_celery_e_decidido_pelo_PROCESSO(monkeypatch):
    """O mesmo container roda gunicorn, `manage.py` e `celery` com o mesmo
    `.env` — só o último não pode usar pool. Uma variável de ambiente exigiria
    acertar isso em cada `docker-compose` de cada loja, e errar em silêncio.
    """
    for argv, esperado in (
        (["/usr/local/bin/celery", "-A", "config", "worker"], True),
        (["/usr/local/bin/celery", "-A", "config", "beat"], True),
        (["celery"], True),
        (["/usr/local/bin/gunicorn"], False),
        (["manage.py", "sync_worker"], False),
        (["manage.py", "migrate"], False),
        ([], False),
    ):
        monkeypatch.setattr(sys, "argv", argv)
        assert _e_celery() is esperado, argv


def test_desligar_o_pool_pela_variavel_continua_valendo(como_gunicorn, monkeypatch):
    """A saída manual não sumiu: quem roda com pgbouncer na frente desliga."""
    monkeypatch.setenv("POSTGRES_POOL", "False")

    banco = _opcoes(build_database_settings(False))

    assert "pool" not in banco["OPTIONS"]


def test_o_filho_do_fork_fecha_a_conexao_herdada():
    """A outra metade do estrago, e ela não tem a ver com pool.

    O processo principal do Celery carrega o Django e pode abrir uma conexão
    antes de bifurcar. O `fork()` copia o descritor do socket para todos os
    filhos, e dois processos escrevendo no mesmo canal recebem respostas
    trocadas — o `psycopg.ProgrammingError: the last operation didn't produce
    records` que aparecia no arranque do worker.

    Não dá para exercitar um `fork()` aqui; o que se afirma é que o gancho
    continua ligado, porque removê-lo devolve o defeito em silêncio.
    """
    from celery.signals import worker_process_init

    import config.celery  # noqa: F401 — registra o gancho

    # Os receptores são guardados por referência FRACA; sem resolver, o que
    # se lê é o nome do weakref — que é vazio, e o teste passaria por engano.
    ligados = set()
    for _chave, referencia in worker_process_init.receivers:
        funcao = referencia() if isinstance(referencia, weakref.ref) else referencia
        ligados.add(getattr(funcao, "__name__", ""))

    assert "conexao_propria_por_processo" in ligados
