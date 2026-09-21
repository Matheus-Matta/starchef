from celery import Celery
from celery.signals import worker_process_init

from config.env import configure_django_settings

configure_django_settings()

app = Celery("starchef")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@worker_process_init.connect
def conexao_propria_por_processo(**_kwargs):
    """Cada filho do prefork abre a PRÓPRIA conexão com o banco.

    O processo principal do Celery carrega o Django e pode abrir uma conexão
    antes de bifurcar — no `autodiscover_tasks`, num `check`, em qualquer
    import que consulte o banco. O `fork()` copia o descritor do socket para
    todos os filhos, e aí dois processos escrevem no MESMO canal: as respostas
    chegam trocadas, e o sintoma não parece de conexão.

    Era isto que produzia, no arranque do worker, o
    `psycopg.ProgrammingError: the last operation didn't produce records` —
    um `SELECT` recebendo o resultado do `UPDATE` de outro processo. Some
    sozinho depois dos primeiros segundos, porque a conexão quebra e cada
    filho abre a sua; o estrago fica nas tarefas que morreram no meio.

    Fechar aqui é o que garante que ninguém herde nada: o que estiver aberto
    neste ponto pertence ao processo principal, e o filho não tem o que fazer
    com isso.
    """
    from django.db import connections

    connections.close_all()
