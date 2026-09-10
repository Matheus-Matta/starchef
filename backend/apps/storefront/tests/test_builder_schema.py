"""A fronteira de segurança: o que o editor manda e o backend recusa ou reescreve."""
import pytest

from apps.storefront.builder_schema import (
    BuilderValidationError,
    sanitize_html,
    validate_project_data,
    validate_seo,
    validate_theme,
)


def _project(component):
    return {"pages": [{"frames": [{"component": component}]}]}


def _first_component(data):
    return data["pages"][0]["frames"][0]["component"]


def test_bloco_desconhecido_e_recusado_com_o_caminho():
    with pytest.raises(BuilderValidationError) as exc:
        validate_project_data(_project({"type": "checkout-form"}))
    assert "pages[0].frames[0].component" in exc.value.errors


def test_tag_script_e_recusada():
    with pytest.raises(BuilderValidationError) as exc:
        validate_project_data(_project({"type": "text", "tagName": "script", "content": "alert(1)"}))
    assert "tagName" in "".join(exc.value.errors)


def test_iframe_e_recusado():
    with pytest.raises(BuilderValidationError):
        validate_project_data(_project({"type": "text", "tagName": "iframe"}))


def test_handler_de_evento_e_recusado():
    with pytest.raises(BuilderValidationError) as exc:
        validate_project_data(
            _project({"type": "sf-button", "tagName": "button", "attributes": {"onclick": "steal()"}})
        )
    assert any("evento" in message for message in exc.value.errors.values())


def test_url_javascript_e_recusada():
    with pytest.raises(BuilderValidationError):
        validate_project_data(
            _project({"type": "sf-link", "tagName": "a", "attributes": {"href": "javascript:alert(1)"}})
        )


def test_url_javascript_com_quebra_de_linha_tambem_e_recusada():
    """`java\\nscript:` é ignorado pelo navegador e executa igual."""
    with pytest.raises(BuilderValidationError):
        validate_project_data(
            _project({"type": "sf-link", "tagName": "a", "attributes": {"href": "java\nscript:alert(1)"}})
        )


def test_imagem_base64_e_recusada():
    """Imagem entra por upload (MenuAsset), nunca embutida no JSON."""
    with pytest.raises(BuilderValidationError):
        validate_project_data(
            _project({"type": "sf-image", "tagName": "img", "attributes": {"src": "data:image/png;base64,AAAA"}})
        )


def test_url_relativa_e_https_passam():
    clean = validate_project_data(
        _project(
            {
                "type": "sf-link",
                "tagName": "a",
                "attributes": {"href": "/cardapio", "title": "Cardápio"},
                "components": [
                    {"type": "sf-link", "tagName": "a", "attributes": {"href": "https://exemplo.com"}},
                ],
            }
        )
    )
    assert _first_component(clean)["attributes"]["href"] == "/cardapio"


def test_css_perigoso_e_recusado():
    with pytest.raises(BuilderValidationError):
        validate_project_data(
            _project({"type": "sf-section", "tagName": "div", "style": {"background": "url(javascript:alert(1))"}})
        )


def test_propriedade_de_css_fora_da_lista_e_descartada_em_silencio():
    """Descartar, e não recusar: derrubar o salvamento por CSS cosmético seria hostil."""
    clean = validate_project_data(
        _project({"type": "sf-section", "tagName": "div", "style": {"padding": "10px", "-moz-appearance": "none"}})
    )
    style = _first_component(clean)["style"]
    assert style == {"padding": "10px"}


def test_camel_case_de_css_e_normalizado():
    clean = validate_project_data(
        _project({"type": "sf-section", "tagName": "div", "style": {"backgroundColor": "#fff"}})
    )
    assert _first_component(clean)["style"] == {"background-color": "#fff"}


def test_html_de_texto_rico_e_sanitizado():
    clean = validate_project_data(
        _project({"type": "text", "tagName": "p", "content": "<b>oi</b><script>alert(1)</script>"})
    )
    content = _first_component(clean)["content"]
    assert "<b>oi</b>" in content
    assert "script" not in content
    assert "alert" not in content


def test_sanitize_html_remove_onerror_e_mantem_o_texto():
    assert sanitize_html('<img src=x onerror="alert(1)">texto') == "texto"


def test_sanitize_html_adiciona_noopener_em_target_blank():
    result = sanitize_html('<a href="https://a.com" target="_blank">ir</a>')
    assert 'rel="noopener noreferrer"' in result


def test_projeto_acima_do_limite_de_bytes_e_recusado(monkeypatch):
    from apps.storefront import builder_schema

    monkeypatch.setattr(builder_schema, "MAX_PROJECT_BYTES", 100)
    with pytest.raises(BuilderValidationError):
        validate_project_data({"pages": [{"frames": [{"component": {"type": "text", "content": "x" * 500}}]}]})


