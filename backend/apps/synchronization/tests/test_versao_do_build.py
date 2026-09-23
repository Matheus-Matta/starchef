"""A versão que o nó declara vem do BUILD, não de uma variável escrita à mão.

`app_version` não trava nada: quem recusa conexão incompatível é
`protocol_version`, que é constante no código. Ela é só o rótulo gravado na
ficha do nó — "esta loja está na versão X" — e existe para responder isso sem
ligar para a loja.

Justamente por não travar nada é que ela envelhecia sem ninguém notar. A loja
rodou meses declarando `3.0.14` com a imagem em `3.0.22`, e a ficha na nuvem
mentia sobre a única coisa que ela conta.

A imagem sabe a própria versão, gravada no build (`ARG APP_VERSION`). A env
continua tendo precedência para quem roda fora de container ou precisa forçar
um valor num diagnóstico.
"""
import pytest


pytestmark = pytest.mark.django_db


def _resolver(monkeypatch, *, env="", build=""):
    """Reexecuta a decisão do settings com o ambiente que o teste montou."""
    import os

    monkeypatch.setenv("SYNC_APP_VERSION", env)
    monkeypatch.setenv("STARCHEF_APP_VERSION", build)

    # `decouple` lê de `os.environ` a cada chamada; a expressão é a mesma do
    # settings, reproduzida aqui para não recarregar o módulo inteiro.
    return os.environ.get("SYNC_APP_VERSION", "") or os.environ.get(
        "STARCHEF_APP_VERSION", ""
    )


def test_sem_env_a_versao_vem_da_IMAGEM(monkeypatch):
    """O caso normal em container: ninguém escreve nada e o valor está certo."""
    assert _resolver(monkeypatch, env="", build="3.0.29") == "3.0.29"


def test_a_env_tem_precedencia_para_forcar_um_valor(monkeypatch):
    """Quem roda fora de container, ou precisa forçar num diagnóstico."""
    assert _resolver(monkeypatch, env="9.9.9", build="3.0.29") == "9.9.9"


def test_sem_nenhum_dos_dois_fica_vazio_e_nao_quebra(monkeypatch):
    """Rótulo ausente não pode impedir a loja de sincronizar."""
    assert _resolver(monkeypatch, env="", build="") == ""


def test_o_settings_usa_ESSA_regra(monkeypatch):
    """O teste que fecha o buraco: a regra existir no teste não basta.

    Sem ele, voltar o settings para `config("SYNC_APP_VERSION", default="")`
    passaria despercebido — que é exatamente o estado anterior.
    """
    import importlib

    monkeypatch.delenv("SYNC_APP_VERSION", raising=False)
    monkeypatch.setenv("STARCHEF_APP_VERSION", "3.0.29-do-build")

    modulo = importlib.import_module("config.settings.sync")
    importlib.reload(modulo)

    assert modulo.SYNC_APP_VERSION == "3.0.29-do-build"


def test_a_versao_declarada_NAO_recusa_conexao(monkeypatch):
    """Ela é rótulo. Quem recusa é o protocolo, e isso não pode mudar.

    Se um dia `app_version` passar a barrar o HELLO, uma loja atrasada em uma
    versão para de sincronizar — e o campo deixa de ser seguro de preencher
    sozinho a partir do build.
    """
    import inspect

    from apps.synchronization.services import authentication

    fonte = inspect.getsource(authentication)
    # `app_version` só pode aparecer onde a presença é REGISTRADA.
    for linha in fonte.splitlines():
        if "app_version" in linha and "raise" in linha:
            pytest.fail(f"app_version virou trava de conexão: {linha.strip()}")
