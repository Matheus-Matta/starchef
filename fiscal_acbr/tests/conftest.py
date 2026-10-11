import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TOKEN = "token-de-teste"


@pytest.fixture
def api(monkeypatch):
    """O comunicador com a SEFAZ simulada, como sobe com ACBR_SIMULADOR=1."""
    monkeypatch.setenv("ACBR_SIMULADOR", "1")
    monkeypatch.setenv("ACBRLIB_TOKEN", TOKEN)
    import app.main

    modulo = importlib.reload(app.main)
    cliente = TestClient(modulo.app)
    cliente.headers["Authorization"] = f"Bearer {TOKEN}"
    return cliente
