# StarChef PDV Desktop (Flutter) — Guia Completo

> App desktop Windows em Flutter: PDV principal + janela "Balança Rápida", offline-first, cliente da mesma API do [`BACKEND.md`](BACKEND.md). Este documento é a porta de entrada — para a arquitetura offline/balança em profundidade veja [`PDV_OFFLINE_SCALE_ARCHITECTURE.md`](PDV_OFFLINE_SCALE_ARCHITECTURE.md), e para a referência técnica módulo a módulo veja [`FLUTTER_PDV_TECNICO.md`](FLUTTER_PDV_TECNICO.md).

## 1. Stack tecnológica

| Camada | Tecnologia |
|---|---|
| Framework | Flutter (desktop Windows) |
| Estado | `ChangeNotifier` + `setState` (decisão deliberada — não BLoC; o app já usava esse padrão) |
| Janela nativa | `window_manager` |
| Banco local | `sqlite_async` com migrations próprias (decisão deliberada — não Drift) |
| Sessão segura | `flutter_secure_storage` |
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

Nenhum token é passado via linha de comando — só `--scale-workstation` e `--restaurant=<uuid>`; a janela de balança restaura a própria sessão do cofre do SO.

## 4. Autenticação e sessão

- **`features/auth/`** (`AuthRepository` + `AuthController`) — login, guarda o par access/refresh via `SecureSessionStore` (`flutter_secure_storage`, três chaves: token de acesso, refresh, usuário em JSON).
- **Restauração no boot**: tenta `GET /auth/me/` com o token salvo; em 401, tenta `POST /auth/refresh/`; se o refresh for explicitamente recusado, limpa o cofre e volta ao login. Se **não houver resposta nenhuma** (sem rede), devolve a sessão salva como está — decisão deliberada para o terminal continuar operando offline em vez de deslogar por falta de conexão.
- **Autorização de caixa é separada da autenticação de usuário**: `features/cash/data/cash_auth_repository.dart` sincroniza (quando online) um hash PBKDF2 (formato Django) via `GET /restaurants/<id>/cash-auth/`, guardado localmente. `core/security/cash_password.dart` verifica a senha **offline**, sem round-trip ao servidor — é o que autoriza ações de caixa (cancelamento, desconto) mesmo sem internet.

## 5. Arquitetura offline-first

> Resumo — a fundo em [`PDV_OFFLINE_SCALE_ARCHITECTURE.md`](PDV_OFFLINE_SCALE_ARCHITECTURE.md).

