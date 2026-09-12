# Análise de riscos — o que a carga encontrou e o que ela ensinou a procurar

> Sumário executivo de todo o trabalho (o que foi feito, o que mudou, o que
> falta): [`RESUMO_TESTE_DE_CARGA.md`](RESUMO_TESTE_DE_CARGA.md).

Documento de saída da rodada de correções de **10/09/2026**, feita a partir dos
testes de carga ([`TESTE_CARGA.md`](TESTE_CARGA.md) e
[`TESTE_CARGA_PDV.md`](TESTE_CARGA_PDV.md)).

Tem duas partes: **o que foi corrigido** e **o que a varredura por famílias
semelhantes encontrou depois** — porque cada defeito achado sob carga é um
representante de uma classe, e a classe costuma ter outros membros.

---

## 1. As três famílias de defeito

Praticamente tudo o que a carga derrubou cabe em três padrões. Vale reconhecê-los
em revisão de código, porque o teste só encontra o que alguém exercita.

### 1.1 `request.data["campo"]` — o corpo é do cliente

Ler um campo obrigatório com colchete levanta `KeyError` quando ele não vem. O
handler da API traduz isso para **500 "Ocorreu um erro interno"**.

O custo não é só a mensagem errada. **O PDV trata 5xx como falha temporária**:
ele devolve a operação à fila e tenta de novo, para sempre, em vez de mandá-la
para a tela de revisão. Um campo esquecido no app do garçom virava uma venda
presa na fila que ninguém conseguia destravar.

**Regra:** campo obrigatório se lê com `required_field(request, "campo", "…")`
(`apps/core/requests.py`), que levanta `ValidationError` → 400 com a mensagem.

### 1.2 `Model.objects.get(pk=<vindo do cliente>)` — a referência pode não existir

`DoesNotExist` também não é capturado por ninguém e vira 500. E o identificador
quase sempre vem de fora: o PDV monta o recebimento com o cadastro que tem em
**cache**, que pode estar velho; o app do garçom manda o produto que estava na
tela dele.

**Regra:** `.filter(...).first()` e um 400/404 dizendo **qual** referência não
existe. Envolver em `try/except (ValueError, ValidationError)` quando o `pk` for
UUID — um valor que nem é UUID estoura antes de consultar.

### 1.3 `Decimal(str(valor))` — dinheiro digitado à mão

`Decimal("dez reais")` levanta `InvalidOperation`; `Decimal("1e30")` passa e só
estoura no driver, com `max_digits` excedido — 500 longe da causa.

**Regra:** `parse_money` / `parse_quantity` / `parse_decimal`
(`apps/core/numbers.py`). No lado Dart, `requireMoney` / `requireQuantity`
(`lib/core/formatters/input_values.dart`) — **`ValueFormatters.number` é para
EXIBIR**: ele devolve `0` para o que não parseia, o que é certo numa tela e
errado numa gravação.

---

## 2. O que foi corrigido

### 2.1 Backend — erro de cliente virando 500

| Onde | Era |
| --- | --- |
| `orders/views.py` `items` | item sem `product` e produto inexistente/de outro restaurante |
| `orders/views.py` `pay` | recebimento sem `payment_method` e sem `amount` |
| `payments/services.py` `register_payment` | forma de pagamento inativa ou de outro restaurante |
| `orders/services.py` `close_order` | `discount`, `service_fee` e `expected_total` em texto |
| `orders/services.py` `add_order_item` | `quantity` e `weight_kg` em texto ou absurdos |
| `payments/services.py` | `opening_amount`, `actual_amount` e `amount` da movimentação |
| `payments/views.py` `close` | `actual_amount` ausente |
| `kitchen/views.py` e `orders/views.py` `status` | `status` ausente |
| `printers/views.py` | `tare_kg` em texto |
| `menu/services/recipes.py` | custo da ficha estourando `max_digits` (quantidade × custo, e a divisão pelo rendimento) |
| `printers/serializers.py` | `settings` recebendo lista em vez de objeto |
| `restaurants/models.py` | `number` com inteiro grande demais (o SQLite não declara faixa, e o DRF não tinha o que herdar) |

