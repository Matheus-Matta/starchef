"""A chave de acesso com a UF e o CNPJ de QUEM EMITE — os mesmos do XML.

A chave era montada com `config.uf`/`config.cnpj` crus. Em branco no cadastro
fiscal, o emitente da nota vinha do restaurante (`acbrlib.emitente.Emitente`),
mas a chave nascia com cUF "00". A ACBrLib consulta pela UF da chave: com
"00" ela procurava a sessão "NFCe_.A_P" no ACBrNFeServicos (o `CUFtoUF` da
ACBr devolve ".A" para código desconhecido) e toda consulta falhava.
"""
from apps.invoices.fiscal import UF_CODES, dv_mod11, only_digits


def emitente_da_chave(config):
    """`uf` e `cnpj` para `build_access_key`: o cadastro fiscal, completado
    pelo restaurante no que estiver em branco."""
    from apps.invoices.acbrlib.emitente import Emitente

    emitente = Emitente(config)
    return {"uf": emitente.uf, "cnpj": emitente.cnpj}


def corrigir(chave, config):
    """A chave já gravada com cUF/CNPJ zerados, refeita com os do emitente.

    Só os campos que faltaram mudam (e o dígito): número, série, cNF e data
    são os mesmos que a ACBrLib pôs no XML. Chave boa volta como está.
    """
    chave = only_digits(chave)
    if len(chave) != 44:
        return chave
    cuf_ok = chave[:2] in UF_CODES.values()
    cnpj_ok = chave[6:20].strip("0") != ""
    if cuf_ok and cnpj_ok:
        return chave
    emitente = emitente_da_chave(config)
    cuf = chave[:2] if cuf_ok else UF_CODES.get((emitente["uf"] or "").upper())
    cnpj = chave[6:20] if cnpj_ok else only_digits(emitente["cnpj"]).rjust(14, "0")[:14]
    if not cuf or not cnpj.strip("0"):
        return chave
    corpo = f"{cuf}{chave[2:6]}{cnpj}{chave[20:43]}"
    return f"{corpo}{dv_mod11(corpo)}"


def consultavel(chave):
    """A ACBrLib só acha o webservice com uma cUF de verdade no começo."""
    chave = only_digits(chave)
    return len(chave) == 44 and chave[:2] in UF_CODES.values()
