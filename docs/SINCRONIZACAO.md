# Sincronização backend-to-backend

Como a loja continua vendendo sem internet, e como tudo que aconteceu lá chega
à nuvem depois — sem duplicar, sem perder e sem misturar contas.

Implementa `afazer/PLANO_IMPLEMENTACAO_SINCRONIZACAO_BACKEND_TO_BACKEND.md`.

`SYNC_ENVIRONMENT` aceita **`development`** e **`production`**. Um valor fora
dessa lista é recusado com exceção — `prod` não vira um terceiro ambiente onde
nenhum nó encontra nenhum outro.

O ambiente faz parte da **identidade do nó** e é conferido no HELLO em três
perguntas: o valor existe, é o mesmo desta instalação, e é o mesmo da ficha do
nó na nuvem. É isso que impede uma loja de homologação entrar na nuvem de
produção com credencial válida. Para virar de um para outro sem derrubar as
lojas, ver `manage.py sync_set_environment` — o comando traz a ordem dos
passos no próprio `--help`.

## O desenho em uma frase

Um backend só, dois papéis. `SYNC_NODE_TYPE=cloud` recebe conexões;
`SYNC_NODE_TYPE=local` abre a conexão de saída. Mesma imagem, mesmo código,
mesmas migrations.

```
PDV, KDS, garçom
        ↓
backend LOCAL  →  PostgreSQL da loja + outbox
        ↓
sync_worker  ⇄  WSS autenticado  ⇄  backend CLOUD
                                          ↓
                                  PostgreSQL central
```

A loja **nunca** precisa expor porta, IP fixo ou certificado: quem disca é ela.

## A garantia central

**Um evento gravado não se perde.** Ela se sustenta em três decisões, e só nas
três juntas:

1. **O evento nasce na mesma transação do dado.** Não em `on_commit` — o plano
   proíbe (§11.1), porque o processo cair entre o commit do pedido e a criação
   do evento é uma venda que existe na loja e nunca existirá na nuvem. Se a
   transação do pedido aborta, o evento aborta junto.
2. **Nada sai do banco antes da confirmação do outro lado.** `PENDING` → `SENT`
   → `RECEIVED` → `APPLIED` → `ACKNOWLEDGED`. Só o último estado libera a
   retenção, e mesmo assim depois de `SYNC_RETENTION_DAYS`.
3. **Reenviar é sempre seguro.** O `event_id` é global e único; o destino que
   já viu aquele id responde ACK sem tocar no domínio.

O que falhou doze vezes vira `DEAD` — e continua no banco, com payload e erro
íntegros, esperando `sync_recover --requeue`.

## Estrutura

```
backend/apps/synchronization/
├── catalog.py              # Os 52 models que sincronizam, e como
├── decisions.py            # Os 27 que NÃO sincronizam, e por quê
├── constants.py            # O vocabulário do protocolo (v1)
├── models/                 # SyncNode, SyncEvent, SyncRun, SyncConflict
├── services/
│   ├── guard.py            # Só DEVELOPMENT roda. Sem exceção.
│   ├── triggers.py         # Rede de segurança: captura escrita fora do ORM
│   ├── dirty.py            # Converte a marca da trigger em evento
│   ├── files.py            # Recebe binário em pedaços, com retomada
│   ├── files_publish.py    # Valida, move atomicamente e associa
│   ├── metrics.py          # As métricas do §19.1
│   ├── crypto.py           # Token, hash, checksum e AES-256-GCM
│   ├── protocol.py         # O envelope v1
│   ├── outbox.py           # A captura transacional
│   ├── inbox.py            # Persistir ANTES de confirmar
│   ├── apply.py            # Aplicação idempotente, sem eco
│   ├── adoption.py         # Quando o destino já criou a linha sozinho
│   ├── conflicts.py        # Quem vence, e o que vai para revisão
│   ├── dispatch.py         # Lotes e confirmações
│   ├── bootstrap.py        # A carga total, retomável
│   ├── enrollment.py       # A matrícula (lado nuvem)
│   ├── enrollment_client.py# A matrícula (lado loja)
│   ├── recovery.py         # Ver, trazer de volta, exportar
│   └── transport.py        # O cliente WSS da loja
├── worker.py               # O laço do sync_worker
├── consumers.py            # O consumer WSS da nuvem
└── management/commands/    # sync_worker, sync_enroll, sync_status, …
```

## Subir

- **Loja**: `docker/local/` — ver o README de lá.
- **Nuvem**: o `docker-compose.yml` da raiz, com o bloco de
  `docker/local/.env.cloud.example` somado ao `.env`.

