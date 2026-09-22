import io, json, logging, zipfile
from typing import Dict, Any
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
    xml_content: str, account, restaurant=None, branch=None, filename: str = "", manifest_meta: dict = None
) -> Dict[str, Any]:
    """
    Processa um texto XML de NF-e (completa ou resumo), criando ou atualizando
    o registro InboundNFe correspondente no banco.
    """
    parsed = parse_nfe_xml(xml_content)
    if not parsed.access_key:
        raise ValueError(f"Chave de acesso não localizada no arquivo {filename or 'XML'}.")

    if not parsed.number and len(parsed.access_key) == 44:
        try:
            parsed.series = str(int(parsed.access_key[22:25]))
            parsed.number = str(int(parsed.access_key[25:34]))
        except Exception:
            pass

    is_summary = not parsed.items and ("resNFe" in xml_content or "<det" not in xml_content)

    with transaction.atomic():
        invoice = InboundNFe.all_objects.filter(
            account=account,
            access_key=parsed.access_key
        ).first()

        action = "updated" if invoice else "created"
        if not restaurant:
            from apps.restaurants.models import Restaurant
            restaurant = getattr(invoice, "restaurant", None) or Restaurant.all_objects.filter(account=account).first()

        meta = (manifest_meta or {}).get(parsed.access_key, {})
        existing_doc = DFeDistributionDocument.all_objects.filter(
            account=account, access_key=parsed.access_key
        ).exclude(nsu__in=("", "MANUAL")).order_by("-nsu").first()
        initial_nsu = meta.get("nsu") or (existing_doc.nsu if existing_doc else "")

        if not invoice:
            status = InboundNFe.STATUS_SUMMARY if is_summary else InboundNFe.STATUS_PENDING_MAPPING
            xml_status = InboundNFe.XML_STATUS_SUMMARY_ONLY if is_summary else InboundNFe.XML_STATUS_FULL_XML_AVAILABLE
            distribution_type = InboundNFe.DISTRIBUTION_SUMMARY if is_summary else InboundNFe.DISTRIBUTION_FULL
            invoice = InboundNFe(
                account=account, restaurant=restaurant, branch=branch,
                access_key=parsed.access_key, nsu=initial_nsu,
                number=parsed.number, series=parsed.series, issue_date=parsed.issue_date,
                supplier_cnpj=parsed.supplier_cnpj, supplier_name=parsed.supplier_name,
                total_products=parsed.total_products, total_invoice=parsed.total_invoice,
                status=status, distribution_type=distribution_type, xml_status=xml_status,
                manifestation_status=meta.get("manifestation_status") or "none",
                summary_xml=xml_content if is_summary else "", full_xml="" if is_summary else xml_content,
            )
            invoice.save()
        else:
            if initial_nsu and (not invoice.nsu or invoice.nsu == "MANUAL"): invoice.nsu = initial_nsu
            if meta.get("manifestation_status") and invoice.manifestation_status == "none": invoice.manifestation_status = meta["manifestation_status"]
            for attr in ("number", "series", "issue_date", "supplier_cnpj", "supplier_name", "total_products", "total_invoice"):
                val = getattr(parsed, attr, None)
                if val and not getattr(invoice, attr, None):
                    setattr(invoice, attr, val)

            if is_summary:
                if not invoice.summary_xml:
                    invoice.summary_xml = xml_content
            else:
                invoice.full_xml = xml_content
                invoice.xml_status = InboundNFe.XML_STATUS_FULL_XML_AVAILABLE
                invoice.distribution_type = InboundNFe.DISTRIBUTION_FULL
                if invoice.status == InboundNFe.STATUS_SUMMARY:
                    invoice.status = InboundNFe.STATUS_PENDING_MAPPING

            if restaurant and not invoice.restaurant:
                invoice.restaurant = restaurant
            if branch and not invoice.branch:
                invoice.branch = branch

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
                doc.xml, doc.schema = xml_content, "procNFe_v4.00.xsd"
                doc.document_type = DFeDistributionDocument.DOC_PROC_NFE
                doc.processing_status, doc.processed_at = DFeDistributionDocument.PROCESSING_OK, timezone.now()
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
    """Processa uma lista de arquivos enviados (.zip ou .xml)."""
    results, errors = [], []
    for uploaded_file in files:
        fname = uploaded_file.name.lower()
        try:
            raw_bytes = uploaded_file.read()
            if fname.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
                    names = z.namelist()
                    m_file = next((zn for zn in names if zn.split("/")[-1].lower() == "manifest.json"), None)
                    try:
                        manifest = json.loads(z.read(m_file).decode("utf-8")) if m_file else {}
                    except Exception:
                        manifest = {}
                    ult = manifest.get("ult_nsu")
                    if ult and restaurant:
                        from apps.inbound_nfe.models import DFeSyncState
                        st, _ = DFeSyncState.all_objects.get_or_create(account=account, restaurant=restaurant, defaults={"cnpj": getattr(restaurant, "cnpj", "") or getattr(account, "cnpj", "")})
                        if not st.ult_nsu or str(ult) > str(st.ult_nsu):
                            st.ult_nsu, st.max_nsu = ult, manifest.get("max_nsu") or ult
                            st.save(update_fields=["ult_nsu", "max_nsu"])
                    m_notes = manifest.get("notes", {})
                    for zname in names:
                        clean = zname.replace("\\", "/")
                        basename = clean.split("/")[-1]
                        if basename.lower().endswith(".xml") and not basename.startswith(".") and not clean.startswith("__MACOSX"):
                            try:
                                res = process_uploaded_xml(_decode_xml_bytes(z.read(zname)), account, restaurant, branch, basename, manifest_meta=m_notes)
                                results.append(res)
                            except Exception as e:
                                errors.append({"filename": basename, "error": str(e)})
            elif fname.endswith(".xml") or raw_bytes.strip().startswith(b"<"):
                res = process_uploaded_xml(_decode_xml_bytes(raw_bytes), account, restaurant, branch, uploaded_file.name)
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
