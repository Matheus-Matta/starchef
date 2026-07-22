"""
Provedores de emissao fiscal (contrato + implementacao "em branco").

O documento fiscal e montado localmente pelo `services.emit_fiscal_invoice`
(chave de acesso, QR, tributos). A ETAPA QUE DEPENDE DE INTEGRACAO EXTERNA
— assinatura com certificado A1, transmissao a SEFAZ e obtencao do protocolo
de autorizacao — vive aqui, nos providers, e esta PROPOSITALMENTE EM BRANCO.

Para colocar em producao, implemente um provider real (SEFAZ direto ou um
integrador como Focus NFe / PlugNotas / WebmaniaBR), registre-o e aponte
`FiscalConfig.provider` para ele.
"""
from apps.invoices.models import Invoice

_REGISTRY = {}


def register_provider(cls):
    """Decorator para registrar um provider pelo seu `name`."""
    _REGISTRY[cls.name] = cls
    return cls


def get_provider(name):
    """Instancia o provider configurado; cai no manual se desconhecido."""
    return _REGISTRY.get(name or ManualFiscalProvider.name, ManualFiscalProvider)()


class FiscalProvider:
    """Contrato de um provedor de emissao. Um provider real preenche protocolo,
    data de autorizacao, XML assinado e status ISSUED."""

    name = "base"

    def emit(self, invoice, config):
        raise NotImplementedError

    def cancel(self, invoice, reason):
        raise NotImplementedError

    def status(self, invoice):
        raise NotImplementedError


@register_provider
class ManualFiscalProvider(FiscalProvider):
    """Provider padrao (scaffold): monta o documento mas NAO transmite a SEFAZ.

    Deixa a nota em `pending` (aguardando autorizacao). O cupom pode ser impresso,
    mas SEM valor fiscal ate um provider real assinar e transmitir.
    """

    name = "manual"

    def emit(self, invoice, config):
        invoice.provider = self.name
        # ── PARTE EM BRANCO: assinar (A1) + transmitir + capturar protocolo ──
        # Um provider real faria:
        #   xml = build_and_sign_xml(invoice, config, certificate)
        #   resp = transmit_to_sefaz(xml, config)
        #   invoice.authorization_protocol = resp.protocol
        #   invoice.authorized_at = resp.datetime
        #   invoice.digest_value = resp.digest
        #   invoice.xml_content = resp.signed_xml
        #   invoice.status = Invoice.STATUS_ISSUED
        invoice.authorization_protocol = ""
        invoice.digest_value = ""
        invoice.status = Invoice.STATUS_PENDING
        invoice.error_message = ""
        return invoice

    def cancel(self, invoice, reason):
        # Um provider real transmitiria o evento de cancelamento a SEFAZ.
        invoice.status = Invoice.STATUS_CANCELLED
        invoice.error_message = reason or ""
        return invoice

    def status(self, invoice):
        return invoice.status


# ── Exemplo de esqueleto para um provider real (deixe pronto para preencher) ──
# @register_provider
# class FocusNfeProvider(FiscalProvider):
#     name = "focus_nfe"
#     def emit(self, invoice, config):
#         # 1) montar o JSON/XML da NFC-e a partir de invoice + invoice.items
#         # 2) POST no integrador com o token de config (EM BRANCO: config.certificate_ref/token)
#         # 3) preencher access_key/protocol/authorized_at/xml/status a partir da resposta
#         raise NotImplementedError("Configurar credenciais do integrador.")
