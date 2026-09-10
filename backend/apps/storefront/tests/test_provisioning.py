"""Tema inicial e home padrão: nenhum cliente começa com um site em branco."""
import pytest
from django.core.management import call_command

from apps.restaurants.models import Restaurant
from apps.storefront.models import MenuPage, MenuSite
from apps.storefront.services.provisioning import ensure_site
from apps.storefront.themes import DEFAULT_THEME_KEY, THEME_PRESETS_BY_KEY, theme_tokens

pytestmark = pytest.mark.django_db


def _new_restaurant(account, name="Pizzaria Itália", cnpj="11222333000181"):
    return Restaurant.objects.create(
        account=account, legal_name=f"{name} LTDA", trade_name=name, cnpj=cnpj
    )


# ── Tema padrão ──────────────────────────────────────────────────────────────


def test_site_provisionado_nasce_com_o_cabecalho_configurado(ecommerce_account):
    """O cabeçalho é do site: existe desde o primeiro minuto e já com navegação.

    Aponta para `categorias`, e não para `navegacao-principal`: o menu de
    navegação nasce manual e VAZIO, então o site novo abriria sem o terceiro
    nível do cabeçalho. As categorias são dinâmicas e já têm conteúdo.
    """
    site = ensure_site(_new_restaurant(ecommerce_account, "Com Cabecalho", "11222333001324"))

    assert site.header["announcement"]["enabled"] is True
    assert site.header["nav_menu"] == "categorias"
    assert site.header["search"]["placeholder"]
    # `profile`, nunca `account` — ver builder_schema.validate_header.
    assert "account" not in site.header["actions"]


def test_site_provisionado_nasce_com_o_tema_padrao_completo(ecommerce_account):
    restaurant = _new_restaurant(ecommerce_account)
    site = ensure_site(restaurant)

    assert site.theme_preset == DEFAULT_THEME_KEY
    # Conjunto COMPLETO de tokens: um preset parcial deixaria buracos que a
    # troca de tema não conseguiria preencher depois.
    assert site.theme == theme_tokens(DEFAULT_THEME_KEY)
    assert site.theme["primaryColor"]
    assert site.theme["backgroundColor"]
    assert site.theme["fontFamily"]


def test_site_provisionado_nasce_com_home_publicada(ecommerce_account):
    restaurant = _new_restaurant(ecommerce_account, "Cantina Roma", "11222333000262")
    site = ensure_site(restaurant)

    home = MenuPage.all_objects.get(site=site, is_home=True)
    assert home.status == MenuPage.STATUS_PUBLISHED
    assert home.published_at is not None
    assert home.published_data == home.draft_data
    # A home traz o nome do restaurante e os blocos que fazem um cardápio.
    content = str(home.published_data)
    assert "Cantina Roma" in content
    for block in ("sf-hero", "sf-categories", "sf-product-grid", "sf-footer"):
        assert block in content
    # Cabeçalho e faixa de aviso NÃO são blocos da página: são do site, para
    # que um clique errado no editor não os apague.
    assert "sf-header" not in content


def test_capa_padrao_nao_leva_html_no_titulo(ecommerce_account):
    """O nome do restaurante vai em `highlight`, não em `<em>` dentro do título.

    A capa renderiza texto puro. Um `<em>` no título passaria pelo saneamento
    de props ESCAPADO e o visitante leria `&lt;em&gt;` na tela — o destaque
    tem prop própria justamente por isso.
    """
    site = ensure_site(_new_restaurant(ecommerce_account, "Cantina Napoli", "11222333000424"))
    home = MenuPage.all_objects.get(site=site, is_home=True)
    hero = next(
        block
        for block in home.published_data["pages"][0]["frames"][0]["component"]["components"]
        if block.get("type") == "sf-hero"
    )

    assert hero["props"]["highlight"] == "Cantina Napoli"
    assert "<" not in hero["props"]["title"]
    assert "&lt;" not in hero["props"]["title"]


def test_paleta_cobre_o_que_antes_era_cor_fixa_no_css(ecommerce_account):
    """Nada de cor de site fora do tema.

    O selo de promoção, o texto sobre o botão, o botão do WhatsApp e o fundo do
    cabeçalho viviam FIXOS no CSS dos blocos. Trocar de preset repintava o site
    e deixava essas ilhas para trás — um selo vermelho num tema azul. Agora são
    tokens como os outros, e todo preset precisa trazê-los.
    """
    from apps.storefront.themes import THEME_PRESETS

    esperados = {
        "saleColor", "onPrimaryColor", "onAccentColor", "whatsappColor",
        "headerBackgroundColor", "announcementBackgroundColor", "announcementTextColor",
    }

    for preset in THEME_PRESETS:
        faltando = esperados - set(preset["tokens"])
        assert not faltando, f"preset {preset['key']} sem: {faltando}"

    site = ensure_site(_new_restaurant(ecommerce_account, "Paleta Cheia", "11222333000505"))
    assert esperados <= set(site.theme)


