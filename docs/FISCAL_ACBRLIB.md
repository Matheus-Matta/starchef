# Emissor fiscal ACBrLib

Terceira opção de emissão de NFC-e/NF-e, ao lado de **Manual** e **Focus NFe**:
o próprio backend (loja ou nuvem) assina e transmite pela **ACBrLib**, que roda
num container ao lado dele — o **comunicador** (`fiscal_acbr/`).

```
PDV ──► backend (/invoices/emit/) ──► comunicador ACBrLib ──► SEFAZ
                    ▲                        │
                    └──────── resposta ──────┘
```

O PDV continua falando só com o backend, como faz com a Focus. O que muda é
quem transmite: em vez de a loja pedir à nuvem (`relay_client`), o backend chama
o comunicador **da própria instalação**, na URL de `ACBRLIB_URL`. Por isso
funciona igual na loja e na nuvem — cada um com o seu comunicador — e funciona
**sem internet**: a loja assina em contingência offline e transmite depois.

## Por que o estado fica no backend, e não no comunicador

O guia de referência do ACBr sugere um comunicador com banco próprio, fila e
sincronizador. Aqui não: o backend já tem tudo isso, testado e sincronizado —
a nota (`Invoice`), os estados de espera (`awaiting`), a porta única de
contingência (`contingency.py` / `entrar_em_contingencia`), a retransmissão
(`reprocess_pending_fiscal_invoices`) e a sincronização com a nuvem. Duplicar
isso no comunicador seriam duas filas de nota fiscal para conciliar.

O comunicador é **sem estado**: recebe o documento, chama a ACBrLib e devolve a
resposta. Se ele reiniciar no meio, nada se perde — a nota pendente está no
banco do backend, com o XML assinado.

## Configuração

| Variável | Onde | Para quê |
|---|---|---|
| `ACBRLIB_URL` | `.env` do backend (loja e nuvem, cada um o seu) | onde o comunicador escuta, ex. `http://fiscal-acbr:8001` |
| `ACBRLIB_TOKEN` | backend **e** comunicador (o mesmo) | o comunicador só atende quem mostra o token |
| `ACBRLIB_TIMEOUT` | backend (padrão 40 s) | maior que o da SEFAZ: um timeout curto vira "não sei se emitiu" |
| `ACBR_LIB_PATH` | comunicador | caminho da `libacbrnfe64.so` (obtida à parte, ver abaixo) |
| `ACBR_SIMULADOR` | comunicador | `1` = SEFAZ simulada, para desenvolvimento e teste de ponta a ponta |

No painel: **Fiscal > Configuração > Provedor = ACBrLib**, e a opção
**Permitir contingência offline** (só NFC-e).

