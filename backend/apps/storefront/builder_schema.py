"""
Contrato do JSON do editor de blocos — validação e sanitização no servidor.

O editor visual roda no navegador do cliente, então **nada** do que ele manda
é confiável: o payload chega por uma requisição HTTP comum e pode ser forjado
com curl. Este módulo é a fronteira. Ele recebe o `projectData` do editor e
devolve uma versão *reescrita* — não apenas aprovada — contendo somente o que
está explicitamente permitido aqui.

O que o módulo garante, e por quê:

- **Componentes conhecidos.** Um bloco de tipo desconhecido é recusado com o
  caminho exato onde apareceu. Sem isso, o editor viraria um canal para
  injetar qualquer HTML na página pública.
- **Sem script.** `<script>`, `<iframe>`, atributos `on*` e URLs `javascript:`
  são rejeitados. Uma página do storefront é servida no domínio do
  restaurante, para os clientes dele: um script arbitrário ali é XSS
  persistente contra o consumidor final.
- **Sem base64.** `data:` em `src`/`href` é recusado — imagem entra por
  `MenuAsset` (upload), que valida tipo e tamanho e sai por CDN.
- **Propriedades visuais fechadas.** O `style` aceita só a lista de
  propriedades de layout/aparência; `behavior`, `-moz-binding` e afins nunca
  chegam ao CSS publicado.
- **Tamanho limitado.** Profundidade, número de nós e bytes têm teto: um JSON
  patológico não pode derrubar a serialização nem o editor de quem abrir a
  página depois.

O front pode (e deve) validar também — mas a validação que vale é esta, porque
é a única que o atacante não controla.
"""
import json
import re
from html import escape
from html.parser import HTMLParser

from django.conf import settings

# ── Limites estruturais ──────────────────────────────────────────────────────
MAX_PROJECT_BYTES = getattr(settings, "STOREFRONT_MAX_PROJECT_BYTES", 2 * 1024 * 1024)
MAX_NODES = getattr(settings, "STOREFRONT_MAX_NODES", 5000)
MAX_DEPTH = getattr(settings, "STOREFRONT_MAX_DEPTH", 40)
MAX_STRING_LENGTH = 20000
MAX_ATTRIBUTE_LENGTH = 2000
MAX_STYLE_VALUE_LENGTH = 500

# ── Componentes que o storefront reconhece ───────────────────────────────────
# Tipos nativos do GrapesJS. `textnode` e `text` aparecem sozinhos quando o
# editor de texto rico quebra um parágrafo; `wrapper` é a raiz de toda página.
GRAPESJS_BUILTIN_COMPONENTS = {
    "wrapper",
    "text",
    "textnode",
}

# Componentes próprios do storefront. O prefixo `sf-` não é decoração: o
# GrapesJS tem um registro global de tipos, e um componente nosso chamado
# `section` ou `image` colidiria com o tipo nativo de mesmo nome — o editor
# passaria a tratar um pelo outro. O prefixo também deixa claro, ao ler um
# projeto salvo, o que é nosso e o que veio da biblioteca.
LAYOUT_COMPONENTS = {
    "sf-section",
    "sf-container",
    "sf-row",
    "sf-column",
    "sf-spacer",
    "sf-divider",
}
CONTENT_COMPONENTS = {
    "sf-heading",
    "sf-text",
    "sf-image",
    "sf-icon",
    "sf-button",
    "sf-link",
    "sf-list",
    "sf-social-links",
    # Elementos de vitrine reutilizáveis fora do card de produto: um selo
    # ("Mais vendido", "Congelado") e uma nota em estrelas podem aparecer
    # soltos numa seção de destaque, não só dentro da grade.
    "sf-badge",
    "sf-rating",
}
# Blocos "inteligentes": renderizam dados reais vindos da API pública. Eles
# guardam CONFIGURAÇÃO (categoria, nº de colunas), nunca cópia de produto.
DATA_COMPONENTS = {
    "sf-hero",
    "sf-banner",
    # Faixa fina no topo da página ("Frete grátis acima de R$ 200").
    "sf-announcement-bar",
    # Linha de filtros/ordenação acima da vitrine.
    "sf-filter-bar",
    "sf-categories",
    "sf-product-grid",
    "sf-product-carousel",
    "sf-featured-products",
    "sf-promotions",
    "sf-restaurant-info",
    "sf-opening-hours",
    "sf-delivery-info",
    "sf-payment-methods",
    "sf-search",
    "sf-cart-button",
    "sf-whatsapp-button",
    "sf-map",
    "sf-header",
    "sf-footer",
}
ALLOWED_COMPONENTS = (
    GRAPESJS_BUILTIN_COMPONENTS | LAYOUT_COMPONENTS | CONTENT_COMPONENTS | DATA_COMPONENTS
)

