# StarChef PDV Desktop (Flutter) — Guia Completo

> **Nesta branch (`release/v3.0.0`) não existem `flutter/` nem `flutter_garcom/`.**
> Eles foram substituídos por `pdv_desktop/` (PDV Windows/Linux) e
> `pdv_mobile/` (atendimento móvel), que falam direto com o backend, sem
> operação offline. As pastas antigas seguem nas outras branches.


> App desktop Windows em Flutter: PDV principal + janela "Balança Rápida", offline-first, cliente da mesma API do [`BACKEND.md`](BACKEND.md). Este documento é a porta de entrada — para a arquitetura offline/balança em profundidade veja [`PDV_OFFLINE_SCALE_ARCHITECTURE.md`](PDV_OFFLINE_SCALE_ARCHITECTURE.md), e para a referência técnica módulo a módulo veja [`FLUTTER_PDV_TECNICO.md`](FLUTTER_PDV_TECNICO.md).

## 1. Stack tecnológica

| Camada | Tecnologia |
|---|---|
| Framework | Flutter (desktop Windows) |
| Estado | `ChangeNotifier` + `setState` (decisão deliberada — não BLoC; o app já usava esse padrão) |
| Janela nativa | `window_manager` |
| Banco local | `sqlite_async` com migrations próprias (decisão deliberada — não Drift) |
| Sessão segura | cofre do SO + fallback Linux protegido por usuário (`0700`/`0600`) |
| HTTP | `http` |
| Hash/criptografia | `crypto` (PBKDF2-HMAC-SHA256, formato do Django, para senha de caixa offline) |
| Porta serial (balança) | `flutter_libserialport` |
| Observabilidade | `sentry_flutter` (opcional, via `PDV_SENTRY_DSN`) |
| Instalador | Inno Setup 6 |

## 2. Estrutura de pastas

```
flutter/
  lib/
    main.dart                  entry point único, decide modo PDV vs janela de balança
    app/
      starchef_app.dart          shell do app principal (PDV)
      scale_window_app.dart      shell da janela "Balança Rápida"
    core/
      config/app_config.dart     resolução de API_BASE_URL e PDV_SENTRY_DSN (dart-define / .env)
      network/                   api_client, offline_store, mutation_relay, realtime_client
      storage/                   session_store, local_preferences, app_paths
      hardware/scale/            protocolos de balança + transporte serial
      errors/                    error_center, app_error, app_error_host
      logging/app_logger.dart    log local estruturado
      security/cash_password.dart  verificação PBKDF2 offline
      widgets/                   copyable_error, responsive_scale, touch_keypad
    features/
      auth/                       login, sessão, renovação de token
      cash/                       autorização de caixa (PIN/senha), separada da auth de usuário
      devices/                    impressoras, agente local de impressão
      home/                       o PDV em si: catálogo, carrinho, checkout, navegação (home_page.dart)
      orders/                     listagem/detalhe de pedido, store local, motivos de cancelamento
      scale/                      "Balança Rápida" (fluxo hands-free de pesagem)
      settings/                   preferências por terminal
      sync/                       revisão da fila offline (outbox / dead-letter)
      topology/                   Caixa Principal / Caixa Cliente (relay de rede local)
  test/                         espelha lib/, ver §9
  windows/installer/            starchef_pdv.iss + build_installer.ps1
```

## 3. Como o app inicia (`lib/main.dart`)

Ordem de inicialização (única entry point para os dois modos):

1. `WidgetsFlutterBinding.ensureInitialized()`.
2. `AppConfig.load()` — resolve `API_BASE_URL` (prioridade: `--dart-define` → `.env` procurado subindo o diretório a partir do cwd e do executável → fallback `http://localhost:8000/api/v1`) e `PDV_SENTRY_DSN` pelo mesmo mecanismo.
3. `ScaleWindowLauncher.isScaleWindow(arguments)` — checa `--scale-workstation` nos argumentos para decidir o modo.
4. `LocalPreferences().load()` — antes do `runApp`, para não haver flash de tema.
5. `ErrorCenter()` criado; se a API caiu no fallback de localhost, reporta um aviso visível (`dedupeKey: 'api-url-fallback'`) — um terminal mal configurado não "funciona" apontando pra lugar nenhum em silêncio.
6. `FlutterError.onError` conectado ao `AppLogger` — nenhuma falha de UI desaparece sem log.
7. `windowManager` inicializado com o tamanho certo por modo (PDV `1280×800`, balança `1180×760`), título sem barra nativa (`titleBarStyle: hidden`).
8. `ApiClient` + `AuthRepository` (com `SecureSessionStore` e `CashAuthRepository`) criados.
9. `runApp(...)` — dentro de `SentryFlutter.init` se houver DSN configurada, senão direto.