def test_tema_incompleto_e_completado_pelo_proprio_preset(ecommerce_account):
    """Site antigo não pode herdar a cor de OUTRO tema ao ganhar tokens novos."""
    from apps.storefront.themes import theme_tokens

    site = ensure_site(_new_restaurant(ecommerce_account, "Tema Antigo", "11222333000586"))
    classico = theme_tokens("classic")

    # Simula um site criado antes de a paleta crescer: preset clássico, sem os
    # tokens novos.
    site.theme = {k: v for k, v in classico.items() if k != "saleColor" and k != "headerBackgroundColor"}
    site.theme_preset = "classic"
    site.save(update_fields=["theme", "theme_preset", "updated_at"])

    ensure_site(site.restaurant)
    site.refresh_from_db()

    # Completou — e com os valores do CLÁSSICO, não do tema padrão.
    assert site.theme["headerBackgroundColor"] == classico["headerBackgroundColor"]
    assert site.theme["primaryColor"] == classico["primaryColor"]


def test_cabecalho_incompleto_ganha_os_campos_novos(ecommerce_account):
    """Site antigo não fica sem um campo que o cabeçalho passou a ter.

    O que o cliente já escolheu é mantido; só o que falta entra com o padrão —
    senão um campo novo (o modo de exibição das ações, por exemplo) nunca
    chegaria aos sites criados antes dele.
    """
    site = ensure_site(_new_restaurant(ecommerce_account, "Header Antigo", "11222333000667"))

    # Simula o cabeçalho salvo antes de as ações ganharem modo e rótulos.
    site.header = {
        "sticky": False,
        "brand_name": "Escolhido pelo cliente",
        "actions": {"cart": True, "profile": False},
    }
    site.save(update_fields=["header", "updated_at"])

    ensure_site(site.restaurant)
    site.refresh_from_db()

    # O que faltava entrou...
    assert site.header["actions"]["display"] == "icon"
    assert site.header["actions"]["cart_label"] == "Carrinho"
    # ...e o que o cliente escolheu ficou.
    assert site.header["brand_name"] == "Escolhido pelo cliente"
    assert site.header["sticky"] is False
    assert site.header["actions"]["profile"] is False


def test_home_padrao_usa_variaveis_do_tema_e_nao_cor_fixa(ecommerce_account):
    """É o que faz trocar o preset repintar a página sem editar um bloco."""
    import re

    site = ensure_site(_new_restaurant(ecommerce_account, "Bar do Zé", "11222333000343"))
    content = str(MenuPage.all_objects.get(site=site, is_home=True).published_data)

    assert "var(--sf-container-width)" in content
    assert "var(--sf-text)" in content
    # Nenhuma cor literal: um `#RRGGBB` aqui sobreviveria à troca de tema e
    # deixaria a página com a paleta antiga em algum canto.
    assert not re.findall(r"#[0-9a-fA-F]{6}", content)


def test_home_padrao_nao_copia_produto_nenhum(ecommerce_account, catalog):
    """A vitrine guarda configuração; produto vem da API na hora de renderizar."""
    site = ensure_site(_new_restaurant(ecommerce_account, "Sushi Bom", "11222333000424"))
    content = str(MenuPage.all_objects.get(site=site, is_home=True).published_data)
    assert "Margherita" not in content
    assert "49.90" not in content


def test_provisionamento_e_idempotente(ecommerce_account):
    restaurant = _new_restaurant(ecommerce_account, "Padaria Sol", "11222333000505")
    first = ensure_site(restaurant)
    second = ensure_site(restaurant)

    assert first.id == second.id
    assert MenuPage.all_objects.filter(site=first).count() == 1


def test_slug_do_site_nao_colide_entre_restaurantes_homonimos(ecommerce_account, other_account_setup):
    """O slug é o endereço público: é global, mesmo entre contas diferentes."""
    first = ensure_site(_new_restaurant(ecommerce_account, "Pizza Express", "11222333000686"))
    second = ensure_site(
        Restaurant.objects.create(
            account=other_account_setup["account"],
            legal_name="Pizza Express LTDA",
            trade_name="Pizza Express",
            cnpj="11222333000767",
        )
    )
    assert first.slug == "pizza-express"
    assert second.slug == "pizza-express-2"


