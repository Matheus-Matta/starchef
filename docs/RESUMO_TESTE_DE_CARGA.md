# Teste de desempenho sob carga massiva — resumo geral

Trabalho de 10 e 11/09/2026 na branch `release/v2.0.0`. Este arquivo é o
sumário executivo: o que foi construído, o que quebrou, o que mudou e o que
ainda vale fazer. O detalhe item a item (arquivo, linha, causa raiz) vive em
[`ANALISE_DE_RISCOS.md`](ANALISE_DE_RISCOS.md); a operação das suítes em
[`TESTE_CARGA.md`](TESTE_CARGA.md) e [`TESTE_CARGA_PDV.md`](TESTE_CARGA_PDV.md).

**Nada disto está commitado.** Está tudo na árvore de trabalho, junto com
alterações que já estavam lá antes (fichas técnicas de preparo, sugestão de
mesa no app do garçom) e que não fazem parte deste trabalho.

---

## 1. O pedido e o critério

"Quebrar o código de propósito": carga massiva, com dados variados, toscos e
inválidos, em todas as entidades e nas quatro frentes (backend, painel web,
PDV desktop, app do garçom), para achar o que o cliente acharia depois.

O critério de sucesso não foi vazão. Foi **veredito por requisição**:

| Veredito | Significa | Conta como |
| --- | --- | --- |
| `erro_servidor` (5xx) | quebrou | defeito |
| `lixo_aceito` (inválido → 2xx) | validação faltando | defeito |
| `falha_transporte` | conexão derrubada / timeout | defeito de ambiente |
| `valido_recusado` | payload bom recusado com 4xx | suspeita — lê-se a mensagem |
| `sobrecarga` (503 + Retry-After) | servidor disse que está saturado | capacidade, não defeito |

E, no PDV, **orçamento de tempo por operação** (p95 máximo defensável por
operação; amostra acima de 10× = travou).

---

## 2. O que foi construído

### 2.1 `loadtest/` — carga das quatro frentes (Python, só stdlib)

- **backend**: tempestade de criação sobre os **46 modelos** que o OpenAPI
  do próprio backend descreve (campo novo entra sozinho), em 7 fases: rajada
  isolada por modelo, tempestade misturada, leitura hostil, corpo cru
  malformado, alteração/exclusão (inclusive de IDs inexistentes), **relatórios
  e agregações** e **operações em lote** (as duas últimas adicionadas na 3ª
  rodada).
- **web**: enxurrada no SPA em degraus (shell, assets, chamadas de abertura)
  e envio de formulário certo/errado no meio dela.
- **desktop**: frota de PDVs simulados falando o protocolo real (fila offline,
  relay secundário → principal, venda, caixa, turno).
- **mobile**: enxame de apps de garçom.
- Três qualidades de payload: **limpo** (CPF/EAN com dígito certo, referências
  reais), **desleixado** (erro de digitação clássico — aceitar ou recusar são
  defensáveis) e **inválido** (13 mutações: obrigatório removido, tipo errado,
  negativo, absurdo, referência quebrada, texto hostil, JSON fundo…).
- `consolidar.py` junta execuções e cruza com o log do servidor: cada 500 sai
  com **arquivo, linha e causa raiz**.
- Perfis `fumaca` / `moderado` / `pesado` / `extremo`. Roda **só na mão**,
  nunca em CI, nunca contra banco real.

### 2.2 `flutter/loadtest/` — carga do núcleo Dart do PDV

Roda o **código real** do terminal (SQLite, `SyncQueueService`,
`OfflineFirstGateway`, balança, impressão); só a rede é falsa. Começa
desligada em toda execução — tudo tem de funcionar offline. Fica fora de
`test/` de propósito.

### 2.3 `docker/loadtest/` — alvo em modo produção (Docker local)

Mesma imagem, mesmo comando (migrate + collectstatic + gunicorn/UvicornWorker)
e mesmos settings (`config.settings.production`) do `docker-compose.yml` da
raiz — que **não foi tocado**. Postgres 16 sobe num container **separado**
(`starchef-pg-loadtest`), depois backend + Redis. Um comando:
`bash loadtest/scripts/start_prod_target.sh 8012` (`--down` derruba).

---

## 3. As rodadas e o que cada uma achou