A `libacbrnfe64.so` **não vem no repositório**: é distribuída pelo Projeto ACBr
(compilada pelo próprio ACBr ou baixada pelo SAC). Ela é montada no container
em `/app/libs`. Sem ela o comunicador **sobe sem emitir**: o `/health`
responde 503 (container "unhealthy" no `docker ps`, sem reiniciar em laço) e
toda operação devolve `erro: configuracao` com a providência ("copie a
libacbrnfe64.so para docker/local/acbr/libs"), que o caixa lê na nota. Ele
**nunca simula** sem `ACBR_SIMULADOR=1` pedido explicitamente: subir simulando
sem ninguém ter pedido faria a loja "emitir" notas que nunca existiram na SEFAZ.

### No servidor da loja (`docker/local`)

O serviço `fiscal-acbr` faz parte do compose da loja e **sobe sempre**, sem
perfil: o backend já recebe `ACBRLIB_URL=http://fiscal-acbr:8001` fixo no
compose, e o instalador gera o `ACBRLIB_TOKEN` e **instala a lib sozinho**
(`instalar-acbrlib.sh`/`.ps1`): baixa o pacote de `ACBRLIB_PACOTE_URL`, confere
a `libacbrnfe64.so` contra `ACBRLIB_SO_SHA256` e põe a lib e os `.xsd` de
`Schemas/NFe` em `docker/local/acbr/libs`. Lib que não confere não é instalada
(aviso, sem derrubar a instalação); lib já instalada e conferida não é baixada
de novo. Link do MediaFire é aceito: o direto muda a cada visita e é lido da
página do arquivo. Para emitir, só falta escolher o provedor **ACBrLib** no
cadastro fiscal do restaurante.

Lib atual: ACBrLibNFe 1.5.0.488 (SVN trunk2 r48608, `Linux-x86_64-MT`), exige
glibc 2.34+ (a imagem é Debian 12, glibc 2.36), SHA-256
`deec61a921b830516ad3d7f5833aee7cb69603391eb497e649296ecc5522b3f0`. Compilada
com `export ACBR_HOME=<fontes>` e `lazbuild --build-all
--build-mode=Linux-x86_64-MT --ws=nogui --no-write-project
Projetos/ACBrLib/Fontes/NFe/ACBrLibNFeConsoleMT.lpi` — sem o `ACBR_HOME` o
projeto não acha `ACBr.inc` nem `synachar`.

A lib abre `libxml2.so` (sem versão) para assinar o XML, e o Debian só traz o
`libxml2.so.2`. A imagem cria o atalho (`fiscal_acbr/Dockerfile`): sem ele o
`/health` responde 200 com a lib carregada, mas a primeira nota falha na
assinatura.

**O fuso do `dhEmi` vai explícito.** O INI leva a data sem fuso (horário de
Brasília) e a ACBrLib acrescenta o fuso — lido de `/etc/timezone`, que no
container dizia `Etc/UTC`. A NFC-e das 22:36 saía `22:36:00+00:00` (19:36 em
Brasília) e a SEFAZ recusava com **704 — Data-Hora de emissão atrasada**. Agora
o backend manda `fuso` no contexto (`ini.fuso_acbr()`) e o comunicador grava
`[DFe] TimeZone.Modo=2` (manual) e `TimeZone.Str` a cada chamada; a imagem
também acerta `/etc/timezone` para `America/Sao_Paulo`.

Tudo isso roda dentro da loja: com a internet fora, o backend da loja chama o
comunicador da loja, e a nota sai em contingência offline (tpEmis=9) quando a
SEFAZ não responde.

### O que vai em `acbr/libs` (loja, nuvem e nuvem de teste)

Tudo da distribuição da ACBrLib NFe para Linux 64 bits:

```text
acbr/libs/
├── libacbrnfe64.so      a biblioteca
└── Schemas/             o conteúdo de Schemas/NFe da distribuição
```

Sem a `.so`, ou sem a pasta `Schemas`, o comunicador sobe "unhealthy" e toda
nota fica em erro dizendo o que falta (`app/motor.py`). A configuração que a
lib lê está em `fiscal_acbr/config/ACBrLib.ini`, conferida contra a fonte da
ACBr (`ACBrDFeConfiguracoes.pas`): `[DFe]` com `UF`, `SSLCryptLib`,
`SSLHttpLib`, `SSLXmlSignLib`, `DadosPFX` e `Senha`; `[NFe]` com `Ambiente`
(0 = produção, 1 = homologação), `FormaEmissao`, `ModeloDF`, `IdCSC`, `CSC`,
`VersaoQRCode`, `PathSchemas`. TLS 1.2 é o padrão da lib, e os endereços da
SEFAZ de cada UF vêm embutidos nela (`IniServicos` vazio).

**Dois modos, os dois de verdade**, escolhidos no cadastro fiscal do
restaurante: **homologação** emite na SEFAZ de homologação, sem valor fiscal,
para testar o cadastro e o sistema; **produção** emite a nota de verdade. Erro
de cadastro, certificado ou SEFAZ fica gravado na nota, para corrigir e
reenviar. O simulador (`ACBR_SIMULADOR=1`) é só dos testes automáticos e do
par de teste de sincronização (`docker/loadtest`).

### O simulador não se passa pela SEFAZ

Com `ACBR_SIMULADOR=1` NENHUMA nota vai à SEFAZ: chave, protocolo e QR Code são
inventados. Para ninguém tomar isso por emissão real:

* a "autorização" vem com o motivo **"SIMULADO — sem valor fiscal (nenhuma
  SEFAZ foi consultada)"**, e não com a frase da SEFAZ ("Autorizado o uso da
  NF-e"), que ele imitava;
