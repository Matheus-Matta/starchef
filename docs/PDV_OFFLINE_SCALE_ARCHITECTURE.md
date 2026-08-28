# PDV offline e Balança Rápida — arquitetura implementada

Este documento descreve o comportamento que existe no código atual. Ele é um registro **AS-IS**, não uma promessa da arquitetura desejada ao fim de todos os sprints. As lacunas conhecidas estão reunidas no final.

Para a estrutura interna do aplicativo Flutter — camadas, arquivos, decisões de
desenho e como estender cada parte —, veja
[`FLUTTER_PDV_TECNICO.md`](FLUTTER_PDV_TECNICO.md).

## Visão geral

O PDV é **offline-first**: o SQLite do Caixa Principal é a fonte de verdade
operacional do restaurante, e a API é sincronização, backup e integração. Se a
internet da loja cair, a operação inteira continua — abrir caixa, vender,
lançar item, fechar pedido, receber, sangrar, fechar caixa, imprimir.

```text
                              ┌──────────────────┐
                              │     BACKEND      │
                              │       API        │
                              └────────▲─┬───────┘
                                       │ │
                              Sync HTTP│ │WebSocket
                                       │ │
                              ┌────────┴─▼───────┐
                              │  CAIXA PRINCIPAL │
                              │ LocalTopology    │  <- API local /local/...
                              │ SyncService      │
                              │ SyncQueueService │
                              │ pdv_operational  │  <- SQLite (fonte de verdade)
                              └──────▲────▲──────┘
                                     │    │
                          Rede local │    │ Rede local
                         ┌───────────┘    └───────────┐
                ┌────────▼────────┐          ┌────────▼────────┐
                │ Caixa Secundário│          │ Apps / Garçons  │
                │ Impressão local │          │ Tablets / etc.  │
                └─────────────────┘          └─────────────────┘
```

O caminho de uma operação no Caixa Principal:

```text
Tela ── ApiClient ── OfflineFirstGateway ── Repository ── SQLite
                            │
                            └── sync_queue (mesma transação)
                                     │
                            SyncService ── ApiClient (transporte) ── API
```

**Leitura**: `OfflineFirstGateway.read` resolve a rota contra o
`EntityCatalog`, responde do SQLite na hora e dispara a reconciliação com o
backend em paralelo — a tela nunca espera a rede. A única exceção é a partida a
frio: quando um recurso nunca foi sincronizado neste terminal, vale a pena
esperar UMA leitura em vez de abrir a tela vazia.

**Escrita**: `OfflineFirstGateway.write` aplica a alteração no SQLite **e**
grava a operação na `sync_queue` na mesma transação (Transactional Outbox), e
responde imediatamente. Se a API estiver fora, a operação simplesmente
permanece na fila.

```text
┌──────────────── processo principal: StarChef PDV ────────────────────────────┐
│ UI ── ApiClient ── OfflineFirstGateway ── <dados>\StarChef\pdv_operational.sqlite │
│           │                                                                  │
│           ├── SyncService (fila de saída + carga paginada + fila fiscal)      │
│           ├── RealtimeClient (WS) ── grava no SQLite, não só na memória       │
│           ├── LocalTopologyService ── servidor local /local/... para a LAN    │
│           └── LocalDeviceAgent (impressão) ── Windows / TCP 9100 / serial     │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────── processo independente: Balança Rápida ───────────────────────────┐
│ UI touch ── HandsFreeMachine ── ApiClient ── mesmo pdv_operational.sqlite     │
│    ├── SerialScaleReader ── porta serial (leitura local contínua)            │
│    │       └── trava exclusiva em <dados>\StarChef\locks\scale_<porta>.lock  │
│    └── leitor USB-CDC/serial reservado pela porta                            │
│          └── <dados>\StarChef\device_bindings.sqlite                         │
└──────────────────────────────────────────────────────────────────────────────┘
```

A leitura de peso continua local: a janela que vai usar a balança abre a porta
serial, decodifica os quadros e resolve a estabilidade em memória. A rede não
participa disso.

### Onde ficam os dados

| Plataforma | Diretório |
| --- | --- |
| Windows | `%LOCALAPPDATA%\StarChef` (`%APPDATA%` como alternativa) |
| Linux / macOS | `$XDG_DATA_HOME/StarChef`, senão `~/.local/share/StarChef` |

O diretório temporário só é usado quando nenhuma dessas variáveis existe. Isso
importa porque a fila offline precisa sobreviver a uma reinicialização — em
`/tmp` ela não sobreviveria.

### Onde ficam as credenciais

Sessão, verificador de senha offline, hash da senha de ações do caixa e chave
de pareamento passam por **três camadas**, consultadas nesta ordem:

1. `<dados>/StarChef/secure` — um arquivo por chave, diretório `0700` e arquivo
   `0600`;
2. `secure_values`, no mesmo `pdv_operational.sqlite` de pedidos, caixa e fila
   de impressão;
3. o cofre nativo do sistema (Secret Service no Linux, DPAPI no Windows).

São três porque cada uma falha por um motivo diferente, e perder o login
significa o operador não conseguir abrir o caixa no dia seguinte — justamente
quando a internet está fora:

- o **cofre nativo** falta com frequência no Ubuntu: autostart sem sessão
  gráfica, keyring bloqueado, empacotamento sem `libsecret`;
- o **arquivo** depende de `chmod` funcionar no volume onde fica o `$HOME`
  (`chmod` ausente num empacotamento restrito, volume exFAT de um pendrive, NFS
  que não aceita mudança de modo);
- o **banco** depende de o SQLite ter aberto — e, se ele não abriu, o PDV já
  avisa na inicialização e nada mais funciona offline de qualquer forma.

Uma gravação só é reportada como falha quando **nenhuma** camada aceitou. Antes,
uma falha de `chmod` abortava a escrita inteira: com o keyring também
indisponível, o login simplesmente não sobrevivia a fechar o PDV. Hoje o
`chmod` é tentado, e uma recusa vira registro e um alerta na abertura — um
arquivo com a permissão padrão do usuário é um risco menor do que o caixa não
abrir de manhã.

O verificador de senha é PBKDF2 e é seguro em repouso — é para isso que ele
existe. Os tokens de sessão passam pelo `PayloadCipher`, que cifra quando há
cofre e degrada para texto quando não há: a mesma exposição que a cópia em
arquivo já tinha nesse cenário, com a diferença de que agora o dado sobrevive.

## Interface do PDV

A tela principal usa três regiões:

- barra lateral fixa e recolhível, com 224 px expandida e 76 px recolhida;
- catálogo de produtos no centro;
- resumo do pedido à direita.

A barra lateral expõe Menu, Mesas, Pedidos, Financeiro, Balança Rápida e Configurações, respeitando as permissões já presentes na sessão. Delivery não é mais um módulo próprio: ele existe apenas como tipo de pedido dentro do fluxo de Pedidos. Ela também contém identificação do operador, restaurante e logout. Em janelas com menos de 1180 px, o menu passa automaticamente ao modo recolhido.

O catálogo oferece busca por nome, código interno e categoria, categorias horizontais com contagem, cards com preço e imagem remota e um ícone de categoria como fallback. O carrinho apresenta contexto do pedido, imagens, itens, subtotal, taxas, desconto, total, revisão e impressão. Sua largura varia entre 350, 380 e 420 px conforme o espaço disponível.

O cabeçalho mantém seleção de restaurante, estado do caixa, atualização e um badge de conectividade/sincronização. O badge pode mostrar `Verificando`, `Online`, `Offline`, `Sincronizando`, `Instável` ou `Revisar`, além da quantidade de operações locais quando aplicável.

## Persistência offline

### Arquivos e tabelas

O banco operacional (`PdvDatabase`) usa `sqlite_async` com WAL e grava em:

```text
%LOCALAPPDATA%\StarChef\pdv_operational.sqlite
```

