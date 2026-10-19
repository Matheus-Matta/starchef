"""O documento fiscal neutro (`documento.py`) no leiaute INI da ACBrLib NFe.

Tradução pura, sem regra fiscal: totais, rateios, ICMS por regime e formas de
pagamento já vêm conferidos pelo documento — o mesmo que a Focus recebe. A
ACBrLib valida o resultado contra o schema (`NFE_Validar`) antes de assinar, e
é a homologação que confirma cada campo contra a SEFAZ do estado
(docs/FISCAL_ACBRLIB.md, "Roteiro de homologação").

O número, a série e o `cNF` vêm da nota já montada pelo backend: são eles que
compõem a chave de acesso, e a ACBrLib chega à MESMA chave que
`fiscal.build_access_key` calculou.
"""
from apps.invoices.acbrlib.emitente import Emitente
from apps.invoices.fiscal import only_digits
from apps.invoices.models import FiscalConfig

SEM_GTIN = "SEM GTIN"

#: O que a SEFAZ de HOMOLOGAÇÃO exige no lugar dos dados reais (rejeições 373
#: e 598). A Focus aplica isso do lado dela; aqui o XML nasce no backend.
TEXTO_HOMOLOGACAO_ITEM = "NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL"
TEXTO_HOMOLOGACAO_DESTINATARIO = "NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL"


def montar(documento, invoice, config, *, tp_emis="1", contingencia=None):
    """INI da nota. `contingencia` = {"dhCont": iso, "xJust": texto} no tpEmis=9."""
    linhas = []

    def secao(nome, campos):
        linhas.append(f"[{nome}]")
        for chave, valor in campos.items():
            if valor not in (None, ""):
                linhas.append(f"{chave}={_limpo(valor)}")
        linhas.append("")

    secao("infNFe", {"versao": "4.00"})
    secao("Identificacao", _identificacao(documento, invoice, tp_emis, contingencia))
    secao("Emitente", _emitente(Emitente(config)))
    homologacao = str(invoice.environment) == FiscalConfig.ENV_HOMOLOGATION
    destinatario = _destinatario(documento)
    if destinatario:
        if homologacao:
            destinatario["xNome"] = TEXTO_HOMOLOGACAO_DESTINATARIO
        secao("Destinatario", destinatario)
    simples = str(config.crt) in {FiscalConfig.CRT_SIMPLES, FiscalConfig.CRT_SIMPLES_EXCESSO}
    for n, item in enumerate(documento["items"], start=1):
        produto = _produto(item)
        if homologacao and n == 1 and str(invoice.document_model) == FiscalConfig.MODEL_NFCE:
            produto["xProd"] = TEXTO_HOMOLOGACAO_ITEM  # NFC-e: só o primeiro item (373)
        secao(f"Produto{n:03d}", produto)
        secao(f"ICMS{n:03d}", _icms(item, simples))
        secao(f"PIS{n:03d}", _tributo(item, "pis", "pPIS", "vPIS"))
        secao(f"COFINS{n:03d}", _tributo(item, "cofins", "pCOFINS", "vCOFINS"))
    secao("Total", {
        "vProd": documento["valor_produtos"], "vDesc": documento["valor_desconto"],
        "vOutro": documento["valor_outras_despesas"], "vNF": documento["valor_total"],
        "vTotTrib": documento["valor_total_tributos"],
    })
    secao("Transportador", {"modFrete": documento.get("modalidade_frete", "9")})
    formas = documento["formas_pagamento"]
    for n, pagamento in enumerate(formas, start=1):
        campos = _pagamento(pagamento)
        # O troco vai DENTRO da seção do pagamento: é só ali que a ACBrLib o lê
        # (`ACBrNFe.IniReader.pas`, `Ler_Pagamento`). Numa seção `[pag]` à
        # parte ele era ignorado, e toda venda com troco voltava 866.
        if n == len(formas) and documento.get("valor_troco"):
            campos["vTroco"] = documento["valor_troco"]
        secao(f"pag{n:03d}", campos)
    return "\n".join(linhas)


def _pagamento(pagamento):
    """Uma forma de pagamento no INI. `tpIntegra` é o grupo do cartão (391)."""
    campos = {"tPag": pagamento["forma_pagamento"], "vPag": pagamento["valor_pagamento"]}
    if pagamento.get("tipo_integracao"):
        campos["tpIntegra"] = pagamento["tipo_integracao"]
    return campos