* em **produção** (ambiente 1) ele **recusa**: a nota fica em erro dizendo que
  a SEFAZ simulada não emite em produção. Antes autorizava, e na nuvem de teste
  toda nota de "produção" saía emitida com um QR Code que não levava a lugar
  nenhum.

Emissão de verdade exige a `libacbrnfe64.so`, o certificado A1 da empresa, o
CSC do ambiente e o emitente cadastrado na SEFAZ — com dados de demonstração a
SEFAZ real recusa.

### A imagem no GitHub (`.github/workflows/fiscal_acbr.yml`)

A Action gera `ghcr.io/matheus-matta/starchef-fiscal-acbr` no nosso GHCR:

| Gatilho | Etiquetas publicadas |
| --- | --- |
| tag `vX.Y.Z` | `X.Y.Z`, `X.Y`, `latest` e `sha-<commit>` |
| **Run workflow** (`workflow_dispatch`) | `manual` e `sha-<commit>` — nunca `latest` nem a versão das lojas |

**A lib dentro da imagem (opcional).** Com o Secret `ACBRLIB_SO_URL` (um link
direto para a `libacbrnfe64.so`, por exemplo um asset de release privado) e a
Variable `ACBRLIB_SO_SHA256`, a Action baixa o arquivo, confere o SHA-256 e o
cabeçalho ELF (uma página de erro baixada no lugar reprova o build) e o embute
em `/opt/acbr`. Aí a loja e a nuvem não copiam nada à mão. Sem o Secret, a
imagem sai sem a lib, como antes. Confira a licença do Projeto ACBr antes de
publicar uma imagem com a lib num registro público.

Ordem de busca no container: a montada em `/app/libs` (vale primeiro: é como
uma loja testa uma lib nova sem esperar imagem) → a embutida em `/opt/acbr` →
nenhuma. Lib presente que não carrega (arquivo corrompido, outra arquitetura)
não derruba o container: ele sobe "unhealthy" e diz o motivo.

### Na nuvem (`docker-compose.yml`)

O `fiscal-acbr` também sobe sempre na nuvem, sem perfil. Os quatro serviços
da imagem do backend recebem `ACBRLIB_URL=${ACBRLIB_URL:-http://fiscal-acbr:8001}`:
o valor do `.env` vale; vazio, vale o emissor da própria nuvem. A lib fica em
`./acbr/libs` (fora do git). A nuvem emite para conta sem servidor de loja; com
loja, só a venda feita na nuvem e só com "A nuvem também emite" ligado
(`emissao_da_loja.py`, ver "Loja e nuvem emitindo ao mesmo tempo").

### Homologação e produção

O ambiente é o do **cadastro fiscal do restaurante** (`FiscalConfig.environment`)
e viaja em cada nota (`tpAmb` no INI e `ambiente` no contexto, que a ACBrLib
grava como `NFe.Ambiente`: 0 = produção, 1 = homologação). Os endereços da
SEFAZ de cada UF e ambiente são da própria ACBrLib — nada a configurar.

Em homologação a SEFAZ exige textos fixos, e o INI os aplica sozinho
(`acbrlib/ini.py`): primeiro item da NFC-e = "NOTA FISCAL EMITIDA EM AMBIENTE DE
HOMOLOGACAO - SEM VALOR FISCAL" (rejeição 373) e destinatário = "NF-E EMITIDA EM
AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL" (598). Em produção, os dados reais.

