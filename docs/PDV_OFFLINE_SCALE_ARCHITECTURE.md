# PDV offline e Balança Rápida — arquitetura implementada

Este documento descreve o comportamento que existe no código atual. Ele é um registro **AS-IS**, não uma promessa da arquitetura desejada ao fim de todos os sprints. As lacunas conhecidas estão reunidas no final.

Para a estrutura interna do aplicativo Flutter — camadas, arquivos, decisões de
desenho e como estender cada parte —, veja
[`FLUTTER_PDV_TECNICO.md`](FLUTTER_PDV_TECNICO.md).

## Visão geral

```text
┌──────────────────────── processo principal: StarChef PDV ────────────────────────┐
│ UI do caixa ── ApiClient ──────────────── API Django                             │
│      │               │                                                           │
│      │               └── <dados>\StarChef\offline_data.sqlite                    │
│      │                                                                           │
│      └── LocalDeviceAgent (somente Windows)                                      │
│             └── fila de impressão ── Windows / TCP 9100 / serial                 │
└──────────────────────────────────────────────────────────────────────────────────┘

┌──────────── processo independente: Balança Rápida (uma ou mais instâncias) ──────┐
│ UI touch ── HandsFreeMachine ── ApiClient ── API Django (só no lançamento)       │
│    │          └── mesmo offline_data.sqlite                                      │
│    ├── SerialScaleReader ── porta serial da balança (leitura local contínua)     │
│    │       └── trava exclusiva em <dados>\StarChef\locks\scale_<porta>.lock      │
│    └── leitor USB-CDC/serial reservado pela porta                                │
│          └── <dados>\StarChef\device_bindings.sqlite                             │
└──────────────────────────────────────────────────────────────────────────────────┘
```

A leitura de peso é local: a janela que vai usar a balança abre a porta serial
ela mesma, decodifica os quadros com o protocolo do fabricante e resolve a
estabilidade em memória. Não existe mais consulta periódica à API para obter
peso, nem lease remoto (`claim-agent`) — a exclusividade vem do sistema
operacional, complementada por uma trava de arquivo que identifica *qual*
janela detém o equipamento. O `LocalDeviceAgent` do processo principal ficou
responsável apenas pela fila de impressão.

A rede só participa no momento do lançamento: registrar a leitura e fechar a
comanda. Portanto, “janela independente” significa isolamento de interface,
foco, hardware e ciclo de vida; não significa um servidor local independente.

### Onde ficam os dados

| Plataforma | Diretório |
| --- | --- |
| Windows | `%LOCALAPPDATA%\StarChef` (`%APPDATA%` como alternativa) |
| Linux / macOS | `$XDG_DATA_HOME/StarChef`, senão `~/.local/share/StarChef` |

O diretório temporário só é usado quando nenhuma dessas variáveis existe. Isso
importa porque a fila offline precisa sobreviver a uma reinicialização — em
`/tmp` ela não sobreviveria.

No Linux, credenciais e a chave de pareamento usam primeiro o Secret Service
do sistema e também mantêm uma cópia em `<dados>/StarChef/secure`. O diretório
recebe modo `0700` e cada arquivo recebe `0600`, bloqueando outros usuários da
máquina. Essa cópia é necessária porque `libsecret` pode devolver vazio ou erro
quando GNOME Keyring/KWallet não está disponível no autostart; sem ela, o login
era perdido e outra chave do Caixa Principal era gerada a cada abertura.

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

A suíte cobre, entre outros pontos, outbox e IDs dependentes, exclusão de cache/fila para ações físicas, widgets do PDV em larguras compactas, persistência/unicidade do vínculo de scanner, framing CR/LF, bytes Code 128, atomicidade do ticket de pesagem, decodificação dos quatro protocolos de balança, resolução de estabilidade e disputa de porta no leitor serial, a máquina de estados hands-free (incluindo timeout, alerta, cancelamento e preservação da venda em caso de falha), persistência das preferências e o botão de fechar de todo alerta global.

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