### 2.2 Backend — dado inválido sendo aceito

- **desconto negativo** no fechamento: a guarda era `> 0`, então o negativo
  passava e **aumentava** o total, sem exigir gerente e sem aparecer;
- **desconto maior que o subtotal**: o total ia a zero pelo `max(0)` do
  recálculo, e a venda ficava com um desconto que nunca existiu;
- **preço e custo negativos** em produtos, variações, adicionais, insumos,
  fichas, itens de ficha, itens de menu e notas fiscais.

`Meta.non_negative_fields` declara quais campos não aceitam sinal negativo.
`price_delta` de variação e `margin_percent` ficam de fora **de propósito**:
existem negativos por natureza.

### 2.3 Backend — integridade

- `POST /restaurants/` não era atômico: uma falha no provisionamento fiscal
  deixava o restaurante criado pela metade. Era também a rota que mais disputava
  lock, por segurar o banco em várias transações curtas seguidas.
- `UserSerializer.create` criava o usuário e o perfil separados: um perfil
  recusado deixava um **usuário órfão** — sem conta vinculada ele não entra, não
  aparece na lista com escopo de tenant e só é encontrado pelo `/admin`.
- `CustomerSerializer`, `StockEntrySerializer` e `StockExitSerializer`: pai e
  filhos em transações separadas. Meia entrada de estoque gravada é pior que
  nenhuma — o inventário nunca mais fecha.
- `AuditCreateUpdateMixin`: o registro e sua entrada de auditoria eram duas
  gravações independentes. Auditoria só vale se for completa.

### 2.4 Backend — corpo que não é objeto

`request.data` pode ser uma **lista** (`[1,2,3]`), e toda view do projeto
escreve `request.data.get(...)` — que em lista é `AttributeError` → 500.
`JsonObjectBodyMixin` (`apps/core/viewsets.py`) recusa com 400 em um lugar só,
e foi estendido às rotas de autenticação e de conta, que ficavam fora da base
comum. `POST /auth/login/` com dois caracteres derrubava a rota mais exposta do
sistema.

### 2.5 PDV Flutter

| Onde | Era |
| --- | --- |
| `offline_first_gateway.dart` `_findCommandByCode` | lia UMA página de 500 comandas e varria em Dart: com mais de 500 cartões, a Balança Rápida respondia "comanda não encontrada" para comandas que **existem**. Agora usa o índice `entity_codes`, que já existia |
| `sync_service.dart` `_deliver` | só capturava `TransientSyncFailure` e `ApiException`. Um `FormatException` do `jsonDecode` — o HTML que um proxy reverso caído devolve — **parava a sincronização inteira do terminal**, com a fila cheia e sem aviso |
| `order_repository.dart` | `quantity <= 0 ? 1 : quantity`: zero, negativo e "duas" viravam **um item cobrado**; produto fora do catálogo local virava item **sem nome e sem preço** |
| `cash_register_repository.dart` | caixa abria sem estação (sessão fantasma que bloqueava a próxima abertura) e com `opening_amount` ilegível virando 0,00 |
| `entity_repository.dart` | busca decodificava o catálogo inteiro a cada tecla; `page_size` sem teto |

### 2.5.1 Segunda rodada — principal, secundário e offline (11/09/2026)

Revisão dirigida ao que a carga não alcança: a cadeia
**secundário → principal → nuvem** e os métodos de caixa sem internet.

