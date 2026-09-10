# StarChef Storefront

Aplicação Nuxt que faz **duas** coisas — e as mantém separadas de propósito:

1. **renderiza o cardápio público** (SSR, rápido, indexável);
2. **hospeda o editor visual de blocos** (GrapesJS), usado só pelo painel.

A regra central do projeto:

```
GrapesJS edita.  Nuxt renderiza.  Django persiste e fornece os dados.
```

O GrapesJS **nunca** entra no bundle do cliente final. Ele é importado
dinamicamente, dentro de um componente `.client.vue`, numa rota separada. No
build atual ele fica sozinho num chunk de ~1,1 MB que só é baixado por quem
abre `/<slug>/editor/`.

---

## Rodar em desenvolvimento

Precisa do backend Django no ar e de um site já provisionado (todo restaurante
de conta com o módulo E-commerce ganha um automaticamente — ver
`docs/BACKEND.md` §9.1).

```bash
cd storefront
npm install
cp .env.example .env
```

```bash
npm run dev
```

Descubra os slugs dos sites no backend:

```bash
cd ../backend && python manage.py shell -c "from apps.storefront.models import MenuSite; print(*MenuSite.all_objects.values_list('slug', flat=True))"
```

E abra cada um pelo endereço. **Não há variável de "qual restaurante"** — o
site é escolhido pelo primeiro segmento da URL:

| Endereço | O que abre |
| --- | --- |
| `http://localhost:3100/burger-palace/` | cardápio público de um restaurante |
| `http://localhost:3100/pizza-rustica/` | cardápio de outro, no mesmo processo |
| `http://localhost:3100/burger-palace/promocoes` | página interna daquele site |
| `http://localhost:3100/burger-palace/editor/` | editor (pede login) |
| `http://localhost:3100/burger-palace/preview/<pageId>` | rascunho, com o renderer de produção |

Com ou sem a barra no final, tanto faz.

| Comando | O que faz |
| --- | --- |
| `npm run dev` | Servidor de desenvolvimento com HMR |
| `npm run build` | Build de produção (Nitro) em `.output/` |
| `npm start` | Roda o build (`node .output/server/index.mjs`) |
| `npm test` | Testes de unidade do compiler, sanitizador e breakpoints |
| `npm run typecheck` | `vue-tsc` sobre o projeto |

---

## Variáveis de ambiente

| Variável | Para que serve |
| --- | --- |
| `STOREFRONT_API_BASE` | URL do Django (`http://localhost:8001` em dev) |
| `PORT` | Porta do servidor Nuxt (3100 em dev) |

São só essas duas. **Como o site sabe de qual restaurante ele é:** pelo primeiro
segmento da URL. O `slug` de `MenuSite` é único na plataforma inteira
(constraint no banco), então ele sozinho identifica o restaurante — sem DNS, sem
arquivo `hosts`, sem uma variável por loja.

Isso substituiu o par `STOREFRONT_TENANT_MODE`/`STOREFRONT_SITE_SLUG`, que tinha
um defeito incômodo: o slug era lido em tempo de **build** e ficava congelado no
bundle, então trocar de restaurante exigia recompilar — e uma imagem Docker
servia uma loja só.

> **O editor e a API precisam estar no MESMO host.** Os cookies de sessão são
> `SameSite=Lax`, e o navegador não os envia em requisições para outro site.
> Porta diferente não atrapalha; host diferente sim — abrir o editor em
> `127.0.0.1:3100` com a API em `localhost:8001` faz o login responder 200 e a
> requisição seguinte voltar 401. Em produção, sirva os dois pelo mesmo domínio
> (ou por subdomínios do mesmo domínio) atrás do proxy. O editor detecta esse
> caso e diz o que está errado, em vez de falhar em silêncio.

Domínio próprio (`pizzaria.com.br` apontando direto para uma loja) fica para
depois. O backend já sabe resolver por hostname
(`/api/v1/public/storefront/by-host/`); enquanto não houver DNS configurado, o
endereço por slug é o único que funciona em qualquer ambiente.

---

## Autenticação do editor

O editor abre por endereço público, então o slug é **entrada do usuário** — e
por isso nada de acesso é decidido no navegador:

```
/burger-palace/editor/  →  GET /api/v1/storefront/auth/session/?site=burger-palace
                            401 → mostra o formulário de entrada
                            403 → "este site não é do seu restaurante"
                            200 → abre o editor
```

Duas garantias, ambas do servidor:

- **Cookies próprios.** O editor usa `sf_access`/`sf_refresh`/`sf_session`, e o
  painel administrativo usa `sc_*`. Os dois batem no mesmo backend, então os
  cookies caem no mesmo domínio — com o mesmo nome, abrir o editor derrubaria a
  sessão do painel na outra aba. Quem escolhe qual ler é o header
  `X-Auth-Scope: storefront`, mandado em toda chamada autenticada.
