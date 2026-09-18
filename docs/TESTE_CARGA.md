# Teste de carga StarChef — backend, web, desktop e mobile

Suíte de carga pesada que roda **só na mão**, por comando. Ela não está no
`pytest`, não roda no GitHub Actions e não deve apontar para produção: o
objetivo declarado é **degradar o alvo até ele reclamar**, criando dezenas de
milhares de registros, metade deles preenchidos errado de propósito.

O código vive em [`loadtest/`](../loadtest) e usa **só a biblioteca padrão do
Python** — nenhuma dependência nova entra no projeto por causa dele.

---

> O que a primeira rodada encontrou, o que foi corrigido e o que segue aberto
> está em [`ANALISE_DE_RISCOS.md`](ANALISE_DE_RISCOS.md).

## 1. O que este teste responde

Não é "quantas requisições por segundo aguenta". A pergunta é mais dura:

> Sob carga, diante de dado certo, dado tosco e dado inválido, o sistema
> continua **respondendo de forma correta e coerente** — ou quebra, aceita
> lixo em silêncio e cobra o cliente duas vezes?

Por isso **toda requisição carrega uma expectativa** e recebe um veredito:

| Veredito | Significa | É defeito? |
| --- | --- | --- |
| `ok` | payload válido → 2xx | não |
| `recusa_correta` | payload inválido → 4xx com mensagem | não (é o certo) |
| `lixo_aceito` | payload inválido → **2xx** | **sim** — validação faltando |
| `erro_servidor` | qualquer coisa → **5xx** | **sim** — quebrou |
| `falha_transporte` | conexão derrubada / timeout | **sim** |
| `valido_recusado` | payload que deveria valer → 4xx | suspeita, vai para uma seção própria |
| `limitado` | 429 | informativo (throttle) |
| `conflito` | 409 | informativo (unicidade, idempotência) |

Um erro do cliente **tem** de virar 4xx com mensagem legível. Nunca 5xx, nunca
um 2xx silencioso. É isso que o relatório cobra.

---

## 2. Como rodar

### 2.1 Suba um alvo descartável

```powershell
powershell -File loadtest\scripts\start_backend.ps1 8011
```

```bash
bash loadtest/scripts/start_backend.sh 8011 2>&1 | tee artifacts/loadtest/servidor.log
```

O `tee` importa: é o log do servidor que diz **por que** cada 500 aconteceu, e
o consolidador (§5) lê exatamente esse arquivo.

O script usa um **banco separado** (`db_loadtest.sqlite3`) e sobe os
`THROTTLE_RATE_*` para valores enormes — sem isso o teste mede o throttle do
DRF em vez do sistema. Popule com dados de demonstração uma vez:

```bash
SQLITE_DB_NAME=db_loadtest.sqlite3 .venv/Scripts/python backend/manage.py seed_demo --skip-orders
```

Para a suíte web, suba também o frontend:

```bash
npm --prefix frontend run dev -- --port 5199
```

### 2.1.1 Alvo em modo produção (gunicorn + Postgres, Docker local)

O `runserver` + SQLite acima mostra o teto do **ambiente de dev**, não do
código: o Daphne single-thread derruba conexão no pico e o SQLite serializa
escrita. Para medir capacidade de verdade, o alvo sobe com a mesma imagem,
o mesmo comando e os mesmos settings (`config.settings.production`) do
`docker-compose.yml` da raiz — que **não é tocado**:

```bash
bash loadtest/scripts/start_prod_target.sh 8012
GUNICORN_WORKERS=8 bash loadtest/scripts/start_prod_target.sh 8012   # mais workers
bash loadtest/scripts/start_prod_target.sh --down                     # derruba tudo
```

O script sobe o **Postgres 16 num container separado** (`starchef-pg-loadtest`,
porta 5433 no host, zerado a cada subida), depois backend gunicorn/UvicornWorker
+ Redis por [`docker/loadtest/docker-compose.yml`](../docker/loadtest/docker-compose.yml)
na rede externa `starchef-loadtest`, espera o `/health/` e roda `seed_demo`.
Os `THROTTLE_RATE_*` vão altos como no alvo de dev. Atrás de proxy corporativo
que intercepta TLS, o build passa `PIP_TRUSTED_HOST` ao pip do container
(vazio em produção).