Ao passar de homologação para produção, no cadastro fiscal, junto com o
ambiente:

* **CSC**: é um só no cadastro (como na Focus) — troque pelo de produção;
* **próximo número**: o contador é um só. Uma nota de produção nunca repete
  o número de uma de teste (`_proximo_numero_livre` confere por ambiente), mas
  150 notas de teste fariam a produção começar no 151, e o buraco 1–150 exige
  inutilização na SEFAZ. Volte o "próximo número" para o primeiro livre da
  produção.

### De quem são os dados da nota

O comunicador não guarda configuração: **em cada chamada** o backend manda
CNPJ, UF, certificado A1 e CSC do restaurante da venda, e o grupo do emitente
vai no INI (`acbrlib/emitente.py`). Uma loja com dois restaurantes emite cada
nota com os dados do dela.

O emitente é o **cadastro fiscal do restaurante** (`FiscalConfig`), e o que
estiver em branco ali é completado, na hora da emissão, pelo **cadastro do
próprio restaurante** (razão social, IE, endereço, bairro, cidade, UF, CEP).
Antes o `FiscalConfig` só copiava esses dados ao ser criado: um endereço
preenchido depois no restaurante nunca chegava à nota. O que falta nos dois
(o código IBGE do município só existe no cadastro fiscal) impede a emissão
**antes** da SEFAZ: a nota é criada com o erro, nomeando os campos, e é
reenviada depois da correção.

## Contrato backend ⇄ comunicador

Todas as rotas exigem `Authorization: Bearer <ACBRLIB_TOKEN>`. O certificado A1,
a senha e o CSC vão em cada chamada (`segredos_de(config)` — inclusive o
emprestado da nuvem); o comunicador só os guarda em memória, pelo hash.

| Rota | Faz | Resposta |
|---|---|---|
| `GET /health` | o comunicador está de pé? (e com a lib carregada?) | `{ok, lib, simulador}` |
| `POST /v1/status-servico` | a SEFAZ responde? (`NFE_StatusServico`) | `{online, cstat, motivo}` |
| `POST /v1/nfe/emitir` | carrega o INI, assina, valida e envia (`tp_emis=1`) — ou só assina (`tp_emis=9`) | resultado |
| `POST /v1/nfe/transmitir` | envia um XML já assinado (contingência) | resultado |
| `POST /v1/nfe/consultar` | situação pela chave (`NFE_Consultar`) | resultado |
| `POST /v1/nfe/cancelar` | evento de cancelamento | resultado |

O **resultado** sempre tem a mesma forma:

```json
{"situacao": "autorizada | rejeitada | denegada | contingencia | processando | nao_encontrada | cancelada",
 "cstat": 100, "motivo": "Autorizado o uso da NF-e", "chave": "3526…", "protocolo": "135…",
 "recebido_em": "2026-10-09T14:03:11-03:00", "xml": "<nfeProc …>", "qrcode": "https://…?p=…",
 "digest_value": "…"}
```

E o erro, em HTTP, é classificado com as exceções que o backend já tem
(`providers.py`) — é isso que decide contingência e retentativa:

| Comunicador | Backend | Efeito |
|---|---|---|
| conexão recusada, 502/503, `{"erro":"sem_comunicacao"}` | `FiscalUnavailable` | contingência (se permitida) ou espera transmissão |
| tempo esgotado | `FiscalAmbiguous` | **consulta antes de qualquer reenvio** |
| `{"erro":"documento_invalido"}` (schema, assinatura) | `FiscalRejection` | erro, correção humana |
| `{"erro":"configuracao"}` (certificado, CSC, lib) | `FiscalConfigurationError` | nada sai até corrigir |
| situação `rejeitada`/`denegada` | `FiscalRejection` | erro |
| situação `nao_encontrada` | `FiscalNotFound` | pode transmitir de novo |

