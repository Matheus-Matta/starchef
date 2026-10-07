"""`POST /imports/`: entrega o lote ao worker e responde na hora (202)."""
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.response import Response

from apps.core.viewsets import BaseTenantViewSet
from apps.imports.models import ImportJob
from apps.imports.targets import AlvoInvalido, campo_chave_valido, resolver_alvo

MAX_LINHAS = 5000


class ImportJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportJob
        fields = ["id", "endpoint", "status", "total", "created_count", "updated_count", "errors",
                  "created_at", "finished_at"]
        read_only_fields = fields


class ImportJobViewSet(BaseTenantViewSet):
    serializer_class = ImportJobSerializer
    queryset = ImportJob.objects.all()
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        # Cada um acompanha a própria importação.
        return super().get_queryset().filter(requested_by=self.request.user)

    def create(self, request, *args, **kwargs):
        linhas = request.data.get("rows")
        if not isinstance(linhas, list) or not linhas:
            return Response({"detail": "Envie as linhas da planilha."}, status=status.HTTP_400_BAD_REQUEST)
        if len(linhas) > MAX_LINHAS:
            return Response({"detail": f"No máximo {MAX_LINHAS} linhas por importação."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not all(isinstance(linha, dict) for linha in linhas):
            return Response({"detail": "Cada linha precisa ser um objeto."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            classe = resolver_alvo(request.data.get("endpoint"))
            chave = campo_chave_valido(classe, request.data.get("key") or "")
        except AlvoInvalido as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        job = ImportJob.objects.create(
            account=request.account, requested_by=request.user, endpoint=request.data["endpoint"],
            key_field=chave, restaurant_scope=request.headers.get("X-Restaurant-ID", "")[:64],
            rows=linhas, total=len(linhas),
        )
        from apps.imports.tasks import run_import_task

        transaction.on_commit(lambda: run_import_task.delay(str(job.pk)))
        return Response(self.get_serializer(job).data, status=status.HTTP_202_ACCEPTED)