- **`OfflineStore`** (`core/network/offline_store.dart`, `sqlite_async`): cache de respostas GET (até 300 entradas, sem TTL — offline sempre entrega a última resposta conhecida) + uma **outbox transacional** de mutações pendentes, com retry, lease e mapeamento de ID temporário→real. Escopado por `origem-da-API | conta | usuário` (com fallback se claims do JWT faltarem).
- **`local_order_store.dart`** (em `features/orders/data/`) é separado do cache HTTP: guarda o pedido em edição para sobreviver a navegação sem ser sobrescrito por um GET em cache desatualizado.
- **Idempotência**: toda mutação da outbox carrega um `Idempotency-Key`, consumido pelo `IdempotencyMiddleware` do backend ([`BACKEND.md`](BACKEND.md#4-appscore--infraestrutura-transversal)) — reenviar uma operação da fila offline não duplica venda.
- **`MutationRelay`** (`core/network/mutation_relay.dart`): usado por terminais "Caixa Cliente" (secundários) para encaminhar mutações ao "Caixa Principal" pela rede local, assinado HMAC-SHA256 (método, rota, timestamp, nonce, conta, operador, filial, corpo), protegido contra replay, só aceita origem LAN. Três desfechos: sucesso; `MutationRelayUnavailable` (nunca chegou a sair — seguro enfileirar localmente); `MutationRelayUncertain` (pode ter sido entregue — **nunca** reenfileira localmente, pra não duplicar venda; tenta confirmar via `GET /v1/operations/<id>` antes de desistir).
- **Topologia (Caixa Principal / Caixa Cliente)** (`features/topology/`): só dois papéis existem. Uma instalação nova sobe como secundária sem principal configurado e fica **bloqueada para escrita** até um humano atribuir os papéis — evita dois principais por acidente. Leituras também passam pelo principal (preferência: principal → nuvem → cache local); **escritas nunca caem para a nuvem direto** — se o principal está inalcançável, o secundário recusa a escrita em vez de arriscar divergência.
- **Outbox / dead-letter** (`features/sync/presentation/outbox_review_dialog.dart`): tela que traduz método+rota para o que a operação significa ("Item adicionado ao pedido"), mostra o motivo da recusa e o payload completo, oferece repetir ou descartar (descarte exige confirmação e vira log `warning`).

## 6. Hardware: balanças e impressoras

**Balanças** (`core/hardware/scale/`): `ScaleProtocol` decodifica o protocolo de quatro fabricantes — genérico (último número da linha), Toledo (STX…ETX), Filizola (gramas terminado em CR) e Urano (`+00.500kg`). Transporte via `flutter_libserialport` (`ScaleTransport`/`SerialScaleTransport`). `SerialScaleReader` resolve estabilidade (tolerância + tempo de assentamento + flag de movimento do protocolo), com watchdog de 4s e reconexão com backoff.

**Impressão**: o backend **não gera** ESC/POS — só renderiza HTML e um payload de texto (ver [`BACKEND.md`](BACKEND.md#7-pedidos-pagamento-e-impressão)). Quem entrega fisicamente é `features/devices/services/local_device_agent.dart`, que recebe novos `PrintJob`s pela rota autenticada `/ws/pdv/<restaurant_id>/`, busca a fila pendente e imprime via rede (TCP 9100), serial ou spool do SO (fallback Windows), marcando `printed`/`failed` de volta na API. Ao conectar ou reconectar, faz uma única reconciliação para cobrir eventos perdidos; não há polling periódico da fila. `print_template_cache.dart` cacheia os templates localmente.

**Exclusividade de periférico**: `core/hardware/peripheral_lock.dart` usa um lock de arquivo (`RandomAccessFile.lock`) com um descritor ao lado (papel, PID, nome do dispositivo) — o SO já impede acesso serial concorrente, o lock existe pra identificar *qual* janela está usando o quê, e é liberado automaticamente pelo SO se o processo morrer.

## 7. Duas janelas, um executável

A janela "Balança Rápida" **não é um app separado** — `ScaleWindowLauncher.open()` relança o **mesmo executável compilado** (`Platform.resolvedExecutable`) como processo totalmente destacado (`Process.start(..., mode: ProcessStartMode.detached)`) com `--scale-workstation --restaurant=<uuid>`. Se o `Process.start` falhar, o PDV cai para uma visão embutida da estação de balança.

As duas janelas compartilham o mesmo arquivo `offline_data.sqlite` (o `sqlite_async` coordena múltiplos processos no mesmo arquivo) e o mesmo cofre de sessão do SO — cada uma restaura a própria sessão, o token nunca trafega por linha de comando. Não há supervisor: se a janela de balança travar, nada a reabre sozinha (limitação conhecida, documentada — a fila de impressão/leitura não depende do processo principal continuar aberto).

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

`features/settings/presentation/terminal_preferences_dialog.dart` — o que é **do terminal** (armazenado localmente, `LocalPreferences`): timeout de comanda, tolerância de estabilidade da balança, alertas sonoros, impressão automática. O que é **do equipamento/conta** (fica no cadastro do backend, `Scale`/`Printer`, compartilhado por todos os terminais que usam aquele hardware): porta, baud rate, protocolo da balança.

## 11. Como rodar em desenvolvimento

```bash
npm run dev:flutter          # a partir da raiz do monorepo — atalho para: cd flutter && flutter run -d windows
# ou, dentro de flutter/:
flutter pub get
flutter run -d windows
```

A janela de balança não tem script próprio de dev — clique em "Balança Rápida" no menu do PDV rodando, que relança o mesmo binário (debug, nesse caso) com `--scale-workstation`. O `.env` é procurado a partir da raiz do monorepo ou de `flutter/` (busca sobe até 8 níveis de diretório).

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

Isso dispara `.github/workflows/flutter.yml` (job `build-installer`): confere que a tag bate com o `pubspec.yaml` (falha o build se alguém esqueceu de bumpar a versão antes de taguear), builda com `API_BASE_URL`/`PDV_SENTRY_DSN` vindos da variável/secret do repositório, gera o instalador e publica (ou atualiza, se já existir) um **GitHub Release** `vX.Y.Z` com o `.exe` anexado e notas geradas a partir dos commits. Commit direto na `main` **não** gera instalador nem Release — só roda `test` — evitando duplicar build a cada push; o job também pode ser disparado manualmente (`workflow_dispatch`, sem tag/Release) com `api_base_url`/`sentry_dsn` customizados.

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

`.github/workflows/flutter.yml` roda o job `test` em `windows-latest` (necessário — `window_manager`, `sqlite_async` e paths do Windows não se comportam igual em outro SO) em push/PR tocando `flutter/**`: `flutter pub get` → `flutter analyze` → `flutter test`. Ver §12 acima para o job `build-installer` (build + instalador + release).

`flutter analyze` está limpo hoje (1 único aviso de nível "info", pré-existente e sem risco).

## 14. Referências

- [`PDV_OFFLINE_SCALE_ARCHITECTURE.md`](PDV_OFFLINE_SCALE_ARCHITECTURE.md) — arquitetura offline/balança/topologia em profundidade, incluindo limitações conhecidas.
- [`FLUTTER_PDV_TECNICO.md`](FLUTTER_PDV_TECNICO.md) — referência técnica módulo a módulo (telas, diálogos, testes).
- [`BACKEND.md`](BACKEND.md) — a API consumida por este app, incluindo o contrato de `PrintJob`/`Scale`/`Idempotency-Key` usados aqui.