Dispare as suítes com `--base-url http://127.0.0.1:8012`. O log do servidor
para o consolidador sai de `docker compose -f docker/loadtest/docker-compose.yml logs backend`.

### 2.2 Dispare

```bash
.venv/Scripts/python loadtest/run.py backend --profile medio --base-url http://127.0.0.1:8011
.venv/Scripts/python loadtest/run.py web     --profile medio --frontend-url http://127.0.0.1:5199
.venv/Scripts/python loadtest/run.py desktop --profile pesado
.venv/Scripts/python loadtest/run.py mobile  --profile pesado
.venv/Scripts/python loadtest/run.py all     --profile leve --label noturno
```

O relatório sai no terminal e em `artifacts/loadtest/carga-<data>.{md,json}`.
O código de saída é `1` quando há defeito ou verificação de coerência
reprovada — dá para usar em script.

### 2.3 Perfis

| Perfil | Conexões | Alvo/s por modelo | Segundos por fase | PDVs | Garçons | Vendas/terminal |
| --- | --- | --- | --- | --- | --- | --- |
| `fumaca` | 8 | 30 | 5 | 2 | 2 | 3 |
| `leve` | 24 | 150 | 15 | 3 | 4 | 8 |
| `medio` | 64 | 500 | 30 | 6 | 10 | 20 |
| `pesado` | 128 | 1000 | 60 | 12 | 24 | 40 |
| `extremo` | 256 | 3000 | 120 | 24 | 60 | 80 |

Qualquer valor do perfil pode ser sobrescrito: `--workers`, `--rate`,
`--duration`, `--terminals`, `--waiters`, `--sales`, `--chaos-ratio`,
`--sloppy-ratio`, `--seed`.

`--offline-ratio` saiu junto com a simulação offline: a linha 3.x do PDV é
só-conectada, e manter a opção sugeriria um comportamento que o app não tem.

**A taxa é um ALVO, não uma promessa.** O gerador dispara em malha aberta: se o
servidor não acompanha, a taxa alcançada cai e isso aparece no relatório como
saturação — que é exatamente o que se quer medir.

---

## 3. As quatro frentes

### 3.1 `backend` — tempestade de criação

As rotas de escrita saem do **OpenAPI do próprio backend** (`/api/schema/`),
não de uma lista escrita à mão: campo novo, enum novo ou campo que virou
obrigatório entram no teste sozinhos. Cinco fases de CRUD, mais duas que o
CRUD não alcança:

1. **Rajada isolada** — cada modelo sozinho na taxa alvo cheia, para conhecer o
   teto individual de cada um.
2. **Tempestade misturada** — todos ao mesmo tempo, onde aparecem contenção de
   banco, lock e fila.
3. **Leitura sob carga** — paginação, página inexistente, `page_size` absurdo,
   busca hostil (`' OR 1=1--`), ordenação por campo que não existe, delta sync
   (`updated_after` + `include_deleted`) e filtro desconhecido.
4. **Corpo cru malformado** — JSON sem fechar, array no lugar de objeto, corpo
   vazio, `Content-Type` errado, 2 MB de texto, 2 KB de bytes binários.
5. **Alteração e exclusão** — PATCH e DELETE sobre o que foi criado **e** sobre
   IDs que nunca existiram.
6. **Relatórios e agregações** (`suites/backend_extra.py`) — os sete
   `/reports/*` mais posição, alertas e validade de estoque, com `GROUP BY`/`SUM`
   sobre a tabela que as fases anteriores acabaram de encher. Os filtros são os
   que a tela manda de verdade, mais intervalo invertido (`date_from` >
   `date_to`), data lixo, `page_size=100000` e `export=csv`. Roda **depois** do
   CRUD de propósito: agregação só tem o que medir com dados dentro.
7. **Operações em lote** — `commands/bulk-create/`, `tables/bulk-create/` e
   `menu/ingredients/bulk/`: um lote válido de cada, e os inválidos (intervalo
   invertido, intervalo de 10⁹ números, texto no lugar de número, negativo,
   lote acima do teto). O limite tem de virar 400 — nunca 500 nem lock preso.