- **Escopo de tenant.** `/auth/session/?site=<slug>` cruza o slug com os sites
  que aquele usuário realmente pode editar (admin da conta vê a conta inteira;
  os demais, só o próprio restaurante) e responde 403 quando não bate. A API de
  páginas e de sites é escopada pelo mesmo tenant, então um id descoberto por
  outro caminho também não abre nada.

Os tokens ficam em cookie **httpOnly**: o JavaScript do editor nunca vê o JWT,
o que fecha o roubo de sessão por XSS.

---

## O editor

Abre em `/<slug>/editor/` (a home) ou `/<slug>/editor/<pageId>` (uma página
específica). O GrapesJS é o motor — canvas, arrastar-e-soltar, seleção,
undo/redo, árvore de componentes — e a UI em volta é Vue.

**O canvas mostra o site de verdade.** Ele é um `<iframe>` isolado, então nada
do CSS do Nuxt chega nele sozinho. `lib/builder/canvas-styles.ts` injeta
`tokens.css` e `blocks.css` como texto, e por cima o tema do restaurante. É por
isso que `blocks.css` é um arquivo separado e sem `@import 'tailwindcss'`: uma
diretiva `@import` ali quebraria a injeção. Uma fonte só para as duas telas —
uma cópia para o editor divergiria na primeira correção, e a divergência
apareceria do pior jeito: o cliente aprova no editor e o site sai diferente.

**Os blocos se desenham de verdade.** `lib/builder/components/previews.ts`
monta HTML estático com as mesmas classes do site, respeitando a configuração
do bloco: desmarcar "mostrar preço" apaga o preço no canvas na hora. Produtos e
categorias da prévia são de exemplo, e a etiqueta cinza no canto diz isso — sem
o aviso, o cliente tentaria editar o nome do produto ali.

**O cabeçalho aparece no topo, mas não é um bloco.** Ele é do site
(`MenuSite.header`), aparece em todas as páginas e não pode ser apagado por
engano. É desenhado no canvas como referência fixa, não selecionável, e a aba
"Site" é onde ele se edita — com o canvas acompanhando cada alteração.

**A moldura segue o vocabulário do Studio SDK do GrapesJS**: cada lateral é um
conjunto de painéis nomeados atrás de abas, e não uma coluna rolante única —
empilhado, o painel de estilo nascia abaixo da dobra e o cliente não sabia que
existia. As abas ficam fixas no topo e só o conteúdo rola; as duas laterais
recolhem para devolver largura ao canvas, e recolhem sozinhas em telas
estreitas (1400 / 1180 / 900px).

| Lateral | Aba | O que faz |
| --- | --- | --- |
| esquerda | Blocos | Seções prontas do backend (`GET /storefront/schema/` → `sections`) e blocos avulsos |
| esquerda | Camadas | A árvore da página, para selecionar o que está soterrado |
| direita | Elemento | Traits (configuração do bloco) e estilo do que está selecionado |
| direita | Página | Título, endereço, página inicial, ordem no menu e SEO |
| direita | Cabeçalho | Marca, faixa de aviso, endereço, busca, ações e navegação |
| direita | Site | Paleta completa, tipografia, catálogo publicado e SEO do site |

As cores da própria moldura saem de tokens (`--sfe-global-bg1`,
`--sfe-primary-bg1`, …) nomeados como as categorias de tema do SDK. Antes eram
dezenas de `#dfe3e8` espalhados, e mudar o cinza do editor exigia achar todos —
foi assim que a aba ativa acabou branca sobre branca.

### O cabeçalho é editável, mas não é um bloco

Clicar no cabeçalho dentro do canvas abre a aba **Cabeçalho** — o mesmo gesto
que se usa para qualquer bloco. Ele continua fora da árvore de componentes:
não se arrasta, não se apaga, e aparece em todas as páginas. O canvas
acompanha cada tecla do formulário, sem salvar.

### A paleta é global, e tudo sai dela

Nenhuma cor do site vive fixa no CSS. O selo de promoção, o texto sobre o
botão, o verde do WhatsApp, o fundo do cabeçalho e o da faixa de aviso eram
literais em `blocks.css` e escapavam do tema: trocar de preset repintava o site
e deixava ilhas para trás. Agora são tokens como `primaryColor`, editáveis em
grupos (Marca, Superfícies, Texto, Cabeçalho, Sinalização), e o valor padrão de
cada um é **derivado do próprio preset** — um tema novo herda um conjunto
coerente sem precisar preencher sete campos a mais.

Sites criados antes de a paleta crescer são completados no provisionamento,
pelo preset deles: um site vermelho não herda o verde do tema padrão só porque
faltava um token.

