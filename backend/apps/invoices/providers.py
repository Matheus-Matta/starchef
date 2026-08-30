"""Provedores de emissao fiscal do StarChef."""

from django.utils.dateparse import parse_datetime

from apps.accounts.models import FocusNfeConfig
from apps.invoices.models import FiscalConfig, Invoice

_REGISTRY = {}


def register_provider(cls):
    _REGISTRY[cls.name] = cls
    return cls


def get_provider(name):
    return _REGISTRY.get(name or ManualFiscalProvider.name, ManualFiscalProvider)()


def fiscal_provider_unavailable_reason(config):
    provider_class = _REGISTRY.get(config.provider)
    if provider_class is None:
        return f"O provedor fiscal '{config.provider}' nao possui integracao de emissao configurada."
    return provider_class().unavailable_reason(config)


class FiscalProvider:
    name = "base"

    def emit(self, invoice, config):
        raise NotImplementedError

    def cancel(self, invoice, reason):
        raise NotImplementedError

    def status(self, invoice):
        raise NotImplementedError

    def unavailable_reason(self, config):
        return None


@register_provider
class ManualFiscalProvider(FiscalProvider):
    """Monta o documento local sem transmitir a SEFAZ."""

    name = "manual"

    def unavailable_reason(self, config):
        return "O provedor fiscal Manual esta selecionado e nao transmite notas fiscais."

    def emit(self, invoice, config):
        invoice.provider = self.name
        invoice.authorization_protocol = ""
        invoice.digest_value = ""
        invoice.status = Invoice.STATUS_PENDING
        invoice.error_message = ""
        return invoice

    def cancel(self, invoice, reason):
        invoice.status = Invoice.STATUS_CANCELLED
        invoice.error_message = reason or ""
        return invoice

    def status(self, invoice):
        return invoice.status


