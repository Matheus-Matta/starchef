"""O cenário dos dois arquivos de teste do empréstimo de credencial.

Não é arquivo de teste: é a loja sem segredo nenhum gravado e a nuvem
respondendo com o pacote dela. Fica fora para que os dois lados da prova — o
resolvedor e quem o consome — partam exatamente do mesmo estado.
"""
from apps.invoices.models import FiscalConfig

#: O que a nuvem devolve. `fiscal_config_id` é preenchido pelo fixture, porque
#: o pacote é amarrado à configuração daquele nó.
PACOTE = {
    "fiscal_config_id": None,
    "csc_id": "000002",
    "csc_token": "CSC-DA-NUVEM",
    "focus_token_homologation": "TOKEN-HOMOLOGACAO",
    "focus_token_production": "TOKEN-PRODUCAO",
    "certificate_base64": "Y2VydGlmaWNhZG8=",
    "certificate_password": "senha-do-a1",
}


def config_sem_segredo(account, restaurant, branch):
    """A configuração como ela chega numa loja: completa, menos os segredos."""
    return FiscalConfig.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        document_model=FiscalConfig.MODEL_NFCE, series=1, next_number=1,
        environment=FiscalConfig.ENV_HOMOLOGATION,
        cnpj="63201558000155", uf="RJ",
    )


def nuvem_devolve(monkeypatch, pacote):
    monkeypatch.setattr(
        "apps.synchronization.services.credentials_client.obter",
        lambda **kwargs: pacote,
    )
