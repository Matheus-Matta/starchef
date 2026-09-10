"""API privada do storefront: rascunho, publicação, versões, modelos e permissão."""
import pytest

from apps.storefront.models import MenuPage, MenuPageVersion, MenuTemplate
from apps.storefront.tests.conftest import SIMPLE_PROJECT, authenticated_client

pytestmark = pytest.mark.django_db


def _errors(response):
    """Erros de validacao dentro do envelope padrao da API."""
    return response.data.get("error", {}).get("message", response.data)


def _draft_with(text):
    return {
        "pages": [
            {
                "frames": [
                    {
                        "component": {
                            "type": "sf-section",
                            "tagName": "section",
                            "components": [{"type": "sf-heading", "tagName": "h1", "content": text}],
                        }
                    }
                ]
            }
        ]
    }


# ── Rascunho ─────────────────────────────────────────────────────────────────


def test_salvar_rascunho_nao_publica(ecommerce_client, page):
    """A invariante central: salvar no editor não pode colocar nada no ar."""
    response = ecommerce_client.patch(
        f"/api/v1/storefront/pages/{page.id}/",
        {"draft_data": _draft_with("Promoção nova")},
        format="json",
    )
    assert response.status_code == 200

    page.refresh_from_db()
    assert "Promoção nova" in str(page.draft_data)
    assert page.published_data == {}
    assert page.status == MenuPage.STATUS_DRAFT


def test_rascunho_com_script_e_recusado(ecommerce_client, page):
    response = ecommerce_client.patch(
        f"/api/v1/storefront/pages/{page.id}/",
        {"draft_data": {"pages": [{"frames": [{"component": {"type": "text", "tagName": "script"}}]}]}},
        format="json",
    )
    assert response.status_code == 400


def test_cliente_nao_consegue_forjar_o_status_publicado(ecommerce_client, page):
    """`status` e `published_data` são read-only: publicar só pela ação de publicar."""
    response = ecommerce_client.patch(
        f"/api/v1/storefront/pages/{page.id}/",
        {"status": "published", "published_data": _draft_with("hack")},
        format="json",
    )
    assert response.status_code == 200
    page.refresh_from_db()
    assert page.status == MenuPage.STATUS_DRAFT
    assert page.published_data == {}


def test_listagem_de_paginas_nao_carrega_o_json_do_editor(ecommerce_client, page):
    response = ecommerce_client.get("/api/v1/storefront/pages/")
    assert response.status_code == 200
    row = response.data["results"][0]
    assert "draft_data" not in row
    assert row["slug"] == "home"


# ── Publicação e versionamento ───────────────────────────────────────────────


def test_publicar_copia_o_rascunho_para_o_publicado(ecommerce_client, page):
    response = ecommerce_client.post(f"/api/v1/storefront/pages/{page.id}/publish/")
    assert response.status_code == 200

    page.refresh_from_db()
    assert page.status == MenuPage.STATUS_PUBLISHED
    assert page.published_at is not None
    assert page.published_data == page.draft_data


def test_publicar_versiona_o_conteudo_anterior(ecommerce_client, page):
    ecommerce_client.post(f"/api/v1/storefront/pages/{page.id}/publish/")
    ecommerce_client.patch(
        f"/api/v1/storefront/pages/{page.id}/", {"draft_data": _draft_with("Segunda versão")}, format="json"
    )
    ecommerce_client.post(f"/api/v1/storefront/pages/{page.id}/publish/")

    versions = MenuPageVersion.all_objects.filter(page=page)
    assert versions.count() == 1
    assert "Bem-vindo" in str(versions.first().data)

    page.refresh_from_db()
    assert "Segunda versão" in str(page.published_data)


def test_pagina_sem_conteudo_nao_publica(ecommerce_client, site):
    empty = MenuPage.all_objects.create(
        account=site.account, restaurant=site.restaurant, site=site, title="Vazia", slug="vazia"
    )
    response = ecommerce_client.post(f"/api/v1/storefront/pages/{empty.id}/publish/")
    assert response.status_code == 400


def test_restaurar_versao_volta_para_o_rascunho_sem_publicar(ecommerce_client, page):
    ecommerce_client.post(f"/api/v1/storefront/pages/{page.id}/publish/")
    ecommerce_client.patch(
        f"/api/v1/storefront/pages/{page.id}/", {"draft_data": _draft_with("Versão ruim")}, format="json"
    )
    ecommerce_client.post(f"/api/v1/storefront/pages/{page.id}/publish/")

    version = MenuPageVersion.all_objects.filter(page=page).order_by("number").first()
    response = ecommerce_client.post(
        f"/api/v1/storefront/pages/{page.id}/versions/{version.id}/restore/", {}, format="json"
    )
    assert response.status_code == 200

    page.refresh_from_db()
    assert "Bem-vindo" in str(page.draft_data)
    # O que está no ar continua sendo a versão ruim até alguém publicar de novo.
    assert "Versão ruim" in str(page.published_data)


