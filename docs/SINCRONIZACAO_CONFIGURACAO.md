# Configurar a sincronização loja ⇄ nuvem

Guia prático: o que preencher, em que ordem, e como saber que funcionou.
Para *como o mecanismo funciona por dentro*, ver [SINCRONIZACAO.md](SINCRONIZACAO.md).

> **Fase DEVELOPMENT.** O código **recusa** qualquer ambiente que não seja
> `development`. Isso é uma exceção levantada, não uma convenção — não adianta
> escrever `production` e esperar que funcione.

---

## O modelo mental, em 30 segundos

É **um backend só**, rodando duas vezes com um papel diferente:

```
     LOJA (dentro do restaurante)              NUVEM
┌────────────────────────────────┐      ┌──────────────────┐
│ SYNC_NODE_TYPE=local           │      │ SYNC_NODE_TYPE=  │
│                                │      │      cloud       │
│ PDV, KDS, garçom  →  backend   │      │                  │
│                      ↓         │      │  backend         │
│                 postgres local │      │    ↓             │
│                   + outbox     │      │  postgres        │
│                      ↑         │      │   central        │
│                 sync_worker ───┼─WSS─→│  (recebe)        │
└────────────────────────────────┘      └──────────────────┘
```

Quem **abre** a conexão é sempre a loja. A nuvem nunca disca para o
restaurante — por isso a loja não precisa de IP fixo, porta aberta nem
certificado. O que a loja precisa é conseguir **sair** para a internet.

Três consequências que valem entender antes de configurar:

1. **A loja funciona sem internet.** O PDV fala com o backend local. Sem
   conexão, os eventos se acumulam na outbox e sobem depois.
2. **Nada é apagado antes de o outro lado confirmar.** Um evento que falhou
   dez vezes continua no banco, com o conteúdo inteiro.
3. **Quem autoriza é a conexão, não o conteúdo.** O `account_id` viaja na
   mensagem só para rastrear; a conta real vem da credencial autenticada.

---

## Antes de começar

Você vai precisar de:

| O quê | Onde consegue |
|---|---|
| A **URL da nuvem** (HTTPS) | Onde seu backend central está publicado |
| A **URL do WebSocket** | Mesma nuvem, caminho `/ws/sync/v1/` |
| O **UUID da conta** | `/admin/accounts/account/` na nuvem |
| **Usuário e senha** de superadmin (ou admin da conta) | Os seus |
| Um **segredo de matrícula** | Você inventa: mínimo 24 caracteres |

O segredo de matrícula **não é** a chave de sincronização. Ele serve só para
cifrar o pacote de credenciais na volta; a chave definitiva nasce na nuvem e
vem dentro desse pacote. Use um valor **diferente por loja** e não reaproveite.

---

## O que precisa ser IGUAL nos dois lados

A pergunta que mais aparece. A resposta curta: **duas variáveis**, e você não
precisa copiar nenhuma à mão.

| Variável | Igual nos dois? | De onde vem |
|---|---|---|
| `SYNC_ENCRYPTION_KEY` | **SIM, obrigatoriamente** | Você gera na nuvem; a loja recebe no pacote de matrícula |
| `SYNC_ENCRYPTION_KEY_ID` | **SIM** | Idem |
| `SYNC_ENVIRONMENT` | **SIM** (`development`) | Você escreve nos dois |
| `SYNC_NODE_TYPE` | **NÃO** | `cloud` lá, `local` aqui |
| `SYNC_AUTH_TOKEN` | **NÃO** | Um por loja, gerado na matrícula |
| `SYNC_ENROLL_PASSWORD` | — | É a senha do usuário **da nuvem**; a loja só a apresenta |
| `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD` | **NÃO** | Cada instalação tem a sua |

A chave AES é **do ambiente**, não do nó: a nuvem cifra com a dela e a loja
decifra com a dela. Se forem diferentes, toda mensagem falha na tag do AES-GCM
e **nada** sincroniza — sem erro no domínio, só NACK em looping.

