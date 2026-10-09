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
íntegros, esperando `sync_recover --requeue`. **Menos a falta de registro-pai**
("aponta para X, que ainda não existe aqui"): esse evento espera o pai por até
3 dias (`retry.JANELA_DA_DEPENDENCIA`), e é retentado NA HORA sempre que chega
dado novo (`retry.acordar_quem_espera_dependencia`). Antes ele morria em cerca
de uma hora e o dado nunca chegava, nem quando o pai aparecia depois.

## Estrutura

```
backend/apps/synchronization/
├── catalog.py              # Os models que sincronizam, e como
├── catalog_clone.py        # Estoque detalhado, nota de entrada e patrimônio
├── decisions.py            # Os que NÃO sincronizam (só técnicos), e por quê
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

Quando uma loja precisa das credenciais fiscais, o canal cifrado usa o A1
canônico de `FiscalConfig.certificate_file` e sua `certificate_password`. Esse
é o mesmo certificado usado pela consulta direta à SEFAZ e pela Focus NFe; não
há mais uma segunda cópia específica do provedor. Arquivo e senha continuam
fora dos eventos comuns do catálogo e só passam nesse envelope temporário.

## Multi-tenant

`account_id` viaja no envelope só para rastreabilidade. **Quem autoriza é a
conexão autenticada.** Um evento cujo `account_id` ou `target_node_id` não
bate com o da conexão é rejeitado e auditado, nunca aplicado. Cada conexão vive
no grupo `sync.account.{account}.node.{node}`; não existe broadcast global.

## A loja é um clone: tudo nos dois sentidos

Não existe mais entidade de mão única. O terminal alterna entre a loja e a
nuvem quando a loja oscila, e o que ele gravou em qualquer um dos dois precisa
chegar ao outro. Fica fora só o que é técnico de cada instalação — sessão,
token, filas e cursores da própria sincronização, o coletor da SEFAZ, a
credencial de emissor (canal próprio, cifrado) — e o que é da plataforma e não
pertence a uma conta (plano, assinatura). `decisions.py` diz o motivo de cada um.

## Conflitos: vence a versão mais nova

Uma regra só, para toda entidade e nos dois sentidos:

> **A versão é o `updated_at` de ORIGEM, em microssegundos. A mais nova entra;
> a mais antiga não muda nada** (`services/conflicts.py`).

Exemplo: a nuvem edita o pedido às 10:00:03 e a loja às 10:00:05. Não importa a
ordem em que os eventos chegam — os dois lados terminam com a de 10:00:05.

Ela substituiu a política por dono ("loja vence", "nuvem vence"), que recusava
a versão mais nova do outro lado e abria conflito. Com o terminal alternando, o
mesmo pedido era editado nos dois servidores com segundos de diferença: cada
edição virava conflito e a loja ficava com o total antigo. A política do
catálogo continua existindo, mas só para a **adoção** (abaixo).

O que sustenta a regra:

- **A aplicação guarda o horário de origem** (`timestamps.py`), também na
  atualização. Antes o `save()` dava à linha o horário "agora", e uma edição
  da nuvem feita às 10:00:03 que chegasse depois de a de 10:00:00 ter sido
  aplicada às 10:00:05 parecia mais velha e era descartada.
- **A exclusão também obedece.** O DELETE carrega o MOMENTO da exclusão como
  versão; um DELETE mais velho que a última edição daqui não apaga, e uma
  versão mais velha que a exclusão não ressuscita a linha (a "lápide" é o
  próprio evento DELETE — `apply._apagada_depois`).
- **O esqueleto.** A linha local que nunca entrou na sincronização (nenhum
  evento de saída, nenhum de entrada aplicado) aceita a versão do outro lado
  mesmo "mais velha" — é a conta criada na matrícula. O fiscal nunca é
  esqueleto.
- **Campos que só a nuvem decide** (`cloud_owned_fields`). A revogação do
  terminal é do painel; a conexão que a loja manda o tempo todo, com
  `is_active=True`, não a desfaz.
- **O relógio.** Com "vence o mais novo", o relógio de quem grava decide. O
  aperto de mão mede o relógio da loja contra o da nuvem; acima de 2 s o worker
  registra erro no log e o desvio aparece em `estado_da_fila`
  (`services/relogio.py`). **Acerte a hora do servidor da loja (NTP).**
- `MANUAL` continua indo para revisão de gente; hoje nenhuma entrada usa.

A NOTA FISCAL entra na mesma regra e desce também: o pagamento feito na nuvem
com a loja fora dispara a NFC-e lá, e de mão única a loja via o pedido pago e
sem nota — e o operador emitia a segunda. O número não colide: quem numera é o
provedor, com um contador só.

A NOTA DE ENTRADA (SEFAZ) é baixada só pela nuvem quando há sincronização
(`inbound_nfe/services/sefaz_na_nuvem.py`): com os dois consultando, a mesma
nota nasceria duas vezes, com ids diferentes. Na loja sincronizada, consulta e
manifestação respondem "faça no painel da nuvem".

A CHAVE DE IDEMPOTÊNCIA atravessa os nós com id DERIVADO de (conta, chave)
(`core.IdempotencyRecord`, migração `core/0002`): a mesma operação tem o mesmo
id na loja e na nuvem. O id era inteiro sequencial e o catálogo dizia
`flow="bidirectional"`, um valor que nenhum portão conhecia — ela nunca
sincronizou.

O pedido que ficou com total zerado por um conflito antigo se conserta com
`manage.py repair_order_totals --order <id> --apply`, na loja.

## O que a simulação do dia a dia achou

`loadtest/dia_a_dia` (ver `docs/TESTE_CARGA.md` §3.9) roda um salão inteiro
contra o par nuvem + loja derrubando a rede no meio. Cada defeito abaixo tem
teste que falha sem a correção.

| Defeito | Efeito no salão | Correção |
|---|---|---|
| O número do evento vinha de um `UPDATE` na linha do nó, travada até o fim da transação | `deadlock detected` com 3 caixas e 5 garçons: 500 ao abrir o caixa | SEQUENCE do PostgreSQL (`services/sequencia_pg.py`, migração `0011`) |
| O signal engolia a falha da captura dentro de um savepoint | o item da comanda gravado SEM evento; nunca chegava à nuvem | a rede de segurança agora pega (abaixo) |
| A rede de segurança encerrava a marca em qualquer erro, até deadlock | a última chance do dado se perdia | erro passageiro (`OperationalError`) fica para a próxima passada |
| "Coberto" = existe evento criado depois da marca, e a marca leva o início da transação | o status de cozinha (`QuerySet.update`) nunca viajava | coberto = evento com versão ≥ a da linha (`dirty._ja_tem_evento`) |
| Usuário gravado antes do perfil não tinha conta: evento descartado | garçom cadastrado na nuvem não entrava na loja | o perfil registra o usuário antes dele (`signals._usuario_antes_do_perfil`) |
| Leitura de balança `immutable` | na nuvem nenhuma leitura tinha o item da comanda | deixou de ser append-only |
| "Rodada 2" da mesma comanda criada nos dois lados | 205 conflitos; itens, pedido e estoque travados atrás | id menor fica com o número (`services/renumeracao.py`, `renumber_on_collision`) |
| O "apliquei" só saía para o que entrava na chegada do lote | eventos RECEIVED para sempre na origem | varredura periódica (`services/confirmacao.py`) |
| A loja não reenviava o SENT na reconexão | o que saiu no instante da queda esperava 5 min | `worker_steps.ao_reconectar` |
| O pagamento preferia a chave do cabeçalho (muda a cada chamada) à do corpo | repetir o recebimento cobrava duas vezes | a chave do corpo primeiro (`orders/views.py`) |
| Duas chamadas com a mesma chave ao mesmo tempo: o middleware ignorava o erro | as duas gravações ficavam | desfaz a segunda e devolve a resposta da primeira (`core/idempotency.py`) |
| Escrita com tempo esgotado ia direto para o operador | o gesto repetido com chave nova duplicava o item | os dois PDVs repetem UMA vez com a mesma chave |
| Pedido aberto na nuvem, terminal de volta à loja antes do sync | "404 pedido não encontrado" no recebimento | `afinidade_com_a_nuvem.dart` nos dois PDVs |
| Mudar só o vínculo (`operators.set`) não salva o pai: sem evento | os três caixas recusados na loja ("operador não vinculado") | `m2m_changed` dos vínculos declarados gera o evento do pai, com a versão adiantada |
| Operador repete o gesto depois do Wi-Fi cair: chave nova | quando a rede volta, as duas tentativas gravam (item e pesagem em dobro) | repetição IDÊNTICA em até 2 min reaproveita a chave (`chaves_de_repeticao.dart`) |
| O "apliquei" perdido na rede: a origem não reenviava o RECEIVED e o destino não confirmava de novo | 172 eventos presos na loja depois das quedas | a origem reenvia o RECEIVED antigo (`reconcile_nodes`) e o destino volta a confirmar o que já aplicou (`inbox._gravar`) |
| Três caixas pagando juntos, pedido sem filial: três locais "Principal" (filial NULA escapa da trava única) | `MultipleObjectsReturned` e TODO recebimento seguinte com 500 | o mais antigo vale, e a criação é serializada (`stock/services/order_stock._default_location`) |
| A mesma comanda fechada na loja e, um minuto depois, na nuvem (caixa ainda na janela do veredito) | o cartão cobrado DUAS vezes (R$ 495,17 e R$ 505,17) | fechar comanda o PDV tenta SEMPRE na loja primeiro; com a loja no ar (pulso do sync < 60 s) a nuvem recusa com 409 `cobrar_na_loja` só o pedido que veio direto pela janela do veredito (`X-Desvio-Da-Loja: janela`), e o PDV volta para a loja. Terminal configurado na nuvem, ou que acabou de ver a loja falhar, cobra na nuvem — a v3.0.86 recusava todos e a comanda não fechava em lugar nenhum (`loja_no_ar.py`, `CobrarNaLoja`) |
| Atualização que leva a rodada a um número ocupado | retentativa eterna | a mesma renumeração da inserção (`renumeracao.resolver_atualizacao`) |
| Loja de pé e sem internet: cobrou o cartão; um caixa ainda na janela da nuvem cobrou de novo (a nuvem não via o pulso da loja) | R$ 1.495,07 cobrados em dobro em 10 min de caos | fechar comanda tenta a loja ANTES, mesmo na janela (`CloudFallback.irDiretoParaANuvem`) |
| A adoção apagava os itens do pedido de um lado para dar lugar aos do outro | pedido pago sem item: o dinheiro em dobro sumia da vista | dinheiro (pedido, item, pagamento, caixa) nunca é adotado: vira conflito aberto para estorno (`adoption.ENTIDADES_DE_DINHEIRO`) |

## O lote viaja comprimido

O payload sai cifrado (AES-GCM) e dado cifrado não comprime — nem pela
compressão do WebSocket. Agora o JSON é comprimido com zlib ANTES de cifrar
(`compression: "zlib"` no envelope), o que reduz o lote várias vezes.

Loja e nuvem atualizam em momentos diferentes, então cada lado só comprime
quando o outro anunciou `"capabilities": ["zlib"]` no aperto de mão (HELLO da
loja, AUTHENTICATED da nuvem). Quem não anuncia recebe sem compressão, como
antes.

### Adoção

Um caso que só aparece rodando: aplicar um `restaurant` da nuvem dispara, na
loja, o signal que cria a Branch espelho — com UUID local. O `branch` da nuvem
chega com o mesmo (restaurante, nome) e outro UUID, e o índice único recusa
**para sempre**.

`services/adoption.py` resolve: a linha local que nasceu de efeito colateral e
nunca foi tocada pela sincronização cede o lugar à identidade da origem. Duas
travas — só adota quem nasceu aqui, e só quando a origem é a autoridade
daquela entidade pela política do catálogo (é para isso que ela ainda existe).
Fora disso, vira `SyncConflict` em vez de bater na fila. Nota fiscal nunca é
adotada.

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

### O que a carga com RLS ligada encontrou

O alvo de carga com a política de pé (`loadtest/scripts/rls_target.sh`) achou
duas coisas que nenhum teste unitário acharia:

**1. O login quebrava.** É o ovo-e-galinha do RLS: a consulta que DESCOBRE a
conta não pode estar filtrada por conta. `accounts_userprofile` está protegida,
a sessão ainda não tem conta, a leitura volta vazia e o sistema responde
"usuário sem conta vinculada" — culpando um cadastro que está perfeito.
Corrigido com `rls.descobrindo_o_tenant()` no login e no middleware, e o login
passou a FIXAR a conta assim que a descobre, para o resto da resposta rodar
escopado em vez de manter a rota mais exposta do sistema lendo sem filtro.

**2. ~1 escrita em 500 falha, e isso ainda não tem correção.** A variável de
conta mora na CONEXÃO. Sem `ATOMIC_REQUESTS`, a requisição não é uma transação,
e com o pool nativo somado ao ASGI não há garantia de que a escrita use a mesma
conexão em que a variável foi gravada. Quando escapa, o `WITH CHECK` recusa com
500. Falha FECHADA — recusa, não vaza —, mas **RLS não está pronta para
produção enquanto isto não for resolvido**. Os dois caminhos conhecidos estão
em `apps/core/rls.py`.

Fora isso, a carga com RLS passou inteira: backend, desktop, mobile e sync, com
todas as verificações de coerência verdes.

**O custo, medido no mesmo perfil e na mesma máquina** (perfil `medio`, alvo de
produção local, execuções sequenciais):

| | sem RLS | com RLS |
| --- | --- | --- |
| vazão | 40,5 req/s | 30,2 req/s |
| p50 | 946 ms | 1209 ms |
| p95 | 2441 ms | 3109 ms |
| 5xx | **0** | 1 (o do `WITH CHECK` acima) |

Uns 25% de vazão. O número é indicativo, não preciso — as duas execuções
dividiram a máquina com o resto do ambiente —, mas a ordem de grandeza é essa,
e o zero na linha dos 5xx sem RLS é o que torna o 500 atribuível à política e
não a um endpoint instável.

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

## Vínculos ManyToMany, e o reparo que o deploy NÃO faz sozinho

Um M2M não gera evento próprio: ele viaja dentro do payload do pai, e só se
estiver declarado em `m2m_fields` com a chave natural. Nove estavam sem
decisão — entre eles `CashStation.operators`, cujo efeito era a loja não
conseguir abrir caixa com o caixa e o operador ambos visíveis na tela.

`manage.py sync_check_registry` agora reprova M2M nem declarado nem excluído.
Ele roda no deploy, e é a trava para isto não voltar: um M2M é invisível para
a checagem de model porque a tabela de ligação nunca aparece em
`get_models()`.

**A chave natural importa.** `operators` casa por `username`, não por `id`: o
id do usuário é inteiro sequencial e os dois bancos numeram independentemente
— casar por ele ligaria o caixa à pessoa errada, e ninguém descobriria
olhando a tela, porque haveria um nome ali.

**Mudar o vínculo agora gera evento sozinho** (`signals.capturar_vinculo`):
`.set()`/`.add()`/`.remove()` não salvam o pai, e antes disso o vínculo novo
nunca saía. **Os vínculos que já estavam errados antes da correção NÃO se
consertam sozinhos.** Nada dispara reenvio: os registros já existem dos dois lados e
nenhum deles mudou. Para cada loja, use **"Sincronizar tudo"** no Admin da
nuvem (ou toque nos registros de origem) para regenerar a fila. Conferir
depois, no banco da loja:

```
select s.name, u.username
  from payments_cashstation s
  left join payments_cashstation_operators o on o.cashstation_id = s.id
  left join auth_user u on u.id = o.user_id;
