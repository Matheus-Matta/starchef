# StarChef PDV Desktop — documentação técnica do aplicativo Flutter

Este documento descreve **como o aplicativo Flutter é construído por dentro**:
cada camada, cada arquivo relevante, as decisões que moldaram o desenho e as
armadilhas que motivaram cada uma delas.

Ele é complementar a [`PDV_OFFLINE_SCALE_ARCHITECTURE.md`](PDV_OFFLINE_SCALE_ARCHITECTURE.md),
que descreve o comportamento operacional e o runbook. Quando os dois divergirem,
o código é a verdade — abra um PR corrigindo o documento.

---

## 1. Stack e decisões estruturantes

| Assunto | Escolha | Por quê |
| --- | --- | --- |
| UI | Flutter Desktop (Windows e Linux) | requisito do produto |
| Estado | `ChangeNotifier` + `setState`, sem pacote de DI | o app já nasceu assim; trocar por BLoC seria reescrita sem ganho funcional |
| Banco local | `sqlite_async` | mantém I/O fora do isolate de UI, habilita WAL e coordena múltiplos processos no mesmo arquivo |
| Segredos | cofre do SO + fallback Linux `0700`/`0600` | mantém o cofre nativo e sobrevive a Secret Service ausente/bloqueado no Ubuntu |
| Serial | `flutter_libserialport` | mesma biblioteca para balança, leitor e impressora serial, nos dois sistemas |
| Janelas | processo por janela (`Process.start`) | isolamento real de foco, hardware e falha |
| HTTP | `http` + camada própria de fila | não há dependência de framework de sync |

### Por que não há injeção de dependência formal

As dependências descem por construtor: `main` cria `ApiClient`, `AuthRepository`,
`LocalPreferences` e `ErrorCenter`, e passa adiante. Duas exceções usam
`InheritedWidget` porque precisam ser alcançáveis de qualquer profundidade:
`ErrorCenterScope` (alertas globais) e o `Theme` do Flutter.

Isso mantém o grafo de dependências visível no `main.dart` e testável sem
container.

---

## 2. Mapa de diretórios

```text
lib/
├── main.dart                  # composition root; decide PDV ou Balança Rápida
├── app/
│   ├── starchef_app.dart      # MaterialApp do PDV (tema, atalhos, erros)
│   └── scale_window_app.dart  # MaterialApp da janela de balança
├── core/                      # sem dependência de features
│   ├── config/                # .env, base URL, URL de WebSocket
│   ├── errors/                # modelo de erro, fila e overlay
│   ├── formatters/            # conversões tolerantes da API
│   ├── hardware/              # balança, travas de periférico
│   ├── logging/               # log estruturado em arquivo
│   ├── network/               # ApiClient, outbox, relay
│   ├── security/              # verificação offline da senha do caixa
│   ├── storage/               # caminhos, preferências, cofre da sessão
│   ├── theme/                 # tokens e ThemeData
│   └── widgets/               # componentes reutilizáveis
└── features/
    ├── auth/                  # login, sessão, refresh
    ├── cash/                  # senha e autorização de caixa
    ├── devices/               # impressoras, balanças, agente de impressão
    ├── home/                  # PDV: catálogo, carrinho, caixa, navegação
    ├── orders/                # listagem e painéis de pedido
    ├── scale/                 # Balança Rápida
    ├── settings/              # preferências do terminal
    ├── sync/                  # revisão da fila offline
    └── topology/              # Caixa Principal / Caixa Cliente
```

Cada feature segue `data/` (acesso), `domain/` (regra pura) e `presentation/`
(widgets). Nem toda feature tem as três: quando não há regra própria, não se
cria uma camada vazia só por simetria.

**Regra de dependência:** `core` nunca importa `features`. `features` importam
`core` e, excepcionalmente, o `domain` de outra feature — como a página da
balança importando `devices/domain/printer_endpoint.dart`.

---

## 3. Bootstrap — `main.dart`

Ordem de inicialização e o motivo de cada passo:

1. `AppConfig.load()` — resolve a URL da API por `--dart-define`, `.env` ou
   fallback local. Procura o `.env` subindo diretórios a partir do executável e
   do diretório atual, o que faz o binário compilado achar o arquivo do projeto.
2. `ScaleWindowLauncher.isScaleWindow(args)` — decide qual dos dois aplicativos
   subir, olhando o argumento `--scale-workstation`.
3. `LocalPreferences.load()` — precisa acontecer **antes** do `runApp`, senão a
   primeira renderização usaria o tema claro e piscaria ao trocar.
4. `windowManager` — tamanho e título dependem do modo.
5. `FlutterError.onError` — erros fora de handler explícito vão para o log; a
   exigência de "nenhuma perda silenciosa" vale também para bugs de UI.
6. `runApp` com `StarChefApp` ou `ScaleWindowApp`.

O token **nunca** vai na linha de comando. A janela de balança restaura a sessão
do cofre do sistema e, no Linux, recebe também uma transferência efêmera em
arquivo `0600`, porque uma segunda instância pode não reler o GNOME Keyring a
tempo. O argumento `--session-handoff=<nome-aleatório>` revela somente o nome;
o arquivo é consumido e apagado no boot. O restaurante continua em
`--restaurant=<uuid>`.

---

## 4. Camada `core`

### 4.1 `core/network/api_client.dart`

O arquivo mais denso do projeto. Ele é, ao mesmo tempo, cliente HTTP, cache de
leitura, outbox transacional e motor de sincronização.

**Fluxo de uma requisição** (`_request`):

```text
                    ┌── é mutação com ID temporário do principal? ──► relay obrigatório
                    │
_request ───────────┼── modo cliente e mutação enfileirável? ──► tenta o principal primeiro
                    │
                    └── _requestWithSessionRecovery ──► _requestOnline
                              │                              │
                              │ 401 ──► refresh ──► repete   │ falha de rede
                              │                              ▼
                              │                    GET  ──► cache local
                              │                    POST ──► outbox (se elegível)
                              ▼
                        sucesso ──► cacheia GET, agenda flush
```

**Renovação de token.** Um 401 dispara `_refreshAccessToken`, que é *single
flight*: várias requisições paralelas recebendo 401 compartilham a mesma
renovação. Sem isso, cada uma tentaria rotacionar o refresh token e todas menos
a primeira seriam recusadas. O retry reusa a **mesma** `Idempotency-Key` da
tentativa original — se o servidor já tinha gravado a escrita antes de recusar
por token vencido, a segunda chamada é reconhecida como repetição.

Rotas sob `/auth/` nunca entram nesse caminho: um 401 ali significa credencial
inválida, e insistir criaria laço.

**Cabeçalho de identidade e ASCII.** Toda requisição leva `X-Terminal-Id` (o
`nodeId` da topologia) e `X-Terminal-Name`. Cabeçalho HTTP **não carrega
UTF-8**: `dart:io` recusa qualquer byte acima de 127 com `FormatException`, e o
rótulo padrão do secundário — "Caixa Secundário …" — tem acento. O estouro
acontecia antes de a requisição sair da máquina e caía no `catch` genérico,
virando uma mensagem que acusava o endereço do servidor.