## Primeiro contato: a matrícula

Uma loja recém-instalada tem banco vazio e nenhuma credencial. Copiar token à
mão do Admin para o `.env` é onde segredo vaza por WhatsApp — então o
`sync_worker` faz isso sozinho no primeiro boot:

1. apresenta usuário, senha, `account_id` e um segredo de matrícula;
2. a nuvem autentica (superusuário ou admin **daquela** conta), provisiona o nó
   e devolve o pacote **cifrado com esse segredo**;
3. a nuvem já enfileira a **carga total** para o nó;
4. a loja grava as credenciais em `SYNC_ENROLL_ENV_PATH` e conecta.

O segredo de matrícula **não** é a chave de sincronização. Ele só protege o
pacote que traz a chave definitiva, que nasce na nuvem. Confundir os dois faria
um segredo digitado por uma pessoa virar a chave de todo o tráfego da loja.

Rematricular reaproveita o mesmo nó (mesmo `pair_id`, credencial nova) e
cancela a carga anterior — uma loja que caiu no meio do primeiro bootstrap
recomeça em vez de travar.

## Multi-tenant

`account_id` viaja no envelope só para rastreabilidade. **Quem autoriza é a
conexão autenticada.** Um evento cujo `account_id` ou `target_node_id` não
bate com o da conexão é rejeitado e auditado, nunca aplicado. Cada conexão vive
no grupo `sync.account.{account}.node.{node}`; não existe broadcast global.

## Conflitos

| Domínio | Regra |
|---|---|
| Produtos, preços, usuários, fiscal | Nuvem vence |
| Vendas, pagamentos, caixa, pedidos | Loja vence |
| Estoque, auditoria, leituras | Append-only (imutável) |
| Clientes | Maior versão; empate vai para revisão |
| Impressoras e balanças | Nuvem, menos IP/porta (`local_only_fields`) |
| Notas fiscais | **Sempre** revisão manual |

Dado fiscal e financeiro nunca é resolvido em silêncio por last-write-wins.

### Adoção

Um caso que só aparece rodando: aplicar um `restaurant` da nuvem dispara, na
loja, o signal que cria a Branch espelho — com UUID local. O `branch` da nuvem
chega com o mesmo (restaurante, nome) e outro UUID, e o índice único recusa
**para sempre**.

`services/adoption.py` resolve: a linha local que nasceu de efeito colateral e
nunca foi tocada pela sincronização cede o lugar à identidade da origem. Duas
travas — só adota quem nasceu aqui, e só quando a origem é a autoridade
daquela entidade. Fora disso, vira `SyncConflict` em vez de bater na fila.

## Permissões

Dois códigos no catálogo do projeto (`accounts.permission_catalog`), atribuíveis
a um Perfil de Acesso como qualquer outro:

| Código | O que libera |
|---|---|
| `sync.view` | Ver nós, fila, cargas e conflitos. |
| `sync.manage` | Disparar carga, reprocessar, revogar e rotacionar credencial. |

Superusuário e administrador da conta têm os dois por definição. A API usa
**este** catálogo, não o `has_perm` do Django: um administrador de conta nunca
teria a permissão do Django, e a API respondia 403 para o dono da conta.

O `/admin/` continua usando as permissões do Django — é como o Django admin
funciona.

## Todo model tem decisão

`manage.py sync_check_registry` **falha o deploy** quando aparece um model que
não está nem no `catalog.py` nem no `decisions.py`. Sem isso, a falha aparece
meses depois: alguém cria um model, ninguém nota que ficou de fora, e a loja
opera com um cadastro que a nuvem não conhece.

## Operação

```
python manage.py sync_status                          # nós, fila, parados
python manage.py sync_recover --requeue               # mortos voltam à fila
python manage.py sync_recover --export fila.json      # resgate manual
python manage.py sync_recover --prune-days 30         # só o já confirmado
python manage.py sync_check_registry                  # roda no deploy
python manage.py sync_enroll --env-file /app/sync/credentials.env
python manage.py sync_provision_node --account <uuid> --name "Loja" --cloud-url wss://…
```

Os mesmos botões estão no Django Admin (change form do nó) e na API
`/api/v1/sync/` — nós, eventos, cargas, conflitos, com `start_run`, `requeue`,
`revoke` e `rotate_credentials`.

## Arquivos (§16)