Nenhum token é passado via linha de comando. No Windows, a janela restaura a
sessão do cofre do SO. No Linux, onde uma segunda instância pode não reler o
GNOME Keyring imediatamente, o PDV também cria uma transferência efêmera em
`~/.local/share/StarChef/scale-session-handoffs`: diretório `0700`, arquivo
`0600`, nome aleatório no argumento `--session-handoff` e conteúdo consumido e
apagado no boot da janela filha. O argumento nunca contém a sessão.

## 4. Autenticação e sessão

- **`features/auth/`** (`AuthRepository` + `AuthController`) — login, guarda o par access/refresh via `SecureSessionStore`. Windows usa o cofre do SO. No Linux, o Secret Service continua sendo a primeira opção, mas os valores também são espelhados em arquivos acessíveis somente ao usuário do PDV dentro de `~/.local/share/StarChef/secure`; isso evita perder a sessão quando GNOME Keyring/KWallet não está disponível no autostart.
- **Restauração no boot**: tenta `GET /auth/me/` com o token salvo; em 401, tenta `POST /auth/refresh/`; se o refresh for explicitamente recusado, limpa o cofre e volta ao login. Se **não houver resposta nenhuma** (sem rede), devolve a sessão salva como está — decisão deliberada para o terminal continuar operando offline em vez de deslogar por falta de conexão.
- **Venda nova zerada** (`_resetToNewSale` em `home_page.dart`): a mesma rotina depois de concluir o pagamento e em "Nova venda" limpa pedido, mesa, comanda, cliente, rascunho, recebimentos, valor e forma digitados, cupom, categoria e busca do catálogo (o campo é recriado vazio por `searchGeneration`) e devolve o foco à busca.
- **IP server local vindo da nuvem, no login** (PDV desktop e app do garçom,
  `features/auth/data/login_pela_nuvem.dart` nos dois). O IP do servidor da
  loja mora no cadastro do RESTAURANTE (`Restaurant.ip_server_local`, editado
  no painel). São **dois logins**: o primeiro, no **IP server nuvem** — fixo
  no build, `api.starchef.com.br` —, só lê `GET /pdv/config/` (IP server local
  e `ip_server_nuvem`, o `API_URL` do .env da nuvem) e tem o token descartado;
  usuário e senha só existem na memória durante o login. O segundo, no **IP
  server local**, é o que vale: a sessão e o erro mostrados são os dele. Sem
  IP local, o padrão é a nuvem (a informada ou a fixa). A config é um extra,
  nunca a porta de entrada: nuvem fora, recusando o usuário ou com erro → fica
  o IP guardado (antes, um usuário que a nuvem não conhecia não entrava nem
  com a loja respondendo). Loja FORA do ar → entra na nuvem; loja recusando a
  senha → o erro aparece. As idas do login usam clientes SEM o desvio
  automático para a nuvem: com ele, um "login na loja" fora do ar entrava na
  nuvem de produção e
  parecia ter entrado na loja. A tela "Servidores" (engrenagem) mostra o IP
  server nuvem (só leitura) e o IP server local (editável só para forçar
  outro neste aparelho).
- **Formas de pagamento da mais usada para a menos usada.** O PDV pede
  `/payments/methods/?ordering=-uso,name`: `uso` é a contagem de recebimentos
  APROVADOS dos últimos 90 dias (`backend/apps/payments/formas_por_uso.py`), e
  a primeira da lista é a que a tela de pagamento já abre selecionada. As
  duas consultas (catálogo e tela de pagamento) são idênticas, para dividir a
  mesma entrada de cache.
- **↑ e ↓ trocam a forma de pagamento** na tela de pagamento, dando a volta
  nas pontas (`forma_vizinha.dart`). Valem com o cursor no campo do valor,
  que não usa as setas (`PdvShortcut.insideTextField`).
- **"Calculando total..."** (`calculo_do_total.dart`): o CUPOM (e os ajustes
  do pedido que já existe, F9) passam por UM cálculo por vez. Enquanto
  ele está no servidor, "Adicionar pagamento" e "Concluir" mostram
  "Calculando total..." e não aceitam clique, Enter nem atalho; um segundo
  ajuste é recusado (duplo clique), a recusa deixa o total anterior e uma
  resposta de uma visita anterior à tela é descartada.