| Onde | Era |
| --- | --- |
| `entity_repository.dart` / `local_topology_service.dart` | **A mesma venda virava dois pedidos no secundário.** Com o principal sem nuvem, ele respondia à criação relayada com o temporário DELE (`offline-…`); quando a internet voltava e o servidor numerava a venda, o secundário ficava com o temporário e a próxima leitura trazia a mesma venda como `srv-…`. O backend não persiste `client_order_id`, então não havia como correlacionar. Agora o principal anexa `_client_ids` (os temporários que promoveu àquele id) aos registros que serve pela rede local, e quem tiver um deles gravado promove antes de gravar |
| `relay_sync_transport.dart` | **Pico do principal mandava a venda do secundário para revisão manual.** 429 ("processando muitas operações locais"), 503 ("não alcançou a nuvem") e 5xx chegavam como `ApiException` sem `isConnectivity` — o `_signedRequest` reconstrói a exceção só com status e prazo — e a fila marcava `FAILED`. Passaram a ser falha temporária, com a mesma tabela de status que o `ApiClient` usa para a nuvem |
| `offline_first_gateway.dart` `_writeScaleCheckout` | **Pesagem relayada estourava `ArgumentError` no principal sem nuvem.** O produto por quilo vinha só no contexto da janela da balança, que não viaja pela rede. Agora é resolvido pelo cadastro da balança (`scale.product`), como o backend faz no replay |
| `cash_register_repository.dart` + diálogo de sangria | **Sangria offline "batia" no terminal e chegava ao servidor com diferença fantasma.** Localmente a sangria contava no saldo na hora; no servidor ela nasce `pending` e só conta depois de autorizada. E a autorização nunca abria offline: a resposta local era a SESSÃO (status `open`), não o movimento (status `pending`) que a tela espera. Agora o movimento nasce pendente nos dois lados, a resposta é o movimento, a aprovação recompõe o saldo, e o diálogo aceita a **senha de ações do caixa** (conferida sem internet) quando não há gerente para logar |
| `pdv_repository.dart` `loadCatalog` | **Catálogo do PDV parava em 300 produtos** — a primeira página. `listAll` segue `next` até o fim (produtos, mesas e comandas), com teto de 5.000 |
| `offline_first_gateway.dart` `handlesWrite` | **Secundário não abria nem fechava caixa sem o principal.** Abrir e fechar eram encaminhados ao principal na hora; com ele desligado, o operador não abria o turno. Agora entram na fila como qualquer venda, e a autorização por senha de ações é local quando não há conexão |
| `cash_register_repository.dart` | **Gaveta somava dinheiro em `double`**, com tolerância de meio centavo no fechamento. Passou a centavos inteiros (`DecimalMoney`), igualdade exata |
| `sync_service.dart` / `api_client.dart` | **Secundário levava até 5 minutos para ver o que os outros terminais fizeram.** Ele não tem WebSocket e nenhum canal do principal o avisa; só o `pullAll` periódico. Como secundário, a cadência cai para 30 s (chamada de rede local, incremental, paginada) e muda em tempo de execução quando o papel muda |

Testes novos: `secondary_temp_id_from_principal_test.dart`,
`secondary_pull_cadence_test.dart`, `catalog_pagination_test.dart`, mais casos
em `secondary_station_queue_test.dart`, `local_api_server_test.dart` e
`offline_first_gateway_test.dart`. Suíte Flutter: 827 testes.

### 2.5.2 Quarta rodada — o que sobrou nas "Suspeitas" (11/09/2026)

Com 5xx e lixo aceito zerados, a seção "Suspeitas" (payload que deveria valer
foi recusado) passou a ser a única fonte de achados. Lida item a item, ela
separou em três pilhas:

**Bugs do backend (corrigidos):**

| Onde | Era |
| --- | --- |
| rota de API inexistente (`PATCH /orders/open-command/<id>/`) | **página HTML de 404 do Django** para um cliente JSON. Qualquer URL sob `/api/` fora do roteamento fazia o mesmo — e o 500 fora do DRF também |
| 53 `return Response({...}, status=400)` diretos nas views, `JsonResponse` dos middlewares | **cada um com seu formato** (`{"detail"}`, `{"template"}`, `{"item"}`), fora do envelope `{success, status_code, error}` que o handler de exceção produz. O front e o PDV precisavam adivinhar. Agora `apps/core/envelope.py` (middleware mais externo) envelopa tudo, preservando o 409 estruturado do caixa (`code`, `message`, `session`) dentro de `error` |
| `POST /commands/` sem `number` | **"Este campo é obrigatório"** — mas o form diz "Auto = próximo número" e o model numera sozinho. O `UniqueConstraint(restaurant, number)` fazia o DRF gerar um `UniqueTogetherValidator`, que exige o campo presente e anulava o `required=False`. A numeração automática nunca era alcançável pela API. Agora a unicidade é conferida só quando o número vem informado |

