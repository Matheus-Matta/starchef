# PDV offline e Balança Rápida — arquitetura implementada

Este documento descreve o comportamento que existe no código atual. Ele é um registro **AS-IS**, não uma promessa da arquitetura desejada ao fim de todos os sprints. As lacunas conhecidas estão reunidas no final.

## Visão geral

```text
┌──────────────────────── processo principal: StarChef PDV ────────────────────────┐
│ UI do caixa ── ApiClient ──────────────── API Django                             │
│      │               │                                                           │
│      │               └── %LOCALAPPDATA%\StarChef\offline_data.sqlite             │
│      │                                                                           │
│      └── LocalDeviceAgent (somente Windows)                                      │
│             ├── balanças seriais ── leituras/leases ── API                       │
│             └── fila de impressão ── Windows / TCP 9100 / serial                 │
└──────────────────────────────────────────────────────────────────────────────────┘

┌──────────── processo independente: Balança Rápida (uma ou mais instâncias) ──────┐
│ UI touch ── ApiClient ── API Django                                              │
│    │          └── mesmo offline_data.sqlite                                      │
│    └── leitor USB-CDC/serial reservado pela porta                                │
│          └── %LOCALAPPDATA%\StarChef\device_bindings.sqlite                      │
└──────────────────────────────────────────────────────────────────────────────────┘
```

O processo principal continua sendo responsável pelo agente local que lê a balança física e executa impressões. A janela de Balança Rápida consome as leituras válidas da API e conduz o fluxo de pesagem/comanda. Portanto, “janela independente” significa isolamento de interface, foco e ciclo de vida; não significa um servidor local independente.

## Interface do PDV

A tela principal usa três regiões:

- barra lateral fixa e recolhível, com 224 px expandida e 76 px recolhida;
- catálogo de produtos no centro;
- resumo do pedido à direita.

A barra lateral expõe Menu, Mesas, Delivery, Pedidos, Financeiro, Balança Rápida e Configurações, respeitando as permissões já presentes na sessão. Ela também contém identificação do operador, restaurante e logout. Em janelas com menos de 1180 px, o menu passa automaticamente ao modo recolhido.

O catálogo oferece busca por nome, código interno e categoria, categorias horizontais com contagem, cards com preço e imagem remota e um ícone de categoria como fallback. O carrinho apresenta contexto do pedido, imagens, itens, subtotal, taxas, desconto, total, revisão e impressão. Sua largura varia entre 350, 380 e 420 px conforme o espaço disponível.

O cabeçalho mantém seleção de restaurante, estado do caixa, atualização e um badge de conectividade/sincronização. O badge pode mostrar `Verificando`, `Online`, `Offline`, `Sincronizando`, `Instável` ou `Revisar`, além da quantidade de operações locais quando aplicável.

## Persistência offline

### Arquivos e tabelas

O `OfflineStore` usa `sqlite_async` e grava, por padrão:

```text
%LOCALAPPDATA%\StarChef\offline_data.sqlite
```

Na ausência de `LOCALAPPDATA`, o diretório temporário do sistema é usado. O banco possui:

| Tabela | Responsabilidade |
| --- | --- |
| `offline_cache` | respostas GET permitidas, com chave e data de atualização |
| `offline_outbox` | mutações locais, tentativas, próximo retry e erro |
| `offline_id_map` | relação entre IDs temporários e IDs retornados pela API |
| `offline_meta` | metadados de migração |

O cache é limitado às 300 entradas mais recentes. O código usa a coordenação entre engines fornecida por `sqlite_async`; ele não executa diretamente um `PRAGMA journal_mode` próprio.

Se existir o arquivo legado `offline_data.json`, o cache é importado uma única vez. Operações pendentes legadas entram no escopo `legacy` e no estado `blocked`, para não serem reenviadas automaticamente sob uma conta ou servidor incorretos. O JSON original não é apagado.

### Escopo de conta e servidor

As chaves de cache e da outbox usam o namespace:

```text
autoridade-da-base-url | account_id, user_id ou sub extraído do JWT
```

Se o token não puder ser interpretado, o fallback é `authenticated`; sem token, `public`. Esse escopo evita que a sincronização normal de uma sessão consuma deliberadamente a fila de outra conta ou outro servidor.

O logout cancela timers, esquece o token e limpa a sessão segura, mas **não apaga** o banco offline. Isso preserva dados pendentes para uma futura reconciliação, porém ainda não existe uma tela de administração para selecionar, exportar ou descartar filas antigas.