| # | Alvo | Achou | Resultado depois das correções |
| --- | --- | --- | --- |
| 1 | `runserver` + SQLite | **3.082 × 5xx** no backend, 51 lixos aceitos, 12 causas raiz de 500; 180 exceções e 1.014 lixos no PDV Dart | 5xx → 0, lixo → 0 nas 4 frentes; PDV 0/0 |
| 2 | revisão dirigida (o que a carga não alcança) | cadeia secundário → principal → nuvem e caixa offline: venda duplicada no secundário, pico do principal mandando venda para revisão manual, sangria com diferença fantasma, catálogo parado em 300 produtos | 827 testes Flutter verdes |
| 3 | idem, suíte ampliada (relatórios + lotes) | 0 × 5xx; a seção "Suspeitas" mostrou que os **forms do painel** não aplicavam regras que conheciam | validação no cliente; 2.736 suspeitas → 186 |
| 4 | idem | rota inexistente devolvendo **HTML**, 53 erros fora do envelope, comanda sem `number` recusada | envelope único; 657 testes |
| 5 | alinhamento entidade a entidade | 74 divergências form ↔ OpenAPI; **49 campos numéricos sem piso** no backend | cruzamento zerado; piso por padrão; 661 testes |
| 6 | **gunicorn + Postgres + Redis** | **`too many clients` × 28.203**, `varchar` estourando (500 ao salvar restaurante), **deadlock** na ficha técnica | 0 × 5xx nas 4 frentes; Postgres em 41 conexões; 664 testes |

### Números finais (perfil `pesado`, 128 conexões, alvo 1.000 req/s)

**Modo produção, 4 workers gunicorn, Docker local:**

| Frente | reqs | rps médio / pico | p50 | p99 | 5xx | lixo aceito |
| --- | --- | --- | --- | --- | --- | --- |
| backend | 27.077 | 54 / 190 | 1,7 s | 6,7 s | **0** | **0** |
| web | 27.274 | 176 / 458 | 195 ms | 4,2 s | **0** | **0** |
| desktop | 5.422 | 22 / 64 | 189 ms | 771 ms | **0** | **0** |
| mobile | 5.386 | 25 / 61 | 331 ms | 6,1 s | **0** | **0** |

PDV Dart: catálogo de 5.000 produtos de p95 225 ms → 30 ms.
Consolidador: _nada a corrigir_.

---

## 4. O que mudou no produto

### 4.1 Backend (Django)

**Padrões transversais** (`apps/core`):

- `requests.py` `required_field` — `request.data["campo"]` virava `KeyError`
  → 500. Agora 400 dizendo qual campo falta.
- `numbers.py` `parse_money` / `parse_quantity` / `parse_decimal` /
  `fits_decimal` — `Decimal(str(valor))` sobre corpo de requisição virava
  `InvalidOperation` ou estouro no driver.
- `viewsets.py` `JsonObjectBodyMixin` — corpo que não é objeto JSON é 400,
  não 500 (rotas de auth precisaram herdar explicitamente).
- `serializers.py` `TenantModelSerializer` — teto de inteiro de 64 bits e
  **piso zero em todo numérico gravável** (`Decimal/Float/Integer`); quem é
  assinado por natureza declara `Meta.signed_fields` (`price_delta`,
  `margin_percent`, `quantity` de movimento de estoque). A lista opt-in
  `non_negative_fields` deixou de existir.
- `envelope.py` `ApiErrorEnvelopeMiddleware` — **todo** erro ≥ 400 sob
  `/api/` sai em `{success, status_code, error: {code, message}}`: view com
  `Response({"detail"})`, `JsonResponse` de middleware, e a página HTML de
  404/405 do Django. Corpo estruturado (409 do caixa com `session`) entra
  inteiro em `error`.
- `exceptions.py` + `middleware.py` — `OperationalError` (pool esgotado, banco
  fora) responde **503 + `Retry-After: 2`**, não 500 nem 401.
- `config/settings/base.py` — **pool nativo de conexões** Postgres (Django
  5.1 + psycopg 3): `POSTGRES_POOL_MAX` por worker, `CONN_MAX_AGE=0`. Sob
  ASGI a conexão persistente vazava por thread. Dependência:
  `psycopg[binary,pool]`.
- SQLite (dev): WAL + `transaction_mode=IMMEDIATE` + timeout 30 s.

**Por domínio:**

- Comandas: `number` opcional de verdade (o `UniqueTogetherValidator` gerado
  pelo `UniqueConstraint` anulava o `required=False`; a numeração automática
  nunca era alcançável pela API).
- Menus: `slug` derivado do nome quando omitido (o `validate` que fazia isso
  era código morto).
- Fiscal: espelho restaurante → `FiscalConfig` corta no `max_length` da coluna
  (`ie` 20 < `state_registration` 40; `zip_code` 9 < 16).
- Fichas técnicas: `recalculate_recipe_costs` trava a receita
  (`select_for_update`) — um recálculo por ficha; zero deadlock.
- Pai e filhos em transações separadas (registro pela metade) →
  `@transaction.atomic` nos serializers que gravam filhos.
- `seed_demo` voltou a gerar vendas (cartão sem `card_subtype` quebrava desde
  a regra da NFC-e).
