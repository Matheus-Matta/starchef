"""
Provisionamento do site: todo restaurante nasce com cardápio no ar.

A regra é uma só — **nunca entregar um site vazio**. Um restaurante que abre o
editor e encontra uma tela em branco não monta cardápio nenhum; ele fecha a
aba. Então, no momento em que o site passa a existir, ele já vem com:

- o tema padrão aplicado (``themes.DEFAULT_THEME_KEY``);
- uma home montada com cabeçalho, capa, categorias, vitrine, horários e rodapé
  (``starter.build_starter_page``);
- essa home **publicada**, para que o endereço público funcione na hora.

Publicar de saída é deliberado: a alternativa (nascer como rascunho) faria o
link do cardápio devolver "página não encontrada" até alguém clicar em
publicar, e é justamente o cliente que não quer mexer em nada que sofreria com
isso. Nada aqui é irreversível — `unpublish` tira do ar quando quiser.

Tudo é idempotente: chamar duas vezes não duplica site nem página.
"""
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.core.modules import MODULE_ECOMMERCE
from apps.menu.services.default_menus import ensure_default_menus
from apps.storefront.builder_schema import validate_header, validate_project_data, validate_seo
from apps.storefront.models import MenuPage, MenuSite
from apps.storefront.starter import build_starter_page, default_header, starter_seo
from apps.storefront.themes import DEFAULT_THEME_KEY, theme_tokens

HOME_SLUG = "home"


def unique_site_slug(restaurant):
    """Slug livre a partir do nome fantasia (`pizzaria-italia`, `-2`, `-3`…).

    O slug é global — é o endereço público e o rótulo do subdomínio —, então
    dois restaurantes com o mesmo nome fantasia, ainda que de contas
    diferentes, não podem receber o mesmo.
    """
    base = slugify(restaurant.trade_name or restaurant.legal_name or "cardapio")[:120] or "cardapio"
    candidate = base
    suffix = 2
    while MenuSite.all_objects.filter(slug=candidate).exists():
        candidate = f"{base}-{suffix}"[:140]
        suffix += 1
    return candidate


@transaction.atomic
def ensure_site(restaurant, *, user=None, theme_key=DEFAULT_THEME_KEY, publish=True):
    """Cria (ou completa) o site do restaurante. Devolve o ``MenuSite``.

    Idempotente: se o site já existe, apenas preenche o que estiver faltando —
    tema vazio ganha o padrão, e um site sem nenhuma página ganha a home.
    """
    site = MenuSite.all_objects.filter(restaurant=restaurant).first()
    created = site is None

    if created:
        site = MenuSite.all_objects.create(
            account=restaurant.account,
            restaurant=restaurant,
            name=restaurant.trade_name or "",
            slug=unique_site_slug(restaurant),
            theme=theme_tokens(theme_key),
            theme_preset=theme_key,
            seo=validate_seo(starter_seo(restaurant.trade_name)),
            header=validate_header(default_header(restaurant.trade_name)),
            created_by=user if getattr(user, "is_authenticated", False) else None,
            updated_by=user if getattr(user, "is_authenticated", False) else None,
        )
    else:
        changed = []
        if not site.theme:
            site.theme = theme_tokens(theme_key)
            site.theme_preset = theme_key
            changed += ["theme", "theme_preset"]
        else:
            # Tema JÁ existe, mas pode estar incompleto: quando a paleta ganha
            # tokens novos (o selo de promoção, o fundo do cabeçalho), os sites
            # criados antes ficam sem eles — e o seletor de cor do painel abre
            # em preto, como se o cliente tivesse escolhido preto.
            #
            # Completa pelo preset DO PRÓPRIO site, não pelo padrão: um site
            # vermelho não deve herdar o verde do tema padrão só porque faltava
            # um token. Nada do que já está escolhido é tocado.
            reference = theme_tokens(site.theme_preset or theme_key)
            missing = {key: value for key, value in reference.items() if key not in site.theme}
            if missing:
                site.theme = {**site.theme, **missing}
                changed.append("theme")
        if not site.seo:
            site.seo = validate_seo(starter_seo(restaurant.trade_name))
            changed.append("seo")
        if not site.header:
            site.header = validate_header(default_header(restaurant.trade_name))
            changed.append("header")
        else:
            # Mesmo caso do tema: quando o cabeçalho ganha um campo novo (o modo
            # de exibição das ações, por exemplo), os sites criados antes ficam
            # sem ele. `validate_header` já preenche todo campo ausente com o
            # padrão, então basta passar o que está salvo por ele — o que o
            # cliente escolheu é mantido, só o que falta entra.
            completed = validate_header(site.header)
            if completed != site.header:
                site.header = completed
                changed.append("header")
        if changed:
            site.save(update_fields=[*changed, "updated_at"])

    # Menus padrao junto com o site: sem eles, todo bloco que pede um menu
    # ofereceria uma lista vazia, e o cliente teria de entender o conceito
    # antes de conseguir ver um carrossel na home.
    ensure_default_menus(restaurant, user=user)

    ensure_home_page(site, user=user, publish=publish)
    return site


def ensure_home_page(site, *, user=None, publish=True):
    """Garante uma home para o site. Não toca em site que já tem página."""
    if MenuPage.all_objects.filter(site=site, deleted_at__isnull=True).exists():
        return None

    restaurant_name = site.name or site.restaurant.trade_name
    content = validate_project_data(build_starter_page(restaurant_name))
    now = timezone.now()
    author = user if getattr(user, "is_authenticated", False) else None

    page = MenuPage.all_objects.create(
        account=site.account,
        restaurant=site.restaurant,
        site=site,
        title="Home",
        slug=HOME_SLUG,
        is_home=True,
        draft_data=content,
        # Publicada de saída: o endereço público precisa funcionar antes de
        # alguém abrir o editor pela primeira vez.
        published_data=content if publish else {},
        status=MenuPage.STATUS_PUBLISHED if publish else MenuPage.STATUS_DRAFT,
        published_at=now if publish else None,
        published_by=author,
        seo=validate_seo(starter_seo(restaurant_name)),
        created_by=author,
        updated_by=author,
    )

    if publish and site.published_at is None:
        site.published_at = now
        site.save(update_fields=["published_at", "updated_at"])

    return page


def account_has_storefront(account):
    return bool(account and account.has_module(MODULE_ECOMMERCE))