Quando o p99 dos relatórios passa de 1 s, o relatório manda medir um
relatório **isolado** (`curl`): se ele responde em dezenas de ms, o gargalo é a
contenção do servidor de dev (Daphne single-thread agregando em paralelo), não
a query — e só faz sentido revisar com gunicorn + Postgres.

Três qualidades de payload convivem, na proporção configurável:

- **limpo** (`--sloppy-ratio 0`): CPF com dígito correto, e-mail válido, EAN com
  dígito verificador certo, referências que existem de verdade → espera 2xx;
- **desleixado** (`--sloppy-ratio`, padrão 0,3): CPF com dígito trocado, e-mail
  sem arroba, telefone pela metade, campo em branco, casas decimais demais →
  aceitar ou recusar são as duas respostas defensáveis; só não pode quebrar;
- **inválido** (`--chaos-ratio`, padrão 0,35): 13 mutações — campo obrigatório
  removido, `null` em obrigatório, tipo errado, texto acima do `maxLength`,
  enum inexistente, valor negativo, referência quebrada, número absurdo
  (10³⁰, `NaN`, `Infinity`), payload vazio, 60 campos inventados, texto hostil
  (SQL/XSS/path traversal), JSON aninhado fundo → espera 4xx.

### 3.2 `web` — enxurrada na retaguarda

Pensada como ataque, em três fases:

1. **Degraus de conexão** (`n/8 → n/4 → n/2 → n → 2n`), misturando o shell do
   SPA, os assets versionados lidos do próprio `index.html` e rotas que não
   existem. O relatório mostra em que degrau a latência dispara.
2. **Chamadas de abertura de tela** — o que o painel busca ao carregar
   (`/auth/me/`, listagens, dashboard), com um quarto do tráfego **anônimo**:
   sem credencial a API tem de responder 401/403, nunca servir dado.
3. **Envio de formulários sob carga** — POST nos recursos que as telas de
   cadastro usam, metade preenchido errado, mais corpos crus.

### 3.3 `desktop` — o PDV do caixa

Simula o **`pdv_desktop` 3.x**, que é só-conectado: ele fala direto com UM
backend e não opera offline. As rotas e os corpos saem do código do app, não de
suposição — se o app mudar de rota, a suíte passa a medir a rota errada e é
isso que os testes de fumaça pegam.

**A topologia é escolha de execução, não do código.** Aponte `--base-url` para
o backend da loja e você mede a operação com backend local; aponte para a nuvem
e mede o acesso direto.

Cinco fases:

1. **Abertura simultânea** — o app dispara sete leituras ao abrir (perfil,
   categorias, produtos, mesas, comandas, formas de pagamento, estações). Com N
   terminais ligando às 8h isso é uma rajada, não uma fila, e é o pior instante
   do dia.
2. **Abrir caixa** — sem sessão aberta o backend recusa o recebimento, e está
   certo. A estação tem lista de operadores autorizados, então a suíte se
   vincula antes: falta de pré-condição do teste não pode virar "defeito do
   sistema" no relatório.
3. **Turno** — vendas concorrentes de ponta a ponta: abre o pedido (comanda ou
   balcão), lança item, recebe em `/orders/{id}/pay/`.
4. **Fiscal** — emissão, e uma regra que vale sozinha: `emitted: false` **sem**
   `message` é defeito. Sem motivo, o PDV cai num texto fixo que ele inventa, e
   o operador lê "o provedor fiscal não está configurado" para qualquer falha —
   inclusive rejeição da SEFAZ.
5. **Conferência** — ninguém foi cobrado duas vezes, e o valor cobrado bate com
   o lançado.

### 3.4 `mobile` — o app do garçom

Simula o **`pdv_mobile` 3.x**, também só-conectado. Não é cópia do desktop
porque o garçom trabalha diferente:

- ele **abre o pedido e lança o item no mesmo gesto**
  (`orders/create-with-item/`, com o item aninhado): na mesa ninguém abre
  comanda vazia para depois anotar;
- ele **não fecha conta** — quem recebe é o caixa. Medir pagamento aqui seria
  medir o app errado;
- são **muitos aparelhos lançando pouco cada**, o oposto do caixa. É o perfil
  que expõe contenção de escrita.

