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
from apps.invoices.models import FiscalConfig, Invoice

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


@register_provider
class FocusNfeProvider(FiscalProvider):
    """Integrador Focus NFe (https://focusnfe.com.br) — assina e transmite a
    NFC-e por fora, sem o restaurante precisar lidar com certificado A1/SOAP
    da SEFAZ diretamente.

    ATENCAO: implementado a partir da documentacao publica do Focus NFe
    (nomes de campos de payload/resposta abaixo), SEM uma conta real (sandbox
    ou producao) para validar contra a API de verdade. Antes de apontar
    `FiscalConfig.provider = "focus_nfe"` em producao:
      1. Crie uma conta de homologacao em https://focusnfe.com.br
      2. Preencha `FiscalConfig.provider_token` com o token de homologacao
      3. Emita uma nota de teste e confira o payload/resposta reais — os nomes
         de campo abaixo podem ter mudado ou variar por versao da API.

    Usa `POST /v2/nfce` com o token em HTTP Basic Auth (usuario = token,
    senha vazia), que e o padrao documentado pelo Focus NFe.
    """

    name = "focus_nfe"
    BASE_URL = "https://homologacao.focusnfe.com.br"  # trocar por api.focusnfe.com.br em producao real
    TIMEOUT_SECONDS = 30

    def _base_url(self, config):
        if config.environment == config.ENV_PRODUCTION:
            return "https://api.focusnfe.com.br"
        return self.BASE_URL

    def _build_payload(self, invoice, config):
        items = []
        for item in invoice.items.all():
            items.append(
                {
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
                }
            )
        payload = {
            "natureza_operacao": "Venda ao consumidor",
            "presenca_comprador": "1",  # operacao presencial
            "cnpj_emitente": config.cnpj,
            "valor_produtos": str(invoice.products_total),
            "valor_desconto": str(invoice.discount_total),
            "modalidade_frete": "9",  # sem frete
            "items": items,
        }
        if invoice.recipient_cpf:
            payload["cpf_destinatario"] = invoice.recipient_cpf
            payload["nome_destinatario"] = invoice.recipient_name
        return payload

    def emit(self, invoice, config):
        import requests

        invoice.provider = self.name
        ref = f"invoice-{invoice.id}"
        url = f"{self._base_url(config)}/v2/nfce?ref={ref}"
        response = requests.post(
            url,
            json=self._build_payload(invoice, config),
            auth=(config.provider_token, ""),
            timeout=self.TIMEOUT_SECONDS,
        )
        data = response.json() if response.content else {}
        status = data.get("status")

        if response.status_code >= 500 or status is None:
            raise RuntimeError(f"Focus NFe: resposta inesperada (HTTP {response.status_code}): {data}")

        if status in ("autorizado",):
            invoice.access_key = data.get("chave_nfe", invoice.access_key)
            invoice.authorization_protocol = data.get("protocolo", "")
            invoice.digest_value = data.get("codigo_verificador", "") or data.get("hash", "")
            invoice.xml_content = data.get("caminho_xml_nota_fiscal", "")
            invoice.danfe_url = data.get("caminho_danfe", "")
            invoice.status = Invoice.STATUS_ISSUED
            invoice.error_message = ""
        elif status in ("processando_autorizacao",):
            # Assincrono: ainda nao saiu o protocolo. Fica pending, sem virar
            # contingencia — nao e uma falha, e uma resposta legitima em andamento.
            invoice.status = Invoice.STATUS_PENDING
            invoice.error_message = ""
        else:
            # "erro_autorizacao", "rejeitado" ou qualquer status desconhecido.
            reason = data.get("mensagem_sefaz") or data.get("mensagem") or f"status={status}"
            invoice.status = Invoice.STATUS_ERROR
            invoice.error_message = str(reason)
            raise RuntimeError(f"Focus NFe rejeitou a nota: {reason}")
        return invoice

    def cancel(self, invoice, reason):
        import requests

        config = FiscalConfig.objects.filter(branch=invoice.branch, is_active=True).first()
        if not config:
            raise RuntimeError("Sem configuracao fiscal para cancelar a nota.")
        url = f"{self._base_url(config)}/v2/nfce/{invoice.access_key}"
        response = requests.delete(
            url,
            json={"justificativa": reason or "Cancelamento solicitado pelo operador."},
            auth=(config.provider_token, ""),
            timeout=self.TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Focus NFe: falha ao cancelar (HTTP {response.status_code}): {response.text}")
        invoice.status = Invoice.STATUS_CANCELLED
        invoice.error_message = reason or ""
        return invoice

    def status(self, invoice):
        return invoice.status