Como o rótulo só é preenchido depois do login (`_onTopologyChanged`) e
`clearSession()` não limpa a identidade da INSTALAÇÃO — ela é da máquina, não
da sessão —, o sintoma aparecia como "logout, e o login seguinte falha
dizendo que a API não pode ser montada"; reiniciar o app "resolvia" só porque
zerava o campo em memória. `_headerSafe` percent-encoda o valor quando ele tem
acento e o backend desfaz (`terminal_name_from_request`), então o nome chega
inteiro ao cadastro do terminal. Texto já ASCII atravessa igual.

**Contrato de status para credenciais.** O `TenantMiddleware` do backend roda
antes do DRF e decide:

| Situação | Status | Quem trata |
| --- | --- | --- |
| credencial apresentada e recusada (token expirado ou malformado) | **401** | o cliente renova o token e repete |
| autenticado, mas sem conta vinculada | **403** | o operador precisa de configuração/permissão |
| sem credencial nenhuma | **403** | fluxo de login |

Essa distinção é o que faz a renovação automática funcionar. Enquanto o
middleware devolvia 403 para token expirado, a renovação — que dispara em 401 —
nunca acontecia, e o operador via "Permissão insuficiente: solicite a permissão
ao responsável" quando na verdade sua sessão apenas tinha vencido.

**Emissão fiscal não configurada.** `POST /invoices/emit/` pode responder HTTP
200 com `{"emitted": false, "message": "..."}` quando o provedor da conta não
está pronto. O PDV não tenta imprimir nesse caso; no acionamento manual mostra a
mensagem e, na tentativa automática após o pagamento, permanece silencioso.

**Escopo.** Cache e outbox são namespaced por
`autoridade-da-URL | account_id|user_id|sub do JWT`. Isso impede que a sessão de
uma conta consuma a fila de outra no mesmo terminal. Sem essas claims o escopo
cai em `authenticated`, e o isolamento por conta se perde — está listado como
limitação conhecida.

**O que pode ser cacheado.** Restaurantes, cardápio, estações, mesas, clientes,
formas de pagamento, impressoras, balanças e, desde a última revisão,
`/cash-register/current/`. Rotas físicas ou transacionais (`checkout-command`,
trabalhos de impressão, leituras) nunca servem do cache.

**O que pode entrar na outbox.** Criar/alterar cliente, criar pedido, abrir
pedido por mesa, incluir item, cancelar item, **fechar o pedido, enviar para a
cozinha e registrar pagamento**.

As três últimas só se tornaram seguras depois que o backend passou a deduplicar
por `Idempotency-Key` (`apps/core/idempotency.py`). Antes delas, um reenvio da
fila podia cobrar duas vezes; hoje a repetição devolve a resposta original sem
executar nada. Abertura e fechamento de **caixa** continuam exigindo servidor,
porque envolvem conferência de valores que o terminal não tem como resolver.

**A impressão nunca entra na fila.** Um cupom não pode "sair mais tarde": ou
imprime agora, ou o operador precisa saber que não saiu.

**Erros de conectividade são marcados.** `ApiException.isConnectivity`
distingue "o servidor recusou" de "não deu para falar com o servidor". A
interface agrupa o segundo caso em um aviso único (`dedupeKey: 'connectivity'`)
que some sozinho quando a conexão volta — sem isso, cada chamada offline
empilhava um cartão e enterrava a tela.

**Ciclo de sincronização** (`_flushPending`):

1. Se há trabalho e o estado não é "conectado", faz `ping()` no `/health/`
   antes de tocar na fila. Sem esse gate, um ciclo com a rede caída gastaria o
   `attempt_count` de cada operação e levaria o backoff ao teto sem chance real
   de entrega.
2. Reivindica uma operação por vez com lease (`claimNext`). A varredura respeita
   a ordem de criação, mas **pula** o que não pode rodar agora (bloqueado, em
   backoff ou com lease de outra janela): antes, uma única operação travada na
   frente segurava a fila inteira, inclusive operações sem nenhuma relação com
   ela. A ordem causal continua garantida pelo dado, não pela posição — quem
   ainda cita um ID temporário (`offline-…`) não mapeado espera a sua vez, para
   não enviar um item antes de o pedido que o contém existir no servidor.
3. Envia no máximo 20 por ciclo, uma requisição por vez.
4. Sucesso: mapeia ID temporário → real e remove da fila.
5. Falha temporária (408/425/429/5xx, socket, timeout): `retry` com backoff
   exponencial de 2 s a 2 min, respeitando `Retry-After`.
6. Falha definitiva: `blocked`, que exige decisão humana.

**Estados publicados** para o badge: `unknown`, `online`, `offline`, `syncing`,
`degraded`, `blocked`.

### 4.2 `core/network/offline_store.dart`

SQLite com quatro tabelas:

> **Cache de respostas ≠ banco de domínio.** As tabelas abaixo guardam
> respostas HTTP. Isso basta para *ler* offline, mas não para *editar*: os
> pedidos têm um store próprio, descrito em 4.2-b.

| Tabela | Papel |
| --- | --- |
| `offline_cache` | respostas GET elegíveis, limitadas às 300 mais recentes |
| `offline_outbox` | mutações locais, estado, tentativas, próxima tentativa, lease |
| `offline_id_map` | de ID temporário (`offline-…`) para o ID real do servidor |
| `offline_meta` | controle de migração e importação do formato legado |

Migrations por versão (`SqliteMigrations`), hoje na versão 2 — a 2 acrescentou
as colunas de lease.

Operações de revisão adicionadas para a tela de dead-letter:

- `unblock(queueId)` — devolve um item `blocked` para `pending`, zerando
  tentativas e erro, **mantendo a chave de idempotência**.
- `discardBlocked(queueId)` — apaga definitivamente, e **só** se o item ainda
  estiver `blocked`. Um item elegível pode estar sendo enviado neste instante;
  apagá-lo perderia a venda em silêncio.

### 4.2-b `features/orders/data/local_order_store.dart`

O cache do `ApiClient` guarda respostas; este store guarda **o pedido**. A
diferença aparece na edição offline: incluir um item alterava só a memória da
tela, e ao sair e voltar a releitura pegava a resposta antiga — que não conhece
o item. A edição parecia perdida.

Tabela `local_orders(scope, order_id, payload, updated_at, has_local_changes)`,
com o mesmo `scope` do cache e da fila (`ApiClient.sessionScope`), de modo que
duas contas no mesmo terminal nunca se enxerguem.

O que ele resolve, e que o cache não resolvia:

- **A edição persiste.** `addItem`, `voidItem` e `patch` gravam no disco e
  recalculam subtotal e total a partir dos itens ativos. Taxa de serviço,
  entrega e desconto vêm do servidor e são preservados — o terminal não tem
  como recalcular a regra de serviço nem uma promoção aplicada lá.
- **O servidor não apaga o que está na fila.** `saveFromServer` preserva os
  itens com id `offline-…` que a resposta ainda não contém. Sem isso, o item
  lançado offline sumiria da tela até a fila esvaziar, dando ao operador a
  impressão de que o lançamento se perdeu.
- **Sem duplicata depois do sync.** `replaceId` troca o id temporário pelo real
  quando a fila confirma, então a resposta seguinte reconhece o item como o
  mesmo em vez de somar um segundo.
- **Total nunca negativo**, mesmo com desconto maior que o subtotal.