### O que pode usar cache

Somente GETs dos seguintes grupos são elegíveis:

- restaurantes;
- cardápio;
- estações de caixa;
- mesas;
- clientes;
- formas de pagamento;
- impressoras;
- balanças.

Mesmo dentro desses grupos, rotas físicas ou transacionais marcadas como online não usam cache. Por exemplo, `latest-reading`, trabalhos de impressão e checkout de comanda nunca retornam uma leitura física antiga.

### O que pode entrar na outbox

A fila é intencionalmente restritiva. Hoje ela aceita:

- criação e alteração de cliente;
- criação de pedido;
- abertura de pedido por mesa;
- inclusão de item em pedido;
- cancelamento (`void`) de item.

Cada mutação recebe um `queue_id`/`idempotency_key`, data, estado e escopo. Criações elegíveis retornam um ID `offline-...` e um objeto otimista marcado com `_offline_pending`. Durante a sincronização, o ID real retornado para um pedido é persistido e substituído nas operações dependentes antes de enviar seus itens.

Pagamentos, abertura/fechamento e movimentos de caixa, envio para cozinha, fechamento de pedido, autenticação, leitura de balança, checkout da comanda, claim/release de dispositivo e mudança de estado de impressão exigem servidor acessível e não entram na fila genérica.

### Estados e retry

| Estado exibido | Condição prática |
| --- | --- |
| `unknown` | ainda sem resultado de conectividade ou sessão limpa |
| `online` | última comunicação bem-sucedida e sem pendências |
| `offline` | falha de transporte, socket ou timeout |
| `degraded` | servidor respondeu com falha temporária |
| `syncing` | há operações elegíveis sendo ou prestes a ser enviadas |
| `blocked` | pelo menos uma operação recebeu erro não recuperável e requer revisão |

HTTP 408, 425, 429 e respostas 5xx são tratados como recuperáveis. O cliente respeita `Retry-After` quando presente; caso contrário, usa backoff exponencial a partir de 2 segundos, limitado a 2 minutos, com pequeno jitter. O disparo normal da fila tem debounce de 450 ms.

Cada ciclo envia no máximo 20 operações, **uma requisição por vez**. Não há chamada HTTP em lote. Um erro temporário move a operação para `retry` e registra a próxima tentativa; um `ApiException` não temporário durante o flush move a operação para `blocked`. O retry é agendado automaticamente; quando o estado volta a ser considerado conectado, o badge com pendências também permite solicitar uma sincronização.

O cabeçalho `Idempotency-Key` é enviado, mas o backend não possui uma camada genérica de deduplicação para todas essas rotas. Logo, o desenho atual não garante exatamente uma vez em caso de queda depois de o servidor confirmar a escrita e antes de o cliente remover a entrada.

## Balança Rápida

### Processo e sessão

Ao selecionar Balança Rápida, o PDV salva a sessão atual no cofre do sistema e inicia o mesmo executável com:

```text
--scale-workstation --restaurant=<uuid>
```

O token não é colocado na linha de comando. O novo processo restaura a sessão pelo `flutter_secure_storage`, cria seu próprio `ApiClient` e permite escolher restaurante e balança. É possível abrir mais de uma instância. Se o processo não puder ser criado, o PDV abre a estação embutida como fallback.

A janela dedicada inicia com 1180 × 760 px e mínimo de 900 × 650 px. Cada processo tem ciclo de vida próprio, portanto fechar ou travar uma janela de balança não fecha a interface principal.

### Fluxo operacional

1. O operador escolhe restaurante e balança. A balança precisa ter um produto por kg e uma impressora padrão configurados.
2. A estação consulta `latest-reading` aproximadamente a cada 700 ms.
3. Uma leitura positiva é considerada localmente estável quando não varia mais de 0,002 kg e permanece assim durante o atraso configurado na balança.
4. O operador confirma o peso/valor e pode acrescentar produtos vendidos por unidade.
5. A comanda é lida pelo scanner serial ou digitada no teclado touch.
6. O cliente chama `checkout-command` com a leitura, extras e `print: true`.
7. O backend, em uma transação, resolve/cria o pedido da comanda, consome a leitura, adiciona o item pesado e os extras, recalcula o pedido e cria o trabalho de impressão.
8. Após sucesso, a estação aguarda 2 segundos e volta a esperar a próxima pesagem.

Existe entrada manual de peso com teclado numérico touch. Ela cria uma `ScaleReading` com origem `manual`, portanto também exige conexão com a API.

### Leitura da balança física

