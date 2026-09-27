# loadtest — carga pesada do StarChef

Suíte manual de carga para as frentes: **backend**, **web**, **desktop** (PDVs
simulados), **mobile** (aplicativos de garçom), **comanda** (o ciclo de vida do
cartão, incluindo a balança) e **sync**. Só biblioteca padrão do Python;
nenhuma dependência nova.

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

## A pergunta da suíte `comanda`

```bash
python loadtest/run.py comanda --profile leve --base-url http://127.0.0.1:8021
```

Ela percorre o cartão de ponta a ponta — lançamento, venda de uma comanda por
conta, cancelamento, remoção de item, pesagem na balança e um turno inteiro de
erros de operador — e termina perguntando **se a mesa ficou livre e o cartão
voltou para a gaveta**.

É pergunta de carga porque o que a quebra é a corrida, e porque o defeito não
aparece como erro: um cartão ocupado sem nada a cobrar some do salão em
silêncio. A suíte cria os próprios cartões e mesas, e separa "o backend
recusou" de "não houve resposta" — só a recusa reprova.

## A pergunta da suíte `promocoes`

```bash
python loadtest/run.py promocoes --profile leve --base-url http://127.0.0.1:8012
```

Três perguntas que só a corrida responde:

1. **o preço lido é sempre um preço que existe?** O preço virou cálculo, e a
   suíte lê o catálogo com trinta terminais enquanto liga e desliga a tabela de
   desconto. Um terceiro valor — nem prateleira, nem promoção — é resolução
   parcial, e no caixa é cobrar um preço que ninguém cadastrou.
2. **"compra única por cliente" resiste a duas vendas simultâneas?**
3. **o código do operador é exigido SEMPRE?** Uma exigência que vale em 99% das
   requisições não vale: o 1% é o lançamento sem rastro.

A fase 3 usa **barreira de largada**, e não volume — o que abre a janela é a
simultaneidade. Seis tentativas soltas juntas disputam mais que trezentas
espaçadas.

**Ela já pagou o próprio custo.** Na primeira execução: seis vendas levaram um
cupom de uso único e **zero resgates** foram gravados. O resgate estava ligado no
ramo errado (`close_order` "pago integralmente", que só dispara ao fechar de novo
um pedido já pago) e o caminho do caixa — fechar, depois cobrar — não gravava
nada. Sem resgate, `usos_do_cupom` responde zero para sempre: "compra única",
"usos por cliente" e "limite total" não valiam nada, e o cupom era infinito.

## Validar a sincronização: o par NUVEM + LOJA

```bash
bash loadtest/scripts/start_sync_pair.sh          # nuvem 8021, loja 8022
.venv/Scripts/python loadtest/validar_sync_par.py
bash loadtest/scripts/start_sync_pair.sh --down
```

A suíte `sync` mede a FILA. Isto mede outra coisa: **o registro atravessou?** São
dois backends com **bancos separados**, matriculados um no outro — com um banco
só, o que a loja "recebeu" seria a mesma linha que a nuvem gravou.

Valida as duas direções: tabela, regra, **vínculo do encarte**, cupom e as chaves
do restaurante descendo; `metafields` do pedido e o **resgate do cupom** subindo.
Termina provando a consequência: **a nuvem recusa o cupom que a loja consumiu**.

> O par precisa do **Celery na nuvem**. A matrícula só ENFILEIRA a carga total, e
> sem worker na fila `sync.bootstrap` (e sem o beat avisando) o par sobe inteiro,
> a loja autentica, e nada sincroniza — foi o que aconteceu na primeira subida:
> cinco containers de pé e a loja com 1 usuário, 0 produtos.

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