Retenção: 200 pedidos por escopo, e pedidos com alterações locais pendentes
nunca são descartados pela limpeza.

### 4.3 `core/network/mutation_relay.dart` e `features/topology/`

**Só existem dois papéis: Caixa Principal e Caixa Cliente.** O modo
"independente" foi removido — enquanto ele existia, dois terminais podiam
sincronizar cada um por conta própria com a nuvem, que é a raiz da divergência.
Um restaurante de um caixa só tem esse caixa como principal; configurações
antigas em `standalone` migram para `principal` na leitura
(`LocalTopologyConfig.modeFrom`).

**Instalação nova nasce secundária, sem principal definido.** Ser o principal é
decisão da loja, não acidente da instalação: se todo terminal novo subisse como
principal, o segundo caixa instalado viraria um segundo principal sincronizando
por conta própria com a nuvem — a divergência que a topologia existe para
impedir. O terminal fica bloqueado para escrita até alguém definir o papel, com
uma mensagem que diz exatamente isso.

**Um secundário mal configurado continua bloqueado, não vira caixa solto.**
`_apply` anexa o relay mesmo quando a configuração é inválida. Sem isso o
`ApiClient` não veria relay nenhum, trataria o terminal como principal e
mandaria vendas direto para a nuvem — justamente o que se quer evitar.

A chave de pareamento e `trusted_network = 1` já vêm prontas na instalação, para
que promover a principal seja um clique. Abrir a porta não é descuido: ela só
aceita requisições assinadas com a chave, vindas da rede local, com nonce contra
repetição e corpo limitado a 256 KB. Uma chave gerada sozinha é estritamente
melhor que nenhuma — sem ela o principal não atenderia ninguém, e pedir ao
operador para clicar em "gerar" não acrescenta segurança.

Instalações antigas em `standalone` são promovidas a principal ativo pela
migração de schema 2 — naquele modo os campos de rede nem apareciam na tela,
então `trusted_network = 0` ali significa "nunca configurado", não "o operador
desligou". Elas já vendiam sozinhas; virar secundárias bloquearia o balcão.

Um principal com o compartilhamento desligado **não é um erro**: ele opera e
sincroniza com a nuvem normalmente, apenas sem servir a LAN
(`LocalTopologyPhase.principalLocalOnly`). Por isso `validate()` e
`lanSharingErrors()` são separados — o segundo nunca impede o terminal de
vender.

**As leituras também passam pelo principal.** `POST /v1/read` é a contraparte
do `/v1/relay`, com a mesma assinatura HMAC e uma allowlist própria de rotas.
O principal responde do próprio `ApiClient` — fresco se ele tiver rede, do
cache dele se não tiver. Antes, só as escritas iam pelo principal e as leituras
iam direto para a nuvem: com a internet fora e a LAN de pé — a falha mais
comum — o secundário conseguia gravar num pedido que não conseguia abrir.

A ordem de preferência de uma leitura no secundário é: principal → nuvem →
cache local. Uma recusa do servidor (`ApiException`) não é repetida pela nuvem,
porque o principal já falou com ele e o resultado seria o mesmo.

**Escrita é diferente de leitura: o secundário não grava sem o principal.**
Com o principal fora, a operação é recusada na hora — nem pela nuvem, nem na
fila local, nem para esvaziar uma fila antiga. Gravar por fora deixaria o
principal sem saber de uma venda que os outros caixas leem dele, e o problema
só apareceria depois, como pedido divergente ou cobrança repetida. Ler é
liberado porque ler não diverge; o cache local continua servindo a tela.

A regra é implementada por presença do relay: `_mutationRelay != null` só
acontece em modo cliente, e é o que separa "sou secundário" de "sou principal e
uso minha própria fila".

**O ritmo do teste de conexão é assimétrico.** `probeInterval` devolve 15 s com
o principal respondendo e 3 s quando ele está fora. Com a ligação de pé nada
urgente depende do teste periódico — uma queda entre dois deles é pega na hora
da gravação, pelo teste sob demanda (`_healthFreshness`, 5 s). Com o principal
fora o operador está impedido de lançar e esperando, e aí cada segundo é caixa
parado. O timer se reagenda a cada rodada, então a queda acelera o ritmo e a
recuperação o desacelera sozinha.

Como isso muda o que o operador pode fazer, um `PdvPrincipalBadge` fica sempre
visível no cabeçalho dos secundários — verde quando o principal responde,
vermelho quando não. Mostrar isso só no erro faria o operador montar um pedido
inteiro para descobrir no fim que não dava para lançar. Em cabeçalho estreito
ele encolhe para o ícone e o texto vai para o tooltip; há teste de overflow,
porque o cabeçalho do PDV já estourou antes por um widget a mais.

O modo Caixa Cliente entrega mutações ao Caixa Principal pela LAN, com HMAC
SHA-256 sobre método, rota, timestamp, nonce, conta, operador, restaurante e
corpo. O principal valida a assinatura, consome o nonce (anti-replay), serializa
as entregas e guarda um recibo por `operation_id` + hash do pedido.

**A lista de operações vive em `core/network/offline_mutations.dart`**, e não em
cada lado. Ela já divergiu uma vez: a fila do `ApiClient` passou a aceitar
fechamento e pagamento, o relay continuou recusando, e essas operações iam do
Caixa Cliente direto para a nuvem — sem duplicar, mas contornando o principal.
São dois padrões de identificador no mesmo arquivo, cada um com sua razão:
`isQueueable` aceita qualquer segmento sem `/` nem `.` (o caminho é montado
pelo próprio app, e exigir tamanho mínimo só deixaria o operador sem vender com
um ID curto); `isRelayable` exige de 8 a 160 caracteres, porque ali o principal
executa o que outra máquina pediu.

Três resultados possíveis, e a distinção é o ponto crítico:

- **Sucesso** — resposta assinada de volta.
- `MutationRelayUnavailable` — a entrega **não começou**. O cliente pode
  guardar na própria outbox com segurança.
- `MutationRelayUncertain` — pode ter sido entregue, mas a confirmação se
  perdeu. O cliente **não** cria cópia local, porque isso duplicaria a venda.
  Antes de desistir ele consulta `/v1/operations/<id>` duas vezes tentando
  recuperar o recibo.

**O principal só aceita conexão da rede local.**
`LocalTopologyService.isLocalNetworkAddress` recusa qualquer origem fora das
faixas privadas de IPv4, antes mesmo de verificar a assinatura, e a recusa é
registrada no log — uma tentativa vinda de fora é a única coisa ali que merece
atenção humana. Loopback passa em qualquer família porque é o próprio terminal.

O socket é aberto em todas as interfaces **de propósito**. Amarrá-lo a um IP
específico deixaria o principal inalcançável depois de uma troca de IP pelo
DHCP — uma falha silenciosa, com o terminal parecendo no ar — e quebraria
máquinas com mais de uma placa de rede. A proteção real é o filtro de origem
somado ao HMAC, que uma origem externa não teria como produzir. O corpo é
limitado a 256 KB.

Os recibos ficam 7 dias (`LocalTopologyStore.receiptRetention`) e a limpeza roda
na gravação seguinte. O prazo é o que dita a segurança: o recibo é o que impede
o principal de executar duas vezes a mesma operação, então precisa cobrir um
terminal que passou o fim de semana fora e voltou com a fila cheia. Encurtar
isso reabre a janela de duplicidade.