- Dezenas de `Model.objects.get(pk=<do cliente>)` → `.filter().first()` com
  400/404 nomeando a referência.

### 4.2 PDV Flutter

- `_findCommandByCode` lia UMA página de 500 comandas: acima disso a Balança
  Rápida dizia "comanda não encontrada" para comanda que existe. Usa o índice
  `entity_codes`.
- `SyncService._deliver` só capturava o esperado: um `FormatException` (HTML
  de proxy caído) **parava a sincronização inteira**.
- `quantity <= 0 ? 1 : quantity` cobrava item que ninguém pediu; produto fora
  do catálogo virava item sem nome/preço. `requireMoney` / `requireQuantity`
  em `input_values.dart`.
- Caixa sem estação (sessão fantasma), `opening_amount` ilegível virando 0,00,
  gaveta em `double` → centavos inteiros (`DecimalMoney`), igualdade exata.
- **Secundário → principal → nuvem**: `_client_ids` no `/v1/read` para
  reconciliar venda criada pelo principal sem nuvem (backend não persiste
  `client_order_id`); `RelaySyncTransport` trata 408/425/429/5xx como
  temporário; pesagem relayada resolve produto por `scale.product`;
  sangria/suprimento offline nascem `pending` e a resposta é o movimento;
  **caixa do secundário funciona inteiro sem rede** (abrir/sangrar/suprir/
  autorizar/fechar via fila; só transferir posse exige quem esteja no ar);
  `loadCatalog` pagina (teto 5.000); pull do secundário a cada 30 s.
- Regra alinhada com o servidor: o que o backend recusa o PDV também recusa,
  antes de imprimir e cobrar.

### 4.3 Painel web (Vue)

- `PdvView.vue` lia `error.response.data.detail` — campo que o envelope não
  tem; a razão real da recusa sumia na pesagem e no recebimento.
- `utils/formValidation.js`, chamado no `save()` do `useResourceForm`:
  obrigatório, inteiro/decimal, piso (`min`, `allowNegative`), `maxlength`,
  `document: "cpf" | "cnpj"`, regra cruzada `notGreaterThan` (SLA). O erro
  aparece **no campo**, sem round-trip.
- `resources.js` alinhado ao OpenAPI dos 25 forms: 60 `maxlength`, 4
  obrigatórios (`phone` do cliente, `internal_code` do produto,
  `max_radius_km`, `legal_name`), `min: 1` na comanda, CPF/CNPJ.
- `CashRegisterView.vue`: salvar caixa desabilitado sem nome/operador; lê
  `data.error ?? data` no 409.

### 4.4 Ferramentas e infra

- `backend/Dockerfile`: `ARG PIP_TRUSTED_HOST` (vazio em produção) para o pip
  do container atrás de proxy que intercepta TLS.
- `.env.example`: `POSTGRES_POOL*`.
- Harness: geradores por convenção de nome (`*_by` → usuário, `station` sob
  `/kitchen/` → estação do KDS, CNPJ de 14 dígitos, `username` válido,
  decimal respeitando o `pattern` do schema, `format: time`, `restaurant`
  nunca omitido, `number`/`name`/`slug` únicos entre fases e execuções).

### 4.5 Testes

| Suíte | Antes | Depois |
| --- | --- | --- |
| backend (pytest) | — | **664** |
| frontend (vitest) | — | **96** |
| PDV Flutter | — | **827** |

Regressões da carga fixadas em `backend/tests/test_entrada_invalida_nao_quebra.py`,
`backend/apps/core/tests/test_api_error_envelope.py`,
`frontend/src/utils/formValidation.test.js` e nos testes Dart de relay/fila/caixa.

### 4.6 Documentação

`ANALISE_DE_RISCOS.md` (inventário completo), `TESTE_CARGA.md`,
`TESTE_CARGA_PDV.md`, seções novas em `BACKEND.md` (envelope, piso numérico,
pool, SQLite) e `FRONTEND.md` (validação de forms), `PDV_OFFLINE_SCALE_ARCHITECTURE.md`.

---

## 5. As lições que valem levar para a próxima revisão de código

1. **Três famílias causavam quase todo 500**: `request.data["campo"]`,
   `Model.objects.get(pk=<do cliente>)` e `Decimal(str(valor))`. O 500 não é
   só a mensagem errada — **o PDV trata 5xx como temporário** e retenta para
   sempre em vez de mandar para revisão. Um campo esquecido virava uma venda
   presa que ninguém destravava.
2. **Opt-in não escala.** `non_negative_fields` deixou 49 campos de fora;
   o mecanismo virou padrão-ligado com opt-out (`signed_fields`).
3. **SQLite esconde três classes de defeito**: largura de `varchar`, pool de
   conexões e deadlock. Só o alvo em modo produção as mostra — 661 testes e
   quatro rodadas passaram por elas sem ver.