# `type` ausente é o caso mais comum no GrapesJS (um `div` puro). Tratado como
# "default" e aceito, desde que a tagName também seja permitida.
DEFAULT_COMPONENT_TYPE = "default"

ALLOWED_TAGS = {
    "div", "section", "article", "aside", "header", "footer", "nav", "main",
    "span", "p", "a", "button", "img", "figure", "figcaption", "picture",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "dl", "dt", "dd",
    "table", "thead", "tbody", "tr", "th", "td",
    "strong", "b", "em", "i", "u", "s", "small", "mark", "sub", "sup",
    "blockquote", "hr", "br", "label", "svg", "path", "g", "circle", "rect", "line", "polyline", "polygon",
}

# Tags que jamais podem entrar, nem no HTML de texto rico. `script`/`style` e
# companhia têm o conteúdo descartado junto (não só a tag).
FORBIDDEN_TAGS = {"script", "style", "iframe", "object", "embed", "link", "meta", "base", "form", "input", "textarea", "select", "option", "noscript", "template", "frame", "frameset", "applet"}

# ── Texto rico: o subconjunto de HTML que sobrevive à sanitização ────────────
RICH_TEXT_TAGS = {
    "p", "br", "span", "strong", "b", "em", "i", "u", "s", "small", "mark",
    "sub", "sup", "a", "ul", "ol", "li", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6", "div",
}
RICH_TEXT_ATTRIBUTES = {
    "a": {"href", "title", "target", "rel"},
    "*": {"class", "id", "title"},
}
VOID_TAGS = {"br", "hr", "img"}

# ── Atributos aceitos nos componentes ────────────────────────────────────────
ALLOWED_ATTRIBUTES = {
    "id", "class", "title", "alt", "href", "src", "srcset", "sizes", "target",
    "rel", "type", "role", "loading", "decoding", "width", "height",
    "viewBox", "fill", "stroke", "stroke-width", "d", "points", "x", "y",
    "cx", "cy", "r", "x1", "x2", "y1", "y2", "xmlns", "preserveAspectRatio",
}
ATTRIBUTE_PREFIXES = ("data-", "aria-")
URL_ATTRIBUTES = {"href", "src", "srcset", "poster", "action"}

SAFE_URL_SCHEMES = {"http", "https", "mailto", "tel", "whatsapp"}
_SCHEME_RE = re.compile(r"^\s*([a-z][a-z0-9+.-]*)\s*:", re.IGNORECASE)
# `on*` cobre onclick, onerror, onload… Tratado por prefixo porque a lista de
# handlers do HTML cresce a cada versão da spec.
_EVENT_ATTRIBUTE_RE = re.compile(r"^on", re.IGNORECASE)
_ATTRIBUTE_NAME_RE = re.compile(r"^[A-Za-z_:][A-Za-z0-9_.:-]*$")
_CLASS_RE = re.compile(r"^[A-Za-z0-9_\- ]{0,200}$")
_SELECTOR_RE = re.compile(r"^[A-Za-z0-9_\-.#>~+*:\[\]='\"() ,%]{0,500}$")
_MEDIA_RE = re.compile(r"^[A-Za-z0-9_\-.:()\s,<>=]{0,300}$")
_PROP_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,60}$")
# Construções de CSS que executam código ou puxam recurso externo arbitrário.
_CSS_FORBIDDEN_RE = re.compile(
    r"(expression\s*\(|javascript\s*:|vbscript\s*:|@import|behavior\s*:|-moz-binding|</)",
    re.IGNORECASE,
)

