/**
 * O CSS que o canvas do editor precisa para parecer com o site.
 *
 * O canvas do GrapesJS é um `<iframe>` com documento próprio. Nada do CSS do
 * Nuxt chega nele sozinho — e sem estas regras o cliente montava a página
 * vendo caixas cinzas sem estilo, descobrindo a aparência real só depois de
 * publicar. Era o defeito mais visível do editor.
 *
 * Os arquivos entram como TEXTO (`?raw`), não como link para um `.css`
 * construído: o nome do arquivo gerado pelo Vite muda a cada build, e apontar
 * para ele exigiria adivinhar o hash. Ler o fonte funciona igual em dev e em
 * produção, e mantém uma fonte só — as mesmas regras que o site público usa.
 *
 * A ordem importa e é o que faz o tema funcionar:
 *
 *   1. `tokens.css`  — os `--sf-*` padrão (piso, para nada ficar ilegível);
 *   2. `blocks.css`  — a aparência dos blocos, em cima desses tokens;
 *   3. tema do restaurante — reescrito a cada alteração no painel de Site,
 *      por último, para vencer o piso sem precisar de `!important`.
 */
import blocksCss from '~/assets/css/blocks.css?raw'
import tokensCss from '~/assets/css/tokens.css?raw'

/** Ajustes que só fazem sentido DENTRO do editor, nunca no site publicado. */
const CANVAS_ONLY_CSS = `
  body{margin:0;background:var(--sf-background);color:var(--sf-text);font-family:var(--sf-font);min-height:100vh}

  /* Bloco sem representação própria (um mapa, um contêiner vazio): uma caixa
     tracejada dizendo o que é. Melhor que um retângulo invisível, que o
     cliente não consegue nem selecionar. */
  .sf-canvas-placeholder{
    display:flex;flex-direction:column;gap:4px;align-items:center;justify-content:center;
    min-height:120px;padding:24px;border:1px dashed var(--sf-border);border-radius:var(--sf-radius);
    background:var(--sf-surface);color:var(--sf-muted-text);text-align:center;
  }
  .sf-canvas-placeholder strong{color:var(--sf-text);font-size:15px}
  .sf-canvas-placeholder span{font-size:13px}

  /* Sobre uma área que já tem cor própria — a capa, por exemplo — o aviso não
     pode ser um cartão opaco: ele viraria conteúdo aos olhos de quem monta a
     página, e o editor deixaria de parecer com o site. Fica só o contorno,
     ocupando exatamente o espaço que a imagem vai ocupar. */
  .sf-canvas-placeholder--ghost{
    width:100%;height:100%;min-height:0;background:transparent;
    border-color:rgb(255 255 255 / 45%);color:inherit;opacity:.75;
  }
  .sf-canvas-placeholder--ghost strong{color:inherit}

  /* O cabeçalho é do SITE, não da página: não entra na árvore de componentes,
     não se arrasta e não se apaga. Mas CLICAR nele abre o painel dele — é como
     se espera editar algo que está na tela. O contorno no hover diz que é
     clicável; sem ele, o cliente não descobre. */
  .sf-canvas-header{position:relative;cursor:pointer;user-select:none}
  .sf-canvas-header *{pointer-events:none}
  .sf-canvas-header::before{
    content:'';position:absolute;inset:0;z-index:4;
    border:2px solid transparent;border-radius:4px;transition:border-color .12s ease;
  }
  .sf-canvas-header:hover::before{border-color:var(--sf-primary)}
  .sf-canvas-header::after{
    content:'Cabeçalho do site — clique para editar';
    position:absolute;top:6px;right:12px;z-index:5;opacity:0;transition:opacity .12s ease;
    padding:3px 8px;border-radius:999px;
    background:var(--sf-primary);color:var(--sf-on-primary);font-size:10px;font-weight:600;
  }
  .sf-canvas-header:hover::after{opacity:1}

  /* Área vazia: sem isto, uma página sem blocos é um iframe branco sem pista
     do que fazer. */
  .sf-canvas-empty{
    display:flex;flex-direction:column;gap:6px;align-items:center;justify-content:center;
    min-height:260px;margin:24px;padding:32px;
    border:2px dashed var(--sf-border);border-radius:var(--sf-radius-lg);
    color:var(--sf-muted-text);text-align:center;
  }
`

/** As `--sf-*` do tema do restaurante, como um bloco `:root`. */
function themeBlock(themeVariables: Record<string, string>): string {
  const tokens = Object.entries(themeVariables)
    .map(([name, value]) => `${name}:${value}`)
    .join(';')
  return tokens ? `:root{${tokens}}` : ''
}

export function canvasStylesheet(themeVariables: Record<string, string>): string {
  return [tokensCss, blocksCss, CANVAS_ONLY_CSS, themeBlock(themeVariables)].join('\n')
}