- **Carrinho só com o total.** Subtotal, taxa de serviço e desconto saíram do
  rodapé do carrinho: eles se decidem (e se mostram) na tela de pagamento, e
  ali roubavam espaço da lista de itens. O desconto é digitado na tela de
  pagamento (`payment_adjustments.dart`); quem não é gerente libera com a senha
  de ações do caixa. `order_discount_field.dart` guarda só a conversão de
  centavos usada por esse campo.
- **Autorização de caixa é separada da autenticação de usuário**: `features/cash/data/cash_auth_repository.dart` sincroniza (quando online) um hash PBKDF2 (formato Django) via `GET /restaurants/<id>/cash-auth/`, guardado localmente. `core/security/cash_password.dart` verifica a senha **offline**, sem round-trip ao servidor — é o que autoriza ações de caixa (cancelamento, desconto) mesmo sem internet.
- O hash é buscado uma vez depois da autenticação. Depois disso, o WebSocket
  envia somente uma invalidação segura quando a senha muda; o PDV relê o
  endpoint uma vez nesse evento ou numa reconexão, sem polling por tempo.

## 5. Arquitetura offline-first

> Resumo — a fundo em [`PDV_OFFLINE_SCALE_ARCHITECTURE.md`](PDV_OFFLINE_SCALE_ARCHITECTURE.md).