Por isso a matrícula entrega a chave da nuvem para a loja automaticamente: você
gera **uma vez**, na nuvem, e não copia nada. O banco guarda só o `key_id` e a
impressão digital (SHA-256) — que existe justamente para conferir que as duas
pontas têm a mesma chave sem nunca armazená-la.

> Deixar `SYNC_ENCRYPTION_KEY` vazia nos DOIS lados também funciona: o
> transporte continua sendo WSS e o AES-GCM é uma camada adicional. O que não
> pode é uma ponta cifrar e a outra não.

---

## Passo 1 — Ligar a sincronização na NUVEM

No servidor da nuvem, acrescente ao `.env` (o bloco completo está em
`docker/local/.env.cloud.example`):

```bash
SYNC_ENABLED=true
SYNC_ENVIRONMENT=development
SYNC_NODE_TYPE=cloud
SYNC_ENCRYPTION_KEY=<gere abaixo>
SYNC_ENCRYPTION_KEY_ID=dev-key-01
THROTTLE_RATE_SYNC_ENROLL=5/hour
```

Gere a chave AES (32 bytes) uma vez e guarde:

```bash
python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Suba e instale a rede de segurança:

```bash
docker compose up -d backend && docker compose exec backend python manage.py sync_install_triggers
```

> Com `SYNC_ENABLED=false` o comando **não instala nada** e diz isso. É de
> propósito: sem sincronização as triggers só gravariam marcas que ninguém
> consome.

### O proxy reverso precisa passar o WebSocket

Esta é a causa nº 1 de "a loja fica tentando conectar para sempre". No nginx:

```nginx
location /ws/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade    $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host       $host;
    proxy_read_timeout 3600s;   # o canal fica aberto; sem isto ele cai sozinho
}
```

Confira antes de seguir:

```bash
CHAVE=$(python -c "import base64,os;print(base64.b64encode(os.urandom(16)).decode())")
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" \
     -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: $CHAVE" \
     https://SUA-NUVEM/ws/sync/v1/
```

A chave precisa ser **16 bytes aleatórios em base64** — não um texto qualquer.
Com uma chave curta o servidor responde `400 invalid Sec-WebSocket-Key`, e é
fácil ler isso como proxy quebrado quando o proxy está perfeito.

Como interpretar a resposta:

| Resposta | Significado |
|---|---|
| `101 Switching Protocols` | Tudo certo: proxy e sincronização no ar |
| `403` com corpo vazio | O proxy **funciona**; a nuvem é que está com `SYNC_ENABLED=false` |
| `400 invalid Sec-WebSocket-Key` | Sua chave de teste é inválida, não o proxy |
| `404` | A rota não existe: a nuvem não está na 3.0.0 |
| `200` ou HTML | O proxy **não** encaminha o upgrade — conserte o `location /ws/` |

O `403` é o que mais engana: ele vem do consumer recusando **antes** do
handshake, o que só acontece com a sincronização desligada. Nesse caso o proxy
já está correto e o problema é o Passo 1 não ter sido feito.

---

## Passo 2 — Configurar a LOJA

```bash
cd docker/local
cp .env.local.example .env.local
```

Abra o `.env.local` e preencha **estes cinco** (o resto já vem pronto):

```bash
SYNC_CLOUD_API_URL=https://sua-nuvem.exemplo.com
SYNC_CLOUD_WSS_URL=wss://sua-nuvem.exemplo.com/ws/sync/v1/
SYNC_ACCOUNT_ID=<UUID da conta>
SYNC_ENROLL_USERNAME=<superadmin>
SYNC_ENROLL_PASSWORD=<senha>
SYNC_ENROLL_SECRET=<seu segredo, 24+ caracteres>
```

E troque os dois obrigatórios de qualquer instalação:

```bash
DJANGO_SECRET_KEY=<50+ caracteres aleatórios>
POSTGRES_PASSWORD=<senha do banco da loja>
```

Ajuste também `DJANGO_ALLOWED_HOSTS` com o IP do servidor na rede do
restaurante — é por ele que o PDV e os tablets vão entrar.

> **Editou o `.env.local` com a loja já no ar?** `restart` **não** basta: o
> `env_file` é lido quando o container é CRIADO, então um container reiniciado
> continua com os valores antigos. O sintoma é bom de reconhecer — o
> `sync_enroll` para e pede a senha no terminal, porque para ele a variável
> está vazia. Recrie:
>
> ```bash
> docker compose --env-file .env.local -f docker-compose.local.yml up -d
> ```
>
> O Compose percebe que o arquivo mudou e recria só o que precisa.

---

## Passo 3 — Subir a loja

```bash
docker compose --env-file .env.local -f docker-compose.local.yml up -d
```

Com `SYNC_AUTO_ENROLL=true` (o padrão), o `sync_worker` se matricula sozinho no
primeiro boot. Acompanhe:

```bash
docker compose --env-file .env.local -f docker-compose.local.yml logs -f sync_worker
```

O que você quer ver:

```
sync: sem credencial local — matriculando na nuvem…
sync: Matriculado: nó <uuid>. A nuvem enfileirou a carga total <uuid>.
sync: autenticado na nuvem (nó <uuid>)
```

### Prefere fazer à mão?

Desligue `SYNC_AUTO_ENROLL` e rode, na nuvem:

```bash
docker compose exec backend python manage.py sync_provision_node \
  --account <uuid> --name "Loja Centro" \
  --cloud-url wss://sua-nuvem.exemplo.com/ws/sync/v1/
