"""O processo web precisa enfileirar no Celery CONFIGURADO, não no padrão.

O `config/__init__.py` estava vazio: o gunicorn sobe o Django sem nunca
importar `config.celery`, e toda `tarefa.delay(...)` do painel caía no app
padrão do Celery — sem broker (tentava um RabbitMQ em localhost que não
existe). O erro era engolido (`bulk_jobs.services._dispatch`, o sinal da
nota) e o operador ficava sem nada: nem resultado, nem aviso de falha no sino.

Funcionava às vezes: quando algum código da sincronização importava
`config.celery`, aquele processo passava a ter o app certo — até reiniciar.

Roda num processo NOVO de propósito: dentro do pytest algum import pode já ter
carregado o app e esconder o defeito, como acontecia em produção.
"""
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

SCRIPT = """
import django
django.setup()
from django.conf import settings
from apps.bulk_jobs.tasks import run_bulk_job_task as tarefa
print(tarefa.app.main, tarefa.app.conf.broker_url == settings.CELERY_BROKER_URL)
"""


def test_tarefa_enfileirada_pelo_django_usa_o_app_e_o_broker_do_projeto():
    resultado = subprocess.run(
        [sys.executable, "-c", SCRIPT], cwd=BACKEND, capture_output=True, text=True, timeout=120,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.test"},
    )

    assert resultado.returncode == 0, resultado.stderr[-2000:]
    assert resultado.stdout.split()[-2:] == ["starchef", "True"], resultado.stdout
