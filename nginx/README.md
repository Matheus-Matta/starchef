# nginx da nuvem (Cloudflare, SSL Full strict)

O serviço `nginx` do `docker-compose.yml` é a única porta pública da nuvem
(80 e 443):

| Domínio | Vai para |
| --- | --- |
| `api.starchef.com.br` | `127.0.0.1:8000` (backend) — `/api`, `/ws`, `/admin`, `/static`, `/media`, `/health` |
| `app.starchef.com.br` | `127.0.0.1:8080` (frontend) — o painel |
| qualquer outro host | recusado (444), sem resposta |

Esta pasta é a `/opt/nginx` do servidor (mude com `NGINX_DIR` no `.env`),
com a mesma estrutura — basta copiá-la:

```
nginx/                       → /opt/nginx/
├── nginx.conf
└── certs/
    ├── origin.pem           ← Origin Certificate da Cloudflare (só no servidor)
    └── origin.key           ← a chave dele, chmod 600 (só no servidor)
```

O certificado NUNCA entra no Git: o `certs/.gitignore` recusa tudo da pasta.

## Primeira instalação

1. **Certificado de origem.** Cloudflare → SSL/TLS → Origin Server → *Create
   Certificate*, para `starchef.com.br` e `*.starchef.com.br`. Salve o
   certificado em `certs/origin.pem` e a chave em `certs/origin.key`. Sem eles
   o nginx não sobe. Não sirva um certificado autoassinado no lugar: em
   "Full (strict)" a Cloudflare recusa (erro 526).
2. **Copiar a configuração**, da raiz do repositório:
   `sudo mkdir -p /opt/nginx && sudo cp -r nginx/. /opt/nginx/`
3. **Cloudflare:**
   - SSL/TLS → modo **Full (strict)**;
   - DNS: `api` e `app` apontando para o IP do servidor, com a nuvem laranja
     (proxied);
   - Network → **WebSockets ligado**: o tempo real do painel, o KDS e o sync
     das lojas passam por `/ws/`.
4. **`.env` da nuvem:** o painel (`app.`) chama a API em outro host (`api.`):
   ```
   API_URL=https://api.starchef.com.br/api/v1
   DJANGO_ALLOWED_HOSTS=api.starchef.com.br
   DJANGO_CORS_ALLOWED_ORIGINS=https://app.starchef.com.br
   DJANGO_CSRF_TRUSTED_ORIGINS=https://app.starchef.com.br
   ```
   Os dois são o mesmo *site* (`starchef.com.br`), então os cookies
   `SameSite=Lax` do login continuam valendo.
5. `docker compose up -d`

## Ao mudar a configuração

Edite aqui em `nginx/` (é o que fica versionado), copie com
`sudo cp nginx/*.conf /opt/nginx/` e recarregue sem derrubar ninguém:

```
docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload
```

## Por que cada coisa

- **Porta local, nunca nome de container:** o nginx roda com
  `network_mode: host` e vai a `127.0.0.1:8000` e `127.0.0.1:8080`, as portas
  que backend e frontend publicam em loopback. Pelo nome ele dependia do DNS
  do Docker: com o frontend parado, "frontend could not be resolved" e o
  painel em 502; e na `apps_net`, compartilhada com outros apps, outro
  serviço com o mesmo nome capturaria o tráfego. Recriar um container não
  muda a porta, então não há IP para reler. Se mudar `BACKEND_PORT` ou
  `FRONTEND_PORT` no `.env`, mude aqui também.
- **`X-Forwarded-Proto https` fixo:** o backend confia nele
  (`SECURE_PROXY_SSL_HEADER`). Como a Cloudflare só chega por 443, ele não
  depende do que o cliente mandou.
- **Rate limit:** um IP é uma LOJA INTEIRA (PDVs, garçons, KDS e painel saem
  pelo mesmo IP), por isso os números são altos: são contra abuso. A defesa
  fina, por conta e por usuário, é do DRF.
- **Sem CSP:** o painel chama ViaCEP, Cosmos, Google Fonts e as imagens do
  S3/R2. Uma CSP precisa listar cada um, senão quebra sem aviso. Fica para
  quando for montada e testada no navegador.

## Fechar a origem (recomendado)

Com a nuvem laranja, ninguém precisa falar direto com o IP do servidor. No
firewall do host, libere 80/443 só para os IPs da Cloudflare. Mais forte
ainda: *Authenticated Origin Pulls* (a Cloudflare apresenta um certificado
cliente). Para ligar, coloque o certificado da Cloudflare em
`certs/cloudflare-origin-pull.pem` e acrescente nos dois `server` de 443:

```
ssl_client_certificate /etc/nginx/certs/cloudflare-origin-pull.pem;
ssl_verify_client on;
```

As portas de `backend` (8000) e `frontend` (8080) são publicadas só em
loopback (`127.0.0.1`): é por elas que o nginx chega aos dois. Nunca as abra
para fora: o backend confia nos cabeçalhos `X-Forwarded-*` de quem se conecta.
