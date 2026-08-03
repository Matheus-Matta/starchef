"""Smoke test do app integrations: só o contrato FiscalProvider existe hoje
(nenhum provider real integrado — ver docs/GAP_ANALYSIS.md). Confirma que a
interface importa e que os métodos abstratos falham como esperado.
"""
import pytest

from apps.integrations.providers import FiscalProvider


def test_fiscal_provider_methods_are_not_implemented():
    provider = FiscalProvider()
    with pytest.raises(NotImplementedError):
        provider.issue(invoice=None)
    with pytest.raises(NotImplementedError):
        provider.cancel(invoice=None, reason="teste")
    with pytest.raises(NotImplementedError):
        provider.status(invoice=None)