def test_restaurar_com_publish_faz_o_rollback_completo(ecommerce_client, page):
    ecommerce_client.post(f"/api/v1/storefront/pages/{page.id}/publish/")
    ecommerce_client.patch(
        f"/api/v1/storefront/pages/{page.id}/", {"draft_data": _draft_with("Versão ruim")}, format="json"
    )
    ecommerce_client.post(f"/api/v1/storefront/pages/{page.id}/publish/")

    version = MenuPageVersion.all_objects.filter(page=page).order_by("number").first()
    response = ecommerce_client.post(
        f"/api/v1/storefront/pages/{page.id}/versions/{version.id}/restore/", {"publish": True}, format="json"
    )
    assert response.status_code == 200

    page.refresh_from_db()
    assert "Bem-vindo" in str(page.published_data)


def test_listar_versoes(ecommerce_client, page):
    ecommerce_client.post(f"/api/v1/storefront/pages/{page.id}/publish/")
    ecommerce_client.patch(
        f"/api/v1/storefront/pages/{page.id}/", {"draft_data": _draft_with("Outra")}, format="json"
    )
    ecommerce_client.post(f"/api/v1/storefront/pages/{page.id}/publish/")

    response = ecommerce_client.get(f"/api/v1/storefront/pages/{page.id}/versions/")
    assert response.status_code == 200
    rows = response.data["results"] if isinstance(response.data, dict) else response.data
    assert len(rows) == 1
    # A listagem não carrega o JSON; o conteúdo só vem no detalhe.
    assert "data" not in rows[0]


def test_retirar_do_ar(ecommerce_client, page):
    ecommerce_client.post(f"/api/v1/storefront/pages/{page.id}/publish/")
    response = ecommerce_client.post(f"/api/v1/storefront/pages/{page.id}/unpublish/")
    assert response.status_code == 200

    page.refresh_from_db()
    assert page.published_data == {}
    assert page.status == MenuPage.STATUS_DRAFT


# ── Modelos prontos ──────────────────────────────────────────────────────────


def test_aplicar_template_copia_o_conteudo_sem_criar_vinculo(ecommerce_client, page):
    template = MenuTemplate.objects.create(
        name="Pizzaria Moderna",
        slug="pizzaria-moderna",
        project_data=_draft_with("Modelo aplicado"),
    )
    response = ecommerce_client.post(f"/api/v1/storefront/pages/{page.id}/apply-template/{template.id}/")
    assert response.status_code == 200

    page.refresh_from_db()
    assert "Modelo aplicado" in str(page.draft_data)
    # Nada na página aponta para o template: mudar o modelo depois não muda a página.
    assert not any(field.name == "template" for field in MenuPage._meta.fields)
    # E o rascunho anterior foi versionado antes de ser sobrescrito.
    assert MenuPageVersion.all_objects.filter(page=page).exists()


def test_template_e_sanitizado_ao_ser_aplicado(ecommerce_client, page):
    """Nem o catálogo da plataforma é confiável para pular a validação."""
    template = MenuTemplate.objects.create(
        name="Modelo Ruim",
        slug="modelo-ruim",
        project_data={"pages": [{"frames": [{"component": {"type": "text", "tagName": "iframe"}}]}]},
    )
    response = ecommerce_client.post(f"/api/v1/storefront/pages/{page.id}/apply-template/{template.id}/")
    assert response.status_code == 400


def test_schema_do_builder_esta_disponivel_para_o_editor(ecommerce_client):
    response = ecommerce_client.get("/api/v1/storefront/schema/")
    assert response.status_code == 200
    assert "sf-product-grid" in response.data["components"]
    assert "background-color" in response.data["style_properties"]
    assert "script" not in response.data["tags"]


# ── Permissões ───────────────────────────────────────────────────────────────


def test_garcom_nao_pode_ver_nem_editar_o_site(waiter_user, page):
    client = authenticated_client(waiter_user)
    assert client.get("/api/v1/storefront/pages/").status_code == 403
    assert (
        client.patch(f"/api/v1/storefront/pages/{page.id}/", {"draft_data": {}}, format="json").status_code == 403
    )


def test_gerente_da_operacao_nao_edita_o_site(api_client, ecommerce_account, page):
    """Gerenciar o salão não dá acesso ao builder — é uma especialidade à parte."""
    response = api_client.patch(
        f"/api/v1/storefront/pages/{page.id}/", {"draft_data": _draft_with("x")}, format="json"
    )
    assert response.status_code == 403