### 4.3-b `core/network/data_signals.dart`

Como a interface fica em tempo real sem nenhuma tela esperar a rede.

A regra é: **ler é sempre local e imediato**; quando um dado novo é gravado —
resposta da nuvem, resposta do principal ou edição offline — o assunto
correspondente é sinalizado e quem observa relê da cópia local. Nenhuma tela
bloqueia em timeout de requisição, e mesmo assim a atualização aparece assim
que o dado existe.

Os assuntos são grosseiros de propósito (`orders`, `menu`, `customers`,
`tables`, `cash`, `payments`): sinalizar "pedidos mudaram" custa uma releitura
local barata, enquanto rastrear a mudança até o campo exigiria um modelo de
eventos que este PDV não tem — e erraria mais do que acertaria.

Avisos são agrupados em uma janela de 120 ms, então uma sincronização que
atualiza vinte pedidos provoca uma releitura, não vinte. Rotas que nenhuma tela
observa (`/print-jobs/`, `latest-reading`, `/auth/`) não geram sinal nenhum.

O `ApiClient` sinaliza em quatro momentos: GET cacheado, mutação enviada,
mutação guardada na fila e operação da fila confirmada pelo servidor.

### 4.4 `core/errors/`

Três arquivos com papéis distintos:

- `app_error.dart` — o modelo. Título, mensagem para o operador, código,
  origem, ação recomendada, detalhes técnicos e horário. `AppError.fromApi`
  **preserva a mensagem do backend literalmente**: uma inconsistência de caixa
  precisa chegar exatamente como o servidor a descreveu.
- `error_center.dart` — a fila. `ChangeNotifier` com no máximo 3 alertas
  visíveis; repetir a mesma falha renova a existente em vez de empilhar cópias.
  Todo `report` grava no log antes de exibir.
- `app_error_host.dart` — a apresentação. Overlay no topo direito, sobre
  qualquer tela, com botão `X` que fecha na hora, cópia dos detalhes e detalhes
  técnicos recolhidos por padrão.

`AppError.unexpected` nunca mostra stack trace ao operador — ele vai só para
`technicalDetails` e para o log.

**Caminho único.** `core/widgets/copyable_error.dart` expõe `showAppError`, que
delega ao `ErrorCenter`. Não existe um segundo caminho de erro visível no app.

### 4.5 `core/hardware/`

#### `scale/scale_protocol.dart`

Classe base com buffer de quadros e quatro implementações. O enquadramento é
tratado na base (STX inicia, ETX/CR/LF terminam, bytes não imprimíveis
descartados, buffer limitado a 64 caracteres); cada subclasse só interpreta o
conteúdo.

| Implementação | Formato tratado |
| --- | --- |
| `GenericNumericProtocol` | último número da linha; sem separador e acima de 100, assume gramas |
| `ToledoProtocol` | STX…ETX, casas implícitas, `I`/`?`/`M` como movimento |
| `FilizolaProtocol` | gramas terminadas em CR, status `S`/`U`/`M` quando presente |
| `UranoProtocol` | `+00.500kg`, converte quando a unidade é `g` |

`ScaleSample.stable` é `bool?` de propósito: `null` significa "o equipamento não
informa", e nesse caso quem decide é o leitor.

#### `scale/scale_transport.dart`

Abstração `ScaleTransport` sobre o canal de bytes, com `SerialScaleTransport`
como implementação real. Ela existe para que a máquina de leitura seja testável
sem hardware — os testes injetam um transporte de memória.

#### `scale/serial_scale_reader.dart`

Junta tudo: reserva a porta, abre o transporte, decodifica, resolve estabilidade
e publica estado.

**Resolução de estabilidade**, na ordem:

1. Variou além da tolerância? Reinicia a contagem.
2. O protocolo disse `stable == false`? Reinicia, mesmo com valor repetido.
3. Caso contrário, estável quando `now - stableSince >= settleDuration`.

Watchdog de 1 s marca `noResponse` após 4 s sem quadros. Falha de porta agenda
reconexão com backoff de 1 s a 15 s.

`requestWeight()` é o "pegar peso" de emergência: reabre o canal se ele não
estiver saudável e envia `protocol.weightRequest` (`ENQ`, 0x05) para balanças
que só respondem sob comando. Devolve um `ScaleWeightRequest` descrevendo o que
aconteceu — inclusive `writeNotSupported`, quando o driver só permitiu abrir a
porta para leitura. Ele **não** produz nem confirma leitura: a resposta segue o
caminho normal e a regra de estabilidade continua valendo.

`SerialScaleTransport` tenta `openReadWrite()` e cai para `openRead()` se o
driver recusar. Isso mantém funcionando as instalações que só aceitam leitura,
ao custo de o botão ficar indisponível nelas.

#### `peripheral_lock.dart`

A exclusividade real vem do sistema operacional. O que faltava era **saber
quem** detém o equipamento. `PeripheralLock` mantém um `RandomAccessFile.lock`
exclusivo em `<dados>/StarChef/locks/` e grava, ao lado, um descritor legível
com papel, PID e nome do equipamento.

O sistema libera a trava sozinho quando o processo morre — uma janela encerrada
à força não deixa a balança presa até o próximo reboot.

### 4.6 `core/storage/`

- `app_paths.dart` — resolve o diretório de dados: `%LOCALAPPDATA%` (ou
  `%APPDATA%`) no Windows; `$XDG_DATA_HOME` ou `~/.local/share` no Linux/macOS.
  O temporário é último recurso, porque a fila offline precisa sobreviver a um
  reboot. `overrideDataDirectory` existe para os testes não escreverem na
  instalação real.
- `local_preferences.dart` — JSON com gravação **atômica** (arquivo temporário
  + rename) e serializada. Uma queda de energia no meio da escrita não deixa
  JSON truncado impedindo o próximo boot. O valor novo vale em memória
  imediatamente; o disco alcança depois.
- `durable_secure_store.dart` — abstrai os segredos usados por sessão, login
  offline, senha de caixa e topologia. No Windows usa apenas o cofre nativo. No
  Linux lê primeiro a cópia durável em `<dados>/StarChef/secure`, protegida por
  diretório `0700` e arquivos `0600`, e tenta espelhá-la no Secret Service. Se
  só existir o valor antigo no keyring, a primeira leitura o migra para o
  fallback. Isso impede que um keyring bloqueado seja confundido com “primeira
  instalação” e gere outra chave do Caixa Principal.
- `session_store.dart` — usa o armazenamento resiliente para access, refresh e
  usuário serializado; a primeira leitura da janela filha prioriza a sessão
  efêmera recebida do processo pai e depois volta ao armazenamento persistente.

O fallback Linux não é uma solicitação de permissão: aplicações desktop comuns
têm acesso ao diretório do próprio usuário. A proteção depende de executar o
PDV sempre como o mesmo usuário, sem `sudo`. Criptografia integral de disco
continua recomendada para proteger contra acesso físico à máquina desligada.

### 4.7 `core/logging/app_logger.dart`