O erro do comunicador traz também um **`motivo`**, que o backend guarda na
exceção (`.motivo`) e transforma na providência escrita na nota
(`acbrlib/cliente.py`): `acbrlib_ausente`, `sefaz_sem_comunicacao`,
`comunicador_fora_do_ar`, `senha_invalida`, `certificado_vencido`,
`certificado_invalido`. Antes de qualquer chamada, o backend confere o A1
sozinho (`acbrlib/certificado.py`): `certificado_ausente`, `senha_invalida`,
`certificado_invalido`, `certificado_vencido` (com a data) e `cnpj_diferente`
(a raiz do CNPJ do certificado — o da matriz vale para a filial). Nenhuma
mensagem nem log leva o certificado, o base64 ou a senha: o que a lib ecoar é
trocado por `***` antes de ser gravado.

## Plano de contingência

A regra que já existe e continua valendo: **contingência é para
indisponibilidade, nunca para recusa** (`contingency.py`). A ACBrLib não muda
isso — muda que, pela primeira vez, a contingência é de verdade: XML assinado
com `tpEmis=9`, chave própria, QR Code offline e transmissão depois.

```
            venda paga
                │
        emitir (tpEmis=1)
       ┌────────┼──────────────┬──────────────────┐
  autorizada  rejeitada   sem comunicação      tempo esgotado
     │           │        (FiscalUnavailable)  (FiscalAmbiguous)
  ISSUED      ERROR            │                    │
                       contingência permitida?   CONSULTA (nunca reenvia)
                        sim │         │ não         │
             assinar tpEmis=9      espera        autorizada → ISSUED
             (mesmo número, chave   transmissão   não encontrada → transmitir
              nova, dhCont, xJust)  (retenta)     sem resposta → consulta de novo
                    │
         PENDING + contingência, DANFE de contingência impresso
                    │
     retransmissão periódica (Celery, 2 min) — envia O MESMO XML
       ┌────────────┼───────────────┐
   autorizada    rejeitada      sem comunicação
     ISSUED   ERROR + alerta     continua pendente
```

### O cliente não sai sem cupom (decisão de 2026-10-13)

Com **Permitir contingência offline** ligado, a ACBrLib também assina e
imprime em contingência a nota **recusada** pela SEFAZ, a de **tempo
esgotado** e a que ficou **aguardando autorização** (em processamento)
— `contingency.imprime_em_contingencia` e `contingencia_offline.tentar(...,
para_imprimir=True)`. Erro de cadastro (certificado, CSC) continua de fora:
sem certificado nem a contingência se assina. Desligado, vale o diagrama acima.

* **Recusada:** o DANFE de contingência sai e o motivo fica em
  `contingency_reason`. Transmitida, a contingência é recusada de novo (o
  conteúdo é o mesmo) e a nota vira erro; depois da correção, **Reenviar**
  descarta o XML recusado e emite uma nota NORMAL nova, mesmo número, chave
  refeita (`reemitir_normal_apos_recusa`). O cupom impresso fica com a chave
  da contingência, que nunca é autorizada — é o preço de o cliente sair com
  papel; corrigir rápido (prazo de 24 h) é o que limita isso.
* **Tempo esgotado / em processamento:** a nota normal PODE ter sido
  autorizada. A chave dela fica em `chave_normal` e, antes de transmitir a
  contingência, é CONSULTADA (`conferir_a_normal`): autorizada, a nota passa a
  ser ela (chave, protocolo, QR refeito) e a contingência é descartada
  (`contingencia_descartada`), sem transmitir — nada em dobro; desconhecida
  ou recusada, a contingência é transmitida; ainda processando, espera a
  próxima rodada.

Os pontos que impedem documento em dobro:

1. **Timeout não transmite contingência às cegas.** A SEFAZ pode ter
   autorizado a primeira: sem contingência ligada, o próximo passo é consultar
   (`AWAITING_RECONCILIATION`); com ela, a chave normal é consultada antes da
   transmissão (acima).