Imagem, XML e PDF **não** viajam dentro do evento. O evento leva os metadados
(nome, tamanho, MIME, SHA-256); o conteúdo vem por HTTPS autenticado por token
de nó, em pedaços de 1 MiB, com retomada por offset.

```
POST /api/v1/sync/files/                 abre ou retoma; devolve o offset
PUT  /api/v1/sync/files/<id>/chunk/      grava um pedaço (corpo binário)
POST /api/v1/sync/files/<id>/complete/   confere e publica
GET  /api/v1/sync/files/<id>/            de onde retomar
GET  /api/v1/sync/files/<id>/download/   baixa a partir de ?offset=
```

Os pedaços se acumulam numa **área temporária** (`media/sync_tmp/`). Só depois
de tamanho e checksum conferirem o arquivo é movido — atomicamente — para o
destino, e só então associado ao registro. Sem esse estágio, uma queda deixaria
um JPEG truncado no lugar da foto do produto, e nada no sistema saberia que
aquilo está pela metade.

Um offset fora de ordem devolve **409 com o offset certo** (no cabeçalho
`X-Sync-Expected-Offset`), para o cliente se realinhar em vez de recomeçar.
Erro de disco ou permissão devolve **503 com o motivo** — não 500 opaco.

## Rede de segurança: escrita fora do ORM (§11.2)

Signals não veem `QuerySet.update`, `bulk_create` nem SQL direto. Uma promoção
aplicada com um `update()` em mil produtos simplesmente não geraria evento, e
ninguém perceberia até a loja vender pelo preço velho.

Triggers no PostgreSQL fecham o buraco. Elas **não** montam o evento — isso
exigiria reescrever a serialização em PL/pgSQL e manter as duas iguais para
sempre. A trigger só anota `(tabela, id, operação)` numa tabela de marcas, e
uma tarefa Python converte a marca em evento com a serialização de sempre.

```
manage.py sync_install_triggers            # idempotente; rode no deploy
manage.py sync_install_triggers --status   # o que existe hoje
```

O compose da loja já roda isso no boot. `manage.py check` avisa quando alguma
tabela sincronizada ficou sem trigger.

O laço é cortado por `app.sync_apply`: durante a aplicação de um evento remoto
a transação marca essa variável e a trigger não anota nada.

## Métricas (§19.1)

```
GET /api/v1/sync/metrics/       # formato de texto do Prometheus
```

Nunca aberta: token de raspagem (`SYNC_METRICS_TOKEN`) ou superusuário. Sem
token configurado, sobra o superusuário.

Os números saem do PostgreSQL, não de contadores em memória — vários processos
respondem o mesmo valor, o que um `prometheus_client` por processo não daria.

## Testes

```
pytest apps/synchronization/                                    # SQLite
pytest --ds=config.settings.test_postgres apps/synchronization/ # PostgreSQL
```

181 testes: cifra e envelope adulterado, isolamento entre contas, token e nó
revogado, idempotência, ordem e dependência faltando, adoção, matrícula,
durabilidade da outbox, lotes e confirmações, carga total, o consumer WSS, o
laço do worker, os comandos de terminal, os botões do Admin, transferência de
arquivo com retomada, métricas e permissões da API.

Oito deles **só rodam no PostgreSQL** (`test_triggers_postgres.py`): a rede de
segurança é PL/pgSQL, e testá-la no SQLite seria testar o `skip`. Para rodá-los:

```
docker run -d --rm --name pg -e POSTGRES_PASSWORD=synctest   -e POSTGRES_USER=starchef -e POSTGRES_DB=starchef_sync   -p 55432:5432 postgres:16-alpine

POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 POSTGRES_PASSWORD=synctest   POSTGRES_DB=starchef_sync POSTGRES_USER=starchef POSTGRES_POOL=False   pytest --ds=config.settings.test_postgres apps/synchronization/
```

Vale a pena: rodar a suíte no PostgreSQL de verdade achou dois defeitos que o
SQLite escondia — um deles derrubaria **toda gravação** em tabela sincronizada.

## Carga

A suíte `sync` do `loadtest/` ataca os **dois** backends ao mesmo tempo:

```
python loadtest/run.py sync --cloud-url http://127.0.0.1:8002 --profile leve
```

Mede a identidade de cada alvo, enche a outbox da loja, acompanha a drenagem,
lê a API de gerenciamento sob carga e ataca a rota de matrícula com credencial
errada. Sem `--cloud-url` ela roda o que cabe num alvo e **diz o que deixou de
medir** — ver `docs/TESTE_CARGA.md`.

## Revisão de arquitetura: o que era real e o que não era