1. **A topologia é principal/secundário, sem descoberta nem failover.** Todo terminal é Caixa Principal ou Caixa Cliente — o modo independente foi removido, porque dois terminais sincronizando cada um por conta própria com a nuvem é a raiz da divergência. Um terminal recém-instalado sobe como **secundário sem principal definido** e fica bloqueado para escrita até alguém dizer qual é o seu papel — assim o segundo caixa instalado não vira, por acidente, um segundo principal sincronizando por conta própria. A chave de pareamento já vem gerada, então promover o primeiro terminal a Caixa Principal é um clique. O principal só aceita conexões da rede local. O principal atende leitura (`/v1/read`) e escrita (`/v1/relay`) dos secundários e é o único que fala com a nuvem. **Um secundário depende do principal para gravar.** Se o principal cair, o secundário continua lendo (da última cópia local), mas recusa qualquer alteração até ele voltar — gravar por fora deixaria o principal sem saber de uma venda que os outros caixas leem dele. O que continua não existindo: descoberta automática na LAN (o IP do principal é configurado à mão), eleição de nó e failover.
2. **Não existe endpoint de batch nem pull incremental.** O cliente envia até 20 requisições individuais por ciclo e não recebe deltas por cursor, watermark ou feed de mudanças.
3. **Offline cobre a venda inteira, do lançamento ao recebimento.** Funcionam sem rede: catálogo, pedidos (lista e detalhe), clientes, itens, fechamento, envio à cozinha e **pagamento**. Os quatro últimos entram na fila e sobem depois, com a deduplicação do backend impedindo cobrança dupla. Um pagamento enfileirado já conta no total recebido, senão o operador nunca zeraria o restante para fechar a venda; a impressão do comprovante é efeito colateral e falhar nela não prende o pedido na tela. Continuam exigindo servidor: abertura/fechamento de **caixa**, impressão e o `checkout-command` da balança — a *leitura* do peso é local, mas transformá-la em pedido envolve resolver comanda, consumir a leitura e recalcular o pedido em uma transação. A sessão de caixa é servida do cache após um reinício sem rede, e o cabeçalho mostra "Caixa (offline)"; o estado pode ter mudado em outro terminal nesse intervalo. O cache não possui TTL; offline, ele entrega a última resposta disponível com `_offline_cache: true`.
4. **Não há resolução de conflitos de domínio.** Não existem versões de registro, merge por campo ou interface para conciliar mudanças concorrentes.
5. **Idempotência é garantida por um middleware genérico.** `IdempotencyMiddleware` guarda, na mesma transação da operação, a resposta produzida para cada `Idempotency-Key` por conta. Um reenvio devolve a resposta original sem executar nada, e a mesma chave usada para outra requisição é recusada com 409. Só respostas de sucesso são memorizadas — um erro precisa poder ser repetido depois que a causa for corrigida. Rotas de autenticação são isentas.
6. **Consumidores da outbox não têm lease.** SQLite coordena o arquivo, mas dois processos com a mesma sessão podem selecionar a mesma operação antes da remoção. Isso reforça a necessidade de idempotência de servidor antes de considerar o fluxo multi-processo exatamente uma vez.
7. **A revisão da fila existe, mas a correção é indireta.** Clicar no badge (ou Configurações → Operações pendentes) abre a lista com o motivo da recusa e o payload completo, e permite reenviar ou descartar item a item. O que ainda não existe é editar o payload na própria tela: a causa precisa ser corrigida no cadastro (comanda, caixa, produto) antes de reenviar.
8. **O scanner dedicado cobre somente serial/USB-CDC.** Não há captura exclusiva de HID, filtro de eventos HID por VID/PID ou claim nativo de um leitor em modo teclado.
9. **A força da identidade depende do hardware/driver.** VID, PID e serial persistidos são revalidados, mas um leitor que não exponha esses campos fica identificado apenas pela COM e pelos metadados disponíveis.
10. **Só a fila do sistema de impressão depende da plataforma.** Balança, leitor de comanda e impressora serial usam `flutter_libserialport`, e a impressora de rede usa socket puro — tudo isso funciona igual em Windows e Linux. A fila do sistema operacional é a única rota com ferramenta externa: `Out-Printer` no Windows e `lp` (CUPS) no Linux, que precisa estar instalado e com a impressora registrada.
11. **Os protocolos de balança cobrem o enquadramento documentado, não todo firmware.** Toledo, Filizola e Urano têm variações por modelo e configuração; o modo `generic` é o mais tolerante. A escolha errada pode produzir peso 1000× maior ou menor, então a conferência contra o visor do equipamento é obrigatória antes de liberar o terminal.
12. **A trava de periférico é por máquina.** Ela impede a disputa entre janelas do mesmo computador. Duas máquinas ligadas fisicamente à mesma balança continuam sendo um problema de instalação, não algo que o software detecte.
13. **Impressão não é exatamente uma vez.** Se a impressão física concluir e a confirmação `mark-printed` falhar, o job pode permanecer pendente e ser reprocessado. A reimpressão do último cupom é explícita e não cria outro pedido.
14. **Code 128 visual depende da rota.** HTML contém a imagem; ESC/POS TCP/serial recebe barras reais para ASCII compatível; a fila do Windows usa texto e depende de evolução futura para renderização gráfica confiável.
15. **Hardware real ainda precisa de homologação.** O comando Code 128, os baud rates, os protocolos de balança e os fluxos de reserva possuem testes automatizados ou validação de código, mas o resultado final varia por firmware, driver, página de código e modelo de impressora/leitor/balança.
16. **O escopo depende das claims do JWT.** Tokens sem `account_id`, `user_id` e `sub` caem no namespace genérico `authenticated`; nesse caso, contas distintas na mesma base URL não ficam isoladas pelo identificador do token.
