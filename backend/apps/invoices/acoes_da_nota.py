"""Ações da nota além da emissão: recriar, baixar o XML e exportar em ZIP.

Ficam fora de `views.py` para ele não crescer (regra das 200 linhas): o
`InvoiceViewSet` herda este mixin, que já traz o reenvio e a recriação em massa.
"""
from django.core.exceptions import ValidationError
from django.http import FileResponse, HttpResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.bulk_jobs.models import BulkJob
from apps.bulk_jobs.services import enqueue_bulk_job, queued_response, run_bulk_job
from apps.core.access import is_tenant_admin
from apps.invoices.bulk import InvoiceBulkResendMixin
from apps.invoices.exportacao_xml import FiltroExportacao, cabe_na_hora, notas_do_filtro
from apps.invoices.exportacao_xml_arquivo import ExportacaoIndisponivel, abrir, situacao
from apps.invoices.recriar_nota import NotaNaoRecriavel, recriar_nota
from apps.invoices.xml_da_nota import XmlIndisponivel, nome_do_arquivo, xml_da_nota

_ID_DO_LOTE = r"xml-export/(?P<job_id>[0-9a-fA-F-]{36})"


class InvoiceAcoesMixin(InvoiceBulkResendMixin):
    @action(detail=True, methods=["post"], url_path="recreate")
    def recreate(self, request, pk=None):
        """Descarta a tentativa travada e emite a nota de novo (`recriar_nota.py`)."""
        try:
            nota = recriar_nota(self.get_object(), user=request.user)
        except NotaNaoRecriavel as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return self._serialize(nota)

    @action(detail=True, methods=["get"], url_path="xml")
    def xml(self, request, pk=None):
        nota = self.get_object()
        try:
            conteudo = xml_da_nota(nota)
        except XmlIndisponivel as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        resposta = HttpResponse(conteudo.encode("utf-8"), content_type="application/xml; charset=utf-8")
        resposta["Content-Disposition"] = f'attachment; filename="{nome_do_arquivo(nota)}"'
        return resposta

    @action(detail=False, methods=["post"], url_path="xml-export")
    def xml_export(self, request):
        """ZIP com os XML do período. Pouca coisa sai na hora; o resto vai ao worker."""
        filtro = FiltroExportacao(data=request.data)
        filtro.is_valid(raise_exception=True)
        escopo = self._restaurante_de_quem_pede()
        payload = filtro.payload(escopo)
        if payload["restaurant"] and escopo and payload["restaurant"] != escopo:
            return Response({"detail": "Restaurante não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        notas = notas_do_filtro(payload)
        total = notas.count()
        if not total:
            return Response({"total": 0, "detail": "Nenhuma nota com XML neste período e filtro."})
        na_hora = cabe_na_hora(notas)
        job = enqueue_bulk_job(account=request.account, user=request.user, action=BulkJob.INVOICE_XML_EXPORT,
                               payload=payload, total=total, dispatch=not na_hora)
        if not na_hora:
            return Response(queued_response(job), status=status.HTTP_202_ACCEPTED)
        return Response(situacao(run_bulk_job(job.pk)), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path=_ID_DO_LOTE)
    def xml_export_status(self, request, job_id=None):
        job = self._exportacao(job_id)
        if job is None:
            return Response({"detail": "Exportação não encontrada."}, status=status.HTTP_404_NOT_FOUND)
        return Response(situacao(job))

    @action(detail=False, methods=["get"], url_path=f"{_ID_DO_LOTE}/download")
    def xml_export_download(self, request, job_id=None):
        job = self._exportacao(job_id)
        if job is None:
            return Response({"detail": "Exportação não encontrada."}, status=status.HTTP_404_NOT_FOUND)
        try:
            arquivo, nome = abrir(job)
        except ExportacaoIndisponivel as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return FileResponse(arquivo, as_attachment=True, filename=nome, content_type="application/zip")

    def _restaurante_de_quem_pede(self):
        """`None` para o administrador (a conta toda); senão o restaurante do perfil."""
        if is_tenant_admin(self.request.user):
            return None
        profile = getattr(self.request.user, "profile", None)
        return str(profile.restaurant_id) if profile and profile.restaurant_id else ""

    def _exportacao(self, job_id):
        """O lote é da conta; fora o administrador, só quem pediu o vê."""
        job = BulkJob.all_objects.filter(
            pk=job_id, account=self.request.account, action=BulkJob.INVOICE_XML_EXPORT,
        ).first()
        if job is None or is_tenant_admin(self.request.user) or job.requested_by_id == self.request.user.pk:
            return job
        return None
