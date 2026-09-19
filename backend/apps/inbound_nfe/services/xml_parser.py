from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime
from typing import List, Optional
import xml.etree.ElementTree as ET

# Namespaces da NFe
NAMESPACES = {
    'nfe': 'http://www.portalfiscal.inf.br/nfe'
}


DOC_RES_NFE = "resNFe"
DOC_PROC_NFE = "procNFe"
DOC_RES_EVENTO = "resEvento"
DOC_PROC_EVENTO = "procEventoNFe"
DOC_UNKNOWN = "unknown"


def detect_document_type(schema: str) -> str:
    """
    Identifica o tipo do documento pelo atributo schema do docZip.
    Exemplos de schemas da SEFAZ:
      - resNFe_v1.01.xsd
      - procNFe_v4.00.xsd
      - resEvento_v1.01.xsd
      - procEventoNFe_v1.00.xsd
    """
    s = (schema or "").lower()
    if s.startswith("resnfe"):
        return DOC_RES_NFE
    elif s.startswith("procnfe"):
        return DOC_PROC_NFE
    elif s.startswith("resevento"):
        return DOC_RES_EVENTO
    elif s.startswith("proceventonfe"):
        return DOC_PROC_EVENTO
    else:
        return DOC_UNKNOWN


@dataclass
class ParsedNFeItem:
    item_number: int
    supplier_code: str
    ean: str
    description: str
    ncm: str
    cfop: str
    commercial_unit: str
    commercial_quantity: Decimal
    commercial_unit_value: Decimal
    taxable_unit: str
    taxable_quantity: Decimal
    taxable_unit_value: Decimal
    product_total: Decimal
    discount: Decimal
    freight: Decimal
    insurance: Decimal
    other_expenses: Decimal
    # Campos adicionais do ponto 13
    ean_trib: str = ""
    cest: str = ""
    tax_data: dict = field(default_factory=dict)


@dataclass
class ParsedNFe:
    access_key: str
    number: str
    series: str
    issue_date: Optional[datetime]
    supplier_cnpj: str
    supplier_name: str
    total_products: Decimal
    total_invoice: Decimal
    nat_op: str = ""                    # Natureza da operação
    supplier_trade_name: str = ""       # xFant do emitente
    supplier_ie: str = ""               # IE do emitente
    items: List[ParsedNFeItem] = field(default_factory=list)


def parse_decimal(text: Optional[str]) -> Decimal:
    if not text:
        return Decimal('0')
    try:
        return Decimal(text)
    except Exception:
        return Decimal('0')


def extract_text(element: Optional[ET.Element], xpath: str, namespaces: dict = NAMESPACES) -> str:
    if element is None:
        return ""
    node = element.find(xpath, namespaces)
    if node is not None and node.text:
        return node.text.strip()
    return ""


def parse_nfe_xml(xml_content: str) -> ParsedNFe:
    """Parse nfeProc or resNFe into a ParsedNFe dataclass."""
    root = ET.fromstring(xml_content)

    # Identificar o tipo do documento (nfeProc ou resNFe)
    tag = root.tag
    is_res_nfe = 'resNFe' in tag
    is_nfe_proc = 'nfeProc' in tag

    if not is_res_nfe and not is_nfe_proc:
        # Tentar verificar se é a tag NFe direta
        if 'NFe' in tag:
            is_nfe_proc = True
        else:
            raise ValueError(f"Documento XML desconhecido ou não suportado: {tag}")

    # Para resNFe (PONTO 5: não possui produtos)
    if is_res_nfe:
        return _parse_res_nfe(root)

    # Para nfeProc (completo, PONTO 13: parser expandido)
    return _parse_nfe_proc(root)