def _identificacao(documento, invoice, tp_emis, contingencia):
    modelo = str(invoice.document_model)
    campos = {
        "cNF": (invoice.fiscal_payload or {}).get("cNF"),
        "natOp": documento["natureza_operacao"],
        "mod": modelo, "serie": invoice.series, "nNF": invoice.number,
        "dhEmi": data_acbr(documento["data_emissao"]), "tpNF": "1",
        "idDest": documento.get("local_destino", "1"),
        # 4 = DANFE NFC-e; 1 = DANFE retrato da NF-e.
        "tpImp": "4" if modelo == FiscalConfig.MODEL_NFCE else "1",
        "tpEmis": tp_emis, "tpAmb": invoice.environment, "finNFe": "1",
        "indFinal": documento.get("consumidor_final", "1"),
        "indPres": documento.get("presenca_comprador", "1"),
        "procEmi": "0", "verProc": "StarChef",
    }
    if contingencia:
        campos.update({**contingencia, "dhCont": data_acbr(contingencia["dhCont"])})
    return campos


def fuso_acbr():
    """O fuso em que `data_acbr` escreve as datas, como a ACBrLib quer: "-03:00".

    A data vai ao INI sem fuso, e a lib o acrescenta. Sem ele explícito, ela
    usava o do container (UTC) e a NFC-e saía três horas "atrasada" (704).
    """
    from django.utils import timezone

    bruto = timezone.localtime().strftime("%z")
    return f"{bruto[:3]}:{bruto[3:]}"


def data_acbr(valor):
    """Data no formato do INI da ACBrLib: `dd/mm/aaaa hh:mm:ss`, horário local."""
    from datetime import datetime

    from django.utils import timezone

    momento = valor if isinstance(valor, datetime) else datetime.fromisoformat(str(valor))
    if timezone.is_aware(momento):
        momento = timezone.localtime(momento)
    return momento.strftime("%d/%m/%Y %H:%M:%S")


def _emitente(config):
    """`config` é o `Emitente`: cadastro fiscal completado pelo restaurante."""
    return {
        "CNPJCPF": only_digits(config.cnpj), "xNome": config.corporate_name or config.trade_name,
        "xFant": config.trade_name, "IE": only_digits(config.ie), "CRT": config.crt,
        "xLgr": config.address_line, "nro": config.address_number or "SN",
        "xBairro": config.district, "cMun": config.city_ibge, "xMun": config.city,
        "UF": config.uf, "CEP": only_digits(config.zip_code),
    }


def _destinatario(documento):
    documento_id = documento.get("cpf_destinatario") or documento.get("cnpj_destinatario")
    if not documento_id:
        return None
    return {"CNPJCPF": documento_id, "xNome": documento.get("nome_destinatario"), "indIEDest": "9"}


def _produto(item):
    return {
        "cProd": item["codigo_produto"], "cEAN": SEM_GTIN, "xProd": item["descricao"],
        "NCM": item["codigo_ncm"], "CEST": item.get("codigo_cest"), "CFOP": item["cfop"],
        "uCom": item["unidade_comercial"], "qCom": item["quantidade_comercial"],
        "vUnCom": item["valor_unitario_comercial"], "vProd": item["valor_bruto"],
        "cEANTrib": SEM_GTIN, "uTrib": item["unidade_tributavel"],
        "qTrib": item["quantidade_tributavel"], "vUnTrib": item["valor_unitario_tributavel"],
        "vDesc": item.get("valor_desconto"), "vOutro": item.get("valor_outras_despesas"),
        "indTot": "1", "vTotTrib": item.get("valor_total_tributos"),
    }


def _icms(item, simples):
    situacao = item["icms_situacao_tributaria"]
    campos = {"orig": item["icms_origem"], ("CSOSN" if simples else "CST"): situacao}
    if item.get("icms_aliquota"):
        campos.update({"vBC": item["icms_base_calculo"], "pICMS": item["icms_aliquota"],
                       "vICMS": item["icms_valor"]})
    return campos


def _tributo(item, prefixo, campo_aliquota, campo_valor):
    campos = {"CST": item[f"{prefixo}_situacao_tributaria"], campo_valor: item[f"{prefixo}_valor"]}
    if item.get(f"{prefixo}_aliquota_porcentual"):
        campos["vBC"] = item[f"{prefixo}_base_calculo"]
        campos[campo_aliquota] = item[f"{prefixo}_aliquota_porcentual"]
    return campos


def _limpo(valor):
    """Uma linha de INI não pode quebrar: quebra de linha viraria outra chave."""
    return str(valor).replace("\r", " ").replace("\n", " ").strip()
