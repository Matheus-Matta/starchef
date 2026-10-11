"""O contrato com o backend (docs/FISCAL_ACBRLIB.md, "Contrato").

O comunicador NÃO guarda configuração: quem emite, onde e com qual certificado
chega em toda chamada. Assim ele reinicia sem perder nada — a nota pendente
mora no banco do backend.
"""
from pydantic import BaseModel


class Certificado(BaseModel):
    pfx_base64: str = ""
    senha: str = ""


class Csc(BaseModel):
    id: str = ""
    token: str = ""


class Contexto(BaseModel):
    referencia: str = ""
    modelo: str = "65"
    ambiente: str = "2"  # 1 = produção, 2 = homologação
    uf: str
    cnpj: str
    certificado: Certificado = Certificado()
    csc: Csc = Csc()


class Emitir(Contexto):
    ini: str
    tp_emis: str = "1"  # "9" = só assina (contingência offline), não transmite


class Transmitir(Contexto):
    xml: str


class Consultar(Contexto):
    chave: str


class Cancelar(Contexto):
    chave: str
    protocolo: str
    justificativa: str
