"""Provedores de emissao fiscal do StarChef."""

from decimal import ROUND_HALF_UP, Decimal

from django.utils.dateparse import parse_datetime

from apps.accounts.models import FocusNfeConfig
from apps.invoices.models import FiscalConfig, Invoice

_REGISTRY = {}
TWO_PLACES = Decimal("0.01")


class FiscalProviderError(RuntimeError):
    """Base das falhas de emissao.

    O servico precisa saber POR QUE a emissao falhou para decidir o que fazer:
    reenviar, parar, ou consultar antes de reenviar. Antes tudo era
    ``RuntimeError`` e uma rejeicao tributaria era tratada igual a uma queda de
    rede — o que gerava retransmissao infinita de uma nota que a SEFAZ ja
    recusou em definitivo.
    """


class FiscalRejection(FiscalProviderError):
    """Documento recusado: a SEFAZ negou, ou ele nem e valido para transmitir.

    Nao existe retentativa automatica: reenviar repete a mesma recusa. So sai
    do lugar depois que alguem corrigir o cadastro ou o pedido.
    """


class FiscalConfigurationError(FiscalProviderError):
    """Certificado, token, CSC ou URL ausente/invalido.

    Nenhuma nota da empresa sai enquanto nao for corrigido, entao nao adianta
    tratar como indisponibilidade momentanea.
    """


class FiscalUnavailable(FiscalProviderError):
    """Falha tecnica temporaria: rede, timeout, 5xx, SEFAZ fora do ar.

    E a UNICA familia que justifica retentativa automatica.
    """


class FiscalNotFound(FiscalProviderError):
    """A consulta nao encontrou o documento no provedor.

    Nao e recusa: e a resposta esperada para uma nota que nunca chegou la. E a
    unica forma de resolver com seguranca uma nota em reconciliacao — se o
    provedor nao tem o documento, retransmitir nao duplica nada.
    """