| Tabela | Responsabilidade |
| --- | --- |
| `secure_values` | sessão, verificador de senha offline e chave de pareamento — a terceira camada durável das credenciais |
| `print_queue` | cupons esperando a impressora: conteúdo pronto, cópia do cadastro da impressora, tentativas, espera e o `PrintJob` de origem quando veio do servidor |
| `entities` | uma linha por recurso do restaurante, com `version`, `source` (LOCAL/REMOTE), `sync_status`, `created_at`, `updated_at`, `deleted_at` e `sort_key` |
| `sync_queue` | fila de saída: `operation_id` (UUID = chave de idempotência), tipo, entidade, operação, método, rota, payload, `status`, `attempts`, `next_retry_at`, `last_error`, reserva (`lease_owner`/`lease_until`) |
| `sync_state` | marca de tempo da última sincronização por tipo, para o delta sync |
| `fiscal_queue` | documentos fiscais pendentes, com situação e retentativa próprias |
| `id_map` | relação entre IDs locais (`offline-...`) e os IDs definitivos |

O arquivo legado `offline_data.sqlite` (`OfflineStore`) continua existindo, mas
só para entregar o que ficou pendente antes desta versão e para atender rotas
que não são recurso operacional. A tela de revisão da fila mostra as duas filas
juntas — uma venda presa na fila antiga é tão invisível quanto uma presa na
nova.

`local_orders.sqlite` deixou de ser um banco: `LocalOrderStore` virou a porta de
entrada da tela de pedidos para o `OrderRepository`. Existiam duas bases para o
mesmo dado, e isso significava duas verdades.

### Que dados existem offline

O `EntityCatalog` é a lista única de "esta rota da API é este recurso local".
Ele cobre restaurante e filial, configuração e perfis fiscais, cardápio
(categorias, produtos, adicionais, variações), salão (setores, mesas,
comandas), clientes, endereços, formas de pagamento, estações e sessões de
caixa, impressoras, balanças, usuários, papéis e pedidos.

Antes essa lista existia em três lugares — rotas cacheáveis no `ApiClient`,
relayáveis no `LocalTopologyService` e carregadas na abertura no
`PdvRepository`. As três divergiram, e o sintoma era um recurso que funcionava
online e sumia offline.

Payloads sigilosos (configuração fiscal, usuários) são cifrados em repouso com
HMAC-SHA256 em modo contador seguido de HMAC sobre o criptograma
(encrypt-then-MAC), com a chave-mestra no cofre do sistema. Copiar apenas o
`.sqlite` não basta para ler CSC e ID CSC.

### Escopo de conta e servidor

O namespace continua sendo:

```text
autoridade-da-base-url | account_id, user_id ou sub extraído do JWT
```

O banco é vinculado ao escopo assim que a sessão fica conhecida — não na
abertura do app. Dados de duas contas nunca compartilham escopo no mesmo
terminal. O logout desvincula, mas **não apaga** o banco: pendências sobrevivem
para reconciliação.

### O que ainda exige servidor

Nada da **operação diária**. A lista restante é de coisas que ou não são
operação, ou não existem sem o servidor por natureza:

| Rota | Por quê |
| --- | --- |
| `/reports/` | Relatório não é operação de balcão. |
| `/print-jobs/`, `mark-printed`, `mark-failed` | São a **cópia** do backend e a confirmação dela. A fila que manda papel para a impressora é local; sem servidor, ela continua girando e a confirmação espera. |
| `/invoices/<id>/print/` | Não existe DANFE sem nota autorizada. |
| `/scales/readings/` | Uma `ScaleReading` descreve um instante que já passou; criá-la depois seria inventar uma leitura. O peso viaja na própria operação de fechamento. |
| `/printers/templates/` | Não é coleção de entidades; o `PrintTemplateCache` guarda os arquivos em disco. |
| `/auth/login/` | Só na **primeira** entrada de um operador neste terminal. Depois disso o login é conferido localmente (`SecureOfflineLoginStore`, PBKDF2 nas três camadas duráveis). |

Saíram da lista, e agora funcionam sem internet:

- **abrir, fechar e movimentar caixa**;
- **autorizar divergência de caixa** — a senha de ações é conferida contra o
  hash já sincronizado, e o que sobe é uma *prova* HMAC, não a senha;
- **fechar a pesagem na comanda** (`checkout-command`);
- **emitir NFC-e**, que passou a ter fila própria;
- **imprimir** recibo, comanda de cozinha, cancelamento, nota de pesagem e
  nota de teste.

Uma ação sobre um recurso só é aplicada localmente se estiver na lista fechada
de `EntityCatalog.localActions`. Uma ação desconhecida vai para o servidor: sem
essa guarda, `DELETE /orders/<id>/payments/<id>/` (um estorno) caía no caminho
genérico de escrita e marcava o pedido inteiro como excluído.

Uma leitura física de balança (`scale_reading`) nunca entra na fila — ela
descreve um instante que já passou. O peso em si (`weight_kg`, `tare_kg`) é
apenas um valor e viaja normalmente, senão não daria para vender a granel
offline.

### Idempotência e prevenção de duplicidade

Todo registro nasce com UUID **antes** de qualquer chamada à API:
`client_order_id`, `client_item_id`, `client_payment_id`,
`client_cash_register_id`, `client_movement_id`, `client_document_id`. O mesmo
identificador vai como `Idempotency-Key`, e o backend
(`apps/core/idempotency.py`) devolve a resposta original em vez de criar uma
segunda venda.

Quando a operação sobe, o ID temporário vira o definitivo em três lugares: no
banco (`replaceId`), nas referências dentro do pai (`replaceReference`, para
item/pagamento/movimentação) e no que ainda estiver na fila
(`registerResolvedId`). Sem o segundo, a próxima leitura vinda do servidor
trataria o item confirmado como "ainda pendente" e o somaria de novo.

### Ordem, retry e revisão

A fila é FIFO por `id` autoincremental — determinístico mesmo para operações
criadas no mesmo milissegundo. FIFO cego, porém, travaria a loja: uma operação
recusada por regra de negócio seguraria todas as vendas atrás dela. A ordem é
preservada **onde importa**: quem ainda cita um ID temporário não resolvido
espera a sua vez; o que é independente passa na frente.

| Situação | Efeito |
| --- | --- |
| timeout, 5xx, 408, 425, 429, sem rede | `PENDING` com backoff 5s, 15s, 30s, 1min, 5min (o teto se repete) |
| 400, validação, conflito | `FAILED`: sai da rotação e aparece na tela de revisão |

`Retry-After` é respeitado quando presente. Cada ciclo envia no máximo 20
operações, uma requisição por vez. A reserva (`lease_owner`/`lease_until`)
impede que o PDV e a janela da Balança Rápida enviem a mesma operação.

Descartar uma operação recusada leva junto o que dependia dela — manter os
dependentes deixaria a fila tentando alterar para sempre um pedido que nunca
existirá no servidor.

### Sincronização de entrada

`SyncService.pullAll` percorre o catálogo do essencial ao acessório, em páginas
de 20 (`?page=N&page_size=20`). Página vazia ou sem `next` encerra o tipo: nunca
repete a página anterior nem inventa registros.

A partir da segunda carga o pedido é incremental:
`?updated_after=<último sync>&include_deleted=1`. O backend implementa os dois
parâmetros em `TenantQuerySetMixin` (`filter_queryset` e `soft_delete_scope`),
para valer inclusive nos viewsets que montam o próprio queryset.
`include_deleted` só tem efeito acompanhado de `updated_after` — sem ele, um
produto removido na retaguarda apenas sumiria da listagem e a cópia local
continuaria vendável no caixa.

### WebSocket

O evento do backend traz `resource`, `action` e `id`. O PDV traduz o modelo para
o tipo local (`EntityCatalog.typeForRealtimeResource`), lê o registro e **grava
no SQLite**; só depois a tela reage. Antes o evento só emitia um sinal e cada
tela reconsultava a API por conta própria — com a internet fora, o aviso não
virava dado nenhum.