Testes: `apps/core/tests/test_api_error_envelope.py`, caso novo em
`tests/test_command_flow.py`. Suíte do backend: 657 testes.

**Falsos positivos do harness (corrigidos em `loadtest/`):** inteiro `*_by`
recebia número aleatório em vez de usuário; `station` do KDS vinha do pool de
caixas; CPF em `document_model` (max 2); CNPJ com 11 dígitos; `username` com
espaço; `display_order` recebendo UUID; casas decimais além do `pattern` do
schema; `format: time` como texto; `restaurant` omitido em modelo que o exige;
`number`/`name`/`slug` repetidos entre fases e entre execuções (o contador
recomeçava do zero a cada processo e colidia com a numeração `max+1` do
servidor). Suspeitas na suíte `backend`, perfil `pesado`: **2.736 → 186**.

**Regras de negócio legítimas (ficam):** sangria sem caixa cadastrado, nota
fiscal 1:1 por pedido, receita 1:1 por produto, `profile.role` obrigatório em
usuário, tara ≥ peso bruto, `alert_minutes > target_minutes`, host de
impressora inválido, menu automático sem categoria. Todas com mensagem que diz
o que falta — que é o critério.

### 2.5.3 Alinhamento entidade a entidade (11/09/2026)

Com a carga limpa, o passo seguinte foi mecânico: cruzar, para os 25 forms do
painel, o que o OpenAPI do backend declara (obrigatório, `maxLength`, tipo,
enum, FK) com o que `config/resources.js` declara. Saíram 74 apontamentos:

| Grupo | Quantos | O que se fez |
| --- | --- | --- |
| `maxLength` no backend, sem `maxlength` no form | 60 | copiado para o form — o input corta na hora em vez de o servidor devolver "no máximo N caracteres" |
| obrigatório no backend, opcional no form | 5 | `phone` do cliente, `internal_code` do produto, `max_radius_km` da zona e `legal_name` do restaurante viraram `required` no form (é o que o modelo diz); o `slug` do menu era o inverso — o `validate` que deriva do nome era **código morto**, porque o DRF exigia o campo antes de chegar lá. Corrigido no serializer (`extra_kwargs`) com teste |
| obrigatório no form, opcional no backend | 8 | ficam: o form é mais estrito de propósito (restaurantes do produto, e-mail do usuário, preço do adicional) |
| tipo/enum/FK divergentes | 0 | — |

E o mesmo olhar do lado do backend: **49 campos numéricos graváveis sem
piso** — `amount` de pagamento, `quantity` de item do pedido, `opening_amount`
do caixa, todas as alíquotas de nota, todas as medidas de etiqueta. O
mecanismo era opt-in (`Meta.non_negative_fields`) e cada serializer novo
esquecia. Invertido: `TenantModelSerializer` barra negativo em **todo**
`DecimalField`/`FloatField`/`IntegerField` gravável, e quem existe negativo
de propósito se declara em `Meta.signed_fields` — `price_delta` da variação,
`margin_percent` do produto, `quantity` do movimento de estoque (o sinal é a
direção). As listas opt-in foram removidas. Testes em
`TestPisoNumericoPorPadrao`; backend com 661 testes; fumaça de carga sobre os
46 modelos: 0 × 5xx, 0 lixo aceito.

Como repetir o cruzamento: gerar o schema (`manage.py spectacular --format
openapi-json`), exportar `resources` (um teste vitest que grava JSON) e
comparar `required`/`maxLength`/`type`/`enum` por campo — o script vive só na
sessão, porque o resultado certo é o cruzamento voltar vazio.

### 2.5.4 Modo produção: o que o SQLite e o `runserver` escondiam (11/09/2026)

Até aqui todo alvo era `runserver` + SQLite. Com o alvo em modo produção —
mesma imagem, gunicorn/UvicornWorker, Postgres 16 e Redis em Docker local
(§2.1.1 de `TESTE_CARGA.md`) — a **primeira rodada quebrou de um jeito que
nenhuma das quatro anteriores mostrou**:

| Onde | Era |
| --- | --- |
| `config/settings/base.py` (Postgres) | **`FATAL: sorry, too many clients already` — 28.203 vezes.** Sob ASGI cada request síncrona vai para uma thread nova; a conexão persistente (`CONN_MAX_AGE=60`) ficava presa na thread descartada. Com 4 workers os 100 `max_connections` acabaram em minutos, **até o login virou 500 e o banco continuou saturado depois que a carga parou.** Agora o pool nativo (Django 5.1 + psycopg 3) segura no máximo `POSTGRES_POOL_MAX` (10) conexões por worker e devolve ao fim da request; `CONN_MAX_AGE` vai a 0. Sob 128 conexões simultâneas o Postgres ficou em 41 |
| `apps/invoices/services.py` `_EMITTER_FIELDS_FROM_RESTAURANT` | **`DataError: value too long for character varying(9)` — 500 ao salvar restaurante.** O cadastro espelha `state_registration` (40) em `FiscalConfig.ie` (20) e `zip_code` (16) em `zip_code` (9). O SQLite não impõe tamanho de `varchar`: passava em dev, nos 661 testes e nas quatro rodadas. Agora o espelho corta no `max_length` da coluna de destino |
| `apps/menu/services/recipes.py` `recalculate_recipe_costs` | **`deadlock detected`** — dois itens lançados ao mesmo tempo na mesma ficha recalculavam em paralelo e atualizavam as mesmas linhas em ordens diferentes. Agora a receita é travada (`select_for_update`) e os itens são percorridos em ordem fixa: um recálculo por ficha de cada vez. 21 deadlocks em 11 k requisições → 0 |
| `apps/core/middleware.py` + `apps/core/exceptions.py` | **Pool esgotado / banco fora virava 500** (ou 401 mentiroso, porque o middleware seguia como anônimo). É sobrecarga, não defeito: agora `OperationalError` responde **503 com `Retry-After: 2`** nos dois lugares. O harness passou a contar 503 à parte (`sobrecarga`), como já fazia com 429 |

Testes: `test_espelho_do_restaurante_cabe_nas_colunas_fiscais`,
`test_banco_indisponivel_e_503_nao_500`,
`test_banco_indisponivel_ao_autenticar_e_503`. Backend: 664 testes.
Dependência nova: `psycopg[binary,pool]`.

**Lição:** a suíte de carga contra SQLite mede o código; só o alvo em modo
produção mede o **sistema** — largura de coluna, pool, lock. As três
correções acima são invisíveis em qualquer teste que rode em SQLite.

### 2.6 Frontend

`PdvView.vue` lia `error.response.data.detail` em quatro pontos — **campo que o
envelope da API não tem** (`{success, status_code, error: {code, message}}`). A
razão real da recusa era trocada por um texto genérico, justamente na pesagem e
no recebimento. Passou a usar `normalizeApiError`, que o próprio arquivo já
importava.

**Forms sem validação no cliente (11/09/2026, terceira rodada).** A suíte `web`
manda o que os forms do painel mandam, e a seção "Suspeitas" mostrou o padrão:
tudo que o servidor recusava com 400 era regra que o form **conhecia e não
aplicava** — o `submit.prevent` desligava até a validação nativa do `<input
min="0">`. O operador digitava `-5`, clicava, esperava o round-trip e recebia
"Um número inteiro válido é exigido" num alerta solto, sem apontar o campo.

Agora `utils/formValidation.js` roda antes de montar o payload, espelhando o
que o backend faria de qualquer jeito, e o erro aparece **no campo**:

| Regra do servidor | Como o form declara | Onde doía |
| --- | --- | --- |
| `IntegerField` | `type: "number"` recusa `1.5`, `abc` | `display_order`, `capacity`, `sla_minutes` |
| `Meta.non_negative_fields` | `number`/`decimal` recusam negativo; `min: 1` para comanda; `allowNegative: true` libera assinado | preços, quantidades, `number` da comanda |
| `required` | obrigatório vazio, inclusive multiselect sem item | `restaurants` do produto |
| `max_length` | `maxlength` | qualquer texto |
| `is_valid_cpf` / 14 dígitos | `document: "cpf"` / `"cnpj"` | cliente, restaurante |
| `alert_minutes <= target_minutes` (`sla/serializers.py`) | `notGreaterThan: { field, message }` | SLA |
| "Vincule pelo menos um usuário ao caixa" | botão de salvar desabilitado sem nome/operador (`CashRegisterView.vue`) | cadastro de caixa |

