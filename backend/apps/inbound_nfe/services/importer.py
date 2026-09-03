import io
import zipfile
import logging
from typing import List, Dict, Any
from django.db import transaction
from django.utils import timezone
from apps.inbound_nfe.models import (
    InboundNFe,
    InboundNFeItem,
    DFeDistributionDocument,
)
from apps.inbound_nfe.services.xml_parser import parse_nfe_xml
from apps.inbound_nfe.services.matching import apply_mapping_to_item

logger = logging.getLogger(__name__)


def process_uploaded_xml(
    xml_content: str,
    account,
    restaurant=None,
    branch=None,
    filename: str = ""
) -> Dict[str, Any]:
    """
    Processa um texto XML de NF-e (completa ou resumo), criando ou atualizando
    o registro InboundNFe correspondente no banco.
    """
    parsed = parse_nfe_xml(xml_content)

    if not parsed.access_key:
        raise ValueError(f"Chave de acesso não localizada no arquivo {filename or 'XML'}.")

    with transaction.atomic():
        # 1. Buscar ou criar InboundNFe por access_key e account
        invoice = InboundNFe.all_objects.filter(
            account=account,
            access_key=parsed.access_key
        ).first()

        action = "updated" if invoice else "created"

        if not restaurant:
            from apps.restaurants.models import Restaurant
            restaurant = getattr(invoice, "restaurant", None) or Restaurant.all_objects.filter(account=account).first()

        if not invoice:
            invoice = InboundNFe(
                account=account,
                restaurant=restaurant,
                branch=branch,
                access_key=parsed.access_key,
                number=parsed.number,
                series=parsed.series,
                issue_date=parsed.issue_date,
                supplier_cnpj=parsed.supplier_cnpj,
                supplier_name=parsed.supplier_name,
                total_products=parsed.total_products,
                total_invoice=parsed.total_invoice,
                status=InboundNFe.STATUS_PENDING_MAPPING,
                full_xml=xml_content,
            )
            invoice.save()
        else:
            # Atualizar dados faltantes na nota existente
            if parsed.number and not invoice.number:
                invoice.number = parsed.number
            if parsed.series and not invoice.series:
                invoice.series = parsed.series
            if parsed.issue_date:
                invoice.issue_date = parsed.issue_date
            if parsed.supplier_cnpj:
                invoice.supplier_cnpj = parsed.supplier_cnpj
            if parsed.supplier_name:
                invoice.supplier_name = parsed.supplier_name
            if parsed.total_products:
                invoice.total_products = parsed.total_products
            if parsed.total_invoice:
                invoice.total_invoice = parsed.total_invoice

            invoice.full_xml = xml_content
            if restaurant and not invoice.restaurant:
                invoice.restaurant = restaurant
            if branch and not invoice.branch:
                invoice.branch = branch

            if invoice.status == InboundNFe.STATUS_SUMMARY:
                invoice.status = InboundNFe.STATUS_PENDING_MAPPING
            invoice.save()

        # 2. Processar itens da nota se o XML for completo
        if parsed.items:
            # Remove itens antigos caso existam para reprocessar com dados completos
            InboundNFeItem.all_objects.filter(invoice=invoice).delete()

            for p_item in parsed.items:
                item = InboundNFeItem.all_objects.create(
                    account=account,
                    restaurant=invoice.restaurant,
                    branch=invoice.branch,
                    invoice=invoice,
                    item_number=p_item.item_number,
                    supplier_code=p_item.supplier_code,
                    ean=p_item.ean,
                    description=p_item.description,
                    ncm=p_item.ncm,
                    cfop=p_item.cfop,
                    commercial_unit=p_item.commercial_unit,
                    commercial_quantity=p_item.commercial_quantity,
                    commercial_unit_value=p_item.commercial_unit_value,
                    taxable_unit=p_item.taxable_unit,
                    taxable_quantity=p_item.taxable_quantity,
                    taxable_unit_value=p_item.taxable_unit_value,
                    product_total=p_item.product_total,
                    discount=p_item.discount,
                    freight=p_item.freight,
                    insurance=p_item.insurance,
                    other_expenses=p_item.other_expenses,
                    ean_trib=p_item.ean_trib,
                    cest=p_item.cest,
                    tax_data=p_item.tax_data,
                )

                try:
                    apply_mapping_to_item(item, invoice.supplier_cnpj)
                except Exception as e:
                    logger.warning(f"Erro no matching do item '{item.description}': {e}")

            # Se todos os itens foram mapeados automaticamente, avança o status
            items_qs = InboundNFeItem.all_objects.filter(invoice=invoice)
            if items_qs.exists() and not items_qs.filter(ingredient__isnull=True, product__isnull=True).exists():
                invoice.status = InboundNFe.STATUS_PENDING_RECEIPT
            else:
                invoice.status = InboundNFe.STATUS_PENDING_MAPPING
            invoice.save(update_fields=['status'])

        # 3. Salvar o documento em DFeDistributionDocument para auditoria
        doc = DFeDistributionDocument.all_objects.filter(
            account=account,
            access_key=parsed.access_key
        ).first()

        if not doc:
            DFeDistributionDocument.all_objects.create(
                account=account,
                restaurant=invoice.restaurant,
                branch=invoice.branch,
                nsu=invoice.nsu or "MANUAL",
                schema="procNFe_v4.00.xsd" if parsed.items else "resNFe_v1.01.xsd",
                document_type=DFeDistributionDocument.DOC_PROC_NFE if parsed.items else DFeDistributionDocument.DOC_RES_NFE,
                access_key=parsed.access_key,
                xml=xml_content,
                processing_status=DFeDistributionDocument.PROCESSING_OK,
                processed_at=timezone.now(),
            )
        else:
            if parsed.items and doc.document_type != DFeDistributionDocument.DOC_PROC_NFE:
                doc.xml = xml_content
                doc.schema = "procNFe_v4.00.xsd"
                doc.document_type = DFeDistributionDocument.DOC_PROC_NFE
                doc.processing_status = DFeDistributionDocument.PROCESSING_OK
                doc.processed_at = timezone.now()
                doc.save(update_fields=['xml', 'schema', 'document_type', 'processing_status', 'processed_at'])

        if action == "created":
            try:
                from apps.inbound_nfe.services.notifications import notify_new_inbound_nfe
                notify_new_inbound_nfe(invoice)
            except Exception as e:
                logger.error(f"Erro ao notificar criação de NF-e via upload: {e}")

    return {
        "access_key": parsed.access_key,
        "number": parsed.number or invoice.number,
        "supplier_name": parsed.supplier_name or invoice.supplier_name,
        "action": action,
        "items_count": len(parsed.items),
        "status": invoice.status,
    }


