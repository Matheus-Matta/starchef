"""Sincronizacao de empresas do StarChef com a API de Empresas da Focus NFe."""

import logging

import requests
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import FocusNfeConfig
from apps.invoices.fiscal import only_digits
from apps.invoices.models import FiscalConfig

logger = logging.getLogger(__name__)


class FocusNfeApiError(RuntimeError):
    """Erro de transporte ou validacao devolvido pela Focus NFe."""


class FocusNfeConfigurationError(RuntimeError):
    """A conta ainda nao possui os dados necessarios para usar a Focus."""


def get_account_focus_config(account):
    if account is None:
        return None
    return FocusNfeConfig.objects.filter(account_id=account.pk).first()


def _clean_payload(payload):
    return {key: value for key, value in payload.items() if value not in (None, "")}


def build_focus_company_payload(config):
    """Converte o cadastro fiscal local no contrato de empresa da Focus."""
    restaurant = config.restaurant
    branch = config.branch
    is_production = config.environment == FiscalConfig.ENV_PRODUCTION
    is_nfe = config.document_model == FiscalConfig.MODEL_NFE
    is_nfce = config.document_model == FiscalConfig.MODEL_NFCE

    payload = {
        "nome": config.corporate_name or restaurant.legal_name or restaurant.trade_name,
        "nome_fantasia": config.trade_name or restaurant.trade_name,
        "cnpj": only_digits(config.cnpj or restaurant.cnpj),
        "inscricao_estadual": only_digits(config.ie or branch.state_registration),
        "regime_tributario": int(config.crt),
        "logradouro": config.address_line or branch.address,
        "municipio": config.city or branch.city,
        "cep": only_digits(config.zip_code or branch.zip_code),
        "uf": (config.uf or branch.state).upper(),
        "telefone": only_digits(branch.phone),
        "email": branch.email,
        "discrimina_impostos": True,
        "habilita_nfe": is_nfe,
        "habilita_nfce": is_nfce,
        "habilita_contingencia_offline_nfce": is_nfce,
        "reaproveita_numero_nfce_contingencia": is_nfce,
    }
    if config.focus_certificate_base64:
        payload["arquivo_certificado_base64"] = config.focus_certificate_base64
        payload["senha_certificado"] = config.focus_certificate_password
    if is_nfe:
        suffix = "producao" if is_production else "homologacao"
        payload[f"serie_nfe_{suffix}"] = str(config.series)
        payload[f"proximo_numero_nfe_{suffix}"] = str(config.next_number)
    if is_nfce:
        suffix = "producao" if is_production else "homologacao"
        payload[f"serie_nfce_{suffix}"] = str(config.series)
        payload[f"proximo_numero_nfce_{suffix}"] = str(config.next_number)
        if config.csc_token:
            payload[f"csc_nfce_{suffix}"] = config.csc_token
        if config.csc_id:
            payload[f"id_token_nfce_{suffix}"] = int(config.csc_id)
    return _clean_payload(payload)


