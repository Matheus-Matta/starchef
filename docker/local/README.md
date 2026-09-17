# Backend da loja (`docker-compose.local.yml`)

O servidor que roda **dentro do restaurante**. O PDV, o KDS e o app do garçom
falam só com ele; ele fala com a nuvem por conta própria, quando dá.

## A ideia em uma frase

É a **mesma imagem** do backend da nuvem, o mesmo código e as mesmas
migrations. `SYNC_NODE_TYPE=local` é o que muda o papel — não há um "backend
local" separado para manter.

    PDV, KDS, garçom
            ↓  (rede interna da loja)
    backend  →  postgres local + outbox
            ↑
    sync_worker  ⇄  WSS  ⇄  nuvem

## Serviços, e por que cada um está aqui

| Serviço | Para quê |
|---|---|
| `postgres` | O banco da loja. A fonte da verdade local. |
| `redis` | Cache, canal do Channels e broker do Celery. |
| `backend` | A API que os aplicativos da loja consomem. |
| `celery_worker` | Tarefas do domínio + retry/reconciliação da sincronização. |
| `celery_beat` | O relógio dessas periódicas. |
| `sync_worker` | **O processo novo:** mantém a conexão WSS com a nuvem. |

`sync_worker` **não** é um worker Celery. Ele não consome fila de broker: ele
abre a conexão de saída para a nuvem, envia a outbox e aplica o que chega. Todo
o estado dele está no PostgreSQL — matar o container no meio de um lote não
perde nada, ele retoma de onde parou.

## Subir

```
cp .env.local.example .env.local
```

Preencha, no mínimo: `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`,
`SYNC_CLOUD_API_URL`, `SYNC_CLOUD_WSS_URL`, `SYNC_ACCOUNT_ID`,
`SYNC_ENROLL_USERNAME`, `SYNC_ENROLL_PASSWORD` e `SYNC_ENROLL_SECRET`. Então:

```
docker compose --env-file .env.local -f docker-compose.local.yml up -d
```

## O que acontece na primeira subida

1. `backend` aplica as migrations no banco vazio da loja.
2. `sync_worker` vê que não há credencial e, com `SYNC_AUTO_ENROLL=true`, se
   **matricula**: apresenta usuário, senha, conta e o segredo de matrícula.
3. A nuvem autentica, provisiona o nó e devolve o pacote de credenciais
   **cifrado com esse segredo**. Ele é gravado em `SYNC_ENROLL_ENV_PATH`
   (volume `sync_credentials`) — sem isso, reiniciar o container perderia o
   token.
4. A nuvem já enfileira a **carga total** para este nó.
5. `sync_worker` conecta e a carga desce: conta, lojas, fiscal, usuários,
   cardápio, impressoras, mesas — na ordem de dependência.

O segredo de matrícula **não** é a chave de sincronização. Ele só protege o
pacote que traz a chave definitiva, que nasce na nuvem. Depois da matrícula dá
para apagar `SYNC_ENROLL_PASSWORD` e `SYNC_ENROLL_SECRET` do `.env.local`.

Prefere fazer à mão? Desligue `SYNC_AUTO_ENROLL`, rode na nuvem:

```
docker compose exec backend python manage.py sync_provision_node --account <uuid> --name "Loja Centro" --cloud-url wss://dev-nuvem.exemplo.com/ws/sync/v1/
```

e cole o pacote impresso no `.env.local`.

## O que roda no boot

O `backend` aplica as migrations, coleta os estáticos e instala as **triggers
da rede de segurança** (`sync_install_triggers`) antes de subir o gunicorn.
Essas triggers capturam escrita feita por fora do ORM — `QuerySet.update`,
`bulk_create`, SQL direto — que os signals do Django não veem. São idempotentes
e acompanham o catálogo, então rodam em todo boot sem migration nova.

`manage.py check` avisa se alguma tabela sincronizada ficar sem trigger.

## Internet caiu. E agora?

Nada. A loja continua vendendo: o PDV fala com o backend local, que grava no
PostgreSQL local. Os eventos se acumulam na outbox e sobem quando a conexão
voltar. O `sync_worker` reconecta sozinho, com backoff e jitter.

O healthcheck do `sync_worker` **não** testa a nuvem de propósito: loja offline
é um estado normal, e um healthcheck que reprovasse isso reiniciaria o worker
em looping justamente no pior momento.

## O que não foi enviado

Nada é apagado antes da confirmação do outro lado. Um evento que falhou doze
vezes vira `DEAD` — e continua no banco, com payload e erro íntegros.

```
docker compose -f docker-compose.local.yml exec sync_worker python manage.py sync_status
docker compose -f docker-compose.local.yml exec sync_worker python manage.py sync_recover --requeue
docker compose -f docker-compose.local.yml exec sync_worker python manage.py sync_recover --export /app/sync/fila.json
```

- `sync_status` — nós, fila, o que está parado e há quanto tempo.
- `sync_recover --requeue` — devolve os mortos à fila. O `event_id` impede
  duplicação no destino, então reenviar é sempre seguro.
- `sync_recover --export` — grava tudo em JSON. O resgate manual de último
  recurso.
- `sync_recover --prune-days 30` — limpeza. Só toca no que a nuvem **já
  confirmou**.

Os mesmos botões existem no Django Admin da nuvem (change form do nó) e na API
(`/api/v1/sync/`).

## Arquivos e métricas

Imagens e anexos não passam pelo WebSocket: vão por HTTPS em pedaços de 1 MiB,
com retomada por offset e conferência de SHA-256 antes de publicar. Os pedaços
ficam em `media/sync_tmp/`, dentro do volume `backend_media` — **não** monte um
volume próprio ali: o Docker o criaria como root e o processo roda como uid
1000, quebrando toda gravação de pedaço.

As métricas do coletor ficam em `/api/v1/sync/metrics/`, protegidas por
`SYNC_METRICS_TOKEN` (ou superusuário, quando o token está vazio).

## A nuvem

Não há compose próprio: é o `docker-compose.yml` da raiz com o bloco de
`.env.cloud.example` somado ao `.env`. Confirme que o proxy reverso encaminha
o WebSocket em `/ws/sync/v1/` preservando `Upgrade`/`Connection` — sem isso o
handshake nunca acontece, e o sintoma é a loja "tentando conectar" para sempre.