2. **O XML de contingência é transmitido como foi assinado.** A retransmissão
   não refaz `dhEmi` nem a chave (`_refresh_emission_for_retry` é pulado): o
   cupom impresso tem aquela chave, e é ela que a SEFAZ tem de receber.
3. **Mesmo número, chave nova.** A troca para contingência reaproveita o `nNF`
   que nunca foi autorizado; a chave muda porque o `tpEmis` faz parte dela.
4. **Uma nota pendente por pedido** — `Invoice` é 1:1 com o pedido, e a emissão
   trava o pedido (`select_for_update`).

Prazo: a NFC-e em contingência tem de ser transmitida em até 24 h. A
retransmissão roda a cada 2 minutos; uma nota pendente há mais de 12 h aparece
como alerta no painel fiscal.

## Recusas comuns tratadas sozinhas

**866 — Ausência de troco.** O troco é `soma(vPag) − vNF`
(`documento_regras._troco`), nunca negativo. Antes vinha só do `change_amount`
do dinheiro, e a nota com cartão/PIX pago a mais (ou desconto dado depois de
pagar) saía sem `vTroco`. Vale para a ACBrLib e para a Focus (o documento é o
mesmo).

No INI da ACBrLib o `vTroco` vai DENTRO da última seção `[pagNNN]`: é só ali
que o leitor da lib o lê (`ACBrNFe.IniReader.pas`, `Ler_Pagamento`). Ele ia
numa seção `[pag]` à parte, que a lib ignorava — e toda venda com troco
voltava 866 mesmo com o valor certo no arquivo. O teste lê o INI como a ACBr
lê (`test_rejeicoes_que_voltavam.py`), e não procura a chave em qualquer lugar.

**386 — CFOP não permitido para o CSOSN.** Na NFC-e do Simples, o CSOSN 500
(ST já recolhida) só aceita CFOP 5405, 5656 ou 5667, e os CSOSN 101, 102, 103,
300, 400 e 900 só aceitam 5101–5104 e 5115. O cadastro guarda os dois
separados; o par que não combina sai com o CFOP padrão do CSOSN (5405 ou
5102), e a troca vai para o log (`cfop_do_csosn.py`). O CFOP da venda ao
consumidor é consequência do CSOSN; no Simples ele não muda imposto nenhum.

**613/539 — Chave difere da existente em BD.** A SEFAZ já tem uma nota
autorizada com a nossa série e número e devolve a chave dela entre colchetes
(`numero_ja_usado.py`, só ACBrLib). O `cNF` decide de quem ela é, porque cada
nota nossa mantém o mesmo `cNF` em todas as tentativas:

* **mesmo cNF** — é uma tentativa anterior desta nota (tempo esgotado, a normal
  que a contingência substituiu): consulta e adota chave e protocolo, sem
  reemitir;
* **cNF diferente** — outro emissor usou o número (dois servidores com o mesmo
  CNPJ e série em bancos separados, como a loja e uma nuvem de teste; ou o
  contador voltado para trás). O número está queimado: a nota é refeita no
  próximo número livre, com `cNF` novo, e reenviada; se o seguinte também
  for de outro emissor, segue andando até `TENTATIVAS_DE_NUMERO` (10) — andar
  um por reenvio deixava o operador clicando e recebendo 613 com o contador
  alguns números atrás. O motivo fica em
  `fiscal_payload["numero_ja_usado_na_sefaz"]`. Passando do teto, a recusa
  fica na nota para correção do cadastro.

**A nota recusada emitida de novo mantém número e `cNF`**
(`numero_desta_emissao`). Recusa não gasta o número na SEFAZ. Antes, cada
"emitir de novo" de uma nota em erro (o botão do PDV, a emissão automática)
dava número e `cNF` novos: um buraco na série por tentativa, e a nota deixava
de se reconhecer quando uma tentativa anterior tinha sido autorizada — virava
"nota de outro emissor" (613) e podia sair uma segunda nota para a mesma venda.