No Windows, o `LocalDeviceAgent` do processo principal roda a cada 3 segundos. Ele atualiza a lista de dispositivos a cada 30 segundos, abre a porta serial configurada, interpreta o último número recebido e publica leituras estáveis na API.

Antes de ler, o agente solicita uma lease de 15 segundos por `agent_instance_id`. O backend rejeita outro agente enquanto essa lease estiver válida. O agente também exige que a balança passe pela faixa de zero antes de um novo disparo, reduzindo repetição quando um prato permanece apoiado.

Se apenas a janela de Balança Rápida estiver aberta e nenhum processo principal estiver executando o agente local, a leitura automática da balança não será produzida por essa janela. O peso manual continua disponível desde que a API esteja online.

## Leitor de comanda USB-CDC/serial

Cada combinação `restaurante:balança` funciona como um slot de leitor. O vínculo local é gravado em:

```text
%LOCALAPPDATA%\StarChef\device_bindings.sqlite
```

A tabela `scanner_bindings` guarda porta, baud rate, VID, PID, número de série e nome do produto. `port_name` é único no banco, impedindo que dois slots sejam configurados deliberadamente com a mesma porta. A interface lista as portas detectadas e permite 9600, 19200, 38400, 57600 ou 115200 baud.

Ao selecionar uma balança, a estação restaura o vínculo e tenta abrir a porta em modo de leitura. A porta aberta é a reserva efetiva no sistema operacional; outra janela recebe erro de porta ocupada/indisponível. O leitor deve enviar caracteres ASCII imprimíveis e terminar cada código com CR ou LF. Frames vazios são ignorados e o decoder limita o buffer a 160 caracteres.

Durante a etapa “Leia a comanda”, um frame válido preenche o código e conclui o checkout automaticamente. Leituras em outras etapas são ignoradas com alerta sonoro. A interface permite desvincular o dispositivo.

Antes de abrir a porta, o serviço compara os valores persistidos de VID, PID e número de série com o dispositivo que ocupa a COM naquele momento. Qualquer divergência disponível bloqueia a abertura e obriga o operador a refazer o vínculo. Quando o dispositivo/driver não fornece um desses identificadores, somente os campos efetivamente capturados podem ser validados.

## Impressão e nota de pesagem

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

## Runbook de instalação e operação

### 1. Preparar o backend

1. Cadastre o restaurante, produtos e comandas.
2. Cadastre uma impressora ativa com conexão `windows`, `network` ou `serial`.
3. Cadastre a balança ativa com porta, baud rate em `settings.baudrate` e produto por kg. A impressora pode ser vinculada no cadastro ou no seletor “Impressora padrão da balança” da estação.
4. Confirme que usuário e token possuem permissão para usar/gerenciar dispositivos, operar balança e pedidos. Alterar a impressora persistida é uma alteração do cadastro da balança.

### 2. Preparar o terminal Windows

1. Instale a impressora no Windows ou confirme IP/porta serial conforme o tipo escolhido.
2. Conecte a balança e valide qual COM foi atribuída.
3. Para leitor dedicado, configure o equipamento em modo serial/USB-CDC, com terminador CR ou LF. Leitores em modo teclado HID não aparecem no seletor serial.
4. Garanta que balança, leitor e impressora serial não disputem a mesma porta.

### 3. Aquecer o cache

Entre no PDV com rede disponível e carregue o restaurante/cardápio ao menos uma vez. Um terminal iniciado offline sem cache prévio não consegue obter o catálogo. A sessão também precisa ter sido salva no cofre local para ser restaurada pela janela independente.

### 4. Iniciar a estação

1. Mantenha o processo principal aberto para que o `LocalDeviceAgent` leia a balança e processe impressões.
2. Abra Balança Rápida pela barra lateral; cada clique bem-sucedido cria outro processo.
3. Escolha o restaurante e a balança.
4. Use a configuração de leitor para escolher a COM e o baud rate e clique em “Vincular e testar”.
5. Inicie a estação, pese, confirme, selecione extras e leia a comanda.

### 5. Diagnóstico rápido