Uma revisão externa levantou 20 pontos. A maior parte deles descreve o
**plano**, não o que foi construído — vale registrar a diferença, porque a
próxima revisão vai levantar os mesmos.

**Três eram defeitos de verdade, e foram corrigidos** (`test_revisao_de_seguranca.py`
prova cada um: os quatro testes falham na versão anterior do código):

1. **Aplicação sem lock de linha.** `apply_event` já fazia domínio e `APPLIED`
   na MESMA transação — isso a revisão errou. O que faltava era o lock: a
   checagem `if status == APPLIED` lia um objeto de fora da transação. E os
   dois caminhos que pedem aplicação (o consumer ao gravar na inbox, o beat a
   cada 15s) pegam o mesmo evento de propósito. Num UPSERT a versão igual
   acabava salvando por acidente; no DELETE não há rede, e a segunda passagem
   apagava o registro que a nuvem tinha acabado de recriar. Agora há
   `SELECT ... FOR UPDATE SKIP LOCKED` com reconferência do estado sob o lock.

2. **A retenção apagava o índice de deduplicação.** `prune` apagava qualquer
   ACKNOWLEDGED, e a deduplicação é a existência da linha de ENTRADA. Basta um
   ACK se perder para a origem deixar o evento em SENT e reenviá-lo na próxima
   reconexão — meses depois, se a loja ficou fora do ar. Agora `prune` só toca
   em OUTBOUND, e `tombstone_inbound` esvazia o payload da entrada mantendo a
   linha. A memória de "já apliquei isto" passou a durar MAIS que o conteúdo,
   que é a ordem correta. De quebra resolve um crescimento sem fim: nada nunca
   apagava um INBOUND, porque ele termina em APPLIED e a retenção só olhava
   ACKNOWLEDGED.

3. **ACK sem endereço.** `apply_ack` casava por `event_id` sem conferir se o
   evento era endereçado a quem estava confirmando. Nunca foi porta aberta (o
   UUID é impossível de adivinhar), mas confirmar é o poder de tirar um evento
   da fila para sempre, e isso não pode depender só do sigilo de um id. O
   consumer agora passa o nó que a conexão autenticou.

**Já estava implementado**, ao contrário do que a revisão supôs: o envelope
inteiro entra como AAD do AES-GCM (`protocol.HEADER_FIELDS`); inbox e domínio
sempre estiveram na mesma transação; o worker da loja é processo próprio, não
uma task Celery infinita (`worker.py`); `entity_type` resolve por registry
fechado, nunca por `apps.get_model()`; cross-tenant é recusado e auditado
(`inbox._validar_escopo`); há teto de eventos e de bytes por lote.

**Não se aplica à topologia atual:** `SKIP LOCKED` na coleta da outbox (o
worker da loja é um só — não há múltiplos consumidores disputando a fila) e
head-of-line blocking por sequência global (um evento que falha vira FAILED com
`next_attempt_at` e sai do filtro; o laço segue para o próximo).

**Também implementado na segunda rodada:**

4. **Segredo aninhado em JSON.** `CAMPOS_PROIBIDOS` olhava o NOME do campo
   Django e parava ali. Um `JSONField` chamado `metadata` — como o de
   `payments.Payment`, que nasce de entrada do PDV — passava no filtro e levava
   o conteúdo inteiro. Agora `serialization._limpar_segredos` varre dicionários
   e listas recursivamente, com teto de profundidade.

5. **Limite de recepção.** O remetente cortava o lote; o destino aceitava o que
   viesse. `inbox._validar_lote` recusa o lote ANTES de gravar qualquer coisa,
   com folga de 4x sobre o lote configurado — é teto de absurdo, não segundo
   corte.

6. **Uma conexão por nó.** Duas conexões com o mesmo `node_id` (uma instalação
   clonada) dividiam a fila entre si, e cada loja ficava com um pedaço do
   banco. O HELLO agora desloca a conexão anterior e registra em ERROR. Deslocar
   e não recusar é deliberado: o caso comum não é clonagem, é reconexão com um
   fantasma do outro lado.

7. **Índices parciais** (`0006`) para as duas consultas do caminho quente. A
   fila viva é uma fatia minúscula da tabela; um índice completo carregaria
   milhões de linhas terminais e seria reescrito a cada evento que termina.

8. **Métricas que faltavam**: `sync_outbox_bytes` e `sync_outbox_events` por
   destino (o que enche disco é byte, não contagem de linha) e
   `sync_inbox_lag_seconds` / `inbox_pending` / `inbox_dead` — a fila de
   entrada falha por motivos diferentes da de saída, e um número só para as
   duas escondia metade dos problemas.