A topbar traz o seletor de páginas (trocar, criar, apagar), os dispositivos
(computador/tablet/celular), desfazer/refazer, pré-visualizar, salvar e
publicar. Salvar grava em `draft_data`; publicar move o rascunho para o que o
público vê — a invariante do backend, respeitada aqui.

**Traits são configuração, estilo é CSS.** O trait grava em `props`, que é o
que o renderer Vue lê; o painel de estilo grava CSS, que o compiler transforma
em regras com media query. Misturar os dois faria espaçamento virar
configuração de bloco e "mostrar preço" virar CSS.

### Ícones

Uma fonte só, usada no site publicado e no editor: `@material-design-icons/svg`
(o pacote oficial do Google, só com os arquivos SVG — sem framework, sem fonte
de ícone por ligatura). Antes cada ícone era desenhado à mão (`<svg><path
stroke="…"/></svg>` repetido em cada componente) ou virava emoji dentro das
prévias do canvas (🛒, 👤, ⌕) — o carrinho do cabeçalho tinha um traço, e a
prévia do mesmo botão dentro do editor tinha outro.

`lib/icons/material-icons.ts` importa cada ícone como TEXTO (`?raw`) — só os
que estão de fato `import`ados entram no bundle, o Vite não empacota o pacote
inteiro — e extrai o `d` do `<path>` uma vez, na importação. Duas saídas para
os dois mundos do projeto:

- `MaterialIcon.vue` — componente Vue, usado nos blocos do site (carrinho,
  busca, localização, capa, avaliação…) e na moldura do editor (abas, botões
  da topbar, painel de blocos);
- `materialIconMarkup(nome, tamanho)` — a mesma coisa como *string* de HTML,
  para os dois lugares que não montam componente Vue: as prévias do canvas
  (montadas como texto) e o campo `media` de cada bloco no painel de Blocos.

A cor sempre vem de fora (`fill: currentColor`), o mesmo princípio que os
ícones desenhados à mão já seguiam — um ícone só, usado num botão verde e
noutro cinza sem precisar de duas variantes.

---

## Estrutura

```
app/
  pages/
    index.vue                     raiz sem slug → 404 (não há loja "padrão")
    [site]/[[...slug]].vue        cardápio público (SSR) — uma rota serve o site inteiro
    [site]/editor/index.vue       editor da home (client-only)
    [site]/editor/[pageId].vue    editor de uma página específica
    [site]/preview/[pageId].vue   preview do rascunho, com o renderer de produção
  components/
    renderer/              o site público. NUNCA importa GrapesJS
      SfNode.vue           resolve cada nó do schema pelo tipo
      blocks/Sf*.vue       os blocos (vitrine, categorias, horários, rodapé…)
    builder/               o editor. Só `.client.vue`
      EditorAuthGate        porta de entrada: sessão, login e 403 por tenant
      PageSwitcher.vue      trocar, criar e apagar páginas
      panels/               formulários de Página e de Site
  composables/             tema, dados do restaurante, tenant e sessão do editor
  assets/css/
    tokens.css             os `--sf-*` padrão
    blocks.css             aparência dos blocos — CSS PURO, injetado no canvas
    storefront.css         só junta o reset do Tailwind com o `blocks.css`
    builder.css            a moldura do editor (topbar, painéis, porta de entrada)

lib/builder/
  create-editor.ts         único lugar que chama `grapesjs.init()`
  canvas-styles.ts         monta a folha injetada no iframe do canvas
  components/previews.ts   como cada bloco se desenha dentro do canvas
  components/, blocks/     tipos e blocos do editor
  compiler/                project data do GrapesJS → schema de renderização
  registry/                mapa de tipos: editor, renderer e injeção
  security/                sanitizador de URL e de texto rico
  styles/, devices/        allowlist de CSS e os três breakpoints
  schema/                  versão do schema e envelope do rascunho

services/api/              toda comunicação com o Django passa por aqui
types/                     contratos do payload público e do render schema
tests/unit/                compiler, sanitizador, breakpoints
```

### Por que existe um compiler

O `project data` do GrapesJS guarda muita coisa que só interessa ao editor. O
compiler traduz isso para uma árvore simples de nós tipados, com os estilos já
resolvidos por breakpoint. O que se ganha:

- o bundle público não carrega uma linha de GrapesJS;
- o SSR renderiza componentes Vue de verdade, com produto e preço reais, em vez
  de despejar HTML exportado;
- trocar o editor um dia não obriga a reescrever o site;
- nada além da allowlist de CSS chega ao navegador do cliente final.

### Dados dinâmicos

Os blocos de vitrine guardam **configuração**, nunca cópia de produto:

```json
{ "type": "sf-product-grid", "props": { "category_id": 12, "columns": { "desktop": 4 } } }
```

Nome, preço, foto e disponibilidade vêm do payload público em tempo de
renderização. Um preço alterado no PDV aparece no site sem ninguém reabrir o
editor.