Três fases: abertura simultânea (com régua mais apertada que a do caixa — o
garçom está em pé na frente do cliente), salão lançando em paralelo, e a
conferência de que todo lançamento aceito virou item de verdade.

### 3.5 `sync` — a fila entre os dois backends

Exercita a sincronização nuvem↔loja: identidade dos nós, escrita pesada
enchendo a outbox, drenagem da fila, e a matrícula sob tentativa de força
bruta. A garantia que ela cobra não é "a fila esvaziou" — é **"nada sumiu"**
entre a outbox e a inbox.

Inclui a fase de **contenção**, que responde se a captura de eventos serializa
a escrita do negócio. Toda gravação sincronizada chama `outbox.record()` dentro
da transação do negócio, e ele incrementa `sequence_counter` na linha do nó —
sempre a MESMA linha. A fase mede a mesma gravação em concorrência 1 e em N: se
a mediana cresce proporcional à concorrência enquanto a vazão fica plana, há
serialização.

> **Leia a atribuição antes do número.** Com `SYNC_ENABLED=false` no alvo,
> `outbox.record` sai cedo e `next_sequence` nem é chamado — a medição continua
> válida como carga de escrita, mas não diz nada sobre o lock. A fase avisa
> quando esse é o caso.
>
> Para medir o lock de verdade, o alvo precisa de `SYNC_ENABLED=true` e nó
> provisionado. Há também um teste de unidade que prova o bloqueio por ordem de
> eventos, sem cronômetro, em
> `backend/apps/synchronization/tests/test_contencao_da_sequencia.py`.

---

## 4. Lendo o relatório

O Markdown abre com a situação (`APROVADO` / `ATENÇÃO` / `REPROVADO`), a taxa
média e de pico, a latência p50/p95/p99, a tabela por grupo e:

- **Verificações de coerência** — pagamento duplicado, fila que escoou,
  healthcheck, cache do garçom. Uma reprovação aqui vale mais que qualquer
  número de latência.
- **Defeitos** — cada 5xx, conexão derrubada e lixo aceito com a requisição
  completa para repetir na mão.
- **Suspeitas** — payload que deveria valer e foi recusado, com a mensagem do
  servidor. Nem sempre é bug: pode ser regra de negócio cruzada (o insumo que
  precisa acompanhar a quantidade de consumo, por exemplo). Se a mensagem não
  explica o motivo, **a recusa é o problema**.
- **`sobrecarga` (503 com `Retry-After`)** — o servidor *disse* que está
  saturado (pool de banco esgotado, banco fora). Conta à parte, como o 429:
  é capacidade, não defeito de rota. O PDV trata como temporário e reenfileira.
  Muitos 503 no perfil `pesado` significam que `GUNICORN_WORKERS ×
  POSTGRES_POOL_MAX` está curto para a carga, não que uma rota quebrou.

### 4.1 SQLite e o `database is locked`

