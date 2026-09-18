"""Contingência é para indisponibilidade, nunca para recusa.

Emitir em contingência uma nota que a SEFAZ RECUSOU não conserta nada: entrega
um cupom ao cliente e cria um documento irregular no CNPJ, que depois só se
resolve cancelando, um a um, dentro do prazo. O caso real que originou esta
regra foi "Código Regime Tributário do emitente diverge do cadastro na Receita
Federal" — em contingência a nota sairia igualmente errada.
"""
import pytest

from apps.invoices import contingency
from apps.invoices.providers import (
    FiscalAmbiguous,
    FiscalConfigurationError,
    FiscalNotFound,
    FiscalProviderError,
    FiscalRejection,
    FiscalUnavailable,
)


# ── a cobertura: nenhuma falha pode ficar sem classificação ─────────────────
def test_toda_falha_fiscal_esta_classificada():
    """O teste que impede a regra de se perder quando alguém criar a próxima.

    Uma exceção nova sem classificação quebra AQUI, na suíte — e não na
    operação de uma loja, no meio de uma venda.
    """
    sem_classificacao = [
        classe.__name__
        for classe in contingency.subclasses_de_falha()
        if not issubclass(classe, contingency.FALHAS_DE_INDISPONIBILIDADE)
        and not issubclass(classe, contingency.FALHAS_DE_DOCUMENTO)
    ]
    assert not sem_classificacao, (
        "Falha fiscal sem classificação de contingência. Decida explicitamente "
        "se ela é indisponibilidade (rede/timeout/SEFAZ fora) ou documento "
        "inválido, em apps/invoices/contingency.py:\n  "
        + "\n  ".join(sem_classificacao)
    )


def test_nenhuma_falha_esta_nos_dois_grupos():
    """Ambiguidade aqui seria pior que omissão: a resposta dependeria da ordem."""
    nos_dois = [
        classe.__name__
        for classe in contingency.subclasses_de_falha()
        if issubclass(classe, contingency.FALHAS_DE_INDISPONIBILIDADE)
        and issubclass(classe, contingency.FALHAS_DE_DOCUMENTO)
    ]
    assert not nos_dois, f"classificação contraditória: {nos_dois}"


# ── a regra ─────────────────────────────────────────────────────────────────
def test_so_indisponibilidade_justifica():
    assert contingency.justifica_contingencia(FiscalUnavailable("timeout")) is True


@pytest.mark.parametrize(
    "erro",
    [
        FiscalRejection("Rejeicao 539: duplicidade"),
        FiscalConfigurationError("certificado vencido"),
        FiscalNotFound("referencia inexistente"),
        FiscalAmbiguous("ja processada, resultado desconhecido"),
    ],
    ids=["rejeicao", "configuracao", "nao_encontrada", "ambigua"],
)
def test_recusa_nunca_justifica(erro):
    assert contingency.justifica_contingencia(erro) is False
    assert contingency.motivo_da_recusa(erro), "toda recusa explica o porquê"


def test_o_caso_real_do_regime_tributario():
    """A rejeição que originou esta regra, com o texto que a SEFAZ devolveu."""
    erro = FiscalRejection(
        "Rejeição: Código Regime Tributário do emitente diverge do cadastro "
        "na Receita Federal"
    )
    assert contingency.justifica_contingencia(erro) is False


# ── falha fechada ───────────────────────────────────────────────────────────
def test_falha_desconhecida_nao_justifica():
    """Emitir à toa é irreversível; não emitir não é.

    Uma exceção que ninguém classificou é tratada como documento inválido. É a
    escolha segura: o pior caso é uma nota a menos, não um documento fiscal
    irregular no CNPJ do cliente.
    """
    assert contingency.classificar(RuntimeError("algo novo")) == contingency.DESCONHECIDA
    assert contingency.justifica_contingencia(RuntimeError("algo novo")) is False


def test_falha_base_sem_subtipo_nao_justifica():
    assert contingency.justifica_contingencia(FiscalProviderError("generica")) is False


def test_desconhecida_tambem_explica_o_motivo():
    motivo = contingency.motivo_da_recusa(RuntimeError("algo novo"))
    assert "não foi classificada" in motivo


# ── as mensagens ────────────────────────────────────────────────────────────
def test_indisponibilidade_nao_tem_motivo_de_recusa():
    assert contingency.motivo_da_recusa(FiscalUnavailable("rede caiu")) == ""


def test_a_recusa_por_duplicidade_fala_em_duplicar():
    """Não encontrada e ambígua recusam por motivo DIFERENTE da rejeição."""
    for erro in (FiscalNotFound("x"), FiscalAmbiguous("y")):
        assert "duplicar" in contingency.motivo_da_recusa(erro)


# ── a porta única ───────────────────────────────────────────────────────────
#
# O serviço de emissão tem cinco blocos de `except` diferentes, dois deles
# terminando num `except Exception` genérico. A contingência precisa ser
# alcançável por UM caminho só — senão a regra se perde de novo na próxima
# alteração.
class _NotaFalsa:
    def __init__(self):
        from apps.invoices.models import Invoice

        self.emission_type = ""
        self.status = Invoice.STATUS_ERROR
        self.error_message = ""
        self.fiscal_payload = {}
        self.updated_by = None


def test_a_porta_aceita_indisponibilidade():
    from apps.invoices.models import Invoice
    from apps.invoices.services import entrar_em_contingencia

    nota = _NotaFalsa()
    entrar_em_contingencia(nota, FiscalUnavailable("SEFAZ fora do ar"))

    assert nota.emission_type == Invoice.EMISSION_CONTINGENCY
    assert nota.status == Invoice.STATUS_PENDING
    assert nota.fiscal_payload["contingency_reason"] == "SEFAZ fora do ar"
    assert nota.fiscal_payload["contingency_class"] == contingency.INDISPONIBILIDADE


def test_a_porta_recusa_rejeicao_com_excecao():
    """Recusa é EXCEÇÃO, não retorno: retorno se ignora sem querer."""
    from django.core.exceptions import ValidationError

    from apps.invoices.services import entrar_em_contingencia

    nota = _NotaFalsa()
    with pytest.raises(ValidationError):
        entrar_em_contingencia(
            nota,
            FiscalRejection(
                "Rejeição: Código Regime Tributário do emitente diverge do "
                "cadastro na Receita Federal"
            ),
        )
    assert nota.emission_type == "", "a nota não pode ter sido tocada"


@pytest.mark.parametrize(
    "erro",
    [
        FiscalConfigurationError("certificado vencido"),
        FiscalNotFound("referencia inexistente"),
        FiscalAmbiguous("resultado desconhecido"),
        RuntimeError("falha nova, nao classificada"),
    ],
    ids=["configuracao", "nao_encontrada", "ambigua", "desconhecida"],
)
def test_a_porta_recusa_tudo_que_nao_e_indisponibilidade(erro):
    from django.core.exceptions import ValidationError

    from apps.invoices.services import entrar_em_contingencia

    with pytest.raises(ValidationError):
        entrar_em_contingencia(_NotaFalsa(), erro)


def test_o_motivo_fica_gravado_para_auditoria():
    """Nota em tpEmis=9 é retransmitida depois; quem auditar meses adiante
    precisa saber o que estava fora do ar naquele momento."""
    from apps.invoices.services import entrar_em_contingencia

    nota = _NotaFalsa()
    entrar_em_contingencia(nota, FiscalUnavailable("timeout ao falar com a Focus"))
    assert "timeout" in nota.fiscal_payload["contingency_reason"]
