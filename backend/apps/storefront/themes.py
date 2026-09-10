"""
Temas prontos do storefront.

Nenhum restaurante deve precisar escolher cor para ter um site apresentável. O
site nasce com o tema `DEFAULT_THEME_KEY` aplicado e uma página inicial já
montada (ver ``starter.py``): quem não quiser mexer em nada tem um cardápio
publicável no mesmo minuto em que a conta é criada; quem quiser, troca o preset
inteiro num clique e só depois ajusta token a token.

Cada preset traz o **conjunto completo** de tokens, nunca um subconjunto. Se um
preset omitisse `surfaceColor`, trocar de tema deixaria o valor do tema anterior
para trás e o resultado seria uma mistura que ninguém escolheu.

Os tokens viram variáveis CSS (`--sf-primary`, `--sf-surface`, …) no renderer e
no canvas do editor. As páginas usam `var(--sf-*)` nos estilos em vez de cores
literais — é o que faz uma troca de tema repintar o site inteiro sem tocar em
nenhuma página.

As chaves aqui precisam existir na allowlist de ``builder_schema.validate_theme``;
o que estiver fora dela é descartado ao salvar.
"""
import copy

DEFAULT_THEME_KEY = "market"

THEME_PRESETS = [
    {
        # O tema com que TODO site nasce. Verde escuro de mercado com destaque
        # amarelo: alto contraste no botão de ação, fundo branco para a foto do
        # produto aparecer, e cartão claro com borda fina — o padrão visual de
        # quem vende comida por catálogo.
        "key": "market",
        "name": "Mercado",
        "description": "Verde e amarelo, cartões claros e foto grande. O padrão para catálogo de produtos.",
        "tokens": {
            "mode": "light",
            "primaryColor": "#004D38",
            "secondaryColor": "#17231F",
            "accentColor": "#F6C928",
            # Fundo creme e superfície branca — é a inversão que dá o ar
            # "premium" da referência: o branco vira destaque em vez de base,
            # e os cartões saltam sem precisar de sombra nem borda.
            "backgroundColor": "#FAF7E8",
            "surfaceColor": "#FFFFFF",
            "textColor": "#17231F",
            "mutedTextColor": "#777F7B",
            "borderColor": "#ECEEEA",
            "fontFamily": "Inter, system-ui, sans-serif",
            "headingFontFamily": "Inter, system-ui, sans-serif",
            "borderRadius": "10px",
            "containerWidth": "1360px",
            "spacing": "24px",
            "buttonStyle": "rounded",
        },
    },
    {
        "key": "classic",
        "name": "Clássico",
        "description": "Fundo claro, vermelho apetitoso. Serve bem pizzaria, restaurante e marmitaria.",
        "tokens": {
            "mode": "light",
            "primaryColor": "#E53935",
            "secondaryColor": "#1F2933",
            "accentColor": "#FFB300",
            "backgroundColor": "#FFFFFF",
            "surfaceColor": "#F7F7F8",
            "textColor": "#1F2933",
            "mutedTextColor": "#6B7280",
            "borderColor": "#E5E7EB",
            "fontFamily": "Inter, system-ui, sans-serif",
            "headingFontFamily": "Inter, system-ui, sans-serif",
            "borderRadius": "12px",
            "containerWidth": "1200px",
            "spacing": "24px",
            "buttonStyle": "rounded",
        },
    },
    {
        "key": "dark",
        "name": "Noturno",
        "description": "Fundo escuro com destaque quente. Hamburgueria, pub e delivery noturno.",
        "tokens": {
            "mode": "dark",
            "primaryColor": "#FF6B35",
            "secondaryColor": "#F5F5F5",
            "accentColor": "#FFC947",
            "backgroundColor": "#0D0D0F",
            "surfaceColor": "#17171B",
            "textColor": "#F5F5F5",
            "mutedTextColor": "#A1A1AA",
            "borderColor": "#2A2A31",
            "fontFamily": "Inter, system-ui, sans-serif",
            "headingFontFamily": "Inter, system-ui, sans-serif",
            "borderRadius": "10px",
            "containerWidth": "1200px",
            "spacing": "24px",
            "buttonStyle": "rounded",
        },
    },
    {
        "key": "warm",
        "name": "Aconchegante",
        "description": "Tons de creme e madeira. Cafeteria, padaria e confeitaria.",
        "tokens": {
            "mode": "light",
            "primaryColor": "#B5651D",
            "secondaryColor": "#3E2C23",
            "accentColor": "#E5A663",
            "backgroundColor": "#FFFCF7",
            "surfaceColor": "#F6EFE6",
            "textColor": "#3E2C23",
            "mutedTextColor": "#8A7466",
            "borderColor": "#EADFD2",
            "fontFamily": "Inter, system-ui, sans-serif",
            "headingFontFamily": "Georgia, 'Times New Roman', serif",
            "borderRadius": "16px",
            "containerWidth": "1120px",
            "spacing": "28px",
            "buttonStyle": "pill",
        },
    },
    {
        "key": "fresh",
        "name": "Natural",
        "description": "Verde e branco. Comida saudável, açaí, saladeria e natural.",
        "tokens": {
            "mode": "light",
            "primaryColor": "#2E7D32",
            "secondaryColor": "#14281D",
            "accentColor": "#8BC34A",
            "backgroundColor": "#FFFFFF",
            "surfaceColor": "#F1F6F1",
            "textColor": "#14281D",
            "mutedTextColor": "#5F6F62",
            "borderColor": "#DDE7DD",
            "fontFamily": "Inter, system-ui, sans-serif",
            "headingFontFamily": "Inter, system-ui, sans-serif",
            "borderRadius": "14px",
            "containerWidth": "1200px",
            "spacing": "24px",
            "buttonStyle": "pill",
        },
    },
    {
        "key": "mono",
        "name": "Minimalista",
        "description": "Preto no branco, sem distração. Deixa a foto do prato falar.",
        "tokens": {
            "mode": "light",
            "primaryColor": "#111111",
            "secondaryColor": "#111111",
            "accentColor": "#555555",
            "backgroundColor": "#FFFFFF",
            "surfaceColor": "#FAFAFA",
            "textColor": "#111111",
            "mutedTextColor": "#767676",
            "borderColor": "#E6E6E6",
            "fontFamily": "Inter, system-ui, sans-serif",
            "headingFontFamily": "Inter, system-ui, sans-serif",
            "borderRadius": "4px",
            "containerWidth": "1080px",
            "spacing": "20px",
            "buttonStyle": "square",
        },
    },
]