| Sintoma | Verificação |
| --- | --- |
| `Offline` | API, DNS/rede e timeout; operações físicas não têm fallback local |
| `Instável` | HTTP 408/425/429/5xx; aguarde o `Retry-After`/backoff automático |
| `Revisar` | existe item `blocked`; hoje a inspeção exige acesso direto ao SQLite/logs da API |
| sem leitura de peso | processo principal aberto, COM da balança, baud rate, lease e passagem pelo zero |
| leitor não aparece | dispositivo em modo USB-CDC/serial e driver que exponha uma COM |
| porta do leitor ocupada | feche a outra janela/processo ou remova o vínculo anterior |
| checkout recusado | leitura recente e ainda não consumida, comanda ativa, permissão e API online |
| impressão não sai | impressora vinculada à balança, ativa, endpoint/IP/COM e job no backend |
| barras não aparecem | usar driver ESC/POS por TCP/serial; spool do Windows recebe fallback textual |

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

A suíte cobre, entre outros pontos, outbox e IDs dependentes, exclusão de cache/fila para ações físicas, widgets do PDV em larguras compactas, persistência/unicidade do vínculo de scanner, framing CR/LF, bytes Code 128 e atomicidade do ticket de pesagem.

No terminal que irá para produção, faça também a homologação física:

1. Abra duas janelas e vincule leitores diferentes; confirme que uma COM já reservada é recusada.
2. Troque o equipamento que ocupa uma COM e confirme que VID/PID/serial divergentes exigem novo vínculo.
3. Imprima uma comanda conhecida, leia as barras impressas de volta e compare o valor.
4. Interrompa a rede durante uma mutação permitida e durante um checkout de balança; a primeira deve ficar pendente e a segunda deve ser recusada.
5. Simule falha da impressora e confira a transição do `PrintJob` e a retomada após corrigir o equipamento.

## Limitações atuais e trabalho futuro

1. **Não existe topologia mestre/escravo local.** Não há descoberta LAN, eleição de nó, servidor local, replicação entre caixas ou failover de mestre. Todos os processos continuam dependentes da API remota para operações transacionais e físicas.
2. **Não existe endpoint de batch nem pull incremental.** O cliente envia até 20 requisições individuais por ciclo e não recebe deltas por cursor, watermark ou feed de mudanças.
3. **Offline ainda é parcial.** A infraestrutura suporta catálogo e um subconjunto de pedidos/clientes, mas pagamento, caixa, cozinha, fechamento, balança e impressão exigem API. Após reiniciar totalmente sem rede, a sessão de caixa atual não é restaurada do cache, o que pode bloquear o início de pedidos. O cache também não possui TTL; offline, ele entrega a última resposta disponível com `_offline_cache: true`.
4. **Não há resolução de conflitos de domínio.** Não existem versões de registro, merge por campo ou interface para conciliar mudanças concorrentes.
5. **Idempotência é incompleta.** A outbox envia uma chave, mas as rotas genéricas de cliente/pedido/item não a deduplicam de forma uniforme no backend.
6. **Consumidores da outbox não têm lease.** SQLite coordena o arquivo, mas dois processos com a mesma sessão podem selecionar a mesma operação antes da remoção. Isso reforça a necessidade de idempotência de servidor antes de considerar o fluxo multi-processo exatamente uma vez.
7. **Não há tela de dead-letter.** O badge informa itens bloqueados, mas não há UI para examinar payload, corrigir, reenviar individualmente ou descartar.
8. **O scanner dedicado cobre somente serial/USB-CDC.** Não há captura exclusiva de HID, filtro de eventos HID por VID/PID ou claim nativo de um leitor em modo teclado.
9. **A força da identidade depende do hardware/driver.** VID, PID e serial persistidos são revalidados, mas um leitor que não exponha esses campos fica identificado apenas pela COM e pelos metadados disponíveis.
10. **O agente físico é Windows-only.** A janela pode ser iniciada nos desktops aceitos pelo launcher, mas leitura de balança, spool e porta serial do agente principal foram implementados com PowerShell/recursos do Windows.
11. **Impressão não é exatamente uma vez.** Se a impressão física concluir e a confirmação `mark-printed` falhar, o job pode permanecer pendente e ser reprocessado.
12. **Code 128 visual depende da rota.** HTML contém a imagem; ESC/POS TCP/serial recebe barras reais para ASCII compatível; a fila do Windows usa texto e depende de evolução futura para renderização gráfica confiável.
13. **Hardware real ainda precisa de homologação.** O comando Code 128, os baud rates e os fluxos de reserva possuem testes automatizados ou validação de código, mas o resultado final varia por firmware, driver, página de código e modelo de impressora/leitor.
14. **O escopo depende das claims do JWT.** Tokens sem `account_id`, `user_id` e `sub` caem no namespace genérico `authenticated`; nesse caso, contas distintas na mesma base URL não ficam isoladas pelo identificador do token.