# ── Propriedades visuais permitidas no `style` ───────────────────────────────
ALLOWED_STYLE_PROPERTIES = {
    # dimensões
    "width", "max-width", "min-width", "height", "max-height", "min-height", "aspect-ratio",
    # espaçamento
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left", "gap",
    "row-gap", "column-gap",
    # layout
    "display", "flex-direction", "flex-wrap", "flex", "flex-grow", "flex-shrink", "flex-basis",
    "justify-content", "align-items", "align-self", "align-content", "order",
    "grid-template-columns", "grid-template-rows", "grid-column", "grid-row", "grid-auto-flow",
    "position", "top", "right", "bottom", "left", "z-index", "overflow", "overflow-x", "overflow-y",
    "float", "clear", "visibility",
    # fundo e borda
    "background", "background-color", "background-image", "background-size",
    "background-position", "background-repeat", "background-attachment",
    "border", "border-top", "border-right", "border-bottom", "border-left",
    "border-color", "border-width", "border-style", "border-radius",
    "border-top-left-radius", "border-top-right-radius",
    "border-bottom-left-radius", "border-bottom-right-radius",
    "box-shadow", "outline",
    # tipografia
    "color", "font-family", "font-size", "font-weight", "font-style",
    "line-height", "letter-spacing", "word-spacing", "text-align", "text-decoration",
    "text-transform", "text-shadow", "white-space", "word-break", "text-overflow",
    "list-style", "list-style-type",
    # imagem e efeitos
    "object-fit", "object-position", "opacity", "filter", "mix-blend-mode",
    "transform", "transform-origin", "transition", "animation", "cursor",
    "pointer-events", "user-select",
}


def _kebab(name):
    """`backgroundColor` → `background-color` (o editor emite os dois formatos)."""
    return re.sub(r"(?<!^)(?=[A-Z])", "-", str(name)).lower()


class BuilderValidationError(Exception):
    """Payload do editor recusado. `errors` traz {caminho: motivo}."""

    def __init__(self, errors):
        self.errors = errors if isinstance(errors, dict) else {"builder": str(errors)}
        super().__init__(self.errors)


