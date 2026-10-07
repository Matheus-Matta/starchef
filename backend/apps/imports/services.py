"""Processa uma importação linha a linha, pela view da própria tela.

Cada linha é uma requisição interna (`APIRequestFactory`) autenticada como
quem pediu: valem a validação do serializer, as permissões e o recorte de
conta/restaurante — exatamente o que a tela faria, só que no worker.

Atualiza o que já existe pela chave (código interno, código ou nome, sem
diferenciar maiúsculas) e cria o resto; uma linha com erro não para as outras.
"""
import logging

from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.tenant import tenant_context
from apps.imports.models import ImportJob
from apps.imports.targets import PREFIXO, resolver_alvo

logger = logging.getLogger(__name__)
MAX_ERROS = 200
_fabrica = APIRequestFactory()


def _requisicao(job, metodo, caminho, dados=None):
    extras = {"HTTP_X_RESTAURANT_ID": job.restaurant_scope} if job.restaurant_scope else {}
    req = getattr(_fabrica, metodo)(caminho, dados, format="json", **extras)
    force_authenticate(req, user=job.requested_by)
    req.account = job.account
    return req


def _existentes(job, classe):
    """{valor da chave normalizado: id}, dentro do que este usuário enxerga."""
    if not job.key_field:
        return {}
    viewset = classe()
    viewset.action_map = {"get": "list"}
    viewset.args, viewset.kwargs, viewset.format_kwarg = (), {}, None
    viewset.request = viewset.initialize_request(_requisicao(job, "get", PREFIXO + job.endpoint))
    pares = viewset.get_queryset().values_list(job.key_field, "pk")
    return {str(valor).strip().lower(): pk for valor, pk in pares if valor not in (None, "")}


def _mensagem(dados):
    if isinstance(dados, dict):
        if "detail" in dados:
            return str(dados["detail"])
        return "; ".join(f"{campo}: {_mensagem(valor)}" for campo, valor in dados.items())
    if isinstance(dados, list):
        return " ".join(_mensagem(item) for item in dados)
    return str(dados)


def run_import(job_id):
    """Executa a importação. Idempotente: só roda a que está na fila."""
    with transaction.atomic():
        job = ImportJob.all_objects.select_for_update().filter(pk=job_id, status=ImportJob.STATUS_QUEUED).first()
        if job is None:
            return None
        job.status = ImportJob.STATUS_RUNNING
        job.save(update_fields=["status", "updated_at"])

    classe = resolver_alvo(job.endpoint)
    criar = classe.as_view({"post": "create"})
    atualizar = classe.as_view({"patch": "partial_update"})
    erros, criados, atualizados = [], 0, 0
    try:
        with tenant_context(job.account):
            existentes = _existentes(job, classe)
            for numero, linha in enumerate(job.rows, start=2):  # linha 1 é o cabeçalho
                chave = str(linha.get(job.key_field, "")).strip().lower() if job.key_field else ""
                pk = existentes.get(chave) if chave else None
                if pk:
                    resposta = atualizar(_requisicao(job, "patch", f"{PREFIXO}{job.endpoint}{pk}/", linha), pk=pk)
                else:
                    resposta = criar(_requisicao(job, "post", PREFIXO + job.endpoint, linha))
                if resposta.status_code >= 400:
                    erros.append(f"Linha {numero}: {_mensagem(resposta.data)}")
                elif pk:
                    atualizados += 1
                else:
                    criados += 1
                    novo = (resposta.data or {}).get("id")
                    # Duas linhas com a mesma chave: a segunda atualiza a primeira.
                    if chave and novo:
                        existentes[chave] = novo
        job.status = ImportJob.STATUS_DONE
    except Exception:  # noqa: BLE001 — a falha vira estado e aviso, nunca silêncio
        logger.exception("Importação %s falhou", job.pk)
        erros.append("A importação parou por um erro inesperado. As linhas anteriores foram gravadas.")
        job.status = ImportJob.STATUS_FAILED
    job.created_count, job.updated_count = criados, atualizados
    job.errors = erros[:MAX_ERROS]
    job.finished_at = timezone.now()
    # Processadas, as linhas não servem para mais nada (os erros guardam o
    # número da linha) e uma planilha grande ocuparia o banco para sempre.
    job.rows = []
    job.save(update_fields=["status", "created_count", "updated_count", "errors", "finished_at", "rows", "updated_at"])
    _avisar(job)
    return job


def _avisar(job):
    from apps.notifications.models import Notification
    from apps.notifications.services import notify

    falhou = job.status == ImportJob.STATUS_FAILED or job.errors
    partes = [f"{job.created_count} criado(s), {job.updated_count} atualizado(s)"]
    if job.errors:
        partes.append(f"{len(job.errors)} linha(s) com erro — {job.errors[0]}")
    notify(
        [job.requested_by], account=job.account,
        level=Notification.LEVEL_WARNING if falhou else Notification.LEVEL_SUCCESS,
        title=f"Importação de {job.total} linha(s) {'com problemas' if falhou else 'concluída'}",
        body=". ".join(partes), entity="imports.ImportJob", object_id=str(job.pk),
        metadata={"endpoint": job.endpoint, "errors": job.errors[:20]},
    )