- **`OfflineStore`** (`core/network/offline_store.dart`, `sqlite_async`): cache de respostas GET (até 300 entradas, sem TTL — offline sempre entrega a última resposta conhecida) + uma **outbox transacional** de mutações pendentes, com retry, lease e mapeamento de ID temporário→real. Escopado por `origem-da-API | conta | usuário` (com fallback se claims do JWT faltarem).
- **`local_order_store.dart`** (em `features/orders/data/`) é separado do cache HTTP: guarda o pedido em edição para sobreviver a navegação sem ser sobrescrito por um GET em cache desatualizado.
- **Tela de pagamento, sem modal antes dela.** À esquerda, o **cupom** (campo
  de código com **Aplicar**/**Trocar** e **Retirar**, `payment_coupon_input.dart`,
  e os vigentes mais usados em botões logo abaixo, `coupon_suggestions.dart`)
  e o resumo, que mostra o que foi aplicado: taxa de serviço (ou
  "não cobrada"), desconto, cupom e "CPF/CNPJ na nota". À direita, abaixo do
  teclado (que se ajusta à altura que sobra), a **chave da taxa de serviço**,
  o **CPF ou CNPJ** (um campo só, reconhecido pelo tamanho) e o **desconto**
  em R$ (`payment_adjustments.dart` + `home_page_payment_ajustes.dart`). Na
  venda nova, taxa, documento e desconto são calculados NO PDV, na hora
  (`fechamento_local.dart`, `home_page_payment_ajuste_local.dart`): cada toque
  simulava a venda inteira no servidor (60 a 120 consultas) com a tela travada.
  A conta é a do servidor — dinheiro em centavos inteiros, taxa meio centavo
  para cima — e a tabela `test/fixtures/fechamento_paridade.json` é lida pelo
  teste do PDV e pelo do backend (`test_fechamento_paridade.py`). O CUPOM
  continua indo ao servidor (`simular`): limite, uso por CPF e grupo só o
  banco sabe. No pedido existente o `/close/` roda de novo. Desconto novo de
  quem não é gerente pede a senha de ações do caixa, conferida no PDV, e ela
  segue com a conclusão (`cash_password`), onde o servidor confere de novo. Com pagamento já
  lançado, taxa, documento e desconto travam. Todos os campos da tela têm a
  mesma altura (`payment_input_style.dart`, `alturaDoCampo`): com a fonte
  real o campo com ícone ficava mais alto que o sem ícone.
- **Fotos do catálogo**: cards de produto e opções de variante resolvem
  `logo_p`, com fallback para o campo legado `image`. O PDV não percorre
  `photo_list`. Sem URL, sem rede ou com
  falha de decodificação, o ícone padrão continua aparecendo e a venda não é
  bloqueada.
- **Idempotência**: toda mutação da outbox carrega um `Idempotency-Key`, consumido pelo `IdempotencyMiddleware` do backend ([`BACKEND.md`](BACKEND.md#4-appscore--infraestrutura-transversal)) — reenviar uma operação da fila offline não duplica venda.
- **`MutationRelay`** (`core/network/mutation_relay.dart`): usado por terminais "Caixa Cliente" (secundários) para encaminhar mutações ao "Caixa Principal" pela rede local, assinado HMAC-SHA256 (método, rota, timestamp, nonce, conta, operador, filial, corpo), protegido contra replay, só aceita origem LAN. Três desfechos: sucesso; `MutationRelayUnavailable` (nunca chegou a sair — seguro enfileirar localmente); `MutationRelayUncertain` (pode ter sido entregue — **nunca** reenfileira localmente, pra não duplicar venda; tenta confirmar via `GET /v1/operations/<id>` antes de desistir).
- **Topologia (Caixa Principal / Caixa Cliente)** (`features/topology/`): só dois papéis existem. Uma instalação nova sobe como secundária sem principal configurado e fica **bloqueada para escrita** até um humano atribuir os papéis — evita dois principais por acidente. Leituras também passam pelo principal (preferência: principal → nuvem → cache local); **escritas nunca caem para a nuvem direto** — se o principal está inalcançável, o secundário recusa a escrita em vez de arriscar divergência.
- **Outbox / dead-letter** (`features/sync/presentation/outbox_review_dialog.dart`): tela que traduz método+rota para o que a operação significa ("Item adicionado ao pedido"), mostra o motivo da recusa e o payload completo, oferece repetir ou descartar (descarte exige confirmação e vira log `warning`).

### 5.1 Cache de leitura do PDV online (`ResponseCache`)

Nesta branch o `pdv_desktop/` fala direto com o servidor, sem `OfflineStore`.
O que existe é um cache **de apresentação**, para a tela abrir na hora
(`core/network/response_cache.dart`, dentro do `ApiClient`):

- Guarda respostas GET de listas de cadastro (`/commands/`, `/menu/products/`,
  `/menu/categories/`, `/customers/`, `/tables/`, `/payments/methods/`,
  `/cash-stations/`, `/printers/`) e a **lista** de pedidos (`/orders/`, só
  para exibir). Caixa, autenticação e o pedido aberto nunca — nada do cache
  decide pagamento ou fechamento; o servidor valida.
- Chave: servidor + conta + usuário (do JWT) + rota + parâmetros ordenados.
  120 entradas no máximo (sai a mais antiga), validade de 24 h.
- **Gravado em disco** (`cache_de_listas.json`, `response_cache_disco.dart`): o
  PDV reiniciado abre com o catálogo na tela. O que volta do disco vem VELHO.
- Escrita, evento de tempo real e **reconexão** NÃO apagam: marcam o assunto
  como **velho**. A tela continua mostrando e relê em silêncio — apagar fazia o
  próximo gesto esperar o servidor, com tela de carregando, a cada venda e a
  cada oscilação da rede. Logout e troca de servidor apagam tudo.
- `loadCatalog` (`features/home/data/pdv_catalog.dart`) devolve o guardado na
  hora e relê por trás SÓ as listas velhas ou com mais de 10 s: depois de uma
  venda, comandas e mesas — não as seis. Se o servidor mudou, emite
  `realtime:pdv` e a tela redesenha. A tela de pedidos abre com a última lista.
- `PdvRepository.listCached` (impressoras) relê a lista VELHA antes de usá-la.
- Requisição que leva 500 ms ou mais vai para o `pdv.log` como `api_lenta`.

### 5.1.1 Desvio para a nuvem: 5 minutos, depois ping

`core/network/veredito_da_loja.dart` (igual no `pdv_mobile/`). A loja
confirmadamente fora manda o terminal para a nuvem por **5 minutos fixos**, e
nenhuma resposta da loja no meio desfaz (fiscal e caixa, que nunca desviam,
falam com ela). Fechar comanda também vai direto: o restaurante inteiro de um
lado só. Vencida a janela, a próxima requisição faz um **ping** na loja
(`CloudFallback.conferirSeVenceu`): respondeu, volta; não, mais 5 minutos.
Antes a janela começava em 30 s e qualquer resposta da loja a desfazia — o
terminal pulava de servidor no meio de uma venda.

### 5.1.2 A venda num envio só (`/orders/submit/`)

O pedido vive no rascunho do PDV até precisar existir, e então sai num payload
(`features/orders/data/order_draft_materializer.dart` →
`backend/apps/orders/venda_inteira.py`), numa transação: entra inteiro ou não
entra. Tudo leva o UUID do PDV (`draft.orderId`, o id de cada linha, o de cada
recebimento), então o reenvio é a MESMA venda.

- **F9 / cozinha** (o "pagar depois"): pedido + itens + comandas + produção.
- **Ir para o pagamento**: NÃO cria nada e não pergunta nada. A tela abre NA
  HORA com a conta feita no PDV (`previa_local.dart`: itens, taxa padrão,
  total), também com comanda quando a conta de todos os cartões já chegou;
  cartão com a conta ainda chegando, ou sem nada a cobrar, espera o servidor.
  `simular` roda em segundo plano só para avisar cedo de comanda já paga ou
  em outra conta — a conclusão não espera por ele (`draft.simulada`). Sair sem
  pagar não deixa nada no servidor. Enquanto a prévia está na tela, o tempo
  real não a relê (`pedido_na_tela.dart`): ela não existe no servidor.
- **Concluir**: pedido + itens + comandas + produção + fechamento (taxa, CPF,
  cupom) + recebimentos, num envio (`home_page_venda_inteira.dart`). Leva só
  as anotações que o caixa viu ao abrir o pagamento (`draft.anotacoesVistas` →
  `command_items`): o que o garçom lança enquanto o cliente paga fica para a
  próxima conta, em vez de fechar com total maior que o recebido. Leva também
  o total mostrado (`expected_total`): mudou no servidor, a venda é recusada
  sem gravar e a tela simula de novo, mostrando a conta de agora.
- Pedido que já existia (F9 antes): os recebimentos vão juntos num envio.

### 5.1.3 Recusa que leva ao lugar certo (`home_page_conflitos.dart`)

A recusa do servidor traz `code` e o pedido de destino
(`backend/apps/orders/conflitos.py` → `error.code`, `error.order_id`), e o PDV
age em vez de mostrar o erro — a decisão é `ConflitoDaVenda.decidir`
(`features/orders/data/conflito_da_venda.dart`, testada):

| Recusa | O PDV faz |
|---|---|
| `comanda_em_outra_conta` | abre a conta #42; itens passados no rascunho vão para ela num envio, e o "ir para o pagamento" segue com ela |
| `comanda_ja_cobrada` / `pedido_ja_pago` | abre o pedido pago; com itens novos no rascunho, só tira a comanda paga e segue com os itens |
| `total_mudou` | recalcula sozinho e diz em que pedido o resto foi cobrado |

Cada ação deixa um recado curto (barra inferior), não um alerta de erro.

### 5.2 Leitura do cartão da comanda

Comanda só abre por casamento EXATO de código ou número, ignorando zeros à
esquerda (`0017` é a 17, e só ela — `core/input/command_code_match.dart`). A aba
Comandas abria "a única comanda que sobrou na lista filtrada" quando nada casava
exato; com um texto antigo na busca, o cartão 17 abriu a 107. Antes de abrir, a
comanda achada é conferida com o código lido; não batendo, o PDV avisa e não
abre, e cada leitura vai ao `pdv.log` (`comanda_lida`). Nas telas que só leem
comanda, o número lido aparece em letras grandes enquanto ela carrega
(`core/widgets/scanned_command_overlay.dart`); na venda e na lista de pedidos,
onde o leitor também lê produto, só depois de saber que é comanda.

## 6. Hardware: balanças e impressoras

**Balanças** (`core/hardware/scale/`): `ScaleProtocol` decodifica o protocolo de quatro fabricantes — genérico (último número da linha), Toledo (STX…ETX), Filizola (gramas terminado em CR) e Urano (`+00.500kg`). Transporte via `flutter_libserialport` (`ScaleTransport`/`SerialScaleTransport`). `SerialScaleReader` resolve estabilidade (tolerância + tempo de assentamento + flag de movimento do protocolo), com watchdog de 4s e reconexão com backoff.

**A leitura da porta é do `LeitorSerialIsolado`** (`core/hardware/leitor_serial_isolado.dart`), e não da `SerialPortReader` da biblioteca: aquela encerrava o isolate de leitura com o `kill()` padrão, que nunca age num laço de chamadas nativas. O isolate seguia lendo a porta fechada; no Linux o descritor é reaproveitado pela porta reaberta (o "pegar peso" fecha e reabre) e, quando a memória da porta era liberada, o processo inteiro caía — a Balança Rápida fechava sozinha. Agora o kill é imediato e a porta só é fechada e liberada depois de o isolate sair. Balança e leitor de código de barras usam o mesmo leitor.

**A etiqueta de pesagem sai na própria Balança Rápida** (`features/scale/data/etiqueta_da_pesagem.dart`): o lançamento pede `imprime_aqui`, o trabalho nasce reservado (`claimed`) para o terminal da balança — fora da fila dos agentes dos PDVs — e a janela imprime e marca `printed`, ou `failed` com o motivo (Reimprimir tenta de novo). Antes qualquer PDV do restaurante podia reservá-lo, e um PC sem a impressora USB/serial da balança o pegava e a etiqueta não saía. Uma reserva presa (janela caiu) volta para a fila em 5 min.

**Impressão**: o backend **não gera** ESC/POS — só renderiza HTML e um payload de texto (ver [`BACKEND.md`](BACKEND.md#7-pedidos-pagamento-e-impressão)). Quem entrega fisicamente é `features/devices/services/local_device_agent.dart`, que recebe novos `PrintJob`s pela rota autenticada `/ws/pdv/<restaurant_id>/`, busca a fila pendente e imprime via rede (TCP 9100), serial ou spool do SO (fallback Windows), marcando `printed`/`failed` de volta na API. Ao conectar ou reconectar, faz uma única reconciliação para cobrir eventos perdidos; não há polling periódico da fila. `print_template_cache.dart` cacheia os templates localmente.

**Pergunta do DANFE** (`ask_print_danfe` do restaurante, `danfe_print_question_dialog.dart`): ligada, "Imprimir a NFC-e?" sai JUNTO com a venda (`startPaidOrderFollowUps` → `_decidirDanfe`), com a próxima venda já liberada — antes ela esperava a resposta do `/invoices/emit/`, que podia levar a SEFAZ inteira ou falhar. Sai depois da escolha de impressora da venda, para os dois modais não disputarem o mesmo Enter. ENTER imprime; ESC, Cancelar ou clique fora cancelam. A resposta é gravada com o número do pedido (`decisoes_do_danfe.dart`, arquivo `danfe_decisoes.json` do terminal, as últimas 50) e segue como `Future<bool>` para a emissão em segundo plano (`home_page_fiscal.dart`) e para o vigia da autorização (`home_page_fiscal_espera.dart`), que a esperam antes de mandar o DANFE; quem disse não também não recebe o aviso de "SEFAZ ainda não autorizou". Se o `/invoices/emit/` falhar, a nota é procurada pelo pedido (`nota_do_pedido.dart`) antes de o DANFE ser dado como perdido. A reimpressão manual não pergunta.

**Exclusividade de periférico**: `core/hardware/peripheral_lock.dart` usa um lock de arquivo (`RandomAccessFile.lock`) com um descritor ao lado (papel, PID, nome do dispositivo) — o SO já impede acesso serial concorrente, o lock existe pra identificar *qual* janela está usando o quê, e é liberado automaticamente pelo SO se o processo morrer.

## 7. Duas janelas, um executável

A janela "Balança Rápida" **não é um app separado** — `ScaleWindowLauncher.open()` relança o **mesmo executável compilado** (`Platform.resolvedExecutable`) como processo totalmente destacado (`Process.start(..., mode: ProcessStartMode.detached)`) com `--scale-workstation --restaurant=<uuid>` e, no Linux, o nome aleatório da transferência efêmera. Se a proteção da transferência ou o `Process.start` falhar, o PDV cai para uma visão embutida da estação de balança.

As duas janelas compartilham o mesmo arquivo `offline_data.sqlite` (o `sqlite_async` coordena múltiplos processos no mesmo arquivo) e o mesmo cofre de sessão do SO. No Linux, a transferência efêmera garante a primeira autenticação sem expor o token na linha de comando. Não há supervisor: se a janela de balança travar, nada a reabre sozinha (limitação conhecida, documentada — a fila de impressão/leitura não depende do processo principal continuar aberto).

## 8. Erros e logging

- **`ErrorCenter`** (`core/errors/error_center.dart`) — fila única de erros visíveis, no máximo 3 simultâneos, repetição da mesma falha renova o card em vez de empilhar.
- **`AppError`** — severidade (`info`/`warning`/`failure`), origem (`api`/`network`/`peripheral`/`localNetwork`/`application`), mensagem literal do backend preservada quando vem de erro de API, stack trace nunca exposto ao operador (só em `technicalDetails`, sob demanda).
- **`AppLogger`** — log local em JSON-por-linha, rotaciona em 2 MB, degrada para console se o disco encher (nunca derruba o caixa), mascara campos sensíveis (`password`, `token`, `pairing_secret`...).
- **Sentry** (opcional): inicializado só se `PDV_SENTRY_DSN` estiver configurada; sem ela, comportamento idêntico a hoje, sem telemetria remota — hoje o único jeito de diagnosticar um incidente em campo é coletar o `pdv.log` do terminal.

## 9. Configuração / variáveis de ambiente

Mesmo `.env` compartilhado com backend/frontend (raiz do monorepo — ver [`BACKEND.md`](BACKEND.md#10-configuração--variáveis-de-ambiente)):

- `API_BASE_URL` / `VITE_API_BASE_URL` / `VITE_BACKEND_TARGET` — de onde vem a URL da API (nessa ordem de prioridade quando absoluta).
- `PDV_SENTRY_DSN` — Sentry deste app (projeto separado do Sentry do backend/frontend — nome sem prefixo `VITE_` de propósito, pra não colidir com a variável `SENTRY_DSN` do backend no mesmo arquivo).
- `STAR_CHEF_ENV_PATH` (`--dart-define`) — sobrescreve a busca automática do `.env`.

Também pode ser tudo passado via `--dart-define` no lugar do `.env` (útil pra build de produção sem depender de um arquivo ao lado do `.exe`).

## 10. Configurações por terminal vs. por conta

`features/settings/presentation/terminal_preferences_dialog.dart` — o que é **do terminal** (armazenado localmente, `LocalPreferences`): tolerância de estabilidade, alertas sonoros e impressão automática. O timeout para ler a comanda (`Restaurant.quick_scale_command_timeout_seconds`) e o tempo de assentamento do peso (`Restaurant.quick_scale_stability_seconds`) são **do restaurante**, compartilhados por todas as balanças e terminais. Porta, baud rate, protocolo e limiar de zero continuam no cadastro do equipamento (`Scale`).

## 11. Como rodar em desenvolvimento

```bash
npm run dev:flutter          # a partir da raiz do monorepo — atalho para: cd flutter && flutter run -d windows
# ou, dentro de flutter/:
flutter pub get
flutter run -d windows
```

A janela de balança não tem script próprio de dev — clique em "Balança Rápida" no menu do PDV rodando, que relança o mesmo binário (debug, nesse caso) com `--scale-workstation`. O `.env` é procurado a partir da raiz do monorepo ou de `flutter/` (busca sobe até 8 níveis de diretório).

### Persistência no Ubuntu

O Linux desktop não apresenta uma permissão de armazenamento para o aplicativo
pedir como no Android. O PDV deve ser iniciado sempre pelo mesmo usuário normal,
sem `sudo`, com acesso ao próprio `~/.local/share/StarChef`.

`flutter_secure_storage` usa `libsecret` e um Secret Service como GNOME Keyring
ou KWallet. O pacote precisa de `libsecret-1-0` em runtime; quando o serviço de
chaves estiver bloqueado, ausente ou indisponível durante o autostart, o PDV usa
o fallback local protegido por modo `0700` no diretório e `0600` nos arquivos.
Sessão, hash de autorização offline e chave de pareamento compartilham esse
mesmo mecanismo resiliente.

Na inicialização, o PDV faz uma pequena gravação de teste nesse diretório. Se
ela falhar, um alerta permanente informa que login, fila offline e pareamento
não sobreviverão ao fechamento, incluindo o caminho que precisa ser corrigido.

Em Ubuntu/Debian, a instalação recomendada é:

```bash
sudo apt install libsecret-1-0 gnome-keyring dbus-x11
```

Para conferir o dono e as permissões sem expor os valores:

```bash
stat -c '%U %a %n' "$HOME/.local/share/StarChef"
stat -c '%U %a %n' "$HOME/.local/share/StarChef/secure"
find "$HOME/.local/share/StarChef/secure" -maxdepth 1 -type f -printf '%u %m %p\n'
```

Se alguma execução anterior com `sudo` tiver deixado a pasta como `root`, feche
o PDV e devolva a propriedade ao usuário da sessão:

```bash
sudo chown -R "$USER":"$USER" "$HOME/.local/share/StarChef"
chmod 700 "$HOME/.local/share/StarChef/secure"
find "$HOME/.local/share/StarChef/secure" -maxdepth 1 -type f -exec chmod 600 {} \;
```

O diretório `secure` deve pertencer ao usuário que abre o PDV e aparecer como
`700`; seus arquivos `.secret`, como `600`. Nunca execute o aplicativo uma vez
com `sudo`: isso pode criar dados pertencentes a `root` e impedir gravações nas
aberturas seguintes.

## 12. Build e release

```powershell
flutter build windows --release
.\windows\installer\build_installer.ps1
```

`build_installer.ps1` lê a versão de `pubspec.yaml` (`version: X.Y.Z+N`, usa só `X.Y.Z`) e passa como `/DAppVersion` ao `ISCC.exe` (Inno Setup 6) — assim a versão só existe em um lugar, não duplicada entre `pubspec.yaml` e `starchef_pdv.iss`. Requer Inno Setup 6 instalado (`ISCC.exe` no PATH ou em `Program Files (x86)\Inno Setup 6`). Saída em `artifacts/StarChef-PDV-Setup-<versão>.exe`.

**Detecção de instalação anterior**: `starchef_pdv.iss` (`[Code]`) lê a versão já instalada pelo mesmo `AppId` no registro (`DisplayVersion`, HKCU e HKLM) antes de instalar — se a versão instalada for igual ou mais nova que a do instalador, aborta com um aviso e não mexe em nada. Só deixa seguir quando é de fato um upgrade. `PrivilegesRequired=lowest` + `AppId` estável fazem o Inno reconhecer a instalação existente e reusar o mesmo diretório (`UsePreviousAppDir`, default do Inno).

**Sem assinatura de código** hoje — o Windows SmartScreen pode alertar o usuário na instalação; assinar exige um certificado de code signing, ainda não incorporado ao processo. **Sem auto-update** — a distribuição do binário para os terminais é manual.

### Cortando um release

1. Bump `version:` em `pubspec.yaml` (ex.: `1.4.0+7`) e mergeie na `main`.
2. `git tag v1.4.0 && git push origin v1.4.0`.

Isso dispara `.github/workflows/pdv_desktop.yml` (job `build-installer`): confere que a tag bate com o `pubspec.yaml` (falha o build se alguém esqueceu de bumpar a versão antes de taguear), builda com `API_BASE_URL`/`PDV_SENTRY_DSN` vindos da variável/secret do repositório, gera o instalador e publica (ou atualiza, se já existir) um **GitHub Release** `vX.Y.Z` com o `.exe` anexado e notas geradas a partir dos commits. Commit direto na `main` **não** gera instalador nem Release — só roda `test` — evitando duplicar build a cada push; o job também pode ser disparado manualmente (`workflow_dispatch`, sem tag/Release) com `api_base_url`/`sentry_dsn` customizados.

A mesma tag `vX.Y.Z` também dispara os workflows de `backend`/`frontend` (mesmo critério: só em tag, nunca em commit direto na main), publicando imagens `ghcr.io/<owner>/starchef-{backend,frontend}:X.Y.Z` (+ `X.Y` + `latest`) — um único release versiona os três, sempre com o mesmo número.

## 13. Testes e CI

236 testes (`flutter test`), organizados espelhando `lib/` sob `test/`. Distribuição deliberada: profundidade em regra pura e protocolo de hardware, testes de widget só onde há risco real de regressão. Os mais importantes:

| Arquivo | O que protege |
|---|---|
| `core/hardware/scale/scale_protocol_test.dart` | Decodificação dos quatro fabricantes de balança, quadros parciais, gramas vs. quilos |
| `core/network/api_client_test.dart` | Cache, outbox, IDs temporários dependentes, rotas que exigem servidor |
| `features/scale/domain/hands_free_machine_test.dart` | Fluxo completo de pesagem hands-free, timeout, cancelamento, preservação da venda |
| `features/topology/services/probe_interval_test.dart` | Principal e secundário reais em `127.0.0.1`: handshake assinado, leitura mediada pelo principal, ritmo do probe mudando com o estado |
| `core/security/cash_password_test.dart` | Valida senha de caixa contra hash PBKDF2 gerado pelo Django |

`.github/workflows/pdv_desktop.yml` roda o job `test` em `windows-latest` (necessário — `window_manager`, `sqlite_async` e paths do Windows não se comportam igual em outro SO) em push/PR tocando `flutter/**`: `flutter pub get` → `flutter analyze` → `flutter test`. Ver §12 acima para o job `build-installer` (build + instalador + release).

`flutter analyze` está limpo hoje (1 único aviso de nível "info", pré-existente e sem risco).

## 14. Referências

- [`PDV_OFFLINE_SCALE_ARCHITECTURE.md`](PDV_OFFLINE_SCALE_ARCHITECTURE.md) — arquitetura offline/balança/topologia em profundidade, incluindo limitações conhecidas.
- [`FLUTTER_PDV_TECNICO.md`](FLUTTER_PDV_TECNICO.md) — referência técnica módulo a módulo (telas, diálogos, testes).
- [`BACKEND.md`](BACKEND.md) — a API consumida por este app, incluindo o contrato de `PrintJob`/`Scale`/`Idempotency-Key` usados aqui.
