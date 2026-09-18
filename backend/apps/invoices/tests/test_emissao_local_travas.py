"""As duas travas da emissão fiscal local — e por que são duas.

Um terminal que liga sozinho começa a alocar numeração própria e a assinar
NFC-e REAIS com o certificado da empresa. Documento fiscal emitido não se
apaga: só se cancela, um a um, dentro do prazo. Desligado por engano custa uma
configuração esquecida; ligado por engano custa documento irreversível no CNPJ
do cliente.

Por isso a conta autoriza (`Account.local_fiscal_allowed`) E a loja liga
(`FiscalConfig.local_fiscal_enabled`). A de cima existe para não depender de
alguém lembrar de conferir a de baixo.
"""
import pytest
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.invoices.models import FiscalConfig, validar_emissao_local

pytestmark = pytest.mark.django_db


def _validar(**kwargs):
    base = {
        "local_fiscal_enabled": False,
        "local_fiscal_contingency": False,
        "provider": FiscalConfig.PROVIDER_FOCUS_NFE,
        "conta_autoriza": True,
    }
    base.update(kwargs)
    return validar_emissao_local(**base)


# ── o padrão ────────────────────────────────────────────────────────────────
def test_tudo_desligado_e_valido():
    """O estado de fábrica não pode ser um estado inválido."""
    assert _validar() == {}


def test_o_padrao_do_model_e_desligado():
    config = FiscalConfig()
    assert config.local_fiscal_enabled is False
    assert config.local_fiscal_contingency is False
    assert config.local_fiscal_url == ""


def test_a_conta_nasce_sem_autorizacao():
    from apps.accounts.models import Account

    assert Account().local_fiscal_allowed is False


# ── as recusas ──────────────────────────────────────────────────────────────
def test_contingencia_sozinha_e_recusada():
    """Um flag que não liga nada, mas passa a impressão de estar coberto."""
    erros = _validar(local_fiscal_contingency=True)
    assert "local_fiscal_contingency" in erros


def test_loja_ligada_sem_a_conta_autorizar_e_recusada():
    erros = _validar(local_fiscal_enabled=True, conta_autoriza=False)
    assert "local_fiscal_enabled" in erros
    assert "conta" in erros["local_fiscal_enabled"].lower()


def test_emissao_local_com_provedor_manual_e_recusada():
    """O terminal se anunciaria autoridade fiscal sem emitir documento nenhum."""
    erros = _validar(local_fiscal_enabled=True, provider=FiscalConfig.PROVIDER_MANUAL)
    assert "local_fiscal_enabled" in erros


# ── o caminho feliz ─────────────────────────────────────────────────────────
def test_as_duas_travas_ligadas_liberam():
    assert _validar(local_fiscal_enabled=True, local_fiscal_contingency=True) == {}


# ── a regra vale no Admin e na API, e vem do MESMO lugar ────────────────────
def test_o_clean_do_model_recusa_contingencia_solta():
    """Sem tocar no banco: a regra é da combinação, não do estado gravado."""
    config = FiscalConfig(local_fiscal_contingency=True,
                          provider=FiscalConfig.PROVIDER_FOCUS_NFE)
    with pytest.raises(DjangoValidationError):
        config.clean()


def test_o_clean_do_model_aceita_o_estado_de_fabrica():
    FiscalConfig(provider=FiscalConfig.PROVIDER_FOCUS_NFE).clean()


def test_o_serializer_usa_a_mesma_funcao_do_model():
    """Se um dia divergirem, a API passa a aceitar o que o Admin recusa."""
    import inspect

    from apps.invoices.serializers import FiscalConfigSerializer

    fonte = inspect.getsource(FiscalConfigSerializer.validate)
    assert "validar_emissao_local" in fonte


def test_a_url_do_comunicador_nao_e_sobrescrita_pela_nuvem():
    """É o endereço daquela máquina, como o IP da impressora."""
    from apps.synchronization.services.registry import registry

    entrada = registry.require("fiscal_config")
    assert "local_fiscal_url" in entrada.local_only_fields