def test_admin_do_tenant_edita_e_publica(admin_client, ecommerce_account, page):
    assert (
        admin_client.patch(
            f"/api/v1/storefront/pages/{page.id}/", {"draft_data": _draft_with("Admin")}, format="json"
        ).status_code
        == 200
    )
    assert admin_client.post(f"/api/v1/storefront/pages/{page.id}/publish/").status_code == 200


def test_perfil_ecommerce_nao_gerencia_dominio(ecommerce_client, site):
    """Domínio mexe em DNS/TLS e pode tirar o site do ar: fica com o administrador."""
    response = ecommerce_client.post(
        "/api/v1/storefront/domains/",
        {"site": str(site.id), "hostname": "cardapio.exemplo.com.br", "domain_type": "custom"},
        format="json",
    )
    assert response.status_code == 403


def test_sem_o_modulo_ecommerce_a_api_fica_fechada(account, ecommerce_user, page):
    account.enabled_modules = []
    account.save(update_fields=["enabled_modules", "updated_at"])
    client = authenticated_client(ecommerce_user)
    assert client.get("/api/v1/storefront/pages/").status_code == 403


def test_anonimo_nao_acessa_a_api_privada(client, page):
    assert client.get("/api/v1/storefront/pages/").status_code == 401


# ── Isolamento multi-tenant ──────────────────────────────────────────────────


def test_usuario_nao_le_pagina_de_outra_conta(ecommerce_client, page, other_account_setup):
    other_page = other_account_setup["page"]
    assert ecommerce_client.get(f"/api/v1/storefront/pages/{other_page.id}/").status_code == 404

    listed = ecommerce_client.get("/api/v1/storefront/pages/")
    assert [row["id"] for row in listed.data["results"]] == [str(page.id)]


def test_usuario_nao_edita_pagina_de_outra_conta(ecommerce_client, other_account_setup):
    other_page = other_account_setup["page"]
    response = ecommerce_client.patch(
        f"/api/v1/storefront/pages/{other_page.id}/", {"draft_data": _draft_with("invasão")}, format="json"
    )
    assert response.status_code == 404
    other_page.refresh_from_db()
    assert "invasão" not in str(other_page.draft_data)


def test_usuario_nao_publica_pagina_de_outra_conta(ecommerce_client, other_account_setup):
    other_page = other_account_setup["page"]
    assert ecommerce_client.post(f"/api/v1/storefront/pages/{other_page.id}/publish/").status_code == 404
    other_page.refresh_from_db()
    assert other_page.published_data == {}


def test_pagina_nao_pode_apontar_para_site_de_outra_conta(ecommerce_client, other_account_setup):
    response = ecommerce_client.post(
        "/api/v1/storefront/pages/",
        {"site": str(other_account_setup["site"].id), "title": "Invasora", "slug": "invasora"},
        format="json",
    )
    assert response.status_code in {400, 404}
    assert not MenuPage.all_objects.filter(slug="invasora").exists()


def test_pagina_herda_o_restaurante_do_site_e_ignora_o_payload(ecommerce_client, site, other_account_setup):
    response = ecommerce_client.post(
        "/api/v1/storefront/pages/",
        {
            "site": str(site.id),
            "title": "Contato",
            "slug": "contato",
            "restaurant": str(other_account_setup["restaurant"].id),
            "draft_data": SIMPLE_PROJECT,
        },
        format="json",
    )
    assert response.status_code == 201
    created = MenuPage.all_objects.get(slug="contato")
    assert created.restaurant_id == site.restaurant_id


def test_slug_de_pagina_e_unico_por_site(ecommerce_client, site, page):
    response = ecommerce_client.post(
        "/api/v1/storefront/pages/",
        {"site": str(site.id), "title": "Outra home", "slug": "home"},
        format="json",
    )
    assert response.status_code == 400
    assert "slug" in _errors(response)


def test_so_uma_pagina_inicial_por_site(ecommerce_client, site, page):
    response = ecommerce_client.post(
        "/api/v1/storefront/pages/",
        {"site": str(site.id), "title": "Segunda home", "slug": "home-2", "is_home": True},
        format="json",
    )
    assert response.status_code == 400
    assert "is_home" in _errors(response)


def test_seed_de_modelos_e_idempotente_e_valido():
    """O catálogo da plataforma tem de passar pelo mesmo validador do editor."""
    from django.core.management import call_command

    call_command("seed_storefront_templates")
    first = {template.slug: template.project_data for template in MenuTemplate.objects.all()}
    assert "pizzaria-moderna" in first

    call_command("seed_storefront_templates")
    assert MenuTemplate.objects.count() == len(first)