JSON por linha em `<dados>/StarChef/pdv.log`, com uma rotação em 2 MB. As
escritas são encadeadas e tolerantes: disco cheio degrada para console, nunca
derruba o caixa. Chaves sensíveis (`password`, `access`, `refresh`, `token`,
`pairing_secret`, `csc_token`, …) são substituídas por `***` antes de gravar —
**em qualquer profundidade**. A máscara olhava só o primeiro nível, e este PDV
registra corpo de requisição inteiro em vários pontos: um `token` dentro de
`{'origin': {...}}` ou numa lista de operações da fila ia para o disco em texto
puro.

### 4.7-b Fechar o aplicativo

Com sessão, fechar o PDV pede a **senha do restaurante** (a mesma das ações de
caixa, configurável por loja — inclusive curta, como `123`) ou a credencial de
um administrador da conta. É a proteção que importa: alguém fechando o caixa no
meio do expediente.

**Sem sessão, a janela fecha direto.** Antes existia aqui um verificador
PBKDF2 embutido no binário, igual em toda instalação — um segredo que basta
extrair de um executável para valer em todos os terminais, e que ainda podia
ser atacado offline. Ele também não protegia nada de verdade: impedir o
fechamento pela janela não é fronteira de segurança, o processo pode ser
encerrado pelo sistema operacional a qualquer momento. E antes do login não há
turno em andamento, caixa aberto nem venda na tela — não há o que proteger.

### 4.8 `core/formatters` e `core/widgets`

`ValueFormatters` concentra as conversões tolerantes: `number` aceita `num`,
ponto e vírgula; `optionalNumber` distingue ausência de zero; `nullableId`
normaliza as três formas de vínculo vazio que a API produz (`null`, `""`,
`"null"`).

`TouchKeypad` e a função pura `nextKeypadValue` ficam separados: o widget
desenha, a função aplica a tecla ao texto e é testável isoladamente.

---

## 5. Features

### 5.1 `auth`

`AuthController` guarda a sessão e é quem sabe renová-la; o `ApiClient` só pede
um token novo ao receber 401. A ligação é feita em `initialize()`:

```dart
_repository.apiClient.attachTokenRefresher(_renewAccessToken);
_repository.apiClient.sessionExpired.listen((_) => _handleSessionExpired());
```

Quem decide encerrar a sessão é o controller, não o `ApiClient`, porque só ele
distingue **recusa do servidor** de **servidor inacessível**. Uma renovação que
falha por falta de rede não pode deslogar o operador no meio de um turno
offline; uma recusa explícita (401/403 na rota de refresh) encerra a sessão com
aviso na tela de login. Em ambos os casos a **fila offline permanece intacta**,
porque o logout é só da credencial.

`restoreSession()` merece atenção: no boot o access token quase sempre está
vencido, já que vive bem menos que o intervalo entre dois turnos. A renovação
acontece **dentro dela**, porque o refresher do `ApiClient` depende de uma
sessão em memória que ainda não existe nesse momento. A ordem é:

1. `GET /auth/me/` com o token guardado.
2. Se vier 401, tenta `POST /auth/refresh/` com o refresh guardado.
3. Renovou: relê o perfil e segue com a sessão nova.
4. Refresh recusado pelo servidor: limpa o cofre e devolve `null` (vai ao login).
5. Sem resposta do servidor em qualquer etapa: devolve a sessão guardada como
   está, para o terminal abrir e operar com o cache.

O passo 5 é deliberado: limpar o cofre offline deixaria o terminal sem conseguir
entrar de novo, porque o login exige servidor.

`AuthUser` expõe as permissões como getters (`canManageDevices`,
`canViewOrders`, `canProcessPayments`, …), que a sidebar consulta para esconder
módulos.

### 5.2 `home` — o PDV

`home_page.dart` é o arquivo maior do projeto (~7.700 linhas) e concentra
catálogo, carrinho, pagamento, caixa e navegação. É reconhecidamente grande;
qualquer trabalho novo ali deve extrair para painéis, como já foi feito com
`product_catalog_panel.dart` e `order_cart_panel.dart`.

**Comanda aberta que não virou venda é descartada.** Abrir uma comanda cria o
pedido na hora — é ele que ocupa a comanda. Sair sem lançar item nenhum
deixava esse pedido vazio segurando a comanda, e o próximo cliente que
pegasse a mesma não conseguia usá-la. `_goHome` descarta o pedido vazio (sem
item que conte e sem recebimento) chamando `/orders/{id}/cancel/`.

Não é um cancelamento comercial: não há consumo a estornar nem motivo a
registrar, então o backend dispensa a autorização do supervisor quando
`order_is_empty` — a senha existe para impedir que alguém apague consumo já
lançado, e ali não há nenhum. Um pedido COM item continua exigindo
autorização e motivo.

O descarte roda em **segundo plano**: voltar ao início é gesto de navegação e
não pode esperar a rede.

**E sem rede ele também acontece**, quando o pedido nunca chegou a subir. Um
id temporário não existe no servidor — mandar o cancelamento para lá só
renderia 404 —, então o gateway reconhece a rota
(`OfflineFirstGateway.discardableOrderId`) e resolve no terminal: apaga da
fila TUDO o que pertence àquele pedido e remove a linha local. A ordem
importa — as operações saem da fila antes do registro, senão a criação
subiria depois e recriaria no servidor exatamente o pedido vazio que se quis
descartar. A comanda não precisa ser liberada: enquanto o pedido não subiu, o
servidor nunca soube que ela estava ocupada.

Operação já em entrega (`PROCESSING`) recusa o descarte com HTTP 409: o
servidor pode estar gravando a venda neste instante, e apagar a fila deixaria
os dois lados discordando em silêncio — mesma prudência da exclusão de um
recebimento enfileirado.

Sobra um caso: pedido que o servidor **já conhece** com o terminal offline. Aí
a comanda fica ocupada até alguém cancelá-lo pela tela de Pedidos.

**O id antigo continua respondendo.** Todo registro nasce com um id
temporário (`offline-<uuid>`) e, quando a criação sobe, passa a viver sob o id
do SERVIDOR — `EntityRepository.replaceId` reescreve a linha e guarda o
`local → remoto` no `id_map`. A tela, porém, pegou o id no momento em que o
pedido nasceu e continua com ele em mãos.

Por isso `OfflineFirstGateway.read`/`write` traduzem caminho, filtros e corpo
antes de resolver a rota (`_promoted`). Sem essa tradução, um pedido aberto
pela comanda recusava o PRIMEIRO item com "Pedido offline-… não existe no
armazenamento local", e só voltava a funcionar quando o operador saía e
entrava de novo — porque aí a tela relia o pedido e ficava com o id novo. A
consulta ao `id_map` só acontece quando existe mesmo um `offline-` à vista.

Rotas que exigem servidor (`/orders/{id}/print/`, por exemplo) não passam por
aqui: elas dependem de a tela já ter relido o pedido, o que `_refreshOrder`
faz em todo gesto que muda a venda.

**Papel de venda concluída não obedece à trava de operação.** `_work` existe
para o operador não disparar duas operações de venda ao mesmo tempo, e por
isso ele **desiste** quando já há uma em curso (`if (busy) return null`).
Impressão e emissão fiscal de uma venda que JÁ terminou não podem obedecer a
essa trava:

- o DANFE sai por uma espera em segundo plano (a autorização da SEFAZ chega
  segundos depois do clique) e, nesse intervalo, o operador já começou a
  próxima venda — `busy` verdadeiro, `_work` devolvendo `null`, e o cupom
  fiscal simplesmente não existia: sem erro, sem fila, sem papel;
- o recibo montado localmente e a própria chamada de emissão tinham o mesmo
  buraco.

Os três passam agora por `_printingStep` (ou try/catch direto), fora da trava.
Falha continua sendo mostrada ao operador — o que não pode é desaparecer.

**Lançar item: um clique, uma unidade.** Produto sem variação e sem adicional
não tem nada a perguntar — clicar nele no catálogo, ou bipar o EAN, soma **uma
unidade** direto (`_addOneMoreOf`; o servidor e o `OrderRepository` agrupam
itens pendentes iguais). O modal de configuração
(`product_config_dialog.dart`) só abre para produto com **variação ou
adicional**, e para produto por peso, que precisa da balança. Antes ele abria
sempre, e confirmar um refrigerante custava dois gestos por unidade num balcão
com fila.

O ajuste fino saiu do modal e foi para o **cartão do item** na lista do pedido:
enquanto o item está em *Aguardando envio*, ele mostra `− quantidade +` embaixo
do nome (`_CartItem._quantityStepper`). Item já em produção não tem contador — o
que a cozinha recebeu não se desfaz assim, e o caminho continua sendo o
cancelamento, com motivo e registro. Produto por peso também não: a quantidade
vem da balança. Chegando a zero, o `−` vira o mesmo cancelamento do `×`.
Teclado e cartão passam pela mesma rotina (`_changeItemQuantity`), para os dois
gestos não divergirem nas recusas.

**Enter confirma os modais que sobraram.** O de configuração do produto e o de
pesagem aceitam Enter com a mesma condição do botão (variação obrigatória
escolhida, peso maior que zero). O atalho vive num `CallbackShortcuts` com um
`Focus` logo abaixo: sem esse nó, o foco fica no escopo da rota do diálogo — um
ancestral — e a tecla passa por cima sem tocar em nada. O campo de observação é
multilinha e trata o próprio Enter (quebra de linha), então continua imune.

**A tela é quebrada em seções por `part` + mixin.** `home_page.dart` concentra
catálogo, pedido, pagamento, caixa, fiscal, impressão e topologia num único
`State` com ~100 campos. Dividir isso em ViewModels de verdade mudaria o fluxo;
o que se faz aqui é MOVER código, sem reescrever uma linha dele:

```dart
// home_page.dart
part 'home_page_cash.dart';
class _HomePageState extends State<HomePage>
    with _HomePageShared, _CashSection, _FiscalSection, … { … }

// home_page_cash.dart
part of 'home_page.dart';
mixin _CashSection on _HomePageShared { … os métodos, iguais … }
```

Por que `part` e não um arquivo separado: os nomes são privados da biblioteca
(`_HomePageState`, `_work`, `_error`). Um arquivo à parte não os enxerga; um
`part` sim. E por que mixin e não outra classe: os métodos usam os campos do
`State` — num mixin eles continuam sendo os mesmos campos, sem parâmetro novo
e sem indireção.

**Cada seção declara o que usa de fora.** No topo do mixin ficam os membros
abstratos que `_HomePageState` fornece. Isso não é burocracia: é o contrato da
seção, ele aparece na compilação quando alguém mexe num lado só, e serve de
mapa das dependências reais daquele assunto. O que é comum a todas
(`api`, `token`, `_work`, `_error`, `_money`) vive em `_HomePageShared`, porque
declarar o mesmo membro em dois mixins faz o Dart recusar a classe.

`_money` e `_number` deixaram de ser `static` por causa disso — um membro
estático não pode coexistir com um herdado de mesmo nome.

Seções já extraídas: caixa, comandas/mesas, entrada (teclado/leitor/atalhos),
fiscal, pedido, pedidos (histórico), pagamento e recibo. Sobrou em
`home_page.dart` o ciclo de vida, a carga, a navegação e os painéis de `build`.

O alvo é nenhum arquivo passar de ~200 linhas, e ainda não chegamos: as seções
grandes precisam ser quebradas de novo, e o corte natural ali é por diálogo e
por painel — cada `showDialog` e cada `Widget _algoPanel()` é um pedaço
independente.

**Um lint aparece nesse desenho.** Um membro definido num mixin e consumido
por outro através da declaração abstrata é marcado como `unused_element`: o
analisador não liga as duas pontas entre mixins. Onde isso acontece há um
`// ignore: unused_element` com a explicação em cima da definição.

**A tela só é apagada uma vez.** Havia três formas de sinalizar carregamento e
todas ocupavam a tela inteira, então qualquer oscilação de rede, voltar ao
início ou abrir uma mesa devolvia o PDV a um fundo em branco no meio do
atendimento. A regra agora:

| Situação | Sinal |
| --- | --- |
| primeira carga, nada a mostrar | spinner ocupando a tela |
| recarga de fundo (`refreshing`) | spinner pequeno no botão Atualizar |
| operação em curso (`busy`) | faixa fina no topo do conteúdo |
| troca de restaurante | volta a ser primeira carga, de propósito |

`_load()` decide sozinho: se já há dados, ele não apaga nada — troca o conteúdo
quando a resposta chega. Uma falha durante recarga de fundo também não vira
tela de erro: o alerta global e o indicador de conexão já contam o que houve, e
o operador continua com uma tela utilizável.

Bloquear a interface durante uma operação era redundante — `_work` já ignora
uma segunda chamada enquanto a primeira não termina. A troca de restaurante é a
única que ainda limpa a tela, e por um motivo: manter o cardápio do restaurante
anterior visível levaria alguém a lançar no lugar errado.

`test/features/home/reload_behaviour_test.dart` fixa os quatro estados.

**Efeito colateral não bloqueia venda.** Fechar com "pagar depois", concluir um
pedido pago e reimprimir seguem o mesmo padrão: a operação de caixa acontece
primeiro e a impressão vem depois, dentro de `try`. Uma impressora fora do ar
vira alerta, nunca um pedido preso na tela. Esse era o mesmo bug em três
lugares — `if (printJob == null) return;` depois de a venda já ter sido
registrada.

Pontos de atenção:

- `_work<T>()` embrulha toda operação assíncrona: liga `busy`, captura a
  exceção e publica no `ErrorCenter`. `onError` permite um título específico —
  é assim que abertura, fechamento e movimentos de caixa ganham a mensagem
  certa.
- `_selectedDestination` mapeia o estado do fluxo para o item destacado na
  sidebar. Delivery não está lá: virou tipo de pedido dentro do fluxo.
- A sessão de caixa agora aceita resposta do cache; `cashSessionFromCache`
  marca isso e o cabeçalho mostra "Caixa (offline)". Abrir e fechar continuam
  exigindo servidor.
- `_orderDetail()` é como um pedido é aberto para edição ou pagamento. A ordem
  de preferência importa: **cópia local primeiro** quando não há rede, porque é
  ela que tem as edições ainda não sincronizadas; depois a entrada da listagem,
  que já é o detalhe completo (`OrderSerializer` aninha os itens e não há
  serializer reduzido para a lista — `tests/test_orders_list_contract.py` fixa
  esse contrato). Antes, um pedido aberto em outro caixa era impossível de
  editar offline: só a rota de detalhe ficava em cache, e ela nunca tinha sido
  chamada para aquele pedido.
