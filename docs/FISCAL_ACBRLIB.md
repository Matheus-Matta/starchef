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
compose, e o instalador gera o `ACBRLIB_TOKEN` e cria `docker/local/acbr/libs`.
Para emitir, só falta:

1. copiar a `libacbrnfe64.so` para `docker/local/acbr/libs` e rodar
   `docker compose --env-file .env.local -f docker-compose.local.yml restart fiscal-acbr`;
2. no painel, escolher o provedor **ACBrLib** no cadastro fiscal do restaurante.

Tudo isso roda dentro da loja: com a internet fora, o backend da loja chama o
comunicador da loja, e a nota sai em contingência offline (tpEmis=9) quando a
SEFAZ não responde.

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
`./acbr/libs` (fora do git). A nuvem emite só para conta sem servidor de loja
(`emissao_da_loja.py`): venda de loja é emitida pela loja.

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

Os pontos que impedem documento em dobro:

1. **Timeout nunca vira contingência.** A SEFAZ pode ter autorizado a primeira;
   o próximo passo é sempre consultar (`AWAITING_RECONCILIATION`).
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
7. Simular timeout (bloquear a resposta) → a nota fica em conciliação e é
   consultada, nunca reenviada.
8. Dois caixas emitindo ao mesmo tempo → números diferentes.
9. Forçar uma rejeição (NCM inválido) → erro explicado, sem contingência.
10. Cancelar uma nota autorizada → evento registrado.

O mapeamento do INI (`acbrlib/ini.py`) segue o leiaute da ACBrLib NFe e é
validado pela própria lib (`NFE_Validar`) antes de qualquer envio; o passo 3
é o que confirma cada campo contra a SEFAZ do estado.