def test_projeto_acima_do_limite_de_nos_e_recusado(monkeypatch):
    from apps.storefront import builder_schema

    monkeypatch.setattr(builder_schema, "MAX_NODES", 3)
    with pytest.raises(BuilderValidationError):
        validate_project_data(
            _project(
                {
                    "type": "sf-section",
                    "components": [{"type": "text", "content": str(index)} for index in range(10)],
                }
            )
        )


def test_props_do_bloco_sao_preservadas_como_configuracao():
    """A vitrine guarda a configuração, não a cópia dos produtos."""
    clean = validate_project_data(
        _project(
            {
                "type": "sf-product-grid",
                "props": {"category_id": 12, "columns": {"desktop": 4, "mobile": 1}, "show_description": True},
            }
        )
    )
    props = _first_component(clean)["props"]
    assert props["category_id"] == 12
    assert props["columns"]["desktop"] == 4
    assert props["show_description"] is True


def test_tema_aceita_so_as_chaves_conhecidas():
    theme = validate_theme({"primaryColor": "#E53935", "evilScript": "<script>", "fontFamily": "Inter"})
    assert theme == {"primaryColor": "#E53935", "fontFamily": "Inter"}


def test_seo_escapa_html_e_valida_url():
    seo = validate_seo(
        {"title": "<script>x</script>Pizzaria", "og_image": "javascript:alert(1)", "index": 1}
    )
    assert "<script>" not in seo["title"]
    assert "og_image" not in seo
    assert seo["index"] is True


def test_todas_as_secoes_da_biblioteca_sao_validas():
    """Uma seção oferecida no editor que o validador recusa é um erro que só
    apareceria quando o cliente arrastasse o bloco e tentasse salvar."""
    from apps.storefront.starter import section_presets

    for preset in section_presets():
        clean = validate_project_data(
            {"pages": [{"frames": [{"component": {"type": "wrapper", "components": [preset["component"]]}}]}]}
        )
        nodes = clean["pages"][0]["frames"][0]["component"]["components"]
        assert nodes, f"seção '{preset['key']}' foi descartada pelo validador"


def test_home_padrao_inteira_passa_pelo_validador():
    from apps.storefront.starter import build_starter_page

    clean = validate_project_data(build_starter_page("Mercado Teste"))
    blocks = str(clean)
    for expected in ("sf-hero", "sf-categories", "sf-filter-bar", "sf-product-grid", "sf-footer"):
        assert expected in blocks


# ── Cabeçalho do site ────────────────────────────────────────────────────────


def test_header_sanitiza_texto_e_url():
    from apps.storefront.builder_schema import validate_header

    header = validate_header(
        {
            "brand_name": "<script>x</script>Pizzaria",
            "logo_url": "javascript:alert(1)",
            "announcement": {"text": "Frete gratis", "highlight": "20% OFF"},
            "nav_menu": "navegacao-principal",
        }
    )

    assert "<script>" not in header["brand_name"]
    assert header["logo_url"] == ""
    assert header["announcement"]["highlight"] == "20% OFF"
    assert header["nav_menu"] == "navegacao-principal"


def test_header_nao_usa_a_chave_account_nas_acoes():
    """Regressão: `actions.account` derrubava a resposta inteira.

    O `TenantResponseSafetyMiddleware` trata QUALQUER chave `account` do corpo
    como marcador de conta; ao encontrar `true` onde esperava um id, bloqueava
    a resposta como vazamento entre tenants e devolvia 404. O nome do campo é
    barato de trocar — a regra do middleware protege o sistema inteiro.
    """
    from apps.storefront.builder_schema import validate_header

    actions = validate_header({"actions": {"cart": True, "profile": True}})["actions"]

    assert actions["cart"] is True
    assert actions["profile"] is True
    assert "account" not in actions


def test_header_modo_de_exibicao_das_acoes_e_lista_fechada():
    """Cada modo tem um layout próprio no CSS; um valor livre cairia sem estilo."""
    from apps.storefront.builder_schema import validate_header

    def display(value):
        return validate_header({"actions": {"display": value}})["actions"]["display"]

    assert display("icon_text") == "icon_text"
    assert display("text") == "text"
    # Desconhecido, vazio ou ausente caem no padrão — nunca num modo sem estilo.
    assert display("qualquer-coisa") == "icon"
    assert display("") == "icon"
    assert validate_header({"actions": {}})["actions"]["display"] == "icon"


def test_header_rotulos_das_acoes_tem_padrao():
    from apps.storefront.builder_schema import validate_header

    actions = validate_header({"actions": {}})["actions"]

    # Modo "só texto" sem rótulo nenhum seria um botão vazio: o padrão evita.
    assert actions["cart_label"] == "Carrinho"
    assert actions["profile_label"] == "Entrar"


def test_header_vazio_vira_dicionario_vazio():
    from apps.storefront.builder_schema import validate_header

    assert validate_header(None) == {}
    assert validate_header({}) == {}
