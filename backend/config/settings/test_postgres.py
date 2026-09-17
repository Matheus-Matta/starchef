"""Settings de teste apontando para PostgreSQL.

`config.settings.test` fixa SQLite de propósito: é o que deixa a suíte rodar em
qualquer máquina, sem serviço nenhum no ar. Mas a rede de segurança do §11.2 é
PL/pgSQL — testá-la exige o banco de verdade, e é para isso que este módulo
existe.

    docker run -d --rm --name pg -e POSTGRES_PASSWORD=synctest \
      -e POSTGRES_USER=starchef -e POSTGRES_DB=starchef_sync \
      -p 55432:5432 postgres:16-alpine

    POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 POSTGRES_PASSWORD=synctest \
      pytest --ds=config.settings.test_postgres \
      apps/synchronization/tests/test_triggers_postgres.py
"""
from .test import *  # noqa: F403

import os

# `build_database_settings` lê as opções do AMBIENTE (decouple), não de
# variáveis deste módulo — então desligar o pool aqui exige exportar a env
# antes de chamá-la. Sem isso, o Django tenta importar `psycopg_pool` (que não
# está nas dependências) e o erro não diz nada sobre teste.
#
# E o pool atrapalharia de qualquer forma: o pytest-django cria e destrói o
# banco de teste, e conexões seguradas por um pool impedem o DROP DATABASE.
os.environ.setdefault("POSTGRES_POOL", "False")

USE_SQLITE_DATABASE = False
globals().update(build_database_settings(False))  # noqa: F405
