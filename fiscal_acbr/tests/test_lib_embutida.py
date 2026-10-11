"""A lib que a Action embutiu na imagem vale quando a loja não montou outra.

A Action `fiscal_acbr.yml` pode baixar a libacbrnfe64.so (Secret
`ACBRLIB_SO_URL`) e pô-la DENTRO da imagem, em /opt/acbr: a loja deixa de
copiar o arquivo à mão. A montada em /app/libs continua tendo precedência —
é como uma loja testa uma versão nova da lib sem esperar uma imagem nova.
"""
import pytest

from app import motor


class LibFalsa:
    def __init__(self, caminho, _config):
        self.caminho = caminho
        self.nome = "acbrlib"


@pytest.fixture
def caminhos(monkeypatch, tmp_path):
    monkeypatch.delenv("ACBR_SIMULADOR", raising=False)
    montada, embutida = tmp_path / "montada.so", tmp_path / "embutida.so"
    monkeypatch.setenv("ACBR_LIB_PATH", str(montada))
    monkeypatch.setenv("ACBR_LIB_EMBUTIDA", str(embutida))
    monkeypatch.setattr("app.acbrlib.AcbrLib", LibFalsa)
    return montada, embutida


def test_sem_lib_montada_usa_a_embutida_na_imagem(caminhos):
    _montada, embutida = caminhos
    embutida.write_bytes(b"so")

    assert motor.criar_motor().caminho == str(embutida)


def test_a_montada_pela_loja_tem_precedencia(caminhos):
    montada, embutida = caminhos
    montada.write_bytes(b"so")
    embutida.write_bytes(b"so")

    assert motor.criar_motor().caminho == str(montada)


def test_sem_nenhuma_continua_recusando_com_a_providencia(caminhos):
    assert motor.criar_motor().nome == "ausente"


def test_lib_que_nao_carrega_nao_derruba_o_comunicador(caminhos, monkeypatch):
    """Arquivo corrompido ou de outra arquitetura: o `ctypes` levanta OSError
    no carregamento. Sem tratar, o container caía no boot e reiniciava em laço."""
    _montada, embutida = caminhos
    embutida.write_bytes(b"isto nao e uma .so")

    def falha(_caminho, _config):
        raise OSError("invalid ELF header")

    monkeypatch.setattr("app.acbrlib.AcbrLib", falha)

    escolhido = motor.criar_motor()

    assert escolhido.nome == "ausente"
    assert "invalid ELF header" in escolhido.mensagem