A foto exibida em `product.image` é a `logo_p` do cadastro; `photo_list` leva a
galeria ordenada e cada variação pode trazer sua própria `logo_p`, sempre
escolhida dessa galeria. Categorias recebem `logo_url` e o restaurante usa a
logo do mesmo acervo central. Os campos antigos permanecem como fallback para
bases migradas.

### Tema e seções prontas

O tema do restaurante (`site.theme`) vira variáveis CSS `--sf-*` no elemento
raiz. As páginas usam `var(--sf-primary)` em vez de `#0B5B34` — é isso que
permite trocar o preset de tema no painel e repintar o site inteiro sem editar
nenhum bloco.

Todo site nasce com o tema **Mercado** (verde/amarelo, cartão claro com foto
grande, selo de desconto e botão "+" redondo) e uma home publicada: faixa de
aviso, cabeçalho com busca, capa promocional, categorias, ofertas do dia,
vitrine com filtros e rodapé. O cliente que não quiser mexer em nada já tem
cardápio no ar.

As mesmas peças aparecem no editor, na categoria **"Seções prontas"** do painel
de blocos. Elas vêm do backend (`GET /api/v1/storefront/schema/` → `sections`,
montadas em `apps/storefront/starter.py`), e não de uma cópia local — uma
segunda lista divergiria na primeira correção.

---

## Imagem Docker

```bash
docker build -t starchef-storefront .
docker run --rm -p 3000:3000 \
  -e STOREFRONT_API_BASE=https://api.seudominio.com.br \
  starchef-storefront
```

Build multi-stage: a imagem final leva só o `.output` do Nitro, sem
`node_modules` nem código-fonte. Uma única variável — a mesma imagem serve dev,
homologação e produção, e **todas as lojas ao mesmo tempo**: qual restaurante
servir vem da URL, não da configuração do contêiner.

> Num build já pronto, `runtimeConfig.public` só é sobrescrito por variáveis com
> o prefixo `NUXT_PUBLIC_` (ex.: `NUXT_PUBLIC_API_BASE`). `STOREFRONT_API_BASE`
> é lido em tempo de build — é o que o `Dockerfile` usa.

---

## Estado atual

Feito (Fase 1–3 e 6 do plano em `afazer/storefront-grapesjs-requisitos-arquitetura.md`):

- [x] renderer público com SSR, tema e SEO
- [x] compiler `project data` → render schema, com estilos responsivos
- [x] blocos de layout, conteúdo, cardápio e restaurante
- [x] editor GrapesJS client-only, com tipos, blocos, devices e undo/redo
- [x] salvar rascunho, autosave com debounce, publicar e pré-visualizar
- [x] sanitização de URL e texto rico no renderer
- [x] endereço por slug (`/<slug>/`) e sessão própria do editor, com 403 por tenant
- [x] canvas com o CSS real do site, prévia dos blocos e cabeçalho de referência
- [x] gerenciar páginas de dentro do editor (trocar, criar, apagar)
- [x] laterais em abas, recolhíveis e responsivas, com tema por tokens
- [x] paleta global completa — nenhuma cor do site fora do tema
- [x] cabeçalho editável clicando nele no canvas
- [x] testes de unidade do compiler, do sanitizador e das prévias do canvas

### O que se edita dentro do editor

A lateral direita tem três abas:

| Aba | O que edita | API |
| --- | --- | --- |
| Elemento | traits e estilo do bloco selecionado (painéis do GrapesJS) | — |
| Página | título, endereço, página inicial, ordem e SEO | `PATCH /storefront/pages/{id}/` |
| Site | tema (presets + tokens), identidade, catálogo, **cabeçalho** e SEO | `PATCH /storefront/sites/{id}/` |

A topbar traz ainda o seletor de páginas, que cria (`POST /storefront/pages/`) e
apaga (`DELETE /storefront/pages/{id}/`) sem sair do editor.

**Tudo o que o model `MenuSite` guarda é editável aqui**, não só no painel
administrativo. Mudar uma cor repinta o canvas na hora, antes de salvar — o
canvas recebe os tokens do tema por `applyCanvasTheme`, e é por isso que o
editor mostra a cor de verdade do restaurante em vez do tema padrão.

A única parte que fica só no painel é **domínios**: ela exige
`storefront.domains`, que o perfil E-commerce não tem (apontar DNS errado tira
o site do ar).

A fazer:

- [ ] UI Vue própria dos painéis de blocos, camadas e estilo (a de Site/Página já é Vue)
- [ ] biblioteca de mídia própria (`AssetLibraryModal`) e adapter do Asset Manager
- [ ] galeria de templates dentro do editor
- [ ] carrinho e checkout
- [ ] validação com Zod na carga do schema publicado
- [ ] testes E2E (Playwright) do fluxo montar → salvar → publicar → abrir