def _parse_res_nfe(root: ET.Element) -> ParsedNFe:
    """
    Parse de resNFe (resumo).
    NÃO possui <det>/<prod>, portanto items=[] sempre.
    """
    access_key = extract_text(root, 'nfe:chNFe')
    supplier_cnpj = extract_text(root, 'nfe:CNPJ')
    supplier_name = extract_text(root, 'nfe:xNome')
    issue_date_str = extract_text(root, 'nfe:dhEmi')
    issue_date = datetime.fromisoformat(issue_date_str) if issue_date_str else None

    total_invoice = parse_decimal(extract_text(root, 'nfe:vNF'))

    return ParsedNFe(
        access_key=access_key,
        number="",  # resNFe geralmente não traz numero isolado, só chNFe
        series="",
        issue_date=issue_date,
        supplier_cnpj=supplier_cnpj,
        supplier_name=supplier_name,
        total_products=Decimal('0'),
        total_invoice=total_invoice,
        items=[]
    )


def _parse_nfe_proc(root: ET.Element) -> ParsedNFe:
    """
    Parse de nfeProc (NF-e completa).
    Extrai todos os campos do ponto 13 incluindo dados tributários.
    """
    inf_nfe = root.find('.//nfe:infNFe', NAMESPACES)
    if inf_nfe is None:
        raise ValueError("Tag infNFe não encontrada.")

    # Chave de acesso
    inf_nfe_id = inf_nfe.attrib.get('Id', '')
    access_key = inf_nfe_id.replace('NFe', '') if inf_nfe_id.startswith('NFe') else inf_nfe_id

    # ide
    ide = inf_nfe.find('nfe:ide', NAMESPACES)
    number = extract_text(ide, 'nfe:nNF')
    series = extract_text(ide, 'nfe:serie')
    nat_op = extract_text(ide, 'nfe:natOp')

    issue_date_str = extract_text(ide, 'nfe:dhEmi')
    if not issue_date_str:
        issue_date_str = extract_text(ide, 'nfe:dEmi')

    issue_date = None
    if issue_date_str:
        try:
            issue_date = datetime.fromisoformat(issue_date_str)
        except ValueError:
            pass

    # Emitente (PONTO 13: xFant, IE)
    emit = inf_nfe.find('nfe:emit', NAMESPACES)
    supplier_cnpj = extract_text(emit, 'nfe:CNPJ')
    supplier_name = extract_text(emit, 'nfe:xNome')
    supplier_trade_name = extract_text(emit, 'nfe:xFant')
    supplier_ie = extract_text(emit, 'nfe:IE')

    # Totais
    total = inf_nfe.find('nfe:total/nfe:ICMSTot', NAMESPACES)
    total_products = parse_decimal(extract_text(total, 'nfe:vProd')) if total is not None else Decimal('0')
    total_invoice = parse_decimal(extract_text(total, 'nfe:vNF')) if total is not None else Decimal('0')

    # Itens (PONTO 13: parser expandido com tributários)
    parsed_items = []
    dets = inf_nfe.findall('nfe:det', NAMESPACES)
    for det in dets:
        item_number = int(det.attrib.get('nItem', '0'))
        prod = det.find('nfe:prod', NAMESPACES)

        if prod is not None:
            supplier_code = extract_text(prod, 'nfe:cProd')
            ean = extract_text(prod, 'nfe:cEAN')
            if ean.upper() == 'SEM GTIN':
                ean = ""

            description = extract_text(prod, 'nfe:xProd')
            ncm = extract_text(prod, 'nfe:NCM')
            cest = extract_text(prod, 'nfe:CEST')
            cfop = extract_text(prod, 'nfe:CFOP')

            commercial_unit = extract_text(prod, 'nfe:uCom')
            commercial_quantity = parse_decimal(extract_text(prod, 'nfe:qCom'))
            commercial_unit_value = parse_decimal(extract_text(prod, 'nfe:vUnCom'))

            ean_trib = extract_text(prod, 'nfe:cEANTrib')
            if ean_trib.upper() == 'SEM GTIN':
                ean_trib = ""

            taxable_unit = extract_text(prod, 'nfe:uTrib')
            taxable_quantity = parse_decimal(extract_text(prod, 'nfe:qTrib'))
            taxable_unit_value = parse_decimal(extract_text(prod, 'nfe:vUnTrib'))

            product_total = parse_decimal(extract_text(prod, 'nfe:vProd'))

            discount = parse_decimal(extract_text(prod, 'nfe:vDesc'))
            freight = parse_decimal(extract_text(prod, 'nfe:vFrete'))
            insurance = parse_decimal(extract_text(prod, 'nfe:vSeg'))
            other_expenses = parse_decimal(extract_text(prod, 'nfe:vOutro'))

            # Dados tributários (PONTO 13: JSONField)
            tax_data = _extract_tax_data(det)

            parsed_item = ParsedNFeItem(
                item_number=item_number,
                supplier_code=supplier_code,
                ean=ean,
                description=description,
                ncm=ncm,
                cfop=cfop,
                commercial_unit=commercial_unit,
                commercial_quantity=commercial_quantity,
                commercial_unit_value=commercial_unit_value,
                taxable_unit=taxable_unit,
                taxable_quantity=taxable_quantity,
                taxable_unit_value=taxable_unit_value,
                product_total=product_total,
                discount=discount,
                freight=freight,
                insurance=insurance,
                other_expenses=other_expenses,
                ean_trib=ean_trib,
                cest=cest,
                tax_data=tax_data,
            )
            parsed_items.append(parsed_item)

    return ParsedNFe(
        access_key=access_key,
        number=number,
        series=series,
        issue_date=issue_date,
        supplier_cnpj=supplier_cnpj,
        supplier_name=supplier_name,
        total_products=total_products,
        total_invoice=total_invoice,
        nat_op=nat_op,
        supplier_trade_name=supplier_trade_name,
        supplier_ie=supplier_ie,
        items=parsed_items
    )


