"""Provedores de emissao fiscal do StarChef."""

from decimal import Decimal

from django.utils.dateparse import parse_datetime

from apps.accounts.models import FocusNfeConfig
from apps.invoices.documento import DocumentoFiscal
from apps.invoices.focus_emission_errors import detail_from_focus, is_company_configuration_error
from apps.invoices.models import FiscalConfig, Invoice

from apps.invoices.providers_erros import (  # noqa: E402,F401 — reexportados
    FiscalAmbiguous,
    FiscalConfigurationError,
    FiscalNotFound,
    FiscalProviderError,
    FiscalRejection,
    FiscalUnavailable,
)

_REGISTRY = {}
TWO_PLACES = Decimal("0.01")


def register_provider(cls):
    _REGISTRY[cls.name] = cls
    return cls


def get_provider(name):
    return _REGISTRY.get(name or ManualFiscalProvider.name, ManualFiscalProvider)()


def provider_class_for(name):
    """A CLASSE do provedor, para quem precisa perguntar algo antes de emitir.

    Devolve `None` quando o nome nao esta registrado — um provedor que saiu do
    codigo mas continua gravado numa configuracao antiga.
    """
    return _REGISTRY.get(name)


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
class FocusNfeProvider(DocumentoFiscal, FiscalProvider):
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
        from apps.invoices.emission_secrets import segredos_de

        token = segredos_de(config).token_do_provedor(config.environment)
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
    def _config_for(invoice):
        """Configuracao fiscal da nota, com o mesmo recuo do servico.

        Buscar so por `branch` deixava de fora a nota cuja filial esta nula —
        situacao normal enquanto a unificacao Restaurant/Filial nao acontece
        (ver `_resolve_fiscal_config`). A consulta e o cancelamento falhavam
        com "sem configuracao fiscal" numa nota perfeitamente emitida.
        """
        config = None
        if invoice.branch_id:
            config = FiscalConfig.objects.filter(branch_id=invoice.branch_id, is_active=True).first()
        if config is None and invoice.restaurant_id:
            config = FiscalConfig.objects.filter(
                branch__restaurant_id=invoice.restaurant_id, is_active=True
            ).first()
        if config is None:
            raise FiscalConfigurationError("Sem configuracao fiscal ativa para esta nota.")
        return config

    @staticmethod
    def _token(config):
        # O token pode não estar GRAVADO aqui: a loja não recebe segredo de
        # emissão pela sincronização (ver `emission_secrets`). Quando falta,
        # ele é pedido emprestado à nuvem, usado e descartado — nunca vai ao
        # disco desta máquina.
        from apps.invoices.emission_secrets import segredos_de

        token = segredos_de(config).token_do_provedor(config.environment)
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
    def _classify_http(code, data):
        """Traduz um HTTP sem situacao fiscal utilizavel na falha correspondente.
        A mesma regra vale na chamada direta e no rele da loja para a nuvem,
        pois ela decide o que pode ser tentado novamente.
        """
        detail = detail_from_focus(data)
        if code in (401, 403):
            return FiscalConfigurationError(
                f"Focus NFe: token recusado pelo provedor (HTTP {code}). Verifique o cadastro fiscal."
            )
        if is_company_configuration_error(code, data):
            return FiscalConfigurationError(f"Focus NFe: configuracao fiscal recusada: {detail}")
        if code == 429 or code >= 500:
            return FiscalUnavailable(f"Focus NFe: provedor indisponivel (HTTP {code}): {detail}")
        if code >= 400:
            return FiscalRejection(f"Focus NFe recusou a requisicao (HTTP {code}): {detail}")
        return FiscalAmbiguous(f"Focus NFe: resposta sem situacao fiscal (HTTP {code}): {detail}")

    # ── a chamada ao provedor: daqui, ou pela nuvem ─────────────────────────
    #
    # `relay_execute` é a chamada de VERDADE, e roda onde está a credencial:
    # na nuvem, quando a loja delega; aqui mesmo, numa instalação única.
    # `_chamar` é quem escolhe. As três operações passam por ele, e nenhuma
    # monta URL por conta própria — é o que mantém o relé com três portas
    # nomeadas em vez de virar um proxy para `/v2/empresas`.

    TRANSMITIR = "transmit"
    CONSULTAR = "consult"
    CANCELAR = "cancel"

    @classmethod
    def relay_execute(cls, config, *, operacao, reference, document_model,
                      payload=None, reason=""):
        """Fala com a Focus e devolve `(status_code, dados)`, sem interpretar.

        Quem interpreta é quem chamou: é lá que `apply_response` grava número,
        série, chave e protocolo na nota. Traduzir aqui criaria um segundo
        dialeto para manter — e a nuvem, que só transmite em nome da loja, não
        tem o que dizer sobre o documento.
        """
        base = cls()._base_url(config)
        token = cls()._token(config)
        timeout = cls()._timeout(config)
        recurso = cls._resource(document_model)
        alvo = f"{base}/v2/{recurso}/{reference}"

        if operacao == cls.TRANSMITIR:
            resposta = cls._request(
                "POST", f"{base}/v2/{recurso}?ref={reference}",
                json=payload, auth=(token, ""), timeout=timeout,
            )
        elif operacao == cls.CONSULTAR:
            resposta = cls._request("GET", alvo, auth=(token, ""), timeout=timeout)
        elif operacao == cls.CANCELAR:
            resposta = cls._request(
                "DELETE", alvo,
                json={"justificativa": reason or "Cancelamento solicitado pelo operador."},
                auth=(token, ""), timeout=timeout,
            )
        else:
            raise FiscalConfigurationError(f"Operação fiscal desconhecida: {operacao!r}.")
        return resposta.status_code, (resposta.json() if resposta.content else {})

    def _chamar(self, config, **kwargs):
        """Direto, ou pela nuvem quando esta instalação é uma loja."""
        from apps.invoices import relay_client

        if relay_client.deve_delegar(config):
            return relay_client.executar(config, **kwargs)
        return self.relay_execute(config, **kwargs)

    def emit(self, invoice, config):
        invoice.provider = self.name
        invoice.provider_reference = self._reference(invoice)
        comum = {
            "reference": invoice.provider_reference,
            "document_model": invoice.document_model,
        }
        codigo, data = self._chamar(
            config, operacao=self.TRANSMITIR,
            payload=self._build_payload(invoice, config), **comum,
        )
        if codigo == 422 and data.get("codigo") == "already_processed":
            # A Focus usa a referencia como chave de idempotencia. Se a resposta
            # da primeira emissao nao chegou ao StarChef, um reenvio devolve 422
            # mesmo que a nota tenha sido autorizada. Consulte o documento ja
            # existente para reconciliar o estado local em vez de marca-lo como
            # erro e induzir novos reenvios.
            codigo, data = self._chamar(config, operacao=self.CONSULTAR, **comum)
            if codigo >= 400 or data.get("status") is None:
                # O documento existe do lado da Focus e nao sabemos como ele
                # terminou: reenviar as cegas duplicaria a nota.
                raise FiscalAmbiguous(
                    "Focus NFe: a nota ja foi processada, mas nao foi possivel "
                    f"consultar o resultado (HTTP {codigo}): {data}"
                )
        if codigo >= 400 or data.get("status") is None:
            raise self._classify_http(codigo, data)
        return self.apply_response(invoice, data)

    def cancel(self, invoice, reason):
        config = self._config_for(invoice)
        codigo, data = self._chamar(
            config, operacao=self.CANCELAR, reason=reason,
            reference=self._reference(invoice),
            document_model=invoice.document_model,
        )
        if codigo == 404:
            raise FiscalNotFound(
                "Focus NFe: nenhum documento com esta referencia foi encontrado para cancelar."
            )
        if codigo >= 400:
            raise self._classify_http(codigo, data)
        return self.apply_response(invoice, data or {"status": "cancelado"})

    def status(self, invoice):
        config = self._config_for(invoice)
        codigo, data = self._chamar(
            config, operacao=self.CONSULTAR,
            reference=self._reference(invoice),
            document_model=invoice.document_model,
        )
        if codigo == 404:
            # Numa consulta, 404 quer dizer "o documento nao esta aqui" — nao
            # que ele foi recusado. Tratar como rejeicao marcaria como recusada
            # justamente a nota que nunca conseguiu ser transmitida.
            raise FiscalNotFound(
                "Focus NFe: nenhum documento com esta referencia foi encontrado no provedor."
            )
        if codigo >= 400 or data.get("status") is None:
            raise self._classify_http(codigo, data)
        self.apply_response(invoice, data)
        return invoice.status


# O provedor ACBrLib se registra ao ser importado (docs/FISCAL_ACBRLIB.md).
from apps.invoices.acbrlib import provider as _acbrlib  # noqa: E402,F401
