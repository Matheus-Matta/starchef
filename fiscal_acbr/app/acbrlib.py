"""A ACBrLib NFe (versão MT) via ctypes — a biblioteca original, sem modificar.

Sequência oficial: `NFE_Inicializar` → `NFE_LimparLista` → `NFE_CarregarINI` →
`NFE_Assinar` → `NFE_Validar` → `NFE_Enviar` (ou `NFE_Consultar`/`NFE_Cancelar`).
Um retorno 0 é a CHAMADA que deu certo; a autorização é o cStat (`sefaz.py`).

A lib não é reentrante para o mesmo handle: um handle por processo, atrás de
uma trava — e o uvicorn roda com UM worker (Dockerfile). A configuração (UF,
ambiente, modelo, certificado, CSC, forma de emissão) é gravada a cada chamada,
porque o comunicador atende qualquer CNPJ que o backend mandar.

Os valores das enumerações (`Ambiente`, `ModeloDF`, `FormaEmissao`) seguem a
documentação da ACBrLib e são os primeiros a conferir na homologação.
"""
import ctypes
import re
import threading

from app import ini, sefaz

TAMANHO = 1024 * 512
FORMA_EMISSAO = {"1": "0", "9": "8"}  # teNormal, teOffLine (NFC-e)
_QR = re.compile(r"<qrCode>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</qrCode>", re.S)
_DIGEST = re.compile(r"<DigestValue>(.*?)</DigestValue>", re.S)
_CHAVE = re.compile(r'Id="NFe(\d{44})"')


