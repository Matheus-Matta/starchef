"""O provedor ACBrLib: o backend assina e transmite pelo comunicador local.

Diferente da Focus, não há relay para a nuvem: a loja transmite com o
comunicador DELA, e por isso emite sem internet (contingência offline). O
documento é o mesmo da Focus (`DocumentoFiscal`), traduzido para INI.

O resultado do comunicador sempre tem `situacao`; cada uma vira um estado da
nota ou a família de falha que o serviço de emissão já sabe tratar.
"""
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.invoices.acbrlib import cliente, ini
from apps.invoices.acbrlib.emitente import Emitente
from apps.invoices.documento import DocumentoFiscal
from apps.invoices.emission_secrets import segredos_de
from apps.invoices.fiscal import only_digits
from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.providers import FiscalProvider, register_provider
from apps.invoices.providers_erros import FiscalConfigurationError, FiscalNotFound, FiscalRejection


@register_provider
class AcbrLibProvider(DocumentoFiscal, FiscalProvider):
    name = FiscalConfig.PROVIDER_ACBRLIB
    rotulo = "ACBrLib"
    transmits = True
    #: Assina tpEmis=9 sem a SEFAZ e transmite depois (`contingencia_offline`).
    contingencia_offline = True

    def unavailable_reason(self, config):
        if not cliente.configurado():
            return "ACBrLib: ACBRLIB_URL não configurada nesta instalação (.env do backend)."
        motivo = _falta_no_emitente(config)
        if motivo:
            return motivo
        segredos = segredos_de(config)
        if not segredos.certificate_base64:
            return "ACBrLib: a empresa não tem certificado A1 cadastrado."
        if config.document_model == FiscalConfig.MODEL_NFCE and not segredos.csc_token:
            return "ACBrLib: a NFC-e precisa do CSC cadastrado."
        return None

    # ── operações ──────────────────────────────────────────────────────────
    def emit(self, invoice, config):
        """Emite; a nota já assinada em contingência é TRANSMITIDA como está."""
        invoice.provider = self.name
        invoice.provider_reference = str(invoice.pk)
        _conferir_emitente(config)
        if invoice.emission_type == Invoice.EMISSION_CONTINGENCY and invoice.xml_content:
            return self.aplicar(invoice, cliente.chamar("/v1/nfe/transmitir", {
                **self._contexto(invoice, config), "xml": invoice.xml_content,
            }))
        return self.aplicar(invoice, cliente.chamar("/v1/nfe/emitir", {
            **self._contexto(invoice, config), "tp_emis": "1",
            "ini": ini.montar(self._build_payload(invoice, config), invoice, config),
        }))

    def emitir_em_contingencia(self, invoice, config, justificativa):
        """Assina a NFC-e em tpEmis=9 SEM transmitir. Mesmo nNF, chave nova."""
        _conferir_emitente(config)
        agora = timezone.localtime().replace(microsecond=0).isoformat()
        contingencia = {"dhCont": agora, "xJust": _justificativa(justificativa)}
        return self.aplicar(invoice, cliente.chamar("/v1/nfe/emitir", {
            **self._contexto(invoice, config), "tp_emis": "9",
            "ini": ini.montar(self._build_payload(invoice, config), invoice, config,
                              tp_emis="9", contingencia=contingencia),
        }))

    def status(self, invoice):
        config = _config_da_nota(invoice)
        return self.aplicar(invoice, cliente.chamar("/v1/nfe/consultar", {
            **self._contexto(invoice, config), "chave": invoice.access_key,
        }))

    def cancel(self, invoice, reason):
        config = _config_da_nota(invoice)
        return self.aplicar(invoice, cliente.chamar("/v1/nfe/cancelar", {
            **self._contexto(invoice, config), "chave": invoice.access_key,
            "protocolo": invoice.authorization_protocol, "justificativa": _justificativa(reason),
        }))

    # ── resultado → nota ───────────────────────────────────────────────────
    def aplicar(self, invoice, resultado):
        situacao = resultado.get("situacao")
        motivo = f"{resultado.get('cstat', '')} {resultado.get('motivo', '')}".strip()
        if situacao in ("rejeitada", "denegada"):
            invoice.status = Invoice.STATUS_ERROR
            invoice.error_message = motivo
            raise FiscalRejection(f"ACBrLib: SEFAZ recusou a nota — {motivo}")
        if situacao == "nao_encontrada":
            raise FiscalNotFound(f"ACBrLib: a SEFAZ não conhece a chave — {motivo}")
        self._copiar(invoice, resultado)
        if situacao == "autorizada":
            invoice.status = Invoice.STATUS_ISSUED
            invoice.authorized_at = parse_datetime(resultado.get("recebido_em") or "") or timezone.now()
        elif situacao == "cancelada":
            invoice.status = Invoice.STATUS_CANCELLED
        else:  # contingencia (assinada, não transmitida) ou processando
            invoice.status = Invoice.STATUS_PENDING
        invoice.error_message = ""
        return invoice

    @staticmethod
    def _copiar(invoice, resultado):
        if resultado.get("chave"):
            invoice.access_key = only_digits(resultado["chave"])
        if resultado.get("protocolo"):
            invoice.authorization_protocol = resultado["protocolo"]
        if resultado.get("xml"):
            invoice.xml_content = resultado["xml"]
        if resultado.get("qrcode"):
            invoice.qr_code_data = resultado["qrcode"]
        if resultado.get("digest_value"):
            invoice.digest_value = resultado["digest_value"]
        payload = dict(invoice.fiscal_payload or {})
        payload["acbrlib"] = {"cstat": resultado.get("cstat"), "motivo": resultado.get("motivo"),
                              "situacao": resultado.get("situacao")}
        invoice.fiscal_payload = payload

    @staticmethod
    def _contexto(invoice, config):
        """Quem emite, onde e com qual certificado — em toda chamada.

        O comunicador não guarda configuração: o backend é a fonte, inclusive
        do segredo emprestado da nuvem (`segredos_de`).
        """
        segredos = segredos_de(config)
        emitente = Emitente(config)
        return {
            "referencia": str(invoice.pk), "modelo": str(invoice.document_model or config.document_model),
            "ambiente": str(invoice.environment or config.environment), "uf": emitente.uf,
            "cnpj": only_digits(emitente.cnpj),
            "certificado": {"pfx_base64": segredos.certificate_base64,
                            "senha": segredos.certificate_password},
            "csc": {"id": segredos.csc_id, "token": segredos.csc_token},
        }


def _falta_no_emitente(config):
    faltando = Emitente(config).faltando()
    if not faltando:
        return None
    return ("ACBrLib: faltam dados do emitente no cadastro fiscal do restaurante "
            f"(e no cadastro do próprio restaurante): {', '.join(faltando)}.")


def _conferir_emitente(config):
    """Na emissão, a nota é criada e a falha fica gravada nela (o operador
    corrige e reenvia) — mas sem ir à SEFAZ: o schema recusaria com a
    mensagem técnica da ACBrLib, sem o nome do campo."""
    motivo = _falta_no_emitente(config)
    if motivo:
        raise FiscalConfigurationError(motivo)


def _justificativa(texto):
    """A SEFAZ exige de 15 a 255 caracteres em xJust."""
    texto = " ".join(str(texto or "").split())[:255]
    return texto if len(texto) >= 15 else f"{texto} - sem comunicacao com a SEFAZ".strip(" -")


def _config_da_nota(invoice):
    from apps.invoices.services import _resolve_fiscal_config

    config = _resolve_fiscal_config(invoice.restaurant, invoice.branch)
    if config is None:
        raise FiscalRejection("ACBrLib: a filial da nota não tem configuração fiscal.")
    return config
