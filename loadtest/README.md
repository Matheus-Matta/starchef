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

## Duas validações que só existem aqui

Há coisas que o pytest não consegue provar, e é por isso que elas moram no
teste de carga em vez de na suíte.

### A corrida pelo bilhete de matrícula

O bilhete vale UMA vez. O teste unitário prova que reapresentar um bilhete já
gasto é recusado — e não prova nada sobre duas apresentações **ao mesmo
tempo**, que é onde "uso único" de verdade se perde. Pior: a suíte roda em
SQLite, que serializa tudo e passaria pelo motivo errado.

```bash
# 1. emita um bilhete NO ALVO e anote o código
docker compose -f docker/loadtest/docker-compose.yml exec -T backend   python manage.py sync_issue_ticket --account <uuid> --label carga

# 2. a suíte dispara N matrículas simultâneas com ele
python loadtest/run.py sync --base-url http://127.0.0.1:8012   --enroll-ticket <codigo> --enroll-account <uuid>
```

Exatamente uma pode passar. Com duas, duas lojas dividem a mesma fila e faltam
dados dias depois, sem nada estourar.

### A aplicação inteira com RLS ligada

Os testes de `apps/core/tests/test_rls_postgres.py` provam o isolamento numa
tabela. O que eles não respondem é se a API TODA continua funcionando com a
política de pé — o modo de falhar do RLS é um endpoint que consultava fora do
contexto de conta e passa a receber zero linha, sem erro nenhum.

```bash
bash loadtest/scripts/rls_target.sh                     # liga no alvo no ar
python loadtest/run.py all --profile pesado --base-url http://127.0.0.1:8012
bash loadtest/scripts/rls_target.sh --off               # volta
```

O script troca o papel do banco junto, e isso é o ponto: com o usuário
SUPERUSER do contêiner a política não vale para ninguém e a carga passaria
verde sem ter exercitado nada.

## Avisos

- **Nunca aponte para produção nem para o banco de desenvolvimento normal.** A
  suíte cria dezenas de milhares de registros e deixa lixo de propósito.
- `--cleanup` apaga o que foi criado; o mais simples é jogar o banco fora.
- SQLite devolve `500 database is locked` sob concorrência. Para os perfis
  `pesado`/`extremo`, aponte o backend para Postgres.