class FocusNfeCompanyClient:
    """CRUD da API `/v2/empresas`, autenticado pelo token mestre."""

    def __init__(self, *, account_config=None, token=None, timeout=None, dry_run=None):
        self.account_config = account_config
        self.token = token if token is not None else getattr(account_config, "master_token", "")
        self.timeout = timeout if timeout is not None else getattr(account_config, "timeout_seconds", 30)
        self.dry_run = dry_run if dry_run is not None else getattr(account_config, "company_dry_run", False)
        self.base_url = getattr(account_config, "production_url", "").rstrip("/")

    def _request(self, method, path, *, token=None, **kwargs):
        credential = token or self.token
        if not credential:
            raise FocusNfeConfigurationError("Token mestre da Focus NFe nao configurado para esta conta.")
        if not self.base_url:
            raise FocusNfeConfigurationError("URL de producao da Focus NFe nao configurada para esta conta.")
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                auth=(credential, ""),
                timeout=self.timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise FocusNfeApiError(f"Focus NFe indisponivel: {exc}") from exc

        try:
            data = response.json() if response.content else {}
        except ValueError:
            data = {"mensagem": response.text}
        if response.status_code >= 400:
            message = data.get("mensagem") if isinstance(data, dict) else None
            errors = data.get("erros") if isinstance(data, dict) else None
            if errors:
                message = "; ".join(str(item.get("mensagem", item)) for item in errors)
            raise FocusNfeApiError(
                f"Focus NFe (HTTP {response.status_code}): {message or data or response.text}"
            )
        return data

    def list(self, *, cnpj=None, offset=0):
        params = {"offset": offset}
        if cnpj:
            params["cnpj"] = only_digits(cnpj)
        return self._request("GET", "/v2/empresas", params=params)

    def get(self, company_id):
        return self._request("GET", f"/v2/empresas/{company_id}")

    def create(self, payload):
        params = {"dry_run": 1} if self.dry_run else None
        return self._request("POST", "/v2/empresas", params=params, json=payload)

    def update(self, company_id, payload):
        params = {"dry_run": 1} if self.dry_run else None
        return self._request("PUT", f"/v2/empresas/{company_id}", params=params, json=payload)

    def delete(self, company_id):
        return self._request("DELETE", f"/v2/empresas/{company_id}")

    def ensure_webhook(self, *, company, cnpj):
        url = getattr(self.account_config, "webhook_url", "")
        token = company.get("token_producao")
        if not url or not token:
            return None
        hooks = self._request("GET", "/v2/hooks", token=token)
        if isinstance(hooks, dict):
            hooks = hooks.get("data") or hooks.get("results") or []
        for hook in hooks or []:
            if hook.get("event") == "nfe" and hook.get("url") == url and only_digits(hook.get("cnpj")) == cnpj:
                return hook
        payload = {"cnpj": cnpj, "event": "nfe", "url": url}
        authorization = getattr(self.account_config, "webhook_authorization", "")
        if authorization:
            payload["authorization"] = authorization
            payload["authorization_header"] = (
                getattr(self.account_config, "webhook_authorization_header", "") or "Authorization"
            )
        return self._request("POST", "/v2/hooks", token=token, json=payload)


def _first_company(data):
    if isinstance(data, list):
        return data[0] if data else None
    if not isinstance(data, dict):
        return None
    companies = data.get("data") or data.get("results") or data.get("empresas")
    if isinstance(companies, list):
        return companies[0] if companies else None
    return data if data.get("id") else None


def _store_focus_company(config, company):
    secret_fragments = ("token", "senha", "password", "csc")
    safe_remote_data = {
        key: value
        for key, value in company.items()
        if not any(fragment in key.lower() for fragment in secret_fragments)
    }
    updates = {
        "focus_company_id": str(company.get("id") or config.focus_company_id),
        "focus_sync_status": FiscalConfig.FOCUS_SYNC_SYNCED,
        "focus_sync_error": "",
        "focus_synced_at": timezone.now(),
        "focus_remote_data": safe_remote_data,
        "updated_at": timezone.now(),
    }
    if config.focus_certificate_base64:
        # O PFX e sua senha so permanecem no banco enquanto a tarefa precisa
        # deles para criar/atualizar a empresa. Apos sucesso, sao descartados.
        updates["focus_certificate_base64"] = ""
        updates["focus_certificate_password"] = ""
    if company.get("token_producao"):
        updates["focus_token_production"] = company["token_producao"]
    if company.get("token_homologacao"):
        updates["focus_token_homologation"] = company["token_homologacao"]
    FiscalConfig.all_objects.filter(pk=config.pk).update(**updates)
    config.refresh_from_db()
    return config