A causa da 613 com cNF diferente é sempre fora do código: **dois pontos
emitindo na mesma série**. Cada ponto de emissão precisa da sua série — inclusive
um ambiente de teste apontado para o mesmo CNPJ. O contador (`avancar_contador`)
nunca anda para trás.

## Cancelamento

Cancelar o pedido cancela a nota (`cancel_order` → `cancel_invoice_for_order`
→ `cancel_fiscal_invoice`): nota AUTORIZADA vira o evento de cancelamento na
SEFAZ (`NFE_Cancelar`, justificativa de 15 a 255 caracteres); nota que nunca
foi autorizada só é cancelada no sistema. Tudo numa transação: se a SEFAZ
recusa (fora do prazo — 30 min para NFC-e na maioria das UFs), o pedido também
NÃO é cancelado e o caixa vê o motivo. O protocolo do EVENTO fica em
`fiscal_payload["cancelamento"]`; o de autorização continua no campo dele
(antes era sobrescrito, e a nota perdia o número que prova a autorização).

## Toda falha deixa a nota gravada

Qualquer falha da emissão grava a nota em `error`, com o motivo em
`error_message`, para corrigir e **reenviar** (botão Reenviar, ou emitir de novo
pelo PDV). Isso vale para o que falha na SEFAZ, no comunicador e no cadastro do
emitente, e também para o que falha ANTES de a nota ser montada
(`invoices/nota_com_erro.py`):

| Falha | O que fica gravado |
| --- | --- |
| pedido sem item faturável (todos cancelados ou cortesia) | nota em erro, "Pedido sem itens faturaveis" |
| CPF/CNPJ do cliente inválido, ou os dois juntos | nota em erro com o motivo; emitir de novo com o documento certo reaproveita a mesma nota |
| exceção no meio da montagem | a montagem é desfeita inteira e a nota fica em erro com a exceção |

A nota que falhou antes de ser montada fica **sem número e sem chave**: o
número só é gasto quando a montagem dá certo (um buraco na série exigiria
inutilização). O reenvio dela passa pela emissão inteira, que a reaproveita.
Continuam recusando sem gravar só o que não é nota: pedido cancelado,
restaurante sem configuração fiscal e documento enviado com tipo errado pela API.

## Numeração e sincronização

- A nota sincroniza nos dois sentidos (`catalog.py`): a emitida na loja sobe; a
  da nuvem desce. Vence a versão mais nova, e nota fiscal nunca é adotada.
- `FiscalConfig.next_number` passou a ser **local de cada nó**
  (`local_only_fields`): com "vence o mais novo", uma edição do cadastro na
  nuvem trazia o contador velho de volta para a loja e a próxima nota repetia
  número. Quem numera é quem emite, e `_proximo_numero_livre` ainda pula
  qualquer número que já apareceu numa nota sincronizada.
- **A nuvem não emite pela ACBrLib uma venda de loja que tem servidor
  local.** Com a loja fora, o PDV recebe pela nuvem; a nota fica para a loja,
  que emite sozinha quando o pedido pago chegar (`emitir_pagos_sem_nota`). Dois
  emissores com a mesma série produziriam números repetidos. Conta só-nuvem
  (sem servidor local) emite pela ACBrLib da nuvem normalmente.

### Loja e nuvem emitindo ao mesmo tempo

No cadastro fiscal do restaurante (seção ACBrLib), **A nuvem também emite**
(`FiscalConfig.cloud_emission`, desligado por padrão) faz a nuvem emitir as
vendas feitas NELA, numa **série só dela** (`cloud_series`, com contador
próprio `cloud_next_number`, que não viaja). Quem emite cada venda:

| Venda | Desligado (padrão) | Ligado |
|---|---|---|
| feita na loja | loja, série da loja | loja, série da loja |
| feita na nuvem (pedido ≥ 1.000.000) | loja, quando o pedido chega | **nuvem, série da nuvem** |