# ── Provisionamento automático ───────────────────────────────────────────────


def test_restaurante_novo_com_ecommerce_ganha_site_sozinho(
    ecommerce_account, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        restaurant = _new_restaurant(ecommerce_account, "Novo Sabor", "11222333000848")

    site = MenuSite.all_objects.get(restaurant=restaurant)
    assert site.theme_preset == DEFAULT_THEME_KEY
    assert MenuPage.all_objects.filter(site=site, is_home=True, status=MenuPage.STATUS_PUBLISHED).exists()


def test_conta_sem_o_modulo_nao_ganha_site(account, django_capture_on_commit_callbacks):
    """Sem o módulo E-commerce contratado não há site — nem vazio."""
    account.enabled_modules = []
    account.save(update_fields=["enabled_modules", "updated_at"])

    with django_capture_on_commit_callbacks(execute=True):
        restaurant = _new_restaurant(account, "Sem Modulo", "11222333000929")

    assert not MenuSite.all_objects.filter(restaurant=restaurant).exists()


def test_comando_provisiona_quem_ficou_para_tras(ecommerce_account):
    """Módulo habilitado depois do cadastro: o sinal já passou, o comando cobre."""
    ecommerce_account.enabled_modules = []
    ecommerce_account.save(update_fields=["enabled_modules", "updated_at"])
    restaurant = _new_restaurant(ecommerce_account, "Atrasado", "11222333001000")
    assert not MenuSite.all_objects.filter(restaurant=restaurant).exists()

    ecommerce_account.enabled_modules = ["ecommerce"]
    ecommerce_account.save(update_fields=["enabled_modules", "updated_at"])
    call_command("provision_storefronts", account=str(ecommerce_account.id))

    site = MenuSite.all_objects.get(restaurant=restaurant)
    assert MenuPage.all_objects.filter(site=site, is_home=True).exists()


# ── API ──────────────────────────────────────────────────────────────────────


def test_site_criado_pela_api_ganha_tema_e_home(admin_client, ecommerce_account, django_capture_on_commit_callbacks):
    # Pelo admin: um usuário comum fica preso ao restaurante do próprio perfil,
    # e este teste cria um restaurante novo de propósito.
    with django_capture_on_commit_callbacks(execute=True):
        restaurant = _new_restaurant(ecommerce_account, "Via API", "11222333001081")
    MenuSite.all_objects.filter(restaurant=restaurant).delete()

    response = admin_client.post(
        "/api/v1/storefront/sites/",
        {"restaurant": str(restaurant.id), "name": "Via API", "slug": "via-api"},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["theme_preset"] == DEFAULT_THEME_KEY
    assert response.data["theme"]["primaryColor"]

    site = MenuSite.all_objects.get(id=response.data["id"])
    assert MenuPage.all_objects.filter(site=site, is_home=True).exists()


def test_trocar_o_preset_repinta_o_tema_inteiro(ecommerce_client, site):
    response = ecommerce_client.patch(
        f"/api/v1/storefront/sites/{site.id}/", {"theme_preset": "dark"}, format="json"
    )
    assert response.status_code == 200
    assert response.data["theme"] == THEME_PRESETS_BY_KEY["dark"]["tokens"]

    site.refresh_from_db()
    assert site.theme_preset == "dark"
    assert site.theme["backgroundColor"] == "#0D0D0F"


def test_preset_desconhecido_e_recusado(ecommerce_client, site):
    response = ecommerce_client.patch(
        f"/api/v1/storefront/sites/{site.id}/", {"theme_preset": "neon-glitter"}, format="json"
    )
    assert response.status_code == 400


def test_editar_o_tema_a_mao_solta_o_rotulo_do_preset(ecommerce_client, site):
    ecommerce_client.patch(f"/api/v1/storefront/sites/{site.id}/", {"theme_preset": "dark"}, format="json")

    custom = dict(THEME_PRESETS_BY_KEY["dark"]["tokens"], primaryColor="#00FFAA")
    response = ecommerce_client.patch(
        f"/api/v1/storefront/sites/{site.id}/", {"theme": custom}, format="json"
    )
    assert response.status_code == 200
    assert response.data["theme"]["primaryColor"] == "#00FFAA"
    # Não é mais o preset "dark": o rótulo sai para a tela não mentir.
    assert response.data["theme_preset"] == ""


def test_catalogo_de_temas_esta_disponivel(ecommerce_client):
    response = ecommerce_client.get("/api/v1/storefront/themes/")
    assert response.status_code == 200
    assert response.data["default"] == DEFAULT_THEME_KEY
    keys = {preset["key"] for preset in response.data["presets"]}
    assert {"classic", "dark", "warm", "fresh", "mono"} <= keys
    for preset in response.data["presets"]:
        assert preset["tokens"]["primaryColor"]


def test_provision_pela_api(ecommerce_client, ecommerce_account, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        restaurant = _new_restaurant(ecommerce_account, "Provisionar", "11222333001162")
    MenuSite.all_objects.filter(restaurant=restaurant).delete()

    response = ecommerce_client.post(
        "/api/v1/storefront/sites/provision/", {"restaurant": str(restaurant.id), "theme": "warm"}, format="json"
    )
    assert response.status_code == 201
    assert response.data["theme_preset"] == "warm"
    assert MenuPage.all_objects.filter(site_id=response.data["id"], is_home=True).exists()


def test_provision_nao_alcanca_restaurante_de_outra_conta(ecommerce_client, other_account_setup):
    response = ecommerce_client.post(
        "/api/v1/storefront/sites/provision/",
        {"restaurant": str(other_account_setup["restaurant"].id)},
        format="json",
    )
    assert response.status_code == 404


def test_site_padrao_responde_no_endpoint_publico(client, ecommerce_account, django_capture_on_commit_callbacks):
    """O teste que resume o pedido: criar restaurante e o cardápio já está no ar."""
    with django_capture_on_commit_callbacks(execute=True):
        restaurant = _new_restaurant(ecommerce_account, "Direto no Ar", "11222333001243")

    site = MenuSite.all_objects.get(restaurant=restaurant)
    response = client.get(f"/api/v1/public/storefront/{site.slug}/")

    assert response.status_code == 200
    body = response.json()
    assert body["page"] is not None
    assert body["site"]["theme"]["primaryColor"]
    assert "Direto no Ar" in str(body["page"]["data"])


# ── PATCH parcial nao apaga token que o formulario nao conhecia ─────────────


def test_patch_parcial_de_tema_preserva_tokens_nao_enviados(ecommerce_client, site):
    """Um formulario que so edita a cor primaria nao pode apagar `mode`/`buttonStyle`."""
    # A fixture `site` nasce com um tema minimo de teste; aqui simulamos o caso
    # real (site provisionado com o preset completo) antes do PATCH parcial.
    site.theme = theme_tokens(DEFAULT_THEME_KEY)
    site.save(update_fields=["theme", "updated_at"])
    original_mode = site.theme.get("mode")
    original_button_style = site.theme.get("buttonStyle")
    assert original_mode and original_button_style  # o preset padrao sempre tem os dois

    response = ecommerce_client.patch(
        f"/api/v1/storefront/sites/{site.id}/", {"theme": {"primaryColor": "#00FF00"}}, format="json"
    )
    assert response.status_code == 200
    assert response.data["theme"]["primaryColor"] == "#00FF00"
    assert response.data["theme"]["mode"] == original_mode
    assert response.data["theme"]["buttonStyle"] == original_button_style

    site.refresh_from_db()
    assert site.theme["mode"] == original_mode


def test_patch_parcial_de_seo_preserva_campos_nao_enviados(ecommerce_client, site):
    ecommerce_client.patch(
        f"/api/v1/storefront/sites/{site.id}/",
        {"seo": {"title": "Título completo", "description": "Descrição completa"}},
        format="json",
    )

    response = ecommerce_client.patch(
        f"/api/v1/storefront/sites/{site.id}/", {"seo": {"description": "Nova descrição"}}, format="json"
    )
    assert response.status_code == 200
    assert response.data["seo"]["title"] == "Título completo"
    assert response.data["seo"]["description"] == "Nova descrição"


def test_patch_parcial_de_seo_da_pagina_preserva_campos_nao_enviados(ecommerce_client, page):
    ecommerce_client.patch(
        f"/api/v1/storefront/pages/{page.id}/",
        {"seo": {"title": "Home", "og_image": "https://exemplo.com/banner.png"}},
        format="json",
    )

    response = ecommerce_client.patch(
        f"/api/v1/storefront/pages/{page.id}/", {"seo": {"title": "Home atualizado"}}, format="json"
    )
    assert response.status_code == 200
    assert response.data["seo"]["title"] == "Home atualizado"
    assert response.data["seo"]["og_image"] == "https://exemplo.com/banner.png"