def sync_focus_company(config, *, client=None):
    """Cria ou atualiza a empresa da Focus e armazena os tokens de emissao."""
    if config.provider != FiscalConfig.PROVIDER_FOCUS_NFE:
        raise FocusNfeApiError("A configuracao fiscal nao usa o provedor Focus NFe.")
    cnpj = only_digits(config.cnpj or config.restaurant.cnpj)
    if len(cnpj) != 14:
        raise FocusNfeApiError("Informe um CNPJ valido antes de sincronizar com a Focus NFe.")

    client = client or FocusNfeCompanyClient(account_config=get_account_focus_config(config.account))
    try:
        payload = build_focus_company_payload(config)
        company = None
        if config.focus_company_id:
            try:
                company = client.update(config.focus_company_id, payload)
            except FocusNfeApiError as exc:
                if "HTTP 404" not in str(exc):
                    raise
        if company is None:
            existing = _first_company(client.list(cnpj=cnpj))
            company = client.update(existing["id"], payload) if existing else client.create(payload)
        try:
            client.ensure_webhook(company=company, cnpj=cnpj)
        except FocusNfeApiError:
            # O webhook e complementar: NFC-e e sincrona e NF-e tambem pode
            # ser consultada. Uma falha aqui nao pode inutilizar os tokens.
            logger.exception("Empresa sincronizada, mas o webhook Focus NFe nao foi cadastrado.")
        return _store_focus_company(config, company)
    except Exception as exc:
        FiscalConfig.all_objects.filter(pk=config.pk).update(
            focus_sync_status=(
                FiscalConfig.FOCUS_SYNC_NOT_CONFIGURED
                if isinstance(exc, FocusNfeConfigurationError)
                else FiscalConfig.FOCUS_SYNC_ERROR
            ),
            focus_sync_error=str(exc),
            updated_at=timezone.now(),
        )
        if isinstance(exc, (FocusNfeApiError, FocusNfeConfigurationError)):
            raise
        raise FocusNfeApiError(str(exc)) from exc


def refresh_focus_company(config, *, client=None):
    if config.provider != FiscalConfig.PROVIDER_FOCUS_NFE:
        raise FocusNfeApiError("A configuracao fiscal nao usa o provedor Focus NFe.")
    client = client or FocusNfeCompanyClient(account_config=get_account_focus_config(config.account))
    if not config.focus_company_id:
        company = _first_company(client.list(cnpj=config.cnpj))
        if not company:
            raise FocusNfeApiError("Empresa ainda nao cadastrada na Focus NFe.")
    else:
        company = client.get(config.focus_company_id)
    return _store_focus_company(config, company)


def delete_focus_company(config, *, client=None):
    """Exclusao remota explicita; nunca e executada por soft-delete local."""
    client = client or FocusNfeCompanyClient(account_config=get_account_focus_config(config.account))
    if config.focus_company_id:
        client.delete(config.focus_company_id)
    FiscalConfig.all_objects.filter(pk=config.pk).update(
        focus_company_id="",
        focus_token_production="",
        focus_token_homologation="",
        focus_certificate_base64="",
        focus_certificate_password="",
        focus_sync_status=FiscalConfig.FOCUS_SYNC_NOT_CONFIGURED,
        focus_sync_error="",
        focus_synced_at=None,
        focus_remote_data={},
        updated_at=timezone.now(),
    )
    config.refresh_from_db()
    return config


def enqueue_focus_company_sync(config):
    """Agenda a sincronizacao sem bloquear o cadastro do restaurante."""
    if config.provider != FiscalConfig.PROVIDER_FOCUS_NFE:
        return False
    account_config = get_account_focus_config(config.account)
    if account_config is None or not account_config.auto_sync:
        return False
    if not account_config.master_token or not account_config.production_url:
        FiscalConfig.all_objects.filter(pk=config.pk).update(
            focus_sync_status=FiscalConfig.FOCUS_SYNC_NOT_CONFIGURED,
            focus_sync_error="Configure o token mestre e a URL de producao da Focus NFe para esta conta.",
            updated_at=timezone.now(),
        )
        return False
    FiscalConfig.all_objects.filter(pk=config.pk).update(
        focus_sync_status=FiscalConfig.FOCUS_SYNC_PENDING,
        focus_sync_error="",
        updated_at=timezone.now(),
    )

    def enqueue():
        try:
            from apps.invoices.tasks import sync_focus_company_task

            sync_focus_company_task.delay(str(config.pk))
        except Exception:
            logger.exception("Nao foi possivel agendar a sincronizacao da empresa Focus NFe.")

    transaction.on_commit(enqueue, robust=True)
    return True