```

Coluna `username` nula é caixa sem operador — e caixa sem operador não abre.

## O que ainda não está pronto

- **O sentido LOJA → NUVEM nunca rodou de verdade.** Medido no par real em
  2026-09-19: a loja tem **1244 eventos de ENTRADA, todos APPLIED** — zero
  falha, zero pendente, zero descartado. O caminho nuvem → loja está provado
  atravessando internet de verdade, e este parágrafo dizia o contrário até
  alguém medir.

  A fila de SAÍDA, porém, está em **zero**: nenhuma venda foi feita nesse nó
  ainda. Então tudo que sobe — venda, pagamento, movimento de caixa, documento
  fiscal — vai estrear em produção. É o maior risco aberto, e o jeito de
  fechá-lo é uma venda de verdade na loja antes de abrir para o movimento.
- **Reconexão sob perda de pacote.** O worker reconecta com backoff e a outbox
  é durável, mas a queda no meio de um lote nunca foi observada num link ruim
  de verdade.
- **Rotação de chave em operação** (`KEY_ROTATION_REQUIRED`). A mensagem existe
  no protocolo e `rotate_credentials` funciona, mas a troca ainda exige o nó
  reconectar — não há renegociação com a conexão de pé.
- **Alertas** (§19.3). As métricas expõem tudo o que os alertas precisam; as
  regras do Alertmanager em si não estão escritas.