class FiscalAmbiguous(FiscalProviderError):
    """A emissao pode ter acontecido, mas o resultado nao foi confirmado.

    Exige consulta pela referencia antes de qualquer reenvio — reenviar as
    cegas e o caminho para duplicar documento fiscal.
    """


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

    #: O provider realmente transmite o documento para fora do StarChef?
    #: Uma nota `pending` de um provider que nao transmite nao esta esperando
    #: autorizacao de ninguem — nao adianta reconsultar nem retransmitir.
    transmits = False

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
    transmits = True

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
            raise FiscalConfigurationError("Focus NFe: configuracao da conta nao encontrada.")
        base_url = account_config.production_url if config.environment == config.ENV_PRODUCTION else account_config.homologation_url
        if not base_url:
            raise FiscalConfigurationError("Focus NFe: URL do ambiente selecionado nao configurada para esta conta.")
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
            raise FiscalConfigurationError(
                "Focus NFe: empresa ainda sem token para o ambiente selecionado. Sincronize o cadastro fiscal."
            )
        return token

    @staticmethod
    def _resource(document_model):
        if document_model == FiscalConfig.MODEL_NFE:
            return "nfe"
        if document_model == FiscalConfig.MODEL_NFCE:
            return "nfce"
        raise FiscalConfigurationError("Focus NFe: o modelo SAT/CF-e nao e suportado por este provedor.")

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

    @staticmethod
    def _allocate_total(items, total):
        """Rateia um total fiscal entre os itens sem perder centavos."""

        total = Decimal(total).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        if not total:
            return {}

        products_total = sum((item.total_price for item in items), start=Decimal("0.00"))
        if products_total <= 0:
            raise FiscalRejection("Focus NFe: nao e possivel ratear valores em uma nota sem produtos.")

        allocations = {}
        allocated = Decimal("0.00")
        for item in items[:-1]:
            amount = (total * item.total_price / products_total).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            amount = min(amount, total - allocated)
            allocations[item.pk] = amount
            allocated += amount
        allocations[items[-1].pk] = total - allocated
        return allocations

    @staticmethod
    def _validate_totals(invoice, items):
        """Valida e devolve despesas que explicam o total da NF-e."""

        items_total = sum((item.total_price for item in items), start=Decimal("0.00")).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
        products_total = invoice.products_total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        discount_total = invoice.discount_total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        invoice_total = invoice.total_amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        if items_total != products_total:
            raise FiscalRejection(
                "Focus NFe: total dos itens difere do valor dos produtos "
                f"({items_total} != {products_total})."
            )
        if discount_total < 0 or discount_total > products_total:
            raise FiscalRejection("Focus NFe: o desconto fiscal deve estar entre zero e o valor dos produtos.")

        other_expenses = invoice_total - products_total + discount_total
        if other_expenses < 0:
            raise FiscalRejection(
                "Focus NFe: total fiscal inconsistente; o valor total deve corresponder a "
                "produtos - desconto + outras despesas."
            )
        return other_expenses

    @staticmethod
    def _icms_situation(item, config):
        """Situacao tributaria do ICMS, escolhida pelo REGIME da empresa.

        Antes era `item.csosn or item.cst_icms or "102"`, sem olhar o CRT. Numa
        empresa de regime normal isso mandava um CSOSN — que so existe no
        Simples — e a SEFAZ recusava de qualquer jeito: o fallback nao evitava
        problema nenhum, so trocava "cadastro incompleto" por "rejeicao".

        Por isso o regime normal sem CST falha aqui mesmo com
        `strict_fiscal_profile` desligado: nao existe valor padrao seguro, e
        adivinhar um CST produziria um documento aceito e errado — pior que a
        recusa. No Simples, CSOSN 102 (tributada sem permissao de credito)
        continua valendo como padrao do varejo.
        """
        if str(config.crt) in {FiscalConfig.CRT_SIMPLES, FiscalConfig.CRT_SIMPLES_EXCESSO}:
            return item.csosn or "102"
        if item.cst_icms:
            return item.cst_icms
        raise FiscalRejection(
            f'Focus NFe: o item "{item.description}" esta sem CST do ICMS e a empresa '
            "esta em regime normal (CRT 3). Informe o CST no perfil fiscal do produto — "
            "CSOSN so vale para o Simples Nacional."
        )

    def _build_item(self, item, config, *, discount=Decimal("0.00"), other_expenses=Decimal("0.00")):
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
            "icms_situacao_tributaria": self._icms_situation(item, config),
            "pis_situacao_tributaria": item.pis_cst or "49",
            "pis_valor": str(item.pis_value),
            "cofins_situacao_tributaria": item.cofins_cst or "49",
            "cofins_valor": str(item.cofins_value),
            "valor_total_tributos": str(item.approx_tax_value),
        }
        if item.cest:
            payload["codigo_cest"] = item.cest
        if discount:
            payload["valor_desconto"] = str(discount)
        if other_expenses:
            payload["valor_outras_despesas"] = str(other_expenses)
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
        items = list(invoice.items.all().order_by("line_number"))
        if not items:
            raise FiscalRejection("Focus NFe: a nota nao possui itens fiscais.")
        other_expenses = self._validate_totals(invoice, items)
        discounts_by_item = self._allocate_total(items, invoice.discount_total)
        expenses_by_item = self._allocate_total(items, other_expenses)
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
            "valor_outras_despesas": str(other_expenses),
            "valor_total": str(invoice.total_amount),
            "valor_total_tributos": str(invoice.tax_approx_total),
            "modalidade_frete": "9",
            "items": [
                self._build_item(
                    item,
                    config,
                    discount=discounts_by_item.get(item.pk, Decimal("0.00")),
                    other_expenses=expenses_by_item.get(item.pk, Decimal("0.00")),
                )
                for item in items
            ],
            "formas_pagamento": payments,
        }
        if change_total:
            payload["valor_troco"] = str(change_total)
        if invoice.recipient_cpf:
            payload["cpf_destinatario"] = invoice.recipient_cpf
            payload["nome_destinatario"] = invoice.recipient_name
        return payload

    @staticmethod
    def _normalize_access_key(value):
        """Converte ``NFe<44 digitos>`` da Focus na chave fiscal de 44 digitos."""

        raw_value = str(value or "").strip()
        if raw_value[:3].lower() == "nfe":
            raw_value = raw_value[3:]
        access_key = "".join(character for character in raw_value if character in "0123456789")
        if len(access_key) != 44:
            raise FiscalAmbiguous(
                "Focus NFe: chave de acesso invalida na resposta; "
                f"esperados 44 digitos, recebidos {len(access_key)}."
            )
        return access_key

    def apply_response(self, invoice, data):
        status = data.get("status")
        if status == "autorizado":
            if data.get("chave_nfe") not in (None, ""):
                invoice.access_key = self._normalize_access_key(data["chave_nfe"])
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
            raise FiscalRejection(f"Focus NFe rejeitou a nota: {reason}")
        return invoice

    @staticmethod
    def _request(method, url, **kwargs):
        """Executa a chamada HTTP traduzindo falha de transporte em `FiscalUnavailable`.

        Uma conexao recusada ou um timeout nao dizem nada sobre a validade do
        documento: sao indisponibilidade, e so elas autorizam retentativa. O
        reenvio depois de um timeout e seguro porque a Focus trata `ref` como
        chave de idempotencia — um POST repetido devolve `already_processed`, e
        o resultado real vem da consulta feita em seguida.
        """
        import requests

        call = {"GET": requests.get, "POST": requests.post, "DELETE": requests.delete}[method]
        try:
            return call(url, **kwargs)
        except requests.Timeout as exc:
            raise FiscalUnavailable(f"Focus NFe: tempo esgotado ao falar com o provedor ({exc}).") from exc
        except requests.RequestException as exc:
            raise FiscalUnavailable(f"Focus NFe: falha de comunicacao com o provedor ({exc}).") from exc

    @staticmethod
    def _classify_http(response, data):
        """Traduz uma resposta HTTP sem situacao fiscal utilizavel na falha correspondente."""
        code = response.status_code
        detail = data or (response.text or "")[:300]
        if code in (401, 403):
            return FiscalConfigurationError(
                f"Focus NFe: token recusado pelo provedor (HTTP {code}). Verifique o cadastro fiscal."
            )
        if code == 429 or code >= 500:
            return FiscalUnavailable(f"Focus NFe: provedor indisponivel (HTTP {code}): {detail}")
        if code >= 400:
            return FiscalRejection(f"Focus NFe recusou a requisicao (HTTP {code}): {detail}")
        return FiscalAmbiguous(f"Focus NFe: resposta sem situacao fiscal (HTTP {code}): {detail}")

    def emit(self, invoice, config):
        invoice.provider = self.name
        invoice.provider_reference = self._reference(invoice)
        resource = self._resource(invoice.document_model)
        base_url = self._base_url(config)
        token = self._token(config)
        timeout = self._timeout(config)
        document_url = f"{base_url}/v2/{resource}/{invoice.provider_reference}"
        response = self._request(
            "POST",
            f"{base_url}/v2/{resource}?ref={invoice.provider_reference}",
            json=self._build_payload(invoice, config),
            auth=(token, ""),
            timeout=timeout,
        )
        data = response.json() if response.content else {}
        if response.status_code == 422 and data.get("codigo") == "already_processed":
            # A Focus usa a referencia como chave de idempotencia. Se a resposta
            # da primeira emissao nao chegou ao StarChef, um reenvio devolve 422
            # mesmo que a nota tenha sido autorizada. Consulte o documento ja
            # existente para reconciliar o estado local em vez de marca-lo como
            # erro e induzir novos reenvios.
            response = self._request("GET", document_url, auth=(token, ""), timeout=timeout)
            data = response.json() if response.content else {}
            if response.status_code >= 400 or data.get("status") is None:
                # O documento existe do lado da Focus e nao sabemos como ele
                # terminou: reenviar as cegas duplicaria a nota.
                raise FiscalAmbiguous(
                    "Focus NFe: a nota ja foi processada, mas nao foi possivel "
                    f"consultar o resultado (HTTP {response.status_code}): {data}"
                )
        if response.status_code >= 400 or data.get("status") is None:
            raise self._classify_http(response, data)
        return self.apply_response(invoice, data)

    def cancel(self, invoice, reason):
        config = FiscalConfig.objects.filter(branch=invoice.branch, is_active=True).first()
        if not config:
            raise FiscalConfigurationError("Sem configuracao fiscal para cancelar a nota.")
        resource = self._resource(invoice.document_model)
        response = self._request(
            "DELETE",
            f"{self._base_url(config)}/v2/{resource}/{self._reference(invoice)}",
            json={"justificativa": reason or "Cancelamento solicitado pelo operador."},
            auth=(self._token(config), ""),
            timeout=self._timeout(config),
        )
        if response.status_code >= 400:
            raise self._classify_http(response, response.json() if response.content else {})
        data = response.json() if response.content else {"status": "cancelado"}
        return self.apply_response(invoice, data)

    def status(self, invoice):
        config = FiscalConfig.objects.filter(branch=invoice.branch, is_active=True).first()
        if not config:
            raise FiscalConfigurationError("Sem configuracao fiscal para consultar a nota.")
        resource = self._resource(invoice.document_model)
        response = self._request(
            "GET",
            f"{self._base_url(config)}/v2/{resource}/{self._reference(invoice)}",
            auth=(self._token(config), ""),
            timeout=self._timeout(config),
        )
        data = response.json() if response.content else {}
        if response.status_code == 404:
            # Numa consulta, 404 quer dizer "o documento nao esta aqui" — nao
            # que ele foi recusado. Tratar como rejeicao marcaria como recusada
            # justamente a nota que nunca conseguiu ser transmitida.
            raise FiscalNotFound(
                "Focus NFe: nenhum documento com esta referencia foi encontrado no provedor."
            )
        if response.status_code >= 400 or data.get("status") is None:
            raise self._classify_http(response, data)
        self.apply_response(invoice, data)
        return invoice.status