# ── Cores derivadas ──────────────────────────────────────────────────────────
# Algumas cores viviam FIXAS no CSS dos blocos e escapavam do tema: o selo de
# promoção era sempre vermelho, o texto sobre o botão sempre branco, o botão do
# WhatsApp sempre verde, o cabeçalho sempre da cor da superfície. Trocar de
# preset repintava o site e deixava essas ilhas para trás.
#
# Agora fazem parte da paleta e são editáveis como qualquer outra. Mas o valor
# PADRÃO de cada uma é derivado do próprio preset, e não escrito preset a
# preset: um tema novo herda um conjunto coerente sem que ninguém precise
# lembrar de preencher sete campos a mais — que é exatamente como um preset
# nasceria com a cor errada.

# Convenções de mercado, iguais em todos os temas: vermelho de desconto e o
# verde da marca do WhatsApp. Ficam editáveis mesmo assim — quem quiser fugir
# da convenção, foge.
SALE_COLOR = "#D92D20"
WHATSAPP_COLOR = "#25D366"


def _derived_tokens(tokens):
    """Cores que saem das outras, para o preset não precisar repeti-las."""
    return {
        "saleColor": SALE_COLOR,
        "whatsappColor": WHATSAPP_COLOR,
        # Texto sobre as cores de ação. O primário é sempre escuro o bastante
        # para pedir texto branco; o destaque é sempre claro (amarelo, âmbar) e
        # pede o texto escuro do tema — branco sobre amarelo não se lê.
        "onPrimaryColor": "#FFFFFF",
        "onAccentColor": tokens["secondaryColor"],
        # O cabeçalho fica na cor da superfície e a faixa de aviso na
        # secundária: é o contraste que separa os dois níveis sem inventar cor.
        "headerBackgroundColor": tokens["surfaceColor"],
        "announcementBackgroundColor": tokens["secondaryColor"],
        "announcementTextColor": tokens["backgroundColor"],
    }


for _preset in THEME_PRESETS:
    # `setdefault`: um preset que QUEIRA fugir da derivação escreve o token
    # direto na sua lista e o valor dele é mantido.
    for _key, _value in _derived_tokens(_preset["tokens"]).items():
        _preset["tokens"].setdefault(_key, _value)


THEME_PRESETS_BY_KEY = {preset["key"]: preset for preset in THEME_PRESETS}
THEME_PRESET_KEYS = [preset["key"] for preset in THEME_PRESETS]


def theme_tokens(key=DEFAULT_THEME_KEY):
    """Cópia dos tokens de um preset (cai no default se a chave não existir).

    Cópia, e não a referência: o dicionário vai parar no JSONField de um site e
    ser editado token a token — devolver o objeto do módulo faria a edição de um
    cliente vazar para todos os sites criados depois, no mesmo processo.
    """
    preset = THEME_PRESETS_BY_KEY.get(key) or THEME_PRESETS_BY_KEY[DEFAULT_THEME_KEY]
    return copy.deepcopy(preset["tokens"])


def default_theme():
    return theme_tokens(DEFAULT_THEME_KEY)


def preset_key_for(theme):
    """Qual preset corresponde a estes tokens (ou "" se foi customizado)."""
    if not theme:
        return ""
    for preset in THEME_PRESETS:
        if all(theme.get(token) == value for token, value in preset["tokens"].items()):
            return preset["key"]
    return ""