@register_provider
class FocusNfeProvider(FiscalProvider):
    """Emite NF-e/NFC-e pela Focus, sem comunicacao SEFAZ direta."""

    name = FiscalConfig.PROVIDER_FOCUS_NFE

    @staticmethod
    def _account_config(config):
        return FocusNfeConfig.objects.filter(account_id=config.account_id).first()

    def unavailable_reason(self, config):
        from apps.invoices.focus import company_payload_missing_fields

        issues = company_payload_missing_fields(config)
        if issues:
            return "A configuracao fiscal da Focus esta incompleta: " + " ".join(
                issue.get("message") or issue["label"] for issue in issues
            )
        account_config = self._account_config(config)
        if account_config is None:
            return "A configuracao da Focus NFe ainda nao foi criada para esta conta."
        base_url = account_config.production_url if config.environment == config.ENV_PRODUCTION else account_config.homologation_url
        if not base_url:
            environment = "producao" if config.environment == config.ENV_PRODUCTION else "homologacao"
            return f"A URL de {environment} da Focus NFe nao esta configurada para esta conta."
        token = config.focus_token_production if config.environment == config.ENV_PRODUCTION else config.focus_token_homologation
        if not token:
            return "A empresa ainda nao possui token Focus para o ambiente selecionado. Sincronize o cadastro fiscal."
        return None

    def _base_url(self, config):
        account_config = self._account_config(config)
        if account_config is None:
            raise RuntimeError("Focus NFe: configuracao da conta nao encontrada.")
        base_url = account_config.production_url if config.environment == config.ENV_PRODUCTION else account_config.homologation_url
        if not base_url:
            raise RuntimeError("Focus NFe: URL do ambiente selecionado nao configurada para esta conta.")
        return base_url.rstrip("/")

    def _timeout(self, config):
        account_config = self._account_config(config)
        return account_config.timeout_seconds if account_config is not None else 30

    @staticmethod
    def _reference(invoice):
        return invoice.provider_reference or f"starchef-{invoice.id}"

    @staticmethod
    def _token(config):
        token = (
            config.focus_token_production
            if config.environment == config.ENV_PRODUCTION
            else config.focus_token_homologation
        )
        if not token:
            raise RuntimeError(
                "Focus NFe: empresa ainda sem token para o ambiente selecionado. Sincronize o cadastro fiscal."
            )
        return token

    @staticmethod
    def _resource(document_model):
        if document_model == FiscalConfig.MODEL_NFE:
            return "nfe"
        if document_model == FiscalConfig.MODEL_NFCE:
            return "nfce"
        raise RuntimeError("Focus NFe: o modelo SAT/CF-e nao e suportado por este provedor.")

    @staticmethod
    def _payment_code(payment):
        method = payment.payment_method
        if method.method_type == "cash":
            return "01"
        if method.method_type == "pix":
            return "17"
        if method.method_type == "voucher":
            return "10"
        if method.method_type == "card":
            if payment.card_subtype == "debit":
                return "04"
            if payment.card_subtype == "credit":
                return "03"
        return "99"

    def _build_payments(self, invoice):
        from apps.payments.models import Payment

        payments = invoice.order.payments.filter(status=Payment.STATUS_APPROVED).select_related("payment_method")
        result = []
        for payment in payments:
            paid_value = payment.amount
            if payment.payment_method.method_type == "cash":
                paid_value += payment.change_amount
            result.append({"forma_pagamento": self._payment_code(payment), "valor_pagamento": str(paid_value)})
        return result or [{"forma_pagamento": "90", "valor_pagamento": "0.00"}]

    def _build_item(self, item, config):
        payload = {
            "numero_item": item.line_number,
            "codigo_produto": item.code or str(item.line_number),
            "descricao": item.description,
            "codigo_ncm": item.ncm or "00000000",
            "cfop": item.cfop or (config.default_profile and config.default_profile.cfop) or "5102",
            "unidade_comercial": item.unit,
            "quantidade_comercial": str(item.quantity),
            "valor_unitario_comercial": str(item.unit_price),
            "valor_bruto": str(item.total_price),
            "unidade_tributavel": item.unit,
            "quantidade_tributavel": str(item.quantity),
            "valor_unitario_tributavel": str(item.unit_price),
            "icms_origem": item.origem or "0",
            "icms_situacao_tributaria": item.csosn or item.cst_icms or "102",
            "pis_situacao_tributaria": item.pis_cst or "49",
            "pis_valor": str(item.pis_value),
            "cofins_situacao_tributaria": item.cofins_cst or "49",
            "cofins_valor": str(item.cofins_value),
            "valor_total_tributos": str(item.approx_tax_value),
        }
        if item.cest:
            payload["codigo_cest"] = item.cest
        if item.icms_rate:
            payload.update(
                {
                    "icms_base_calculo": str(item.icms_base),
                    "icms_aliquota": str(item.icms_rate),
                    "icms_valor": str(item.icms_value),
                }
            )
        if item.pis_rate:
            payload["pis_base_calculo"] = str(item.total_price)
            payload["pis_aliquota_porcentual"] = str(item.pis_rate)
        if item.cofins_rate:
            payload["cofins_base_calculo"] = str(item.total_price)
            payload["cofins_aliquota_porcentual"] = str(item.cofins_rate)
        return payload

    def _build_payload(self, invoice, config):
        payments = self._build_payments(invoice)
        change_total = sum(
            (
                payment.change_amount
                for payment in invoice.order.payments.filter(status="approved", payment_method__method_type="cash")
            ),
            start=0,
        )
        payload = {
            "natureza_operacao": "Venda ao consumidor",
            "data_emissao": invoice.fiscal_payload.get("emission"),
            "indicador_inscricao_estadual_destinatario": "9",
            "local_destino": "1",
            "consumidor_final": "1",
            "finalidade_emissao": "1",
            "presenca_comprador": "4" if invoice.order.order_type == "delivery" else "1",
            "cnpj_emitente": config.cnpj,
            "valor_produtos": str(invoice.products_total),
            "valor_desconto": str(invoice.discount_total),
            "valor_total": str(invoice.total_amount),
            "valor_total_tributos": str(invoice.tax_approx_total),
            "modalidade_frete": "9",
            "items": [self._build_item(item, config) for item in invoice.items.all()],
            "formas_pagamento": payments,
        }
        if change_total:
            payload["valor_troco"] = str(change_total)
        if invoice.recipient_cpf:
            payload["cpf_destinatario"] = invoice.recipient_cpf
            payload["nome_destinatario"] = invoice.recipient_name
        return payload

    def apply_response(self, invoice, data):
        status = data.get("status")
        if status == "autorizado":
            invoice.access_key = data.get("chave_nfe", invoice.access_key)
            if data.get("numero") not in (None, ""):
                invoice.number = str(data["numero"])
            if data.get("serie") not in (None, ""):
                invoice.series = int(data["serie"])
            invoice.authorization_protocol = data.get("protocolo", "")
            invoice.digest_value = data.get("codigo_verificador", "") or data.get("hash", "")
            invoice.xml_content = data.get("caminho_xml_nota_fiscal", "")
            invoice.danfe_url = data.get("caminho_danfe", "") or data.get("url_danfe", "")
            invoice.qr_code_data = data.get("qrcode_url", invoice.qr_code_data)
            authorized_at = data.get("data_autorizacao") or data.get("data_emissao")
            if authorized_at:
                invoice.authorized_at = parse_datetime(authorized_at)
            invoice.status = Invoice.STATUS_ISSUED
            invoice.error_message = ""
        elif status in {"processando_autorizacao", "processando"}:
            invoice.status = Invoice.STATUS_PENDING
            invoice.error_message = ""
        elif status == "cancelado":
            invoice.status = Invoice.STATUS_CANCELLED
            invoice.error_message = ""
        else:
            reason = data.get("mensagem_sefaz") or data.get("mensagem") or f"status={status}"
            invoice.status = Invoice.STATUS_ERROR
            invoice.error_message = str(reason)
            raise RuntimeError(f"Focus NFe rejeitou a nota: {reason}")
        return invoice

    def emit(self, invoice, config):
        import requests

        invoice.provider = self.name
        invoice.provider_reference = self._reference(invoice)
        resource = self._resource(invoice.document_model)
        response = requests.post(
            f"{self._base_url(config)}/v2/{resource}?ref={invoice.provider_reference}",
            json=self._build_payload(invoice, config),
            auth=(self._token(config), ""),
            timeout=self._timeout(config),
        )
        data = response.json() if response.content else {}
        if response.status_code >= 500 or data.get("status") is None:
            raise RuntimeError(f"Focus NFe: resposta inesperada (HTTP {response.status_code}): {data}")
        return self.apply_response(invoice, data)

    def cancel(self, invoice, reason):
        import requests

        config = FiscalConfig.objects.filter(branch=invoice.branch, is_active=True).first()
        if not config:
            raise RuntimeError("Sem configuracao fiscal para cancelar a nota.")
        resource = self._resource(invoice.document_model)
        response = requests.delete(
            f"{self._base_url(config)}/v2/{resource}/{self._reference(invoice)}",
            json={"justificativa": reason or "Cancelamento solicitado pelo operador."},
            auth=(self._token(config), ""),
            timeout=self._timeout(config),
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Focus NFe: falha ao cancelar (HTTP {response.status_code}): {response.text}")
        data = response.json() if response.content else {"status": "cancelado"}
        return self.apply_response(invoice, data)

    def status(self, invoice):
        import requests

        config = FiscalConfig.objects.filter(branch=invoice.branch, is_active=True).first()
        if not config:
            raise RuntimeError("Sem configuracao fiscal para consultar a nota.")
        resource = self._resource(invoice.document_model)
        response = requests.get(
            f"{self._base_url(config)}/v2/{resource}/{self._reference(invoice)}",
            auth=(self._token(config), ""),
            timeout=self._timeout(config),
        )
        data = response.json() if response.content else {}
        if response.status_code >= 400:
            raise RuntimeError(f"Focus NFe: falha ao consultar (HTTP {response.status_code}): {data}")
        self.apply_response(invoice, data)
        return invoice.status