9. **Bilhete de matrícula de uso único** (`manage.py sync_issue_ticket`). O
   `SYNC_ENROLL_SECRET` fixo nunca foi suficiente sozinho para matricular nada
   — a rota também exige usuário, senha e `account_id` —, então a revisão
   exagerou ao chamar o ponto de crítico. Mas ele não expira e não diz quem
   usou. O bilhete nasce para UMA conta, morre ao ser usado ou no prazo, e
   guarda quem emitiu e qual nó saiu dele. É **aditivo**: o segredo combinado
   continua valendo, para adotar loja por loja.

10. **RLS na nuvem** (`manage.py install_rls` + `RLS_ENABLED`). Implementada,
    testada contra PostgreSQL e **desligada por padrão** — ver abaixo.

## RLS: como ligar, e a armadilha que quase todo mundo cai

A política vive em `apps/core/rls.py` e cobre toda tabela com `account` (a
lista é descoberta, não fixa, para uma tabela nova não ficar de fora em
silêncio). Uma consulta que esqueceu o filtro não devolve dado errado: devolve
nada.

A ordem importa:

```
manage.py install_rls --status     # o que falta, e se o usuário do banco serve
manage.py install_rls              # cria as políticas
RLS_ENABLED=true                   # a aplicação passa a se identificar
```

Invertida, o passo 2 sem o 3 faz toda consulta devolver zero linha.

**A armadilha:** `SUPERUSER` e `BYPASSRLS` ignoram qualquer política, e
`FORCE ROW LEVEL SECURITY` **não** os alcança — ele só estende a política ao
dono da tabela. Instalar RLS com o usuário errado responde "48 tabelas
protegidas", pinta o `--status` de verde e não protege absolutamente nada. Foi
o que aconteceu na primeira execução dos testes aqui, e é por isso que
`rls.papel_burla_rls()` existe e grita em vermelho na instalação. **Crie um
usuário de aplicação sem SUPERUSER e sem BYPASSRLS antes de confiar no
relatório.**

Trabalho que legitimamente atravessa contas (o despacho, as métricas, a
retenção) declara isso com `rls.escopo_da_plataforma()` ou o decorador
`@trabalho_de_plataforma`. Num deploy endurecido esse escopo deixaria de ser
variável de sessão e viraria um segundo usuário de banco com `BYPASSRLS` — aí
nem o código da API conseguiria abri-lo. Enquanto for variável de sessão, o
controle é disciplina apoiada por revisão, não impossibilidade.

**Continua fora, por decisão:**

- **mTLS por nó com CA interna.** Mudaria a operação inteira de
  provisionamento, e rende menos do que parece: a chave privada moraria na
  mesma máquina que a credencial de hoje. O ganho real seria revogação mais
  fina e detecção de clonagem — e a detecção de clonagem foi feita (item 6)
  sem trocar o esquema de credencial.
- **Separar `SyncEvent` em outbox/delivery/inbox.** Zero valor de segurança;
  é migração de dados com a sincronização no ar para ganhar ergonomia de
  auditoria e tamanho de índice. Os índices parciais (item 7) resolvem a parte
  que doía.
- **Ordenação por agregado.** Não há head-of-line blocking para resolver: um
  evento que falha vira FAILED com `next_attempt_at` e sai do filtro; o laço
  segue para o próximo.
- **JWT curto para o canal de sincronização.** O canal não usa JWT — a
  identidade é o token do nó, validado no HELLO.
- **Bootstrap com high-water mark.** Já é keyset (`order_by("pk")` +
  `iterator`) com transação por registro; não existe a transação longa que a
  revisão supôs.

## O que ainda não está pronto

- **Homologação com duas instalações reais.** O protocolo foi exercitado ponta
  a ponta com dois bancos PostgreSQL separados e o compose da loja no ar, mas
  nunca com uma loja e uma nuvem em máquinas diferentes, atravessando internet
  de verdade. A reconexão sob perda de pacote é o que falta observar.
- **Rotação de chave em operação** (`KEY_ROTATION_REQUIRED`). A mensagem existe
  no protocolo e `rotate_credentials` funciona, mas a troca ainda exige o nó
  reconectar — não há renegociação com a conexão de pé.
- **Alertas** (§19.3). As métricas expõem tudo o que os alertas precisam; as
  regras do Alertmanager em si não estão escritas.
