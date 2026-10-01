"""Classificacao das recusas HTTP devolvidas pela Focus na emissao."""

from apps.invoices.providers import FiscalConfigurationError, FocusNfeProvider


def test_csc_e_id_token_nao_configurados_exigem_correcao_da_configuracao():
    """O 422 da empresa nao e rejeicao tributaria do pedido."""

    erro = FocusNfeProvider._classify_http(
        422,
        {
            "codigo": "erro_validacao",
            "mensagem": (
                "Erro de validação (Código CSC não configurado. Solicite ao suporte técnico.; "
                "Id Token não configurado. Solicite ao suporte técnico.)"
            ),
        },
    )

    assert isinstance(erro, FiscalConfigurationError)
    assert "Código CSC não configurado" in str(erro)
    assert "Id Token não configurado" in str(erro)