O SQLite foi destravado em `build_database_settings`: WAL, `transaction_mode`
`IMMEDIATE` e `SQLITE_LOCK_TIMEOUT` de 30s (ver
[`BACKEND.md`](BACKEND.md#sqlite-não-trava-mais-com-dois-terminais-vendendo)).
Isso derrubou os 5xx de contenção de milhares para praticamente zero nos perfis
até `medio`.

O limite continua existindo: SQLite tem **um escritor por vez**. Se ainda
aparecer `database is locked`, ou 5xx concentrado em payload **válido**, o
relatório avisa — e a saída é medir contra Postgres:

```bash
POSTGRES_HOST=localhost POSTGRES_DB=starchef POSTGRES_USER=starchef \
  POSTGRES_PASSWORD=starchef bash loadtest/scripts/start_backend.sh 8011
```

Os perfis `pesado` e `extremo` só fazem sentido contra Postgres.

---

## 5. Consolidar várias execuções

Rodar as quatro frentes gera quatro relatórios. O consolidador junta tudo num
plano de correção único, cruzando os defeitos com o **traceback do servidor**:

```bash
.venv/Scripts/python loadtest/consolidar.py "artifacts/loadtest/carga-*.json" --server-log artifacts/loadtest/servidor.log
```

Sai `artifacts/loadtest/PLANO-DE-CORRECAO.md` com:

1. resumo de cada execução (vazão, latência, 5xx, lixo aceito);
2. **plano de correção ordenado por gravidade**, com arquivo e linha;
3. causas raiz dos 500 agrupadas por exceção + último quadro no código do
   projeto — é o que transforma "3082 erros" em "quatro linhas para corrigir";
4. payload inválido que a API aceitou;
5. verificações de coerência reprovadas;
6. suspeitas.

O log do servidor é o JSON que o Django escreve durante as execuções — o mesmo
que o `tee` de §2.1 guarda. Sem ele o plano sai sem a seção de causas raiz, que
é a parte que aponta arquivo e linha.

---

## 6. Limpeza

A suíte **deixa lixo de propósito** — é a forma de testar leitura e listagem
com tabela cheia. Três saídas:

- `--cleanup` apaga o que a execução criou (o DELETE também vira teste);
- apagar `backend/db_loadtest.sqlite3` e rodar `migrate` + `seed_demo`;
- `DROP DATABASE` quando o alvo for Postgres.

Nunca aponte a suíte para o banco de desenvolvimento normal.

---

## 7. Estrutura do código

```
loadtest/
  run.py                     ponto de entrada
  scripts/start_backend.*    alvo descartavel (banco proprio, throttle alto)
  starchef_load/
    cli.py config.py         linha de comando e perfis
    http_client.py           cliente keep-alive por thread (stdlib, envia bytes crus)
    workers.py               ritmo alvo em malha aberta + pool de threads
    schema.py                le o OpenAPI e descreve cada rota de escrita
    builder.py fakes.py      gera payload valido/desleixado com IDs reais
    chaos.py                 as 13 mutacoes e os 7 corpos crus
    refs.py                  IDs do tenant + criacao do cenario minimo
    result.py metrics.py     veredito por requisicao e agregacao
    report.py                Markdown + JSON
    serverlog.py             traduz o traceback do Django em causa raiz
    consolidate.py           junta execucoes num plano de correcao
    suites/                  backend.py backend_extra.py web.py desktop.py mobile.py
    sim/                     outbox.py terminal.py sale.py cash.py shift.py waiter.py
  consolidar.py              gera o PLANO-DE-CORRECAO.md
```

## 8. O que este teste NÃO faz

- Não executa o código Dart do PDV: as suítes reproduzem as REQUISIÇÕES dos
  apps, extraídas do código deles, não o binário Flutter. Homologação de
  balança, impressora e leitor continua sendo física.
- Não simula operação offline. A linha 3.x do PDV é só-conectada — a simulação
  da cadeia Caixa Principal → Secundários, que existia aqui para a linha 1.8.x,
  foi removida junto com ela. Testar uma arquitetura aposentada dá a impressão
  de cobertura que não existe.
- Não mede WebSocket. As invalidações em tempo real ficam fora desta versão.
- Não substitui o `pytest`: ele prova regra de negócio; este prova comportamento
  sob volume.


## Suíte `sync` — os dois backends ao mesmo tempo

As outras quatro suítes atacam um alvo. Esta ataca o par (loja + nuvem), porque
o que ela mede não existe dentro de um processo: é a fila entre eles.

```
python loadtest/run.py sync --cloud-url http://127.0.0.1:8002 --profile leve
```

`--base-url` é o backend da **loja** (nó LOCAL) e `--cloud-url`, o da **nuvem**
(nó CLOUD). Sem credencial própria para a nuvem (`--cloud-username` /
`--cloud-password`), ela usa a mesma da loja.

Cinco fases: identidade dos dois alvos, escrita pesada na loja (enchendo a
outbox), drenagem da fila, leitura da API de gerenciamento sob carga nos dois
lados, e a rota de matrícula atacada com credencial errada (403 é o certo;
201 e 500 são falhas).

Sem `--cloud-url` a suíte roda só o que cabe num alvo e **diz no relatório o
que deixou de medir** — ela não inventa um segundo backend.

O veredito que importa não é "a fila esvaziou": loja offline é um estado
legítimo. É **"nada sumiu"** — todo evento continua em algum estado do banco.