A gravação é marcada como `REMOTE`, portanto não gera operação de saída: é o que
corta o laço `backend → WS → SQLite → fila → backend`.

Um evento fora de ordem (WebSocket e sincronização periódica correndo juntos) é
descartado pelo `ConflictResolver`, comparando `updated_at`.

### Conflitos

A regra é conservadora: **o que o operador acabou de fazer e ainda não subiu
vale mais que a cópia do servidor**. Descartar a alteração local apagaria da
tela um item lançado há segundos, ainda na fila. A exceção é o retorno da
própria entrega — a resposta do servidor à operação que acabou de subir é a
verdade, com identificadores e numeração definitivos.

### Fiscal (NFC-e)

A venda não depende da nota. `POST /invoices/emit/` entra na `fiscal_queue` e
devolve `_fiscal_pending`; o pedido segue `paid` enquanto o documento fica
`PENDING`. A fila fiscal tem cadência (30s) e escada de retentativa próprias
(15s, 30s, 1min, 5min, 15min): uma nota recusada pela SEFAZ não pode segurar a
sincronização das vendas. Uma rejeição definitiva vira `FAILED` e não volta em
laço.

Antes, a mesma situação devolvia erro no meio do recebimento, como se a venda
tivesse falhado.

### Estados exibidos

| Estado | Condição prática |
| --- | --- |
| `unknown` | ainda sem resultado de conectividade ou sessão limpa |
| `online` | última comunicação bem-sucedida e sem pendências |
| `offline` | falha de transporte, socket ou timeout |
| `degraded` | servidor respondeu com falha temporária |
| `syncing` | há operações elegíveis sendo ou prestes a ser enviadas |
| `blocked` | pelo menos uma operação precisa de revisão |

O indicador soma as duas filas. Mostrar só a legada faria o PDV parecer "tudo
sincronizado" com vendas esperando na fila nova.

### Periféricos

A **configuração** de impressoras e balanças é centralizada no SQLite do
principal e chega aos outros terminais pela API local. A **execução** continua
no dispositivo que alcança o equipamento fisicamente: o Caixa Secundário imprime
nas impressoras ligadas a ele, e o backend externo nunca é necessário para uma
impressão local.

### Inicialização

1. abrir o SQLite e executar as migrations;
2. verificar a integridade (`PRAGMA quick_check`; uma falha vai para o log e não
   impede a abertura);
3. montar fila, fila fiscal e gateway;
4. ligar o gateway ao `ApiClient`;
5. desenhar a interface a partir do que houver no banco;
6. em segundo plano: sincronizar, subir a fila, abrir o servidor local e
   conectar o WebSocket.

A interface não espera API externa, WebSocket nem sincronização completa.

## Balança Rápida

### Processo e sessão

Ao selecionar Balança Rápida, o PDV salva a sessão atual no cofre do sistema e inicia o mesmo executável com:

```text
--scale-workstation --restaurant=<uuid>
```

O token não é colocado na linha de comando. O novo processo restaura a sessão
pelo `flutter_secure_storage`. No Linux, o PDV também grava uma transferência
efêmera em `scale-session-handoffs`, protegida com diretório `0700` e arquivo
`0600`, e passa somente `--session-handoff=<nome-aleatório>`. A janela consome e
apaga o arquivo no boot; entradas não consumidas expiram em um minuto. Isso
evita a tela de login quando a segunda instância do Ubuntu ainda não consegue
reler o GNOME Keyring. Depois, ela cria seu próprio `ApiClient` e permite
escolher restaurante e balança. É possível abrir mais de uma instância. Se a
transferência não puder ser protegida ou o processo não puder ser criado, o PDV
abre a estação embutida como fallback.

A janela dedicada inicia com 1180 × 760 px e mínimo de 900 × 650 px. Cada processo tem ciclo de vida próprio, portanto fechar ou travar uma janela de balança não fecha a interface principal.

### Máquina de estados hands-free

O fluxo vive em `HandsFreeMachine`, uma classe sem dependência de widgets ou
API. Ela recebe amostras da balança e leituras do scanner e decide a etapa
seguinte, o que permite testar estabilização, timeout e cancelamento sem
hardware conectado. O relógio é injetado (`tick(now)`), então os testes
controlam o tempo.

| Estado | Significado |
| --- | --- |
| `idle` | estação parada, em configuração |
| `waitingWeight` | Estado 1: esperando peso válido e estável |
| `waitingCommand` | Estado 2: item registrado, contando o tempo da comanda |
| `commandOverdue` | tempo esgotado; período curto de confirmação antes de cancelar |
| `creatingOrder` | Estado 3: lançando o pedido e imprimindo |
| `completed` | sucesso; volta sozinho ao Estado 1 |
| `failed` | recusa do servidor; a pesagem é preservada para nova leitura |

Fluxo operacional:

1. O operador escolhe restaurante e balança. A balança precisa ter um produto por kg e uma impressora padrão configurados.
2. Ao iniciar, a estação abre a porta serial da balança e passa a receber quadros continuamente.
3. Assim que o peso estabiliza — sem oscilar além da tolerância durante o atraso configurado, e sem o bit de movimento do equipamento — o item é registrado e a tela pede a comanda. **Não há confirmação por toque nesse ponto**: o fluxo normal não exige teclado nem mouse.
4. O preço por kg é congelado no instante da estabilização, para que uma alteração de tabela durante a pesagem não mude o valor mostrado ao cliente.
5. O operador pode acrescentar produtos por unidade ou cancelar, sem pressa: o tempo restante aparece na tela.
6. A comanda é lida pelo scanner serial ou digitada no teclado touch.
7. A estação registra a leitura (`POST /scales/readings/`) e chama `checkout-command` com extras e impressão.
8. O backend, em uma transação, resolve/cria o pedido da comanda, consome a leitura, adiciona o item pesado e os extras, recalcula o pedido e cria o trabalho de impressão.
9. Após sucesso, a estação aguarda 2 segundos e volta ao Estado 1.

A leitura só é registrada no servidor no momento do lançamento, e não a cada
pesagem: uma operação cancelada ou expirada não deixa leituras órfãs.

Existe entrada manual de peso com teclado numérico touch. Ela entra na máquina
como uma amostra já estável e percorre exatamente o mesmo caminho.

### Resets e timeouts

- **Timeout da comanda.** Configurável em `preferences.json` (padrão 45 s, faixa aceita de 10 s a 600 s). Ao esgotar, a estação emite alerta sonoro e visual e entra em `commandOverdue`, com 10 segundos de confirmação. Ler a comanda nesse intervalo ainda conclui a venda; passado o prazo, a operação temporária é descartada e o fluxo volta ao Estado 1.
- **Peso zerado.** Retirar o prato **não** cancela a operação por padrão. Retirar o prato logo após a pesagem é o comportamento normal do cliente, e cancelar aí descartaria vendas legítimas; o abandono real é tratado pelo timeout. A política estrita existe (`cancelOnZeroDuringCommand`) para quem preferir o cancelamento imediato.
- **Falha no lançamento.** A pesagem é preservada e o operador pode reler a comanda. A venda nunca é descartada por uma recusa do servidor ou da impressora.
- **Leitura fora de etapa.** Um código lido enquanto a estação espera peso é ignorado com alerta sonoro, em vez de ser lançado em uma operação inexistente.

### Leitura da balança física

A janela que vai usar a balança abre a porta ela mesma (`SerialScaleReader`,
via `flutter_libserialport`). Não há PowerShell no caminho, o que faz a leitura
funcionar igual em Windows e Linux, e não há nenhuma chamada periódica à API
para obter peso.

O protocolo é escolhido em `settings.protocol` no cadastro da balança:

| Valor | Família | Enquadramento tratado |
| --- | --- | --- |
| `generic` (padrão) | qualquer equipamento em transmissão contínua | último número de cada linha; sem separador decimal e acima de 100, interpreta gramas |
| `toledo` | Toledo Prix / 9091 | STX…ETX, dígitos com casas implícitas, marcas `I`/`?`/`M` de movimento |
| `filizola` | Filizola CS / MF | gramas terminadas em CR, campo de status `S`/`U`/`M` quando presente |
| `urano` | Urano UDC / POP-S | `+00.500kg`, com conversão quando a unidade é `g` |

Cada família documenta o enquadramento mais comum, mas firmware, configuração e
modelo ainda variam: **todo modelo novo exige homologação física** antes de ir
para produção. Quando o protocolo não transmite estabilidade, quem decide é o
leitor, comparando leituras consecutivas dentro da tolerância
(`scale_stability_tolerance_kg`, padrão 0,002 kg) durante o atraso configurado
na balança. Quando o equipamento informa movimento, esse bit prevalece sobre a
repetição do valor.

Um watchdog marca `noResponse` se os quadros pararem por mais de 4 segundos, e
uma falha de porta agenda reconexão com backoff de até 15 segundos.

### Botão "Pegar peso da balança"

Existe para o caso em que **o visor mostra o peso e a tela não recebe nada**.
Duas causas explicam quase todos esses casos, e o botão trata as duas:

1. **A balança está em modo sob demanda.** Muitos modelos saem de fábrica
   respondendo só quando recebem uma solicitação, e ficam mudos em transmissão
   contínua. O botão envia `ENQ` (0x05), o pedido usado pelas três famílias
   suportadas.
2. **O canal caiu.** Antes de pedir, a porta é fechada e reaberta.

A porta é aberta em leitura/escrita quando o driver permite; se ele só aceitar
leitura, o botão informa isso explicitamente em vez de falhar em silêncio — e a
leitura contínua segue funcionando normalmente.

O botão **não confirma peso nenhum**: ele apenas solicita. A resposta entra
pelo mesmo caminho de qualquer leitura e continua passando pela regra de
estabilidade. Se o equipamento não responder, o cartão de diagnóstico mostra
"sem resposta" e o operador tem a entrada manual como saída.

### Ownership dos periféricos

A exclusividade real vem do sistema operacional: uma porta serial só abre uma
vez. O que faltava era *saber quem* a está usando. Antes de abrir, o leitor
reserva `scale:<porta>` com uma trava de arquivo (`RandomAccessFile.lock`) em
`<dados>\StarChef\locks\`, e grava ao lado um descritor com papel, PID e nome
do equipamento.

O sistema libera a trava sozinho quando o processo morre, então uma janela
encerrada à força não deixa a balança bloqueada até o próximo reboot. A segunda
janela lê o descritor e informa exatamente qual janela precisa ser fechada, em
vez de mostrar apenas “porta ocupada”.

### Status de conexão na estação

O cartão de diagnóstico agora reflete o estado local do leitor, sem consultar a
API:

| Estado | O que o cartão informa |
| --- | --- |
| `disconnected` | estação parada ou balança sem porta cadastrada |
| `connecting` | abrindo a porta ou aguardando o primeiro quadro |
| `connected` | quadros chegando, com o peso atual e se já estabilizou |
| `noResponse` | porta aberta, mas o equipamento parou de transmitir |
| `portBusy` | outra janela detém o equipamento (com a identificação do dono) |
| `readError` | quadros ilegíveis para o protocolo escolhido |

## Leitor de comanda USB-CDC/serial

Cada combinação `restaurante:balança` funciona como um slot de leitor. O vínculo local é gravado em:

```text
%LOCALAPPDATA%\StarChef\device_bindings.sqlite
```

A tabela `scanner_bindings` guarda porta, baud rate, VID, PID, número de série e nome do produto. `port_name` é único no banco, impedindo que dois slots sejam configurados deliberadamente com a mesma porta. A interface lista as portas detectadas e permite 9600, 19200, 38400, 57600 ou 115200 baud.

Ao selecionar uma balança, a estação restaura o vínculo e tenta abrir a porta em modo de leitura. A porta aberta é a reserva efetiva no sistema operacional; outra janela recebe erro de porta ocupada/indisponível. O leitor deve enviar caracteres ASCII imprimíveis e terminar cada código com CR ou LF. Frames vazios são ignorados e o decoder limita o buffer a 160 caracteres.

Durante a etapa “Leia a comanda”, um frame válido preenche o código e conclui o checkout automaticamente. Leituras em outras etapas são ignoradas com alerta sonoro. A interface permite desvincular o dispositivo.

Antes de abrir a porta, o serviço compara os valores persistidos de VID, PID e número de série com o dispositivo que ocupa a COM naquele momento. Qualquer divergência disponível bloqueia a abertura e obriga o operador a refazer o vínculo. Quando o dispositivo/driver não fornece um desses identificadores, somente os campos efetivamente capturados podem ser validados.

## Impressão

### Quem imprime cada coisa

| Trabalho | Quem monta | Quem manda para o papel | Precisa de servidor? |
| --- | --- | --- | --- |
| Recibo do cliente | backend **ou** terminal | fila local → impressora | não |
| Comanda de cozinha (por setor) | backend **ou** terminal | fila local → impressora | não |
| Cancelamento de item | backend **ou** terminal | fila local → impressora | não |
| Nota de pesagem | backend **ou** terminal | fila local → impressora | não |
| Teste de impressora | backend **ou** terminal | direto (é diagnóstico: o operador precisa do erro na hora) | não |
| DANFE da NFC-e | backend | fila local → impressora | sim — não há DANFE sem nota autorizada |

O **cadastro** de impressoras vem do SQLite local (§18), então o terminal
continua sabendo para onde imprimir mesmo sem internet. E, quando o backend não
responde, é o terminal que monta o cupom — ver "Cupons montados no terminal".

### A comanda de cozinha: quem imprime, e por quê

É a decisão mais perigosa do PDV offline-first, porque os dois erros possíveis
são graves: sair a mesma comanda duas vezes, ou não sair nenhuma.

A pergunta é **factual**, não um palpite sobre a conexão:

```text
POST /orders/<id>/send-to-kitchen/   (grava local + enfileira, responde na hora)
        │
        ├── a operação saiu da fila em até 3s?
        │      SIM → o backend criou o PrintJob; o agente imprime. Fim.
        │      NÃO ↓
        │
        ├── reivindica a impressão: marca `offline_printed: true` no corpo
        │   AINDA enfileirado (falha se a operação subiu nesse instante)
        │
        ├── imprime aqui, montando o cupom por setor com `OrderPresenter`
        │
        └── não saiu papel? desmarca, e a impressão volta a ser do backend
```

A marcação **antes** de imprimir é o que fecha a janela em que a operação
subia entre "imprimi" e "avisei" — era assim que saíam duas comandas para a
mesma rodada. E a desmarcação cobre o inverso: impressora sem papel aqui não
pode deixar a cozinha sem comanda nem agora nem quando a fila sincronizar.

Antes desta versão a escolha era feita **antes** do POST, olhando o último
estado conhecido da rede. Com o PDV offline-first toda escrita passa pela fila,
e esse estado podia estar velho — o resultado era exatamente um dos dois erros.

### Só o item novo

A comanda leva apenas os itens em `pending`, capturados pela tela antes do
envio. O backend faz o mesmo do seu lado: `send_order_to_kitchen` monta o lote
com os itens ainda não enviados e marca-os como `sent`. Lançar A, enviar,
lançar B e enviar de novo imprime A e depois B — nunca A duas vezes.

### Cancelamento

Segue a mesma regra da comanda: se a operação de `void` chegou ao servidor, ele
cria o cupom (`register_kitchen_item_cancellation_jobs`) e o agente imprime; se
ficou na fila, quem imprime é o terminal, nas impressoras do setor do produto.

Só vale para item **já enviado à produção** — antes disso, cancelar é apenas
tirar da conta. Sem o cupom, o prato continuaria sendo feito depois de o
cliente desistir.

### A fila de impressão é local

A fila de trabalhos sempre viveu no backend: o agente perguntava
`/print-jobs/` e imprimia o que viesse. Com a internet fora não havia o que
perguntar — e nada saía no papel, nem um cupom montado aqui mesmo. Pior: uma
impressora sem papel simplesmente engolia o trabalho, porque não existia nada
guardando o que faltava imprimir.

Agora existe `print_queue`, no SQLite do terminal, alimentada por duas fontes e
drenada por um executor só:

```text
cupom montado aqui ──┐
                     ├──▶ print_queue (local) ──▶ impressora
