"""O ZIP da exportação de XML: onde fica, até quando vale e quem o apaga.

O arquivo vai para o armazenamento de mídia (disco ou S3) com o id do lote no
nome — um UUID, então não dá para adivinhar o de outra conta. Mesmo assim ele
nunca é entregue pela URL de mídia: o download passa pela API, que confere a
conta e quem pediu. O XML traz o CPF do consumidor.

Vale 24 h a partir do fim do lote. Vencido, a API recusa na hora (410), mesmo
que a limpeza ainda não tenha passado; a limpeza (`limpar_vencidas`, de hora
em hora pelo beat) é o que libera o espaço.
"""
from datetime import timedelta

from django.core.files import File
from django.core.files.storage import default_storage
from django.utils import timezone

VALIDADE = timedelta(hours=24)
PASTA = "exportacoes_xml"


class ExportacaoIndisponivel(Exception):
    def __init__(self, mensagem, status):
        super().__init__(mensagem)
        self.status = status


def salvar(job, conteudo):
    return default_storage.save(f"{PASTA}/{job.pk}.zip", File(conteudo))


def expira_em(job):
    return job.finished_at + VALIDADE if job.finished_at else None


def vencida(job, agora=None):
    limite = expira_em(job)
    return bool((job.result or {}).get("expirada")) or (limite is not None and (agora or timezone.now()) >= limite)


def situacao(job):
    """O que a tela da exportação mostra. Nunca o caminho do arquivo."""
    from apps.bulk_jobs.models import BulkJob

    resultado = job.result or {}
    disponivel = job.status == BulkJob.DONE and bool(resultado.get("arquivo")) and not vencida(job)
    return {
        "id": str(job.pk),
        "status": job.status,
        "total": job.total,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
        "expires_at": expira_em(job),
        "expired": vencida(job),
        "result": {campo: resultado.get(campo) for campo in ("total", "quantidade_de_falhas", "falhas", "nome")},
        "download_url": f"/invoices/xml-export/{job.pk}/download/" if disponivel else None,
    }


def abrir(job):
    """(arquivo aberto, nome para o download) ou `ExportacaoIndisponivel`."""
    from apps.bulk_jobs.models import BulkJob

    if job.status in (BulkJob.QUEUED, BulkJob.RUNNING):
        raise ExportacaoIndisponivel("O ZIP ainda está sendo montado. Aguarde o aviso no sino.", 409)
    resultado = job.result or {}
    if job.status == BulkJob.FAILED or not resultado.get("arquivo"):
        raise ExportacaoIndisponivel("Esta exportação não gerou arquivo.", 404)
    if vencida(job) or not default_storage.exists(resultado["arquivo"]):
        raise ExportacaoIndisponivel("O ZIP passou das 24 horas e foi apagado. Gere a exportação de novo.", 410)
    return default_storage.open(resultado["arquivo"], "rb"), resultado.get("nome") or "notas-fiscais.zip"


def limpar_vencidas(agora=None):
    """Apaga o ZIP de cada exportação vencida e a marca como expirada."""
    from apps.bulk_jobs.models import BulkJob

    agora = agora or timezone.now()
    vencidos = BulkJob.all_objects.filter(
        action=BulkJob.INVOICE_XML_EXPORT, status=BulkJob.DONE, finished_at__lte=agora - VALIDADE,
    ).exclude(result__has_key="expirada")
    apagados = 0
    for job in vencidos:
        caminho = (job.result or {}).get("arquivo")
        if caminho:
            default_storage.delete(caminho)
            apagados += 1
        job.result = {**(job.result or {}), "expirada": True}
        job.save(update_fields=["result", "updated_at"])
    return apagados