"Feita na nuvem" é o pedido na faixa da nuvem (`orders/sequence_ranges.py`).
A loja deixa de varrer esses pedidos (`emitir_pagos_sem_nota`): eles chegam
pagos e ainda sem nota — a nota vem atrás — e varrê-los daria duas notas.

**Por que série separada, e não trocar o último número pela sincronização
(ou por WebSocket).** Funcionaria só com os dois lados conectados. A nuvem
emite justamente quando a loja está fora — e aí nenhum dos dois enxerga o
contador do outro: a loja em contingência offline e a nuvem entregariam o
mesmo número. Série diferente não colide nunca, online ou offline, sem fila
distribuída nem trava entre servidores. A SEFAZ aceita várias séries no mesmo
CNPJ (é o normal: uma por ponto de emissão).

O que continua igual em cada ponto: uma emissão por vez (trava do cadastro,
`select_for_update`), o pulo de número já visto numa nota sincronizada
(`_proximo_numero_livre`) e as notas viajando nos dois sentidos — o painel dos
dois lados mostra as duas séries.

A série da nuvem é obrigatória e diferente da série da loja: o serializer
responde 400 e o banco tem a trava (`fiscal_config_serie_da_nuvem_distinta`)
para o que não passa por ele (admin, shell). Ao ligar em produção, confira na
SEFAZ que a série escolhida não tem uso anterior.

## Teste no par Docker (loja ⇄ nuvem)

Com o par de `docker/loadtest/docker-compose.pair.yml` no ar (cada lado com o
seu comunicador em modo simulador; `bash loadtest/scripts/start_sync_pair.sh`):

1. `docker exec -i syncpair-backend-cloud-1 python manage.py shell < loadtest/fiscal_acbr/preparar.py > dados.json`
   — configuração ACBrLib e 4 caixas, criados NA NUVEM (descem pela sincronização).
   O certificado é fictício (`/tmp/teste.pfx` em cada container do backend):
   o simulador não confere assinatura, e a loja o recebe emprestado da nuvem.
2. `python loadtest/fiscal_acbr/emitir.py dados.json vendas.json` — 100 vendas
   com a SEFAZ no ar, 100 com ela fora (contingência) e uma de 200 itens em cada.
3. Voltar a SEFAZ: `POST http://127.0.0.1:8032/_simulador/modo {"modo":"online"}`.
4. `python loadtest/fiscal_acbr/conferir.py vendas.json` — tudo autorizado,
   chave da contingência preservada, número sem repetição, os dois bancos iguais.

Resultado da primeira rodada e os dois defeitos que ela achou:
`docs/ANALISE_DE_RISCOS.md`, seção 2.5.7.

## Roteiro de homologação

1. Subir o comunicador com a lib e o certificado de homologação;
   `GET /health` com `lib: true`.
2. `POST /v1/status-servico` em homologação: `online: true`.
3. Venda real no PDV → NFC-e autorizada (cStat 100), DANFE com protocolo.
4. Derrubar a internet → venda → DANFE de **contingência**; nota `pendente`.
5. Reiniciar o container com a nota pendente → nada se perde.
6. Voltar a internet → a nota é autorizada sozinha em até 2 min.
7. Simular timeout (bloquear a resposta) → sem contingência ligada, a nota
   fica em conciliação e é consultada, nunca reenviada; com ela, sai o DANFE de
   contingência e a chave normal é consultada antes da transmissão.
8. Dois caixas emitindo ao mesmo tempo → números diferentes.
9. Forçar uma rejeição (NCM inválido) → sem contingência ligada, erro
   explicado; com ela, DANFE de contingência, erro na transmissão, corrigir e
   reenviar sai como nota normal nova.
10. Cancelar uma nota autorizada → evento registrado.

O mapeamento do INI (`acbrlib/ini.py`) segue o leiaute da ACBrLib NFe e é
validado pela própria lib (`NFE_Validar`) antes de qualquer envio; o passo 3
é o que confirma cada campo contra a SEFAZ do estado.
