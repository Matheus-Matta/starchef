# loadtest — carga pesada do StarChef

Suíte manual de carga para as quatro frentes: **backend**, **web**, **desktop**
(PDVs simulados) e **mobile** (aplicativos de garçom). Só biblioteca padrão do
Python; nenhuma dependência nova.

A documentação completa — o que cada fase faz, como ler o relatório, perfis e
limpeza — está em [`docs/TESTE_CARGA.md`](../docs/TESTE_CARGA.md). Este arquivo
é só o cartão de referência.

## Rodar

```bash
# 1. alvo descartavel (banco proprio, throttle praticamente desligado)
bash loadtest/scripts/start_backend.sh 8011
SQLITE_DB_NAME=db_loadtest.sqlite3 .venv/Scripts/python backend/manage.py seed_demo --skip-orders

# 2. carga
.venv/Scripts/python loadtest/run.py backend --profile medio --base-url http://127.0.0.1:8011
.venv/Scripts/python loadtest/run.py all     --profile pesado
```

Perfis: `fumaca`, `leve`, `medio`, `pesado`, `extremo`.
Relatório em `artifacts/loadtest/carga-<data>.{md,json}`. Saída `1` quando há
defeito ou verificação de coerência reprovada.

## Avisos

- **Nunca aponte para produção nem para o banco de desenvolvimento normal.** A
  suíte cria dezenas de milhares de registros e deixa lixo de propósito.
- `--cleanup` apaga o que foi criado; o mais simples é jogar o banco fora.
- SQLite devolve `500 database is locked` sob concorrência. Para os perfis
  `pesado`/`extremo`, aponte o backend para Postgres.