```

Ele imprime o pacote **uma única vez** — token e chave não são recuperáveis
depois. Cole no `.env.local` e suba a loja.

---

## Apontar o PDV para a loja

A URL é **`http://`**, sem `s`:

```
http://<ip-da-loja>:8000/api/v1
```

O backend da loja serve HTTP puro — quem termina TLS é um proxy reverso
externo, que este compose deliberadamente não inclui (mesma decisão do compose
da nuvem). Com `https://` o PDV falha no handshake:

```
Falha de TLS ao conectar em https://...: Handshake error in client
```

Não é rede, nem certificado: é que não há nada escutando TLS daquele lado.

Dois detalhes que costumam morder em seguida:

- **`localhost` só vale no mesmo computador.** De outro terminal da rede, use o
  IP do servidor — e esse IP precisa estar em `DJANGO_ALLOWED_HOSTS` no
  `.env.local`, senão o backend responde `400 DisallowedHost`.
- **O WebSocket é derivado da URL**: `http://host:8000/api/v1` vira
  `ws://host:8000` sozinho. Acertar o esquema aqui acerta o tempo real também.

---

## Passo 4 — Conferir que funcionou

Na **loja**:

```bash
docker compose --env-file .env.local -f docker-compose.local.yml \
  exec backend python manage.py sync_status
```

```
Configuração
  SYNC_ENABLED ......: True
  SYNC_NODE_TYPE ....: LOCAL
Nós
  LOCAL  Loja Centro  [este]  ACTIVE   visto=2026-09-17 18:30  env=0 rec=412
  CLOUD  Nuvem                ACTIVE
Fila
  total ............: 412
  a enviar .........: 0        ← zerado = tudo subiu
  a aplicar ........: 0
  mortos ...........: 0        ← tem de ser 0
```

Na **nuvem**, o nó aparece em `/admin/synchronization/syncnode/` com estado
`ACTIVE` e a carga em `/admin/synchronization/syncrun/` com progresso.

### O teste que vale mais que tudo

Crie um produto **na nuvem** e veja ele aparecer na loja:

```bash
# na loja, alguns segundos depois:
docker compose --env-file .env.local -f docker-compose.local.yml \
  exec backend python manage.py shell -c "
from apps.menu.models import Product
print(Product.all_objects.order_by('-created_at').values_list('name', flat=True)[:5])"
```

E o caminho inverso: registre uma venda no PDV e confira no Admin da nuvem.

---