def _extract_tax_data(det: ET.Element) -> dict:
    """
    Extrai dados tributários de um <det> da NF-e.
    Retorna um dicionário com as informações de ICMS, PIS, COFINS, IPI.
    Armazenado como JSONField no InboundNFeItem.
    """
    tax = {}

    # ICMS
    imposto = det.find('nfe:imposto', NAMESPACES)
    if imposto is not None:
        icms_group = imposto.find('nfe:ICMS', NAMESPACES)
        if icms_group is not None:
            # O ICMS tem vários sub-elementos possíveis (ICMS00, ICMS10, ICMSSN102, etc.)
            for child in icms_group:
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                icms_data = {}
                for field_el in child:
                    field_tag = field_el.tag.split('}')[-1] if '}' in field_el.tag else field_el.tag
                    icms_data[field_tag] = field_el.text or ""
                tax['ICMS'] = {'tipo': tag, **icms_data}
                break  # Só o primeiro sub-elemento

        # PIS
        pis_group = imposto.find('nfe:PIS', NAMESPACES)
        if pis_group is not None:
            for child in pis_group:
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                pis_data = {}
                for field_el in child:
                    field_tag = field_el.tag.split('}')[-1] if '}' in field_el.tag else field_el.tag
                    pis_data[field_tag] = field_el.text or ""
                tax['PIS'] = {'tipo': tag, **pis_data}
                break

        # COFINS
        cofins_group = imposto.find('nfe:COFINS', NAMESPACES)
        if cofins_group is not None:
            for child in cofins_group:
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                cofins_data = {}
                for field_el in child:
                    field_tag = field_el.tag.split('}')[-1] if '}' in field_el.tag else field_el.tag
                    cofins_data[field_tag] = field_el.text or ""
                tax['COFINS'] = {'tipo': tag, **cofins_data}
                break

        # IPI
        ipi_group = imposto.find('nfe:IPI', NAMESPACES)
        if ipi_group is not None:
            ipi_data = {}
            for child in ipi_group:
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if len(child) > 0:
                    # Sub-elementos como IPITrib, IPINT
                    sub_data = {}
                    for field_el in child:
                        field_tag = field_el.tag.split('}')[-1] if '}' in field_el.tag else field_el.tag
                        sub_data[field_tag] = field_el.text or ""
                    ipi_data[tag] = sub_data
                else:
                    ipi_data[tag] = child.text or ""
            tax['IPI'] = ipi_data

    return tax