PrintJob do servidor ┘         │
                               └──▶ mark-printed (quando houver rede)
```

| Situação | O que acontece |
| --- | --- |
| Impressora sem papel, cabo solto, equipamento desligado | Volta para a fila com espera crescente: 5s, 15s, 30s, 1min, 2min (o teto se repete). Sai sozinho quando o papel volta. |
| Erro que repetir não resolve (sem conteúdo, impressora sem endereço) | `FAILED`: sai da rotação e fica visível para revisão. |
| Papel saiu, `mark-printed` não passou | Fica `PRINTED` **no disco** e não volta a imprimir. A confirmação espera a rede. |
| Cupom com mais de 12 h | Expira. Uma comanda de ontem saindo hoje confunde a cozinha mais do que ajuda. |

Três detalhes que evitam papel duplicado:

- **`remote_job_id` é único por escopo.** Enquanto o `mark-printed` não é
  aceito, o trabalho continua `pending` no servidor e volta a aparecer na
  consulta seguinte — sem essa chave, ele entraria de novo na fila.
- **A reserva (`lease`) é por processo.** O PDV e a janela da Balança Rápida
  compartilham o banco; sem ela, os dois pegariam o mesmo trabalho.
- **O estado `PRINTED` vive no disco.** Antes essa memória era um conjunto em
  RAM que se perdia ao fechar o PDV — e o cupom saía de novo na abertura
  seguinte.

A fila gira por conta própria a cada 20 segundos, com ou sem rede. É isso que
faz um cupom que falhou por falta de papel sair assim que o papel volta, sem
depender de um evento do servidor que, offline, nunca chega.

**Caminho degradado:** se o banco local não abrir (disco cheio, arquivo
corrompido), o agente volta a imprimir direto do servidor, como antes da fila.
Um restaurante com internet funcionando não pode ficar sem imprimir também por
causa disso — o PDV já avisou do problema na inicialização.

### Cupons montados no terminal

O backend renderiza os cupons (`apps/printers/services.py`). Sem internet não
há renderização — e o cliente continua com a mão estendida esperando o
comprovante. `LocalPrintRenderer` monta os mesmos cupons no terminal:

| Cupom | Espelha |
| --- | --- |
| Recibo do cliente | `_customer_receipt_text` |
| Cupom de cancelamento | `_kitchen_cancellation_text` |
| Nota de pesagem | `_weigh_ticket_text` |
| Nota de teste | `register_printer_test_job` |
| Comanda de cozinha | `_kitchen_ticket_text` (já existia em `OrderPresenter`) |

As larguras (42 colunas no cupom, 32 na comanda), a ordem das linhas e a coluna
do valor são as mesmas de propósito: o mesmo pedido impresso online e offline
tem que sair igual no papel. **Se o cupom do backend mudar, este muda junto** —
há teste fixando o formato.

O terminal só assume a impressão quando a operação **não chegou** ao servidor,
e sempre reivindicando antes (ver acima). Nos três casos onde isso vale —
comanda de cozinha, cancelamento e nota de pesagem — o corpo enfileirado leva
`offline_printed: true`, e o backend cria o `PrintJob` já impresso: a auditoria
continua completa e o papel não sai duas vezes.

### Pesagem sem servidor

A leitura do peso sempre foi local (porta serial). O que dependia da API era
transformá-la em item: sem isso o buffet pesava e ninguém conseguia cobrar.

Offline, o terminal acha a comanda na cópia local, abre ou retoma o pedido dela,
lança o item pesado e os extras, recalcula e imprime a nota — **uma** operação
na fila, não uma por item: o servidor executa o `checkout-command` inteiro no
replay, e lançar cada item separadamente duplicaria tudo.

Como não existe `ScaleReading` (criá-la exige servidor, e registrar depois um
peso "de antes" seria inventar uma leitura que nunca aconteceu naquele
instante), a operação leva o **peso bruto**. O backend materializa a leitura no
replay — é a mesma simetria de `client_batch_serial` na comanda de cozinha.

Online nada muda: é o servidor que liga a leitura ao item, numera o pedido e
renderiza a nota. Esta é uma das duas rotas em que o local é *alternativa*, não
primeiro caminho.

### Autorização de caixa sem servidor

Um caixa que fecha com diferença precisa da senha de ações do restaurante. O
terminal já sabia conferir essa senha sem rede — ele guarda o hash PBKDF2 no
cofre do sistema. Faltava o servidor reconhecer a autorização no replay.

A senha em texto **não** entra na fila. O terminal prova que possui o hash
devolvendo um HMAC-SHA256 dele sobre `{cash_register_id}:{nonce}`, e o backend
recompõe o mesmo valor a partir do hash que guarda. Guardar a senha em disco
seria pior do que a espera que a autorização offline evita.

Online, o comportamento é o de sempre — inclusive o login de um gerente, que
só o servidor sabe validar. Esta é a outra rota em que o local é alternativa.

### Impressão no Caixa Secundário

A configuração é central; a execução é de quem alcança o equipamento (§17,
§19). Um Caixa Secundário com impressora USB própria imprime dela, e o backend
externo nunca é necessário para isso.

### Impressão em nome de quem não tem impressora

O app do garçom não imprime nada por conta própria — ele manda o pedido para
o Caixa Principal (`RelayPrintFallback`,
`flutter/lib/features/topology/services/relay_print_fallback.dart`) e quem
decide se sai papel é o terminal que tem a impressora física.

A regra é a mesma usada em todo o resto do sistema (§17): a operação chegou
ao backend? Se chegou, o `PrintJob` de lá cuida da impressão. Se ficou na
fila, o Principal reivindica com `offline_printed` e imprime localmente,
montando a comanda por setor (`send-to-kitchen`) ou o cupom de cancelamento
(`items/<id>/void/`) a partir do próprio SQLite — sem depender de nenhum
estado de tela, porque quem mandou a operação pode não ter UI nenhuma.

Um Caixa Secundário continua se resolvendo sozinho, como na seção anterior.
O responsável só age quando a operação chega **sem** `offline_printed` já
marcado — ou seja, veio do app do garçom, ou veio de um Caixa Secundário que
alcançou o Principal rápido o bastante para se considerar "entregue" sem
saber que o Principal, por trás, estava sem internet para o backend. Nos dois
casos, a marca de reivindicação impede a mesma comanda de sair duas vezes.

## Nota de pesagem

A estação lista as impressoras ativas e permite selecionar a **impressora padrão daquela balança**. A escolha é persistida no campo `Scale.printer` por uma chamada `PATCH /scales/<id>/`. A impressora deve pertencer ao mesmo restaurante e, quando aplicável, à mesma filial. Não existe fallback genérico por restaurante: o backend não escolhe a primeira impressora disponível. Se a configuração for ausente ou inválida, a transação falha antes de consumir a leitura ou criar itens.

O trabalho `weigh_ticket` usa payload versão 2 e contém:

- identificação do restaurante;
- pedido e comanda;
- todos os itens ativos do pedido, inclusive extras;
- subtotal e total recalculados;
- metadados de Code 128 da comanda;
- representação em texto e HTML.

O HTML incorpora o Code 128 como imagem PNG em data URI. Para impressoras com driver `escpos`, o agente local gera o comando `GS k` em Code 128 conjunto B quando o valor é ASCII imprimível e cabe no comando. Isso vale para conexões TCP e seriais. Para spool do Windows, drivers não ESC/POS ou valores incompatíveis, o código permanece como texto explícito; essa rota não imprime barras reais por conta própria.

O agente consulta jobs `pending` e `rendered`, envia o conteúdo para a impressora configurada e chama `mark-printed`. Falhas são reportadas por `mark-failed`. As conexões suportadas pelo agente são:

- fila de impressão do Windows por nome (`Out-Printer`);
- TCP/IP, porta 9100 por padrão;
- porta serial com baud rate configurável.

Notas de pesagem são processadas automaticamente mesmo quando `auto_print` da impressora está desativado; os outros tipos de job respeitam esse campo.

## Caixa Secundário e aplicativos: fila e cópia local próprias

A mesma arquitetura vale nos três níveis. Muda só **para onde a fila entrega**:

```text
Aplicativo do garçom ──fila──▶ Caixa Principal ──fila──▶ BACKEND
Caixa Secundário ─────fila──▶ Caixa Principal ──fila──▶ BACKEND
```

Nenhum dos dois fala com a nuvem, nem para ler (§8, §9).

### Caixa Secundário

O secundário tem **o mesmo núcleo do principal**: SQLite próprio, gravação
local, fila com reserva, retentativa e chave de idempotência. A única diferença
é o transporte: `RelaySyncTransport` entrega ao Caixa Principal pela rede
local, no lugar do `ApiClient` que entrega ao backend.

Antes ele não tinha fila nenhuma. Com o principal fora do ar, cada operação era
recusada na hora e o operador ficava sem vender até alguém religar o outro
computador. Agora:

- **escrita**: grava no SQLite do próprio terminal e enfileira; a tela responde
  na hora e a operação sobe quando o principal voltar;
- **leitura**: sai do SQLite do próprio terminal, que é alimentado pelo
  principal — com o principal fora, o secundário continua consultando o
  cardápio, as mesas, as comandas e os pedidos que já tinha recebido;
- **retentativa**: mesma escada (5s, 15s, 30s, 1min, 5min);
- **entrega ambígua** ([`MutationRelayUncertain`]): volta para a fila. O
  principal guarda um recibo por `operation_id`, então repetir devolve a
  resposta original em vez de criar uma segunda venda;
- **recusa do principal** (409, 400): vira pendência para revisão, não
  retentativa infinita.

O secundário só aceita gravar o que o principal sabe executar
(`OfflineMutations.isRelayable`). Abrir caixa, por exemplo, não entra: aceitar
deixaria o operador com uma operação salva que nunca teria como ser entregue.

O principal também **não entrega tudo**: configuração fiscal, perfis fiscais,
usuários, papéis e filiais ficam de fora (`sharedWithSecondary: false`). Um
terminal ou tablet no salão não precisa do CSC da NFC-e nem da lista de
usuários da conta.

### Aplicativo do garçom

O aparelho já guardava as escritas pendentes (`RelayGateway` +
`OfflineQueueStore`, arquivo JSON com escrita atômica). O que faltava era a
leitura: sem o principal, a tela ficava vazia — nem a comanda aberta há um
minuto o garçom conseguia abrir.

O `PrincipalCache` guarda as últimas respostas confirmadas pelo principal,
indexadas por rota + filtros, com carimbo de tempo, teto de 120 entradas e
descarte da mais antiga. Sobrevive a fechar o app; um arquivo corrompido é
descartado em vez de travar a abertura.

Ele **não finge que o dado é atual**. Toda resposta servida dali vem marcada
(`_from_cache`, `_cached_at`), e a tela mostra a faixa "Caixa Principal fora do
ar. Dados de HH:MM — pode ter mudado", em vermelho depois de 30 minutos. É o
aviso que evita o erro mais caro do modo offline: lançar um item sobre um
pedido que outro terminal já fechou.

Duas exceções deliberadas:

- **Sem cache e sem principal, a leitura falha** com o motivo na tela. Fingir
  que está tudo bem é pior do que dizer que o caixa não respondeu.
- **A sessão de caixa nunca vem do cache.** Um caixa "aberto" segundo uma cópia
  velha pode já ter sido fechado, e aceitar isso autorizaria um recebimento em
  dinheiro numa sessão que não existe mais. Sem principal, a forma dinheiro
  simplesmente não aparece; as outras continuam.

O cache pertence a um operador e a um pareamento: sair da sessão ou trocar de
Caixa Principal o esvazia, para o próximo garçom não ver os pedidos do turno
anterior como se fossem os dele.

## O que o aplicativo do garçom faz

- abrir pedido por comanda, balcão, delivery e retirada;
- vincular e trocar a mesa da comanda (`table_id`, o campo que o backend
  valida);
- lançar e cancelar item;
- enviar para a cozinha — quem imprime é o principal;
- **fechar a conta** (taxa de serviço e desconto);
- **receber**, em qualquer forma de pagamento cadastrada.

Cada recebimento nasce com `client_payment_id` no aparelho. É a chave que o
backend usa para deduplicar: um reenvio depois de um timeout devolve o mesmo
recebimento em vez de cobrar duas vezes.

O que continua sendo só do caixa físico: gaveta, impressora fiscal e o
recebimento em espécie fora de uma sessão aberta.

## Windows e Ubuntu

O mesmo código roda nos dois. O que muda é onde ficam os dados, onde ficam as
credenciais e como se fala com a impressora.

| Assunto | Windows | Ubuntu |
| --- | --- | --- |
| Dados | `%LOCALAPPDATA%\StarChef` (`%APPDATA%` como alternativa) | `$XDG_DATA_HOME/StarChef`, senão `~/.local/share/StarChef` |
| Banco operacional | `pdv_operational.sqlite` no diretório acima | idem |
| SQLite | biblioteca do pacote `sqlite3` | `libsqlite3.so.0` do sistema (presente em qualquer Ubuntu Desktop) |
| Credenciais | DPAPI via `flutter_secure_storage` | Secret Service (`libsecret`) **e** cópia em `<dados>/StarChef/secure` com `0700`/`0600` |
| Fila de impressão do SO | `Out-Printer` | `lp` (CUPS) |
| TCP 9100 e serial | idênticos | idênticos |
| Servidor local | porta ≥1024, sem privilégio | porta ≥1024; liberar no firewall (`sudo ufw allow <porta>/tcp`) |

Cuidados que o código já toma, e por quê:

- **Nada de `json_extract`.** A filtragem local não usa a extensão JSON1;
  colunas indexadas resolvem os filtros comuns e o restante é filtrado em
  Dart. Assim o comportamento não depende de como o SQLite da máquina foi
  compilado.
- **`PRAGMA busy_timeout = 5000`.** O PDV e a janela da Balança Rápida são dois
  processos sobre o mesmo arquivo. Sem espera, uma gravação simultânea
  devolveria `SQLITE_BUSY` na hora e a venda falharia por um bloqueio de
  milissegundos.
- **Sem cofre, sem cifra.** Numa instalação Linux sem Secret Service
  (autostart sem GNOME Keyring/KWallet), cifrar com uma chave que se perde no
  próximo boot seria pior do que não cifrar: a configuração fiscal ficaria
  ilegível e o terminal não emitiria nota nenhuma. O `PayloadCipher` degrada
  para texto puro e registra `cofre_indisponivel_payload_sem_cifra` — corrija a
  instalação (`libsecret-1-0` e um keyring desbloqueado) em vez de conviver com
  o aviso.
- **Registro ilegível não derruba a tela.** Se a chave mudar entre
  reinstalações, o registro afetado é pulado com log e volta na próxima
  sincronização, em vez de esvaziar o cardápio sem explicação.
- **Todos os caminhos de arquivo usam `Platform.pathSeparator`**, e os nomes de
  arquivo e de import são minúsculos — o sistema de arquivos do Linux
  diferencia maiúsculas.
- **Todo carimbo de tempo persistido é UTC.** A comparação entre a versão local
  e a do servidor não pode depender do fuso da máquina.

## Runbook de instalação e operação

### 1. Preparar o backend

1. Cadastre o restaurante, produtos e comandas.
2. Cadastre uma impressora ativa com conexão `windows`, `network` ou `serial`.
3. Cadastre a balança ativa com porta, baud rate em `settings.baudrate`, protocolo em `settings.protocol` (`generic`, `toledo`, `filizola` ou `urano`) e produto por kg. A impressora pode ser vinculada no cadastro ou no seletor “Impressora padrão da balança” da estação.
4. Confirme que usuário e token possuem permissão para usar/gerenciar dispositivos, operar balança e pedidos. Alterar a impressora persistida é uma alteração do cadastro da balança.

### 2. Preparar o terminal

1. Instale a impressora no sistema (fila do Windows ou CUPS no Linux) ou confirme IP/porta serial conforme o tipo escolhido.
2. Conecte a balança e valide qual porta foi atribuída (`COM3`, `/dev/ttyUSB0`, …).
3. Para leitor dedicado, configure o equipamento em modo serial/USB-CDC, com terminador CR ou LF. Leitores em modo teclado HID não aparecem no seletor serial.
4. Garanta que balança, leitor e impressora serial não disputem a mesma porta.
5. Em Configurações → Preferências deste terminal, ajuste o tempo da comanda, a tolerância de estabilidade e os alertas conforme o balcão. Essa tela também lista as portas seriais detectadas, útil para conferir o passo 2.
6. **Defina o papel do terminal** em Configurações → Rede local de caixas. O primeiro terminal da loja deve ser marcado como **Caixa Principal**; até isso ser feito, ele não grava nada. Para os demais, marque **Caixa Cliente** e informe o IP e a chave de pareamento do principal (as duas aparecem na tela dele).

### 3. Aquecer o cache

Entre no PDV com rede disponível e carregue o restaurante/cardápio ao menos uma vez. Um terminal iniciado offline sem cache prévio não consegue obter o catálogo. Se houver caixa aberto, essa primeira entrada também guarda a sessão de caixa, que passa a ser restaurada em um reinício sem rede. A sessão de usuário precisa ter sido salva no cofre local para ser restaurada pela janela independente.

### 4. Iniciar a estação

1. Abra Balança Rápida pela barra lateral; cada clique bem-sucedido cria outro processo. A leitura do peso não depende mais do processo principal ficar aberto — só a impressão depende, porque a fila de impressão roda nele.
2. Escolha o restaurante e a balança. O cartão de configuração mostra a porta, o baud rate e o protocolo que serão usados.
3. Use a configuração de leitor para escolher a COM e o baud rate do scanner e clique em “Vincular e testar”.
4. Inicie a estação, pese, selecione extras e leia a comanda. O fluxo normal não pede toque na tela.

### 5. Diagnóstico rápido

| Sintoma | Verificação |
| --- | --- |
| `Offline` | API, DNS/rede e timeout; operações físicas não têm fallback local |
| "O Caixa Principal está indisponível" em um secundário | rede local, IP do principal e se o terminal principal está aberto. O secundário lê da cópia local, mas por decisão de projeto não grava sem ele |
| `Permissão insuficiente` logo ao abrir | era o sintoma de token expirado tratado como 403; hoje o servidor responde 401 e o terminal renova sozinho. Se persistir, o usuário realmente não tem conta/perfil vinculado |
| `Instável` | HTTP 408/425/429/5xx; aguarde o `Retry-After`/backoff automático |
| `Revisar` | clique no badge para abrir a fila, ver o motivo da recusa e decidir entre reenviar ou descartar |
| "Este pedido ainda não está salvo neste terminal" | o pedido não estava na página guardada. Abra a tela de Pedidos com rede ao menos uma vez; o PDV também guarda os 50 mais recentes sozinho a cada abertura |
| "Editando com os dados salvos localmente" | aviso normal offline: o pedido veio da cópia local e pode não refletir alterações feitas em outro caixa |
| sem leitura de peso | use "Pegar peso da balança": ele reabre a porta e envia o pedido `ENQ`, cobrindo equipamento em modo sob demanda e canal caído. Persistindo, confira COM, baud rate e protocolo |
| peso nunca estabiliza | tolerância (`scale_stability_tolerance_kg`), `auto_print_delay_seconds` e vibração na bancada |
| valor lido errado por 1000× | protocolo incorreto; confira se o equipamento transmite gramas ou quilos |
| `Porta ocupada` na balança | o cartão informa qual janela detém o equipamento; feche-a ou escolha outra balança |
| leitor não aparece | dispositivo em modo USB-CDC/serial e driver que exponha uma COM |
| porta do leitor ocupada | feche a outra janela/processo ou remova o vínculo anterior |
| checkout recusado | comanda ativa, permissão e API online |
| Balança Rápida abre no login no Ubuntu | use um pacote que contenha a transferência efêmera de sessão; confira permissão de escrita em `~/.local/share/StarChef` e a presença do comando `chmod` |
| PDV principal abre deslogado no Ubuntu | confira o dono de `~/.local/share/StarChef`, nunca execute com `sudo`; instale `libsecret-1-0` e um Secret Service. O fallback fica em `secure/` com modo `0700/0600` |
| chave/hash do Caixa Principal muda após reiniciar | confira se `secure/` pertence ao mesmo usuário que inicia o PDV e procure `secure_fallback_*`/`secure_native_*` em `pdv.log` |
| impressão não sai | processo principal aberto, impressora vinculada à balança, ativa, endpoint/IP/COM e job no backend |
| barras não aparecem | usar driver ESC/POS por TCP/serial; spool do Windows recebe fallback textual |

Os eventos de operação ficam em `<dados>\StarChef\pdv.log`, um JSON por linha,
com uma rotação. Senhas e tokens são mascarados antes da gravação.

Para copiar os bancos locais como diagnóstico, encerre todas as instâncias do aplicativo antes da cópia. O projeto não implementa um comando próprio de snapshot/backup desses arquivos.

## Validação antes de liberar um terminal

Execute as verificações automatizadas do projeto:

```powershell
Set-Location flutter
flutter analyze
flutter test
flutter build windows