## Quando algo dá errado

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `sync: a nuvem não respondeu ao HELLO` | Proxy não encaminha WebSocket | Refaça o teste do `101` do Passo 1 |
| `Credencial inválida` | Token errado, ou nó revogado | `sync_enroll --force` para rematricular |
| `A sincronização está liberada somente em DEVELOPMENT` | `SYNC_ENVIRONMENT` diferente nos dois lados | Os dois precisam ser `development` |
| `Faltam SYNC_CLOUD_WSS_URL e/ou SYNC_AUTH_TOKEN` | Loja sem credencial | Ligue `SYNC_AUTO_ENROLL` ou rode `sync_enroll` |
| Fila cresce e não drena | Worker parado, ou nuvem fora | `logs sync_worker`; a fila **não se perde** |
| `403` na matrícula | Usuário não é superadmin nem admin **daquela** conta | Confira o `SYNC_ACCOUNT_ID` |
| `503: SYNC_ENABLED=false` na matrícula | A **nuvem** está com a sincronização desligada | Faça o Passo 1 no servidor da nuvem |
| `sync_enroll` pede a senha no terminal | Container criado antes de você editar o `.env.local` | `up -d` para recriar (não `restart`) |
| `409` ao iniciar carga | Já existe uma carga em andamento | Espere, ou veja `sync_status` |

**A loja fica offline e ninguém percebe?** O healthcheck do `sync_worker`
**não** testa a nuvem de propósito — loja sem internet é um estado normal, e
reprovar isso reiniciaria o worker em looping no pior momento. Para monitorar
de fato, use as métricas:

```bash
curl -H "Authorization: Bearer $SYNC_METRICS_TOKEN" \
     https://sua-nuvem/api/v1/sync/metrics/
```

`sync_event_lag_seconds` é a que denuncia fila parada: um contador alto de
pendentes pode ser um pico, mas um evento parado há duas horas é sempre
problema.

---

## O que nunca se perde

Esta é a promessa central, e é bom saber como cobrá-la.

```bash
# o que está parado, e há quanto tempo
manage.py sync_status

# devolve à fila o que desistiu (o event_id impede duplicar no destino)
manage.py sync_recover --requeue

# resgate manual: grava tudo em JSON
manage.py sync_recover --export /app/sync/fila.json

# limpeza: só toca no que a nuvem JÁ confirmou
manage.py sync_recover --prune-days 30
```

Um evento que falhou doze vezes vira `DEAD` — e **continua no banco**, com o
conteúdo e o erro intactos. Nada é apagado antes da confirmação do outro lado.

Os mesmos botões estão no Admin da nuvem (na tela do nó) e na API
`/api/v1/sync/`.

> **No Git Bash do Windows**, prefixe com `MSYS_NO_PATHCONV=1` qualquer comando
> que passe um caminho absoluto do container:
>
> ```bash
> MSYS_NO_PATHCONV=1 docker compose --env-file .env.local \
>   -f docker-compose.local.yml exec backend \
>   python manage.py sync_recover --export /app/sync/fila.json
> ```
>
> Sem isso o Git Bash traduz `/app/sync/fila.json` para
> `C:/Program Files/Git/app/sync/fila.json` **antes** de o comando entrar no
> container, e o erro que aparece é um `FileNotFoundError` com um caminho do
> Windows que ninguém escreveu. No PowerShell, Linux e macOS não acontece.

---

## Quem pode mexer

Dois códigos no catálogo de permissões, atribuíveis a um Perfil de Acesso:

| Código | Libera |
|---|---|
| `sync.view` | Ver nós, fila, cargas e conflitos |
| `sync.manage` | Disparar carga, reprocessar, revogar, rotacionar credencial |

Superusuário e administrador da conta já têm os dois.

---

## Voltar atrás

```bash
# desligar na loja: pare o worker, o resto continua vendendo
docker compose --env-file .env.local -f docker-compose.local.yml stop sync_worker

# revogar o vínculo (na nuvem): a credencial morre na hora
#   Admin -> Nós de sincronização -> Revogar vínculo
# Os eventos pendentes NÃO são apagados: reativar retoma de onde parou.
```

Para desligar de vez, `SYNC_ENABLED=false` nos dois lados e
`manage.py sync_install_triggers --remove` na nuvem.
