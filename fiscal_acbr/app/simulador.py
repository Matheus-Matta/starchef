"""SEFAZ simulada: para desenvolver e testar a cadeia sem a lib nem certificado.

`ACBR_SIMULAR_SEFAZ` escolhe o comportamento: `online` (autoriza), `fora`
(sem comunicação), `lenta` (resposta perdida depois do envio) e `recusa`. A
chave é calculada do INI do mesmo jeito que a SEFAZ faria — e do jeito que o
backend calculou —, então o resto do sistema não percebe a diferença.

O QUE ELE NUNCA FAZ é se passar pela SEFAZ de verdade. Respondia "Autorizado o
uso da NF-e" — a frase real — e autorizava até em PRODUÇÃO: na nuvem de teste
toda nota saía "emitida", com protocolo e QR Code que não levavam a lugar
nenhum, e quem testava concluía que a emissão funcionava. Agora a resposta diz
que é simulada, e produção é recusada.
"""
import os
from datetime import datetime

from app import ini, sefaz

_UF = {"SP": "35", "RJ": "33", "MG": "31", "PR": "41", "SC": "42", "RS": "43", "BA": "29",
       "GO": "52", "DF": "53", "ES": "32", "PE": "26", "CE": "23"}


def _dv(chave43):
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    total = sum(int(d) * pesos[i % 8] for i, d in enumerate(reversed(chave43)))
    dv = 11 - total % 11
    return 0 if dv >= 10 else dv


def chave_do_ini(texto, uf, cnpj):
    ident = ini.ler(texto).get("identificacao", {})
    emissao = datetime.strptime(ident["dhemi"], "%d/%m/%Y %H:%M:%S")
    chave43 = (f"{_UF.get(uf.upper(), '00')}{emissao:%y%m}{cnpj.rjust(14, '0')}"
               f"{ident['mod'].rjust(2, '0')}{ident['serie'].rjust(3, '0')}"
               f"{ident['nnf'].rjust(9, '0')}{ident['tpemis']}{ident['cnf'].rjust(8, '0')}")
    return f"{chave43}{_dv(chave43)}"


#: O motivo da "autorização": diz o que ela é, para ninguém tomá-la por real.
MOTIVO_SIMULADO = "SIMULADO — sem valor fiscal (nenhuma SEFAZ foi consultada)"

PRODUCAO = "1"


def _recusar_producao(pedido):
    if str(getattr(pedido, "ambiente", "")) == PRODUCAO:
        raise sefaz.FalhaDeConfiguracao(
            "SEFAZ SIMULADA não emite em PRODUÇÃO: nenhuma nota foi enviada à SEFAZ. "
            "Para emitir de verdade, instale a libacbrnfe64.so e tire o "
            "ACBR_SIMULADOR=1 do serviço fiscal-acbr (docs/FISCAL_ACBRLIB.md)."
        )


class Simulador:
    nome = "simulador"

    def __init__(self):
        self.autorizadas = {}

    def _modo(self):
        return os.environ.get("ACBR_SIMULAR_SEFAZ", "online")

    def _transmitir(self, chave, xml_assinado):
        modo = self._modo()
        if modo == "fora":
            raise sefaz.FalhaDeComunicacao("SEFAZ simulada fora do ar.")
        if modo == "lenta":
            self.autorizadas[chave] = xml_assinado  # autorizou, mas a resposta se perdeu
            raise sefaz.FalhaIncerta("Resposta da SEFAZ simulada perdida depois do envio.")
        if modo == "recusa":
            return {"situacao": "rejeitada", "cstat": "778", "motivo": "NCM inexistente (simulado)"}
        self.autorizadas[chave] = xml_assinado
        return self._autorizada(chave, xml_assinado)

    def _autorizada(self, chave, xml):
        return {"situacao": "autorizada", "cstat": "100", "motivo": MOTIVO_SIMULADO,
                "chave": chave, "protocolo": f"1{chave[-14:]}",
                "recebido_em": datetime.now().astimezone().isoformat(timespec="seconds"),
                "xml": f"<nfeProc>{xml}<protNFe>{chave}</protNFe></nfeProc>"}

    def emitir(self, pedido):
        _recusar_producao(pedido)
        chave = chave_do_ini(pedido.ini, pedido.uf, pedido.cnpj)
        assinado = f"<NFe Id=\"NFe{chave}\" tpEmis=\"{pedido.tp_emis}\"/>"
        if pedido.tp_emis == "9":
            return {"situacao": "contingencia", "chave": chave, "xml": assinado,
                    "qrcode": f"https://qr.simulado?p={chave}|2|{pedido.ambiente}|offline"}
        return self._transmitir(chave, assinado)

    def transmitir(self, pedido):
        _recusar_producao(pedido)
        chave = pedido.xml.split('Id="NFe')[1][:44]
        return self._transmitir(chave, pedido.xml)

    def consultar(self, pedido):
        if pedido.chave in self.autorizadas:
            return self._autorizada(pedido.chave, self.autorizadas[pedido.chave])
        return {"situacao": "nao_encontrada", "cstat": "217", "motivo": "NF-e não consta na base"}

    def cancelar(self, pedido):
        if pedido.chave not in self.autorizadas:
            return {"situacao": "rejeitada", "cstat": "217", "motivo": "NF-e não consta na base"}
        return {"situacao": "cancelada", "cstat": "135", "motivo": "Evento registrado",
                "chave": pedido.chave, "protocolo": f"9{pedido.chave[-14:]}"}

    def status_servico(self, _pedido):
        online = self._modo() != "fora"
        return {"online": online, "cstat": "107" if online else "108",
                "motivo": "Serviço em operação" if online else "Serviço paralisado (simulado)"}
