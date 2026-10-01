# StarChef na loja (`docker-compose.local.yml`)

O StarChef **inteiro** rodando num servidor dentro do restaurante: retaguarda
web, API para o PDV/KDS/garçom, banco e filas. Pronto para produção, com as
**mesmas imagens da nuvem**: nada é compilado na loja.

## Instalar em 3 passos

1. Instale o **Docker** no servidor da loja (Docker Desktop no Windows, Docker
   Engine no Linux) e copie esta pasta para ele.
2. Rode o instalador **nesta pasta**:
   - Windows: `powershell -ExecutionPolicy Bypass -File .\instalar.ps1`
   - Linux: `sh instalar.sh`
3. Ele pergunta o **IP do servidor** na rede da loja (já sugere um) e faz o resto.

No fim aparece:

```
StarChef no ar.
  Painel:       http://192.168.0.10/
  API do PDV:   http://192.168.0.10/api/v1
  Admin:        http://192.168.0.10/admin/
  Primeiro acesso: abra o Admin e use o token XXXX para criar a conta e o administrador.
```

**O que o instalador faz por você:** cria o `.env.local` a partir do
`.env.local.example`, gera a chave do Django, a senha do banco e os tokens,
baixa as imagens, sobe tudo e espera o backend ficar pronto. Rodar de novo é
seguro: ele só completa o que falta e nunca troca o que já está preenchido.

## As únicas variáveis que importam

Tudo fica no `.env.local`. Os quatro obrigatórios estão no topo:

| Variável | O que é | Quem preenche |
|---|---|---|
| `STARCHEF_VERSION` | versão das imagens, ex. `3.0.62` | já vem no exemplo |
| `STORE_HOST` | IP do servidor na rede da loja, ex. `192.168.0.10` | o instalador pergunta |
| `DJANGO_SECRET_KEY` | chave do Django | o instalador gera |
| `POSTGRES_PASSWORD` | senha do banco | o instalador gera |

**Quer a loja conversando com a nuvem?** Mude `SYNC_ENABLED=true` e preencha
`SYNC_ACCOUNT_ID`, `SYNC_ENROLL_USERNAME` e `SYNC_ENROLL_PASSWORD` (um
administrador da conta). Depois rode o instalador de novo.

Os endereços (`ALLOWED_HOSTS`, CORS, CSRF) saem **sozinhos** do `STORE_HOST`.
Antes eram três listas a manter iguais à mão, e esquecer o IP numa delas dava
"Bad Request (400)" sem pista nenhuma.

## Endereços

| Para | Endereço |
|---|---|
| Painel (navegador) | `http://IP/` |
| PDV, KDS, app do garçom | `http://IP/api/v1` |
| Admin do Django | `http://IP/admin/` |
| API direta (PDVs antigos) | `http://IP:8000/api/v1` |

A porta **80** é a porta única: o `proxy` (Caddy) manda `/api`, `/ws`,
`/admin`, `/static` e `/media` para o backend e o resto para o painel. Mesma
origem é o que dispensa CORS e deixa o cookie de login funcionar. A **8000**
continua aberta para PDVs que já apontam para ela.

Sem HTTPS de propósito: é rede interna e não há domínio público para emitir
certificado. **Restrinja as portas 80 e 8000 no firewall** à faixa da loja.

## Serviços

| Serviço | Para quê |
|---|---|
| `proxy` | A porta única da loja (Caddy). |
| `frontend` | A retaguarda web, a mesma do app.starchef.com.br. |
| `backend` | A API que os aplicativos da loja consomem. |
| `celery_worker` | Tarefas do domínio + retry/reconciliação da sincronização. |
| `celery_beat` | O relógio dessas periódicas. |
| `sync_worker` | A conexão WSS com a nuvem. Com `SYNC_ENABLED=false` fica parado de propósito, sem erro. |
| `postgres` | O banco da loja. A fonte da verdade local. |
| `redis` | Cache, canal do Channels e broker do Celery. |

## Dia a dia

Rode na pasta, trocando `dc` por
`docker compose --env-file .env.local -f docker-compose.local.yml`:

| Para | Comando |
|---|---|
| Ver se está tudo de pé | `dc ps` |
| Ver o log do backend | `dc logs -f backend` |
| Reiniciar tudo | `dc restart` |
| Parar (os dados ficam) | `dc down` |
| **Atualizar a versão** | troque `STARCHEF_VERSION` no `.env.local` e `dc pull && dc up -d` |
| **Backup do banco** | `dc exec -T postgres pg_dump -U starchef starchef_local > backup.sql` |
| Restaurar o backup | `dc exec -T postgres psql -U starchef starchef_local < backup.sql` |

Faça o backup **antes de atualizar a versão**: as migrations rodam sozinhas
na subida, e um backup é o único caminho de volta.

**Nunca use `dc down -v`**: o `-v` apaga os volumes, e com eles o banco da loja.

## Com sincronização: o que acontece na primeira subida

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

Depois disso roda `manage.py check`, e é a **última coisa impressa antes do
gunicorn**. Os avisos já saíam no `migrate`, mas ali sobem junto com centenas
de linhas de migration e ninguém os lê; no fim do log eles ficam onde quem
está subindo a loja está olhando.

Ele avisa se alguma tabela sincronizada ficar sem trigger, se faltar
credencial do nó (`W003`) e se o papel declarado discordar do `SyncNode`
gravado (`W008`) — este último é o que pega uma loja se achando nuvem.

O `check` **não derruba o boot**: sincronização mal configurada degrada a
sincronização, não tira a loja do ar. Um `migrate` que falha, esse sim,
impede o gunicorn de subir.

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
docker compose --env-file .env.local -f docker-compose.local.yml exec sync_worker python manage.py sync_status
docker compose --env-file .env.local -f docker-compose.local.yml exec sync_worker python manage.py sync_recover --requeue
docker compose --env-file .env.local -f docker-compose.local.yml exec sync_worker python manage.py sync_recover --export /app/sync/fila.json
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