class _HtmlSanitizer(HTMLParser):
    """Reescreve HTML mantendo apenas tags/atributos do subconjunto de texto rico.

    Tags fora da lista perdem a marcação mas mantêm o texto (um `<marquee>`
    vira o texto que estava dentro dele); as de `FORBIDDEN_TAGS` perdem também
    o conteúdo, senão o corpo de um `<script>` reapareceria como texto visível.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.open_tags = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in FORBIDDEN_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag not in RICH_TEXT_TAGS:
            return
        allowed = RICH_TEXT_ATTRIBUTES.get(tag, set()) | RICH_TEXT_ATTRIBUTES["*"]
        rendered = []
        for name, value in attrs:
            name = (name or "").lower()
            if name not in allowed or _EVENT_ATTRIBUTE_RE.match(name):
                continue
            value = "" if value is None else str(value)[:MAX_ATTRIBUTE_LENGTH]
            if name == "href":
                if not is_safe_url(value):
                    continue
            rendered.append(f'{name}="{escape(value, quote=True)}"')
        # Link que abre em outra aba sem `noopener` dá à página de destino
        # acesso ao `window.opener` da loja — daí a adição automática.
        if tag == "a" and any(part.startswith('target="_blank"') for part in rendered):
            if not any(part.startswith("rel=") for part in rendered):
                rendered.append('rel="noopener noreferrer"')
        attributes = (" " + " ".join(rendered)) if rendered else ""
        if tag in VOID_TAGS:
            self.parts.append(f"<{tag}{attributes} />")
            return
        self.parts.append(f"<{tag}{attributes}>")
        self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in FORBIDDEN_TAGS or self.skip_depth:
            return
        if tag in RICH_TEXT_TAGS:
            self.handle_starttag(tag, attrs)
            if self.open_tags and self.open_tags[-1] == tag:
                self.open_tags.pop()
                self.parts.append(f"</{tag}>")

    def handle_endtag(self, tag):
        if tag in FORBIDDEN_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag in self.open_tags:
            while self.open_tags:
                current = self.open_tags.pop()
                self.parts.append(f"</{current}>")
                if current == tag:
                    break

    def handle_data(self, data):
        if self.skip_depth:
            return
        self.parts.append(escape(data, quote=False))

    def handle_comment(self, data):
        """Comentário é descartado: `<!--[if IE]><script>` é um vetor clássico."""

    def handle_entityref(self, name):
        if not self.skip_depth:
            self.parts.append(f"&{name};")

    def handle_charref(self, name):
        if not self.skip_depth:
            self.parts.append(f"&#{name};")

    def result(self):
        while self.open_tags:
            self.parts.append(f"</{self.open_tags.pop()}>")
        return "".join(self.parts)


def sanitize_html(value):
    """Devolve o HTML reescrito com o subconjunto seguro de texto rico."""
    if not value:
        return ""
    parser = _HtmlSanitizer()
    parser.feed(str(value)[:MAX_STRING_LENGTH])
    parser.close()
    return parser.result()


def is_safe_url(value):
    """True para http(s)/mailto/tel, caminho relativo, âncora ou querystring.

    Sem esquema conhecido → é relativo, e relativo é sempre seguro. Com
    esquema fora da lista (`javascript:`, `data:`, `file:`) → recusado.
    """
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return True
    # `\n`/`\t` no meio do esquema são ignorados pelos navegadores, que ainda
    # assim executam `java\nscript:alert(1)`. Normalizamos antes de olhar.
    normalized = re.sub(r"[\s\x00-\x1f]", "", text)
    match = _SCHEME_RE.match(normalized)
    if not match:
        return True
    return match.group(1).lower() in SAFE_URL_SCHEMES


def sanitize_url(value):
    """URL segura, ou string vazia. Nunca levanta — o campo simplesmente esvazia."""
    return str(value).strip()[:MAX_ATTRIBUTE_LENGTH] if is_safe_url(value) else ""


def sanitize_style(style, path, errors):
    """Filtra o dicionário de estilo pela lista de propriedades permitidas."""
    if not isinstance(style, dict):
        return {}
    clean = {}
    for raw_name, raw_value in style.items():
        name = _kebab(raw_name)
        if name not in ALLOWED_STYLE_PROPERTIES:
            # Propriedade fora da lista é descartada em silêncio: o editor
            # emite muita coisa cosmética e derrubar o salvamento inteiro por
            # causa de uma delas seria hostil com quem está editando.
            continue
        if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
            clean[name] = raw_value
            continue
        if not isinstance(raw_value, str):
            continue
        value = raw_value.strip()[:MAX_STYLE_VALUE_LENGTH]
        if _CSS_FORBIDDEN_RE.search(value):
            errors[f"{path}.style.{name}"] = "Valor de CSS não permitido."
            continue
        for url in re.findall(r"url\(\s*['\"]?([^'\")]+)", value, re.IGNORECASE):
            if not is_safe_url(url):
                errors[f"{path}.style.{name}"] = "URL não permitida em CSS."
                break
        else:
            clean[name] = value
    return clean


def _sanitize_props(value, path, errors, depth=0):
    """Configuração do bloco: JSON simples, sem HTML e com profundidade limitada."""
    if depth > 6:
        errors[path] = "Configuração do bloco aninhada demais."
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return escape(value[:MAX_ATTRIBUTE_LENGTH], quote=False)
    if isinstance(value, list):
        return [_sanitize_props(item, f"{path}[{i}]", errors, depth + 1) for i, item in enumerate(value[:200])]
    if isinstance(value, dict):
        clean = {}
        for key, item in list(value.items())[:100]:
            if not _PROP_KEY_RE.match(str(key)):
                continue
            clean[str(key)] = _sanitize_props(item, f"{path}.{key}", errors, depth + 1)
        return clean
    errors[path] = "Tipo de valor não suportado na configuração do bloco."
    return None


def _sanitize_attributes(attributes, path, errors):
    if not isinstance(attributes, dict):
        return {}
    clean = {}
    for raw_name, raw_value in attributes.items():
        name = str(raw_name)
        if _EVENT_ATTRIBUTE_RE.match(name):
            errors[f"{path}.attributes.{name}"] = "Handler de evento não é permitido."
            continue
        if not _ATTRIBUTE_NAME_RE.match(name):
            continue
        if name not in ALLOWED_ATTRIBUTES and not name.startswith(ATTRIBUTE_PREFIXES):
            continue
        if isinstance(raw_value, bool) or raw_value is None:
            clean[name] = raw_value
            continue
        if isinstance(raw_value, (int, float)):
            clean[name] = raw_value
            continue
        value = str(raw_value)[:MAX_ATTRIBUTE_LENGTH]
        if name in URL_ATTRIBUTES:
            if not is_safe_url(value):
                errors[f"{path}.attributes.{name}"] = "URL não permitida (use http, https, mailto, tel ou caminho relativo)."
                continue
        elif name == "style":
            continue
        clean[name] = value
    return clean


class _Counter:
    def __init__(self):
        self.nodes = 0


def _sanitize_component(node, path, errors, counter, depth=0):
    if depth > MAX_DEPTH:
        errors[path] = "Estrutura de blocos profunda demais."
        return None
    if isinstance(node, str):
        # O GrapesJS aceita um filho como string pura (texto).
        return sanitize_html(node)
    if not isinstance(node, dict):
        errors[path] = "Bloco inválido."
        return None

    counter.nodes += 1
    if counter.nodes > MAX_NODES:
        errors["builder"] = f"A página excede o limite de {MAX_NODES} blocos."
        return None

    component_type = node.get("type") or DEFAULT_COMPONENT_TYPE
    if component_type != DEFAULT_COMPONENT_TYPE and component_type not in ALLOWED_COMPONENTS:
        errors[path] = f"Bloco não suportado: '{component_type}'."
        return None

    tag_name = str(node.get("tagName") or "").lower()
    if tag_name:
        if tag_name in FORBIDDEN_TAGS:
            errors[f"{path}.tagName"] = f"Tag não permitida: '{tag_name}'."
            return None
        if tag_name not in ALLOWED_TAGS:
            errors[f"{path}.tagName"] = f"Tag não suportada: '{tag_name}'."
            return None

    clean = {"type": component_type}
    if tag_name:
        clean["tagName"] = tag_name

    if node.get("name"):
        clean["name"] = escape(str(node["name"])[:150], quote=False)

    classes = node.get("classes")
    if isinstance(classes, list):
        clean_classes = []
        for item in classes[:50]:
            # O GrapesJS grava a classe ora como string, ora como
            # {"name": "...", "private": false}.
            name = item.get("name") if isinstance(item, dict) else item
            name = str(name or "")
            if _CLASS_RE.match(name):
                clean_classes.append(name)
        if clean_classes:
            clean["classes"] = clean_classes

    attributes = _sanitize_attributes(node.get("attributes"), path, errors)
    if attributes:
        clean["attributes"] = attributes

    style = sanitize_style(node.get("style"), path, errors)
    if style:
        clean["style"] = style

    if "content" in node and node["content"] is not None:
        clean["content"] = sanitize_html(node["content"])

    if "props" in node and node["props"] is not None:
        props = _sanitize_props(node["props"], f"{path}.props", errors)
        if props is not None:
            clean["props"] = props

    # Flags de edição do próprio GrapesJS: booleanos, sem risco.
    for flag in ("removable", "draggable", "droppable", "badgable", "stylable", "highlightable", "copyable", "selectable", "editable", "layerable", "hoverable", "void"):
        if isinstance(node.get(flag), bool):
            clean[flag] = node[flag]

    children = node.get("components")
    if isinstance(children, list):
        clean_children = []
        for index, child in enumerate(children):
            sanitized = _sanitize_component(child, f"{path}.components[{index}]", errors, counter, depth + 1)
            if sanitized is not None:
                clean_children.append(sanitized)
        clean["components"] = clean_children

    return clean


def _sanitize_style_rules(rules, errors):
    if not isinstance(rules, list):
        return []
    clean_rules = []
    for index, rule in enumerate(rules[:2000]):
        if not isinstance(rule, dict):
            continue
        path = f"styles[{index}]"
        selectors = []
        for selector in (rule.get("selectors") or [])[:20]:
            name = selector.get("name") if isinstance(selector, dict) else selector
            name = str(name or "")
            if _SELECTOR_RE.match(name):
                selectors.append(name)
        selectors_add = str(rule.get("selectorsAdd") or "")[:500]
        if selectors_add and not _SELECTOR_RE.match(selectors_add):
            selectors_add = ""
        media = str(rule.get("mediaText") or "")[:300]
        if media and not _MEDIA_RE.match(media):
            media = ""
        style = sanitize_style(rule.get("style"), path, errors)
        if not style:
            continue
        clean_rule = {"selectors": selectors, "style": style}
        if selectors_add:
            clean_rule["selectorsAdd"] = selectors_add
        if media:
            clean_rule["mediaText"] = media
        if isinstance(rule.get("state"), str) and _SELECTOR_RE.match(rule["state"]):
            clean_rule["state"] = rule["state"]
        clean_rules.append(clean_rule)
    return clean_rules


def _sanitize_assets(assets):
    if not isinstance(assets, list):
        return []
    clean = []
    for asset in assets[:500]:
        if isinstance(asset, str):
            url = sanitize_url(asset)
            if url:
                clean.append(url)
            continue
        if not isinstance(asset, dict):
            continue
        url = sanitize_url(asset.get("src"))
        if not url:
            continue
        entry = {"type": "image", "src": url}
        if asset.get("name"):
            entry["name"] = escape(str(asset["name"])[:200], quote=False)
        for numeric in ("width", "height"):
            if isinstance(asset.get(numeric), (int, float)):
                entry[numeric] = asset[numeric]
        clean.append(entry)
    return clean


def _sanitize_page(page, index, errors, counter):
    if not isinstance(page, dict):
        errors[f"pages[{index}]"] = "Página inválida."
        return None
    clean = {}
    if page.get("id"):
        clean["id"] = str(page["id"])[:80]
    if page.get("name"):
        clean["name"] = escape(str(page["name"])[:150], quote=False)
    frames = page.get("frames")
    clean_frames = []
    if isinstance(frames, list):
        for frame_index, frame in enumerate(frames[:10]):
            if not isinstance(frame, dict):
                continue
            component = frame.get("component")
            path = f"pages[{index}].frames[{frame_index}].component"
            sanitized = _sanitize_component(component, path, errors, counter) if component is not None else None
            clean_frame = {}
            if frame.get("id"):
                clean_frame["id"] = str(frame["id"])[:80]
            if sanitized is not None:
                clean_frame["component"] = sanitized
            clean_frames.append(clean_frame)
    clean["frames"] = clean_frames
    return clean


def validate_project_data(data):
    """Valida e devolve o `projectData` reescrito, pronto para persistir.

    Levanta ``BuilderValidationError`` quando o payload contém algo proibido —
    componente desconhecido, tag bloqueada, `javascript:`, tamanho acima do
    teto. Coisas meramente desconhecidas e inofensivas (uma propriedade de CSS
    fora da lista, um atributo cosmético) são descartadas em silêncio.
    """
    if data in (None, "", {}):
        return {}
    if not isinstance(data, dict):
        raise BuilderValidationError({"builder": "O conteúdo do editor deve ser um objeto JSON."})

    try:
        raw_size = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise BuilderValidationError({"builder": f"Conteúdo do editor não serializável: {exc}"}) from exc
    if raw_size > MAX_PROJECT_BYTES:
        raise BuilderValidationError(
            {"builder": f"O conteúdo da página tem {raw_size} bytes e o limite é {MAX_PROJECT_BYTES}."}
        )

    errors = {}
    counter = _Counter()
    clean = {}

    pages = data.get("pages")
    if isinstance(pages, list):
        clean_pages = []
        for index, page in enumerate(pages[:50]):
            sanitized = _sanitize_page(page, index, errors, counter)
            if sanitized is not None:
                clean_pages.append(sanitized)
        clean["pages"] = clean_pages
    else:
        clean["pages"] = []

    clean["styles"] = _sanitize_style_rules(data.get("styles"), errors)
    clean["assets"] = _sanitize_assets(data.get("assets"))

    # Metadados do nosso editor (tema aplicado, versão do schema). Passa pelo
    # mesmo saneamento de props.
    if isinstance(data.get("meta"), dict):
        meta = _sanitize_props(data["meta"], "meta", errors)
        if meta:
            clean["meta"] = meta

    if errors:
        raise BuilderValidationError(errors)
    return clean


def validate_theme(theme):
    """Tema global do site: só chaves conhecidas, e cada valor é texto curto."""
    if not theme:
        return {}
    if not isinstance(theme, dict):
        raise BuilderValidationError({"theme": "O tema deve ser um objeto JSON."})
    allowed = {
        "primaryColor", "secondaryColor", "accentColor", "backgroundColor",
        "surfaceColor", "textColor", "mutedTextColor", "borderColor",
        # Cores que antes estavam FIXAS no CSS dos blocos e por isso escapavam
        # do tema: o selo de promoção era sempre vermelho, o texto sobre o
        # botão sempre branco, o WhatsApp sempre verde. Trocar de preset
        # repintava o site e deixava essas ilhas para trás.
        "saleColor", "onPrimaryColor", "onAccentColor", "whatsappColor",
        # O cabeçalho tem fundo próprio (dele e da faixa de aviso) para poder
        # contrastar com o corpo da página — mas sai da MESMA paleta, e não de
        # valores soltos no CSS.
        "headerBackgroundColor", "announcementBackgroundColor", "announcementTextColor",
        "fontFamily", "headingFontFamily", "borderRadius", "containerWidth",
        "spacing", "buttonStyle", "mode", "logoUrl", "faviconUrl",
    }
    clean = {}
    errors = {}
    for key, value in theme.items():
        if key not in allowed:
            continue
        if value is None:
            continue
        text = str(value).strip()[:200]
        if _CSS_FORBIDDEN_RE.search(text):
            errors[f"theme.{key}"] = "Valor não permitido."
            continue
        if key in {"logoUrl", "faviconUrl"}:
            text = sanitize_url(text)
        clean[key] = text
    if errors:
        raise BuilderValidationError(errors)
    return clean


def validate_header(header):
    """Configuracao do cabecalho do site — global, nao um bloco da pagina.

    O cabecalho e o unico elemento que aparece em TODAS as paginas e que o
    restaurante nao pode apagar sem querer: por isso mora no site
    (`MenuSite.header`), e nao numa arvore de blocos que um clique errado
    remove. O que ele mostra continua configuravel — so o "existir" e que nao
    esta em disputa.

    A navegacao vem de um MENU (pelo handle), nao de uma lista escrita aqui:
    assim o restaurante monta o menu uma vez, com submenus, e reaproveita a
    mesma lista no rodape ou numa vitrine.
    """
    if not header:
        return {}
    if not isinstance(header, dict):
        raise BuilderValidationError({"header": "A configuracao do cabecalho deve ser um objeto JSON."})

    def text(value, limit=180):
        return escape(str(value or "")[:limit], quote=False)

    announcement = header.get("announcement") or {}
    location = header.get("location") or {}
    search = header.get("search") or {}
    actions = header.get("actions") or {}

    clean = {
        "sticky": bool(header.get("sticky", True)),
        "brand_name": text(header.get("brand_name"), 80),
        "logo_url": sanitize_url(header.get("logo_url")),
        "announcement": {
            "enabled": bool(announcement.get("enabled", True)),
            "text": text(announcement.get("text"), 200),
            # Trecho em amarelo dentro da faixa (ex.: o "20% OFF").
            "highlight": text(announcement.get("highlight"), 60),
            "secondary": text(announcement.get("secondary"), 200),
            "url": sanitize_url(announcement.get("url")),
        },
        "location": {
            "enabled": bool(location.get("enabled", True)),
            "label": text(location.get("label"), 40) or "Entregar em",
            "value": text(location.get("value"), 80),
        },
        "search": {
            "enabled": bool(search.get("enabled", True)),
            "placeholder": text(search.get("placeholder"), 120) or "Buscar produtos e categorias",
        },
        "actions": {
            "cart": bool(actions.get("cart", True)),
            # `profile`, e nao `account`: o TenantResponseSafetyMiddleware trata
            # QUALQUER chave `account` do corpo como marcador de conta e, ao ver
            # um `true` onde esperava um id, bloqueia a resposta inteira como
            # vazamento entre tenants. O nome aqui e barato de trocar; a regra
            # do middleware protege o sistema todo e nao deve ser afrouxada.
            "profile": bool(actions.get("profile", True)),
            # Como as acoes aparecem: so o icone (o circulo colorido), icone
            # com rotulo ao lado, ou so o texto. Uma lista fechada, e nao texto
            # livre, porque cada valor tem um layout proprio no CSS — um valor
            # desconhecido cairia num botao sem estilo nenhum.
            "display": (
                actions.get("display")
                if actions.get("display") in {"icon", "icon_text", "text"}
                else "icon"
            ),
            "cart_label": text(actions.get("cart_label"), 30) or "Carrinho",
            "profile_label": text(actions.get("profile_label"), 30) or "Entrar",
        },
        # Handles de `menu.Menu`. O payload publico entrega os menus resolvidos
        # em `menus`, indexados por handle — o cabecalho so aponta.
        "nav_menu": text(header.get("nav_menu"), 140),
        "secondary_menu": text(header.get("secondary_menu"), 140),
    }
    return clean


def validate_seo(seo):
    """SEO da página/site: texto puro, sem HTML, com URLs validadas."""
    if not seo:
        return {}
    if not isinstance(seo, dict):
        raise BuilderValidationError({"seo": "O SEO deve ser um objeto JSON."})
    clean = {}
    if seo.get("title") is not None:
        clean["title"] = escape(str(seo["title"])[:180], quote=False)
    if seo.get("description") is not None:
        clean["description"] = escape(str(seo["description"])[:400], quote=False)
    if seo.get("keywords") is not None:
        keywords = seo["keywords"]
        if isinstance(keywords, (list, tuple)):
            keywords = ", ".join(str(item) for item in keywords)
        clean["keywords"] = escape(str(keywords)[:300], quote=False)
    for url_key in ("og_image", "canonical_url"):
        if seo.get(url_key):
            url = sanitize_url(seo[url_key])
            if url:
                clean[url_key] = url
    if "index" in seo:
        clean["index"] = bool(seo["index"])
    return clean