- Toda resposta de pedido passa por `LocalOrderStore.saveFromServer`, e toda
  mutação offline por `addItem`/`voidItem`. É isso que faz a edição continuar
  lá depois de navegar.
- `_warmOrdersCache()` guarda a página de pedidos recentes assim que o PDV
  abre, fora do caminho crítico. Sem isso, o operador só teria os pedidos
  offline se tivesse visitado a tela de Pedidos antes da rede cair.
- **A query precisa ser a mesma.** O cache é indexado por rota + query, então
  o aquecimento e a tela de Pedidos compartilham `_ordersQuery`. Um
  `page_size` diferente vira outra entrada e o cache não serve para nada —
  há um teste guardando isso.

### 5.3 `scale` — Balança Rápida

Três camadas bem separadas:

**`domain/hands_free_machine.dart`** — a regra, sem widget nem API. Recebe
amostras e leituras, devolve `List<HandsFreeEffect>` descrevendo o que a
interface deve fazer (bipar, criar pedido, avisar cancelamento). O relógio é
injetado por `tick(now)`, então os testes controlam o tempo.

```text
idle ──start()──► waitingWeight ──peso estável──► waitingCommand
                       ▲                              │
                       │                       timeout│  comanda lida
                       │                              ▼         │
                       ├──────cancelado──────── commandOverdue   │
                       │                              │          │
                       │                       expirou│          ▼
                       └──────────────────────────────┘   creatingOrder
                                                            │      │
                                              readyForNext  │      │ falha
                                       completed ◄──────────┘      ▼
                                                                failed
                                                                   │
                                                       nova leitura │
                                                       creatingOrder ◄┘
```

Decisões embutidas:

- O **preço por kg é congelado** no instante da estabilização. Uma alteração de
  tabela durante a pesagem não pode mudar o valor mostrado ao cliente.
- Uma leitura de comanda fora da etapa certa é **recusada com alerta**, em vez
  de lançada numa operação inexistente.
- Uma falha ao criar o pedido **preserva a pesagem** (`failed` mantém
  `weighedItem`); a venda não se perde por recusa do servidor ou da impressora.
- **Zerar o peso não cancela** por padrão. Retirar o prato é comportamento
  normal do cliente; o abandono real é tratado pelo timeout. A política estrita
  existe em `cancelOnZeroDuringCommand`.

**`presentation/scale_workstation_page.dart`** — liga a máquina ao mundo: cria
o `SerialScaleReader`, alimenta `onSample`, executa os efeitos, faz o checkout e
desenha as etapas.

A leitura é registrada no servidor **no momento do lançamento**, não a cada
pesagem — assim uma operação cancelada não deixa leituras órfãs.

**`services/serial_scanner_service.dart`** — leitor de comanda em modo
serial/USB-CDC. Antes de abrir, revalida VID, PID e número de série contra o que
foi persistido: se o equipamento na COM mudou, exige novo vínculo. O
`ScannerFrameDecoder` monta um código por quadro terminado em CR/LF.

**`data/scanner_binding_store.dart`** — SQLite com `port_name` único, impedindo
que dois slots reservem a mesma porta deliberadamente.

**`core/input/`** — o controlador central de entrada do PDV. Teclado, leitor
USB que simula teclado, leitor serial e área de transferência produzem o mesmo
evento interno (`ScannedCode`), e o `PdvInputRouter` decide o destino pela tela
atual, nesta ordem: campo/modal em foco, captura do leitor (que consome o
Enter final), atalhos da página, atalhos globais. `PdvShortcuts` é o registro
único — é dele que saem tanto a tecla que o roteador escuta quanto a linha que
a página de ajuda (F1) mostra.

**`services/scale_window_launcher.dart`** — abre a estação como processo
independente. No Linux, prepara a transferência de sessão com diretório `0700`,
arquivo `0600`, validade de um minuto e remoção após a primeira leitura.

### 5.4 `devices`

- `domain/printer_endpoint.dart` — **o ponto de verdade** sobre como falar com
  a impressora. O backend guarda os mesmos campos em dois níveis (direto e em
  `settings`), e antes cada tela repetia essa resolução com regras levemente
  diferentes. Divergências ali significavam uma tela dizendo "configurada"
  enquanto o agente falhava por endereço ausente.
- `services/local_device_agent.dart` — consome a fila de impressão e entrega:
  - **rede**: `Socket` na porta 9100, multiplataforma;
  - **serial**: `flutter_libserialport`, multiplataforma;
  - **fila do sistema**: `Out-Printer` no Windows, `lp` (CUPS) no Linux — a
    única rota que ainda depende de ferramenta externa, porque não existe API
    de spool portátil.
- Código de barras: para driver ESC/POS, gera `GS k` Code 128 conjunto B quando
  o valor é ASCII imprimível; caso contrário cai para texto explícito.

O agente **não lê balança**. Isso saiu daqui quando a leitura passou a ser local
na janela: manter os dois abrindo a mesma COM era uma disputa real.

### 5.5 `sync/presentation/outbox_review_dialog.dart`

A tela de dead-letter. Traduz método e rota para o que a operação significa
("Item adicionado ao pedido", "Cancelamento de item"), mostra o motivo da recusa
e o payload completo, e oferece tentar de novo ou descartar. O descarte pede
confirmação explícita e é registrado como `warning` no log com o corpo da
operação.

### 5.6 `settings/presentation/terminal_preferences_dialog.dart`

Preferências que pertencem ao **terminal**, não à conta: tempo da comanda,
tolerância de estabilidade, alertas sonoros e impressão automática. Dois
balcões do mesmo restaurante podem precisar de valores diferentes.

Porta, baud rate e protocolo da balança **não** ficam aqui: valem para todos os
terminais que usam aquele equipamento, então moram no cadastro do backend.

---

## 6. Testes

```powershell
Set-Location flutter
flutter analyze
flutter test
flutter build windows
```

### 6.1 Instalador Windows (Inno Setup)

`windows/installer/starchef_pdv.iss` gera o `.exe` de instalação. A versão
(`AppVersion`) não fica mais hardcoded ali — o script abaixo lê `version:` de
`pubspec.yaml` e passa como `/DAppVersion` ao ISCC, então a versão só existe em
um lugar:

```powershell
flutter build windows --release
.\windows\installer\build_installer.ps1
```

Requer o Inno Setup 6 instalado (`ISCC.exe` no PATH ou em
`Program Files (x86)\Inno Setup 6`). O instalador não é assinado digitalmente
— o Windows SmartScreen pode alertar o usuário na instalação; assinar exige um
certificado de code signing que ainda não faz parte do processo.

129 testes hoje. A distribuição reflete uma escolha: testar regra pura e
protocolo de hardware com profundidade, e widgets apenas onde há risco real de
regressão (larguras compactas, botão de fechar do alerta).