Testes: `utils/formValidation.test.js` e o caso "barra antes de chamar a API"
em `useResourceForm.test.js`. Suíte do frontend: 96 testes.

### 2.7 Ferramentas

`manage.py seed_demo` quebrava sem `--skip-orders`: gerava pagamento em cartão
sem `card_subtype`, que o próprio `register_payment` recusa desde a regra da
NFC-e. A base de demonstração estava sem venda nenhuma havia tempo.

---

## 3. Resultado medido

Perfil `pesado`, mesma semente, antes e depois:

| Frente | 5xx antes | 5xx depois | Dado inválido aceito antes | depois |
| --- | --- | --- | --- | --- |
| backend | 3.082 | **0** | 51 | **0** |
| web | 0 | **0** | 2 | **0** |
| desktop | 3.014 | **0** | 151 | **0** |
| mobile | 2.268 | **0** | 104 | **0** |
| PDV Flutter | 180 exceções | **0** | 1.014 | **0** |

No PDV, a leitura do catálogo com 5.000 produtos caiu de **p95 225 ms para
30 ms**. Causas raiz de 500 no log do servidor: de **12 para 0** (as que
sobram são `database is locked` do SQLite sob 128 conexões — teto do ambiente,
não do código; ver [`BACKEND.md`](BACKEND.md#sqlite-não-trava-mais-com-dois-terminais-vendendo)).

Os testes que fixam essas correções estão em
`backend/tests/test_entrada_invalida_nao_quebra.py`.

**Terceira rodada (11/09/2026, perfil `pesado`, suíte ampliada com relatórios
e lotes):** 50.686 requisições, **0 × 5xx registrados e 0 dado inválido aceito
nas quatro frentes**. O que sobrou:

| Frente | reqs | p50 | p99 | sem resposta |
| --- | --- | --- | --- | --- |
| backend | 12.435 | 4,4 s | 20,5 s | 1.111 |
| web | 27.361 | 200 ms | 5,4 s | 164 |
| desktop | 5.487 | 133 ms | 4,7 s | 2 |
| mobile | 5.403 | 251 ms | 12,4 s | 1 |

- **"Sem resposta" é o Daphne de dev** derrubando conexão no pico (item 1 da
  seção 4); no log do servidor todos os 500 são `database is locked` do
  SQLite (item 2). Nenhuma causa raiz de código.
- **Relatórios sob carga a 10–16 s no p99**, mas **50 ms isolados** (`curl`
  em `dashboard`, `sales`, `products`, `restaurants`). É contenção do processo
  único agregando em paralelo, não plano de query — o relatório da suíte passou
  a mandar fazer exatamente essa medição antes de procurar índice.
- **Lotes**: 200 comandas em 78 ms (p50), lote invertido/gigante/texto/negativo
  → 400 em 30 ms; 500 insumos de uma vez → 400 pelo teto. Nenhum lock preso.
- **Falso positivo do harness corrigido**: `builder.py` tratava todo inteiro
  terminado em `_order` como FK de pedido e mandava UUID em `display_order`
  (6 "suspeitas" por rodada que não eram do backend).

**Quarta rodada (11/09/2026, `backend` perfil `pesado`, após §2.5.2):** 12.741
requisições, **0 × 5xx, 0 dado inválido aceito**, suspeitas de 2.736 para 186
(todas regra de negócio com mensagem clara). 520 sem resposta — Daphne de dev.

---

**Modo produção (11/09/2026, gunicorn 4 workers + Postgres 16 + Redis, Docker
local, perfil `pesado`, após §2.5.4):**

| Frente | reqs | rps médio / pico | p50 | p99 | 5xx | lixo | sem resposta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| backend | 27.077 | 54 / 190 | 1,7 s | 6,7 s | **0** | **0** | 4 |
| web | 27.274 | 176 / 458 | 195 ms | 4,2 s | **0** | **0** | 2 |
| desktop | 5.422 | 22 / 64 | 189 ms | 771 ms | **0** | **0** | 0 |
| mobile | 5.386 | 25 / 61 | 331 ms | 6,1 s | **0** | **0** | 0 |

Postgres estável em 41 conexões sob 128 clientes (antes: 100+ e `too many
clients`). Os 6 "sem resposta" são timeouts de 20 s do cliente em leituras
durante o pico — nenhuma conexão derrubada (Daphne de dev derrubava 1.111).
Plano de correção do consolidador: _nada a corrigir_.

## 4. O que continua em aberto

São coisas que a análise levantou e que **não foram mexidas**, por exigirem
decisão de produto ou ambiente:

1. ~~O servidor de desenvolvimento satura.~~ **Medido (§3, modo produção):**
   4 workers gunicorn aguentam 190 req/s de pico sem derrubar conexão. O que
   sobra é dimensionamento: `GUNICORN_WORKERS × POSTGRES_POOL_MAX` contra o
   `max_connections` do Postgres da VPS.

2. ~~SQLite tem um escritor por vez.~~ **Resolvido pelo alvo em modo
   produção** (`start_prod_target.sh`): perfis `pesado`/`extremo` rodam
   contra Postgres. O SQLite fica para a fumaça rápida.

3. ~~`PdvRepository.loadCatalog` não pagina.~~ Corrigido em §2.5.1.

3a. ~~Secundário não abre nem fecha caixa sem internet.~~ **Resolvido
   (11/09/2026, decisão de produto: o caixa do secundário funciona inteiro sem
   rede).** Abrir e fechar passaram a ser escrita local + fila num secundário,
   como qualquer venda; a autorização por senha de ações também é aplicada
   localmente quando o principal não responde. Só transferir a posse da sessão
   continua exigindo quem esteja no ar. O guard de estação do principal, no
   replay, impede duas sessões na mesma gaveta.

3b. **Secundário não recebe eventos do principal.** Só o `pullAll` o atualiza;
   a cadência caiu de 5 min para 30 s (§2.5.1), mas continua sendo polling.
   Um canal principal → clientes (o mesmo WebSocket que o principal já recebe
   da nuvem, reemitido na rede local) tiraria a defasagem de vez.

3c. ~~Aritmética de dinheiro da gaveta em `double`.~~ **Resolvido**: a gaveta
   passou a somar em centavos inteiros (`DecimalMoney`), e o fechamento compara
   igualdade exata em vez de tolerância de meio centavo.

4. **Emissão fiscal não entrou em nenhuma suíte.** `POST /invoices/emit/` está
   na lista de bloqueio dos dois testes, porque chama provedor externo. A fila
   fiscal do PDV é exercitada; o caminho servidor→SEFAZ não.

4a. **Relatórios em Postgres: p99 de 4–7 s sob carga, 120–440 ms isolados.**
   Medido no modo produção. Ainda é contenção de CPU dos 4 workers, não plano
   de query; mas `sales` isolado a 437 ms com a base de demonstração merece um
   `EXPLAIN` antes de a base crescer.

5. **WebSocket não é medido.** As invalidações em tempo real (`/ws/pdv/`,
   `/ws/kitchen/`) não têm carga. Uma tempestade de eventos com muitos terminais
   conectados é um cenário plausível e não testado.

6. **A cadeia real secundário → principal não é exercitada pela rede.** Os dois
   testes simulam o relay em processo; a API local `/local/...` com assinatura
   HMAC tem testes de unidade, mas não de volume.

---

## 5. Como repetir

```powershell
# backend + web + desktop + mobile
bash loadtest/scripts/start_backend.sh 8011 2>&1 | tee artifacts/loadtest/servidor.log
.venv/Scripts/python loadtest/run.py all --profile pesado

# nucleo do PDV
Set-Location flutter
flutter test loadtest/ --dart-define=PERFIL=pesado

# plano consolidado, com causa raiz por arquivo e linha
.venv/Scripts/python loadtest/consolidar.py "artifacts/loadtest/carga-*.json" `
  "artifacts/loadtest/pdv/*.json" --server-log artifacts/loadtest/servidor.log
```