Set-Location ..\backend
pytest
python manage.py check
```

A suíte cobre, entre outros pontos, o banco operacional (transação única entre entidade e fila, paginação local, versão, exclusão lógica, origem LOCAL/REMOTE), a fila de sincronização (FIFO, dependência entre operações, reserva, backoff, erro temporário x definitivo, descarte em cadeia), o roteamento offline-first (venda completa sem rede, turno de caixa, venda a peso, fila fiscal, rotas que exigem servidor), a sincronização paginada e incremental, o WebSocket gravando no SQLite, a API local `/local/...` do Caixa Principal, a fila do Caixa Secundário contra o principal (ordem, chave repetida, entrega ambígua, recusa), a cópia local do aplicativo do garçom (marcação, expiração, sessão de caixa nunca vinda do cache), a decisão de quem imprime a comanda de cozinha, o formato dos cupons montados no terminal (recibo, cancelamento, nota de pesagem e teste), a pesagem fechada sem servidor, a autorização de caixa por prova HMAC, a fila de impressão local (retentativa, reserva, expiração, trabalho do servidor entrando uma vez só), a durabilidade das credenciais sem cofre e sem `chmod`, o isolamento do app do garçom em relação à nuvem, a cifra dos payloads sigilosos, exclusão de cache/fila para ações físicas, widgets do PDV em larguras compactas, persistência/unicidade do vínculo de scanner, framing CR/LF, bytes Code 128, atomicidade do ticket de pesagem, decodificação dos quatro protocolos de balança, resolução de estabilidade e disputa de porta no leitor serial, a máquina de estados hands-free (incluindo timeout, alerta, cancelamento e preservação da venda em caso de falha), persistência das preferências e o botão de fechar de todo alerta global.

No terminal que irá para produção, faça também a homologação física:

1. Abra duas janelas e vincule leitores diferentes; confirme que uma COM já reservada é recusada.
2. Aponte duas janelas para a mesma balança e confirme que a segunda informa qual janela detém o equipamento.
3. Troque o equipamento que ocupa uma COM e confirme que VID/PID/serial divergentes exigem novo vínculo.
4. Com o modelo real de balança, compare o peso mostrado na estação com o do visor do equipamento em pelo menos três faixas (leve, média, próxima da capacidade) e confirme que o protocolo escolhido não erra a escala.
5. Retire e recoloque o prato repetidas vezes e confirme que a estabilização não dispara antes do tempo nem trava.
6. Imprima uma comanda conhecida, leia as barras impressas de volta e compare o valor.
7. Interrompa a rede durante uma mutação permitida e durante um checkout de balança; a primeira deve ficar pendente e a segunda deve ser recusada sem perder a pesagem.
8. Deixe a comanda sem ler até o timeout e confirme o alerta, o período de confirmação e o retorno ao Estado 1.
9. Simule falha da impressora e confira a transição do `PrintJob` e a retomada após corrigir o equipamento.

## Limitações atuais e trabalho futuro

1. **A topologia é principal/secundário, sem descoberta nem failover.** Todo terminal é Caixa Principal ou Caixa Secundário — o modo independente foi removido, porque dois terminais sincronizando cada um por conta própria com a nuvem é a raiz da divergência. Um terminal recém-instalado sobe como **secundário sem principal definido** e fica bloqueado para escrita até alguém dizer qual é o seu papel. A chave de pareamento já vem gerada, então promover o primeiro terminal a Caixa Principal é um clique. O principal só aceita conexões da rede local, atende leitura (`/v1/read`, `/local/...`) e escrita (`/v1/relay`, `/local/...`) e é o único que fala com a nuvem. **Se o principal cair, o secundário continua vendendo** — grava no próprio SQLite e enfileira para ele — mas trabalha sobre a última cópia recebida: um pedido aberto em outro terminal depois da queda não aparece. O que continua não existindo: descoberta automática na LAN (o IP do principal é configurado à mão), eleição de nó e failover.
2. **Existe pull incremental, mas não endpoint de batch.** A entrada usa `?updated_after=&include_deleted=1` por tipo, então uma reconexão não rebaixa a base inteira. A saída continua sendo até 20 requisições individuais por ciclo — não há endpoint que aceite um lote de operações.
3. **Offline cobre a operação inteira, do turno ao recebimento.** Funcionam sem rede: catálogo, pedidos (lista e detalhe), clientes, itens, vínculo de mesa da comanda, fechamento, envio à cozinha, pagamento, venda a peso e **abertura, sangria, suprimento e fechamento de caixa**. Tudo entra na fila e sobe depois, com a deduplicação do backend impedindo cobrança dupla. Continuam exigindo servidor: impressão do backend e o `checkout-command` da balança — a *leitura* do peso é local, mas transformá-la em pedido envolve resolver comanda, consumir a leitura e recalcular o pedido em uma transação. O cabeçalho mostra "Caixa (offline)" quando a sessão foi lida do banco local sem conseguir confirmar com o servidor; o estado pode ter mudado em outro terminal nesse intervalo.
4. **A resolução de conflitos é por registro, não por campo.** Cada entidade tem `version`, `source` e `sync_status`, e o `ConflictResolver` decide entre a cópia local pendente e a versão do servidor. O que não existe é merge campo a campo nem uma interface para o operador conciliar duas alterações concorrentes: a alteração local pendente simplesmente vence até subir.
5. **Idempotência é garantida por um middleware genérico.** `IdempotencyMiddleware` guarda, na mesma transação da operação, a resposta produzida para cada `Idempotency-Key` por conta. Um reenvio devolve a resposta original sem executar nada, e a mesma chave usada para outra requisição é recusada com 409. Só respostas de sucesso são memorizadas — um erro precisa poder ser repetido depois que a causa for corrigida. Rotas de autenticação são isentas.
6. **Consumidores da fila têm reserva por lease.** `sync_queue.lease_owner`/`lease_until` impedem que o PDV e a janela da Balança Rápida enviem a mesma operação. A reserva expira em 30 segundos: um processo encerrado no meio do envio libera a operação, e a deduplicação do backend é o que garante que o reenvio não duplique.
7. **A revisão da fila existe, mas a correção é indireta.** Clicar no badge (ou Configurações → Operações pendentes) abre a lista com o motivo da recusa e o payload completo, e permite reenviar ou descartar item a item. O que ainda não existe é editar o payload na própria tela: a causa precisa ser corrigida no cadastro (comanda, caixa, produto) antes de reenviar.
8. **O scanner dedicado cobre somente serial/USB-CDC.** Não há captura exclusiva de HID, filtro de eventos HID por VID/PID ou claim nativo de um leitor em modo teclado.
9. **A força da identidade depende do hardware/driver.** VID, PID e serial persistidos são revalidados, mas um leitor que não exponha esses campos fica identificado apenas pela COM e pelos metadados disponíveis.
10. **Só a fila do sistema de impressão depende da plataforma.** Balança, leitor de comanda e impressora serial usam `flutter_libserialport`, e a impressora de rede usa socket puro — tudo isso funciona igual em Windows e Linux. A fila do sistema operacional é a única rota com ferramenta externa: `Out-Printer` no Windows e `lp` (CUPS) no Linux, que precisa estar instalado e com a impressora registrada.
11. **Os protocolos de balança cobrem o enquadramento documentado, não todo firmware.** Toledo, Filizola e Urano têm variações por modelo e configuração; o modo `generic` é o mais tolerante. A escolha errada pode produzir peso 1000× maior ou menor, então a conferência contra o visor do equipamento é obrigatória antes de liberar o terminal.
12. **A trava de periférico é por máquina.** Ela impede a disputa entre janelas do mesmo computador. Duas máquinas ligadas fisicamente à mesma balança continuam sendo um problema de instalação, não algo que o software detecte.
13. **Impressão não é exatamente uma vez, mas erra para o lado seguro.** A fila local guarda `PRINTED` no disco, então um `mark-printed` que não passa não faz o cupom sair de novo — nem depois de fechar o PDV. O que ainda pode duplicar é o caso raro de a impressora aceitar os bytes e o papel não sair (guilhotina travada, fim de bobina no meio): aí o trabalho é dado como impresso. A reimpressão do último cupom é explícita e não cria outro pedido.
14. **Code 128 visual depende da rota.** HTML contém a imagem; ESC/POS TCP/serial recebe barras reais para ASCII compatível; a fila do Windows usa texto e depende de evolução futura para renderização gráfica confiável.
15. **A operação diária não depende da API; o cadastro e os relatórios dependem.** Vender, receber, abrir e fechar caixa, pesar, autorizar divergência e imprimir funcionam com a internet desligada. Cadastrar produto, conferir relatório e o **primeiro** login de um operador neste terminal continuam exigindo servidor.
16. **Hardware real ainda precisa de homologação.** O comando Code 128, os baud rates, os protocolos de balança e os fluxos de reserva possuem testes automatizados ou validação de código, mas o resultado final varia por firmware, driver, página de código e modelo de impressora/leitor/balança.
17. **O app do garçom recebe, mas não emite nota nem abre gaveta.** Ele fecha a conta e registra recebimentos pelo Caixa Principal, mas a NFC-e, o cupom fiscal e a gaveta continuam no caixa físico. Recebimento em dinheiro exige uma sessão de caixa aberta no principal.
18. **A emissão fiscal offline é adiada, não contingenciada.** A venda conclui e o documento fica `PENDING` na `fiscal_queue` até a conexão voltar. O PDV **não** emite em contingência offline (modelo 9) por conta própria nem imprime DANFE sem nota autorizada — isso depende do provedor fiscal e das regras do estado, e cabe ao backend decidir.
19. **O escopo depende das claims do JWT.** Tokens sem `account_id`, `user_id` e `sub` caem no namespace genérico `authenticated`; nesse caso, contas distintas na mesma base URL não ficam isoladas pelo identificador do token.