def import_uploaded_files(
    files: list,
    account,
    restaurant=None,
    branch=None
) -> Dict[str, Any]:
    """
    Processa uma lista de arquivos enviados (Django UploadedFile), descompactando
    arquivos .zip ou processando arquivos .xml diretamente.
    """
    results = []
    errors = []

    for uploaded_file in files:
        fname = uploaded_file.name.lower()
        try:
            raw_bytes = uploaded_file.read()

            if fname.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
                    for zname in z.namelist():
                        if zname.lower().endswith(".xml") and not zname.startswith("__MACOSX"):
                            try:
                                xml_bytes = z.read(zname)
                                xml_text = _decode_xml_bytes(xml_bytes)
                                res = process_uploaded_xml(
                                    xml_text,
                                    account=account,
                                    restaurant=restaurant,
                                    branch=branch,
                                    filename=zname
                                )
                                results.append(res)
                            except Exception as e:
                                errors.append({"filename": zname, "error": str(e)})
            elif fname.endswith(".xml") or raw_bytes.strip().startswith(b"<"):
                xml_text = _decode_xml_bytes(raw_bytes)
                res = process_uploaded_xml(
                    xml_text,
                    account=account,
                    restaurant=restaurant,
                    branch=branch,
                    filename=uploaded_file.name
                )
                results.append(res)
            else:
                errors.append({
                    "filename": uploaded_file.name,
                    "error": "Tipo de arquivo não suportado. Envie arquivos .xml ou pacotes .zip."
                })
        except Exception as e:
            errors.append({"filename": uploaded_file.name, "error": str(e)})

    return {
        "total_processed": len(results),
        "total_errors": len(errors),
        "results": results,
        "errors": errors,
    }


def _decode_xml_bytes(data: bytes) -> str:
    """Decodifica bytes para string tentando UTF-8 e ISO-8859-1."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("iso-8859-1")