| Arquivo | O que protege |
| --- | --- |
| `core/hardware/scale/scale_protocol_test.dart` | decodificação dos quatro fabricantes, quadros parciais, gramas vs. quilos |
| `core/hardware/scale/serial_scale_reader_test.dart` | estabilidade, tolerância, porta ocupada, disputa entre janelas |
| `features/scale/domain/hands_free_machine_test.dart` | fluxo completo, timeout, cancelamento, preservação da venda |
| `core/network/outbox_review_test.dart` | desbloqueio com chave preservada, proteção contra descarte indevido |
| `core/network/api_client_test.dart` | cache, outbox, IDs dependentes, rotas que exigem servidor |
| `features/auth/data/auth_repository_test.dart` | renovação no boot, recusa que limpa o cofre, queda de rede que **não** desloga |
| `features/topology/services/probe_interval_test.dart` | principal e secundário reais em 127.0.0.1: handshake assinado, leitura pelo principal e o ritmo do probe mudando com o estado |
| `core/errors/error_center_test.dart` | mensagem literal do backend, botão `X`, stack trace oculto |
| `core/storage/local_preferences_test.dart` | persistência, JSON corrompido, limites |
| `core/storage/app_paths_test.dart` | destino estável, nunca o temporário |
| `core/storage/durable_secure_store_test.dart` | migração do keyring e persistência de sessão quando o Secret Service falha |
| `features/devices/domain/printer_endpoint_test.dart` | resolução de transporte nos dois níveis |
| `core/widgets/touch_keypad_test.dart` | acumulação, backspace, casas decimais |
| `features/home/pdv_widgets_test.dart` | sidebar sem Delivery, larguras compactas |

**Padrão para testar hardware:** injete o transporte. `SerialScaleReader` recebe
uma `transportFactory`; nenhum teste precisa de equipamento conectado.

**Padrão para testar tempo:** injete o instante. `HandsFreeMachine.tick(now)`
recebe o relógio; nenhum teste espera segundos reais.

---

## 7. Como fazer as mudanças mais comuns

### Adicionar suporte a uma balança nova

1. Crie a subclasse em `core/hardware/scale/scale_protocol.dart` implementando
   só `_frameToSample`. Se o equipamento pedir outro byte de solicitação,
   sobrescreva `weightRequest` — o padrão é `ENQ` (0x05).
2. Registre em `ScaleProtocol.forId` e em `available`.
3. Escreva o teste de decodificação com quadros reais capturados do
   equipamento.
4. Cadastre `settings.protocol` no backend com o novo identificador.
5. **Homologue fisicamente** em três faixas de peso contra o visor — protocolo
   errado produz valor 1000× maior ou menor.

### Permitir que uma nova operação funcione offline

1. Adicione a rota em `OfflineMutations` — **um lugar só**, consultado pela
   fila e pelo relay. Se ela estiver em `ApiClient._requiresOnline`, remova
   de lá.
2. Se ela cria recurso, adicione também em `_createsResource` para gerar ID
   temporário.
3. **Confirme que o reenvio é seguro.** O `IdempotencyMiddleware` cobre
   qualquer POST/PUT/PATCH/DELETE que chegue com `Idempotency-Key` — que o
   `ApiClient` sempre envia. Rotas sob `/api/v1/auth/` são isentas de
   propósito: login e refresh precisam poder repetir.
4. Adicione a tradução legível em `OutboxReviewDialog._describe`.
5. Escreva o teste em `test/core/network/offline_orders_test.dart` e, no
   backend, em `tests/test_idempotency.py`.

### Exibir produtos em uma tela nova

Reutilize `ProductCatalogPanel`: ele já traz busca, filtro por categoria em
select e a grade de cards. É o que a Balança Rápida usa para os extras, com as
categorias derivadas dos próprios produtos (`extraCategories`) para não custar
outra chamada nem quebrar offline.

Os cards **não têm foto**, como no frontend web: a imagem remota falhava com o
terminal offline e ocupava espaço sem ajudar quem já sabe o que vai lançar.

### Adicionar uma preferência do terminal

1. Chave, getter e setter em `LocalPreferences`, com limites aplicados no
   setter.
2. Controle em `TerminalPreferencesDialog`.
3. Teste de persistência e de limite.

### Adicionar um erro visível

Nunca crie `SnackBar` de erro. Use `showAppError(context, error)` ou
`ErrorCenterScope.read(context).reportApi(...)`. O botão `X`, o log e a cópia
vêm de graça.

### Adicionar uma caixa de seleção

Sempre com `isExpanded: true`, e com `overflow: TextOverflow.ellipsis` nos
rótulos longos.

O `StarChefApp` amplia o texto de 1,04× a 1,22× conforme a largura da janela.
Sem `isExpanded`, o item selecionado usa a largura natural do texto e estoura o
`RenderFlex` interno do `InputDecorator` — o operador perde parte do rótulo e o
app registra `RenderFlex overflowed` no log. Foi assim que "Pendentes de
pagamento" quebrou dentro de uma caixa de 230 px.

`test/core/widgets/dropdown_overflow_test.dart` guarda esse caso, incluindo um
controle negativo que falha sem `isExpanded` — ele existe para provar que é
essa propriedade, e não outra coisa, que resolve.

---

## 8. Limitações do aplicativo

Estas são específicas do cliente Flutter; a lista completa, incluindo backend e
hardware, está em `PDV_OFFLINE_SCALE_ARCHITECTURE.md`.

1. **`home_page.dart` é grande demais.** ~7.700 linhas e 87 `setState`
   concentrando catálogo, pedido, pagamento, caixa, fiscal, impressão e
   topologia. Extrair painéis é trabalho pendente e deve acompanhar qualquer
   mudança grande nessa tela. O caminho desenhado é View/ViewModel por
   assunto — venda, pagamento, caixa, pedidos, fiscal e casca de navegação —
   mantendo `ChangeNotifier`, sem migrar o projeto para outra biblioteca de
   estado. `core/network/api_client.dart` (~1.865 linhas) tem o mesmo
   problema e se separa em transporte, conectividade, sincronização e
   renovação de sessão.
2. **Idempotência depende do servidor.** O cliente envia a chave; nem todas as
   rotas a deduplicam de forma uniforme.
3. **A fila do sistema de impressão não é portátil.** Rede e serial funcionam
   nos dois sistemas; o spool depende de `Out-Printer` ou `lp` estarem
   presentes.
4. **O leitor HID é capturado por cadência, não por dispositivo.**
   `core/input/scanner_keyboard_capture.dart` reconhece o leitor USB que
   simula teclado pelo ritmo das teclas e pelo Enter/Tab final. Isolar um HID
   específico por VID/PID continua exigindo código nativo por plataforma — o
   que significa que um teclado usado muito rápido pode, em tese, ser lido
   como código.
5. **A trava de periférico é por máquina.** Duas máquinas ligadas fisicamente
   ao mesmo equipamento continuam sendo um problema de instalação.
6. **O cache não tem TTL.** Offline, ele entrega a última resposta conhecida
   marcada com `_offline_cache: true`.
7. **A atualização automática ainda não é verificável.** O `PdvAutoUpdater`
   existe e roda (`app/starchef_app.dart`): ele consulta o manifesto, baixa e
   troca o binário. O que falta é a garantia de PROCEDÊNCIA — o instalador não
   é assinado com Authenticode e o `latest.json` não é assinado, então o
   SHA-256 publicado ali só protege contra corrupção de download, não contra
   um manifesto substituído. Ver `PDV_UPDATE_RELEASE.md`.