class AcbrLib:
    nome = "acbrlib"

    def __init__(self, caminho, arquivo_config="/app/config/ACBrLib.ini"):
        self.lib = ctypes.CDLL(caminho)
        self.trava = threading.Lock()
        self.handle = ctypes.c_void_p()
        self._ok(self.lib.NFE_Inicializar(ctypes.byref(self.handle), _c(arquivo_config), _c("")))

    # ── chamadas de baixo nível ───────────────────────────────────────────
    def _ok(self, codigo):
        if codigo < 0:
            raise _classificar(self._ultimo_retorno())

    def _ultimo_retorno(self):
        tamanho = ctypes.c_int(TAMANHO)
        buffer = ctypes.create_string_buffer(TAMANHO)
        self.lib.NFE_UltimoRetorno(self.handle, buffer, ctypes.byref(tamanho))
        return buffer.value.decode("utf-8", "replace")

    def _texto(self, funcao, *args):
        tamanho = ctypes.c_int(TAMANHO)
        buffer = ctypes.create_string_buffer(TAMANHO)
        self._ok(funcao(self.handle, *args, buffer, ctypes.byref(tamanho)))
        if tamanho.value > TAMANHO:  # a resposta não coube: a lib a guarda no último retorno
            return self._ultimo_retorno()
        return buffer.value.decode("utf-8", "replace")

    def _configurar(self, pedido, tp_emis="1"):
        valores = {
            ("DFe", "UF"): pedido.uf,
            ("DFe", "DadosPFX"): pedido.certificado.pfx_base64,
            ("DFe", "Senha"): pedido.certificado.senha,
            ("NFe", "Ambiente"): "0" if pedido.ambiente == "1" else "1",
            ("NFe", "ModeloDF"): "1" if pedido.modelo == "65" else "0",
            ("NFe", "IdCSC"): pedido.csc.id,
            ("NFe", "CSC"): pedido.csc.token,
            ("NFe", "VersaoQRCode"): "2",
            ("NFe", "FormaEmissao"): FORMA_EMISSAO.get(tp_emis, "0"),
        }
        for (secao, chave), valor in valores.items():
            self._ok(self.lib.NFE_ConfigGravarValor(self.handle, _c(secao), _c(chave), _c(valor or "")))

    def _xml_atual(self):
        return self._texto(self.lib.NFE_ObterXml, ctypes.c_int(0))

    # ── operações do contrato ─────────────────────────────────────────────
    def emitir(self, pedido):
        with self.trava:
            self._configurar(pedido, pedido.tp_emis)
            self._ok(self.lib.NFE_LimparLista(self.handle))
            self._ok(self.lib.NFE_CarregarINI(self.handle, _c(pedido.ini)))
            self._ok(self.lib.NFE_Assinar(self.handle))
            self._ok(self.lib.NFE_Validar(self.handle))
            assinado = self._xml_atual()
            if pedido.tp_emis == "9":
                return {"situacao": "contingencia", **_do_xml(assinado), "xml": assinado}
            return self._enviar(pedido)

    def transmitir(self, pedido):
        with self.trava:
            self._configurar(pedido, "9")
            self._ok(self.lib.NFE_LimparLista(self.handle))
            self._ok(self.lib.NFE_CarregarXML(self.handle, _c(pedido.xml)))
            return self._enviar(pedido)

    def _enviar(self, pedido):
        resposta = ini.ler(self._texto(self.lib.NFE_Enviar, ctypes.c_int(1),
                                       ctypes.c_bool(False), ctypes.c_bool(True), ctypes.c_bool(False)))
        nota = ini.primeira(resposta, "nfe", "retorno", "envio")
        cstat = nota.get("cstat", "")
        if cstat in sefaz.DUPLICIDADE:
            return self._consultar_chave(pedido, nota.get("chdfe") or _do_xml(self._xml_atual())["chave"])
        return self._resultado(nota, xml=self._xml_atual())

    def consultar(self, pedido):
        with self.trava:
            self._configurar(pedido)
            return self._consultar_chave(pedido, pedido.chave)

    def _consultar_chave(self, _pedido, chave):
        resposta = ini.ler(self._texto(self.lib.NFE_Consultar, _c(chave), ctypes.c_bool(False)))
        return self._resultado(ini.primeira(resposta, "consulta", "retorno"), chave=chave)

    def cancelar(self, pedido):
        with self.trava:
            self._configurar(pedido)
            resposta = ini.ler(self._texto(self.lib.NFE_Cancelar, _c(pedido.chave),
                                           _c(pedido.justificativa), _c(pedido.cnpj), ctypes.c_int(1)))
            return self._resultado(ini.primeira(resposta, "evento", "cancelamento", "retorno"),
                                   chave=pedido.chave)

    def status_servico(self, pedido):
        with self.trava:
            self._configurar(pedido)
            resposta = ini.primeira(ini.ler(self._texto(self.lib.NFE_StatusServico)), "status")
        cstat = resposta.get("cstat", "")
        return {"online": cstat == "107", "cstat": cstat, "motivo": resposta.get("xmotivo", "")}

    @staticmethod
    def _resultado(campos, *, xml="", chave=""):
        cstat = campos.get("cstat", "")
        return {"situacao": sefaz.situacao(cstat), "cstat": cstat, "motivo": campos.get("xmotivo", ""),
                "chave": campos.get("chdfe") or campos.get("chnfe") or chave,
                "protocolo": campos.get("nprot", ""), "recebido_em": campos.get("dhrecbto", ""),
                "xml": xml, **({k: v for k, v in _do_xml(xml).items() if k != "chave"} if xml else {})}


def _do_xml(xml):
    """Chave, QR Code e digest de um XML assinado."""
    def achar(padrao):
        return (padrao.search(xml or "") or [None, ""])[1]

    return {"chave": achar(_CHAVE), "qrcode": achar(_QR).strip(), "digest_value": achar(_DIGEST)}


def _classificar(mensagem):
    """A falha da lib vira a família do contrato (docs/FISCAL_ACBRLIB.md)."""
    texto = mensagem.lower()
    if any(p in texto for p in ("certificado", "pfx", "senha", "csc", "biblioteca")):
        return sefaz.FalhaDeConfiguracao(mensagem)
    if any(p in texto for p in ("schema", "validar", "rejei", "ini inv")):
        return sefaz.DocumentoInvalido(mensagem)
    if any(p in texto for p in ("timeout", "tempo limite", "timed out", "read timed")):
        return sefaz.FalhaIncerta(mensagem)
    if any(p in texto for p in ("socket", "conex", "http", "host", "resolver", "winsock")):
        return sefaz.FalhaDeComunicacao(mensagem)
    # Falha não reconhecida durante o envio: tratar como INCERTA é o lado seguro —
    # o backend consulta antes de qualquer reenvio.
    return sefaz.FalhaIncerta(mensagem)


def _c(texto):
    return str(texto).encode("utf-8")