4. **`UniqueConstraint` gera `UniqueTogetherValidator`** que exige os campos
   presentes — anula qualquer `required=False` e qualquer auto-preenchimento
   no `validate`.
5. **Sob ASGI, `CONN_MAX_AGE > 0` vaza conexão por thread.** Pool ou nada.
6. **"Suspeita" com mensagem clara é regra de negócio; sem mensagem é bug.**
   O critério de leitura da seção "Suspeitas" é esse.

---

## 6. O que ainda vale fazer

Em ordem de valor, com o esforço estimado.

### Alto valor

1. **Dimensionar a VPS de produção com os números medidos.** 4 workers
   aguentaram 190 req/s de pico em 20 cores locais; a VPS é menor. Regra:
   `GUNICORN_WORKERS × POSTGRES_POOL_MAX < max_connections` do Postgres.
   Rodar `start_prod_target.sh` com `GUNICORN_WORKERS` igual ao da VPS e
   `mem_limit` equivalente dá o número real. *(1 tarde)*
2. **Canal de eventos principal → secundários.** O secundário só vê o que os
   outros terminais fizeram pelo `pullAll` de 30 s (era 5 min). Reemitir na
   rede local o mesmo WebSocket que o principal recebe da nuvem tira a
   defasagem de vez. Decisão de produto pendente. *(2–3 dias)*
3. **`EXPLAIN` dos relatórios com base grande.** `reports/sales` isolado a
   437 ms já na base de demonstração; sob carga, p99 de 4–7 s. Hoje é CPU dos
   workers, mas a agregação cresce com a tabela de pedidos. Índice em
   `(restaurant, created_at)` e nos `GROUP BY` mais usados. *(1 dia)*

### Médio valor

4. **WebSocket sob carga.** `/ws/pdv/` e `/ws/kitchen/` não têm nenhuma
   medição; uma tempestade de invalidações com dezenas de terminais é
   cenário plausível. *(1–2 dias para a suíte)*
5. **Cadeia secundário → principal pela rede real.** Os simuladores fazem o
   relay em processo; a API local `/local/...` com HMAC tem testes de unidade,
   não de volume. *(1 dia)*
6. **Emissão fiscal.** `POST /invoices/emit/` está bloqueado nas suítes por
   chamar provedor externo; a fila fiscal do PDV é exercitada, o caminho
   servidor → SEFAZ não. Precisa de um Focus NFe de homologação ou um
   stub. *(depende do provedor)*
7. **Perfil `extremo` em produção.** Só o `pesado` rodou no alvo Docker.
   *(1 execução)*

### Manutenção

8. **Cruzamento form ↔ OpenAPI como verificação repetível.** O script que
   zerou as 74 divergências viveu só na sessão; vale um teste (vitest lendo o
   `schema.json` gerado) que acuse `maxLength`/obrigatório divergente em CI.
   *(meio dia)*
9. **Harness: pools que ainda produzem suspeita legítima.** `profile.role`
   de usuário, categoria de menu automático, estação de caixa para
   `cash-register/open` — o gerador não sabe montar esses contextos e o
   servidor recusa corretamente. Ensinar o cenário mínimo a criar cada um
   tiraria ~60 linhas por rodada da seção "Suspeitas". *(meio dia)*
10. **`POSTGRES_CONN_MAX_AGE=0` já está no `.env`** — mas conferir na VPS que
    `POSTGRES_POOL` fica ligado (padrão) e que a imagem publicada traz
    `psycopg[pool]` (requirements alterado; precisa de nova tag de release).
11. **Commit.** Tudo isto está na árvore de trabalho junto com trabalho
    anterior não relacionado; separar em commits por tema antes de mesclar.

---

## 7. Como repetir tudo

```powershell
# alvo de dev (rápido, SQLite) — fumaça
bash loadtest/scripts/start_backend.sh 8011
.venv/Scripts/python loadtest/run.py all --profile fumaca --base-url http://127.0.0.1:8011

# alvo em modo produção (Docker local: Postgres separado + gunicorn + Redis)
bash loadtest/scripts/start_prod_target.sh 8012
npm --prefix frontend run dev -- --port 5199
.venv/Scripts/python loadtest/run.py all --profile pesado --base-url http://127.0.0.1:8012 --frontend-url http://127.0.0.1:5199
docker compose -f docker/loadtest/docker-compose.yml logs backend --no-log-prefix > artifacts/loadtest/servidor.log
.venv/Scripts/python loadtest/consolidar.py "artifacts/loadtest/carga-*.json" --server-log artifacts/loadtest/servidor.log
bash loadtest/scripts/start_prod_target.sh --down

# núcleo do PDV
Set-Location flutter
flutter test loadtest/ --dart-define=PERFIL=pesado
```
