"""API de gerenciamento da sincronização.

O que ela cobre: ver os nós e o estado de cada um, ler a fila, disparar carga,
reprocessar o que falhou e resolver conflitos. É o mesmo conjunto de ações do
Admin, disponível para uma tela própria.

Tudo aqui é restrito: exige superusuário ou a permissão específica, e o
queryset é filtrado pela conta do usuário. A matrícula — a única rota aberta a
não autenticados — mora em `views_enroll.py`.
"""
import logging

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.synchronization.constants import ConflictStatus
from apps.synchronization.models import SyncConflict, SyncEvent, SyncNode, SyncRun
from apps.synchronization.permissions import CanManageSync, CanStartFullSync
from apps.synchronization.serializers import (
    StartRunSerializer,
    SyncConflictSerializer,
    SyncEventDetailSerializer,
    SyncEventSerializer,
    SyncNodeSerializer,
    SyncRunSerializer,
)
from apps.synchronization.services import bootstrap, guard, provisioning, recovery
from apps.synchronization.views_mixins import AccountScopedMixin

logger = logging.getLogger(__name__)


class SyncNodeViewSet(AccountScopedMixin, viewsets.ModelViewSet):
    """Os nós da conta: cadastro, estado e as ações de carga."""

    serializer_class = SyncNodeSerializer
    permission_classes = [IsAuthenticated, CanManageSync]
    queryset = SyncNode.objects.select_related("account", "restaurant").all()
    filterset_fields = ["node_type", "status", "is_active"]
    search_fields = ["name", "id"]

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, CanStartFullSync])
    def start_run(self, request, pk=None):
        """Dispara a carga. Enfileira só depois do commit, e volta na hora."""
        no = self.get_object()
        entrada = StartRunSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)

        try:
            guard.ensure_enabled()
            run = bootstrap.start_run(
                target_node=no,
                run_type=entrada.validated_data["run_type"],
                user=request.user,
                ip=self._ip(request),
                reason=entrada.validated_data.get("reason", ""),
            )
        except bootstrap.BootstrapBusy as erro:
            return Response({"detail": str(erro)}, status=status.HTTP_409_CONFLICT)
        except guard.SyncDisabled as erro:
            return Response({"detail": str(erro)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        from apps.synchronization.tasks.bootstrap import run_bootstrap

        transaction.on_commit(lambda: run_bootstrap.delay(str(run.id)))
        logger.info("sync-api: %s iniciou carga %s no nó %s", request.user, run.id, no.id)
        return Response(SyncRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, CanStartFullSync])
    def requeue(self, request, pk=None):
        """Devolve à fila o que falhou ou morreu neste nó."""
        no = self.get_object()
        total = recovery.requeue(account_id=no.account_id, apenas_mortos=False)
        return Response({"requeued": total})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, CanStartFullSync])
    def revoke(self, request, pk=None):
        no = self.get_object()
        provisioning.revoke(no, motivo=f"Revogado por {request.user} pela API.")
        return Response(SyncNodeSerializer(no).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, CanStartFullSync])
    def rotate_credentials(self, request, pk=None):
        """Token e chave novos. Aparecem UMA vez, nesta resposta."""
        no = self.get_object()
        segredos = provisioning.rotate_credentials(no)
        logger.warning("sync-api: %s rotacionou a credencial do nó %s", request.user, no.id)
        return Response({"package": segredos, "warning": "Guarde agora: não é possível recuperar."})

    @action(detail=False, methods=["get"])
    def status(self, request):
        """Retrato da sincronização inteira desta conta."""
        conta = self._account_id(request)
        return Response({
            "enabled": guard.is_enabled(),
            "environment": guard.current_environment(),
            "node_type": guard.node_type(),
            "queue": recovery.snapshot(account_id=conta),
            "open_conflicts": SyncConflict.objects.filter(
                account_id=conta, status=ConflictStatus.OPEN
            ).count() if conta else 0,
            "running": SyncRunSerializer(
                SyncRun.objects.filter(account_id=conta).order_by("-created_at")[:5], many=True
            ).data if conta else [],
        })

    def _ip(self, request):
        encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
        return encaminhado.split(",")[0].strip() or request.META.get("REMOTE_ADDR")


class SyncEventViewSet(AccountScopedMixin, viewsets.ReadOnlyModelViewSet):
    """A fila, só leitura — com o botão de devolver à fila."""

    permission_classes = [IsAuthenticated, CanManageSync]
    queryset = SyncEvent.objects.all()
    filterset_fields = ["direction", "status", "entity_type", "operation"]
    search_fields = ["entity_id", "event_id"]

    def get_serializer_class(self):
        return SyncEventDetailSerializer if self.action == "retrieve" else SyncEventSerializer

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, CanStartFullSync])
    def requeue(self, request, pk=None):
        evento = self.get_object()
        recovery.requeue([evento])
        return Response(SyncEventSerializer(evento).data)

    @action(detail=False, methods=["get"])
    def dead(self, request):
        """Os que desistiram. Continuam íntegros e reprocessáveis."""
        mortos = recovery.dead_letters(account_id=self._account_id(request))
        return Response(SyncEventSerializer(mortos, many=True).data)

    @action(detail=False, methods=["get"])
    def stuck(self, request):
        minutos = int(request.query_params.get("minutes", 30))
        return Response(SyncEventSerializer(recovery.stuck(minutos), many=True).data)


class SyncRunViewSet(AccountScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = SyncRunSerializer
    permission_classes = [IsAuthenticated, CanManageSync]
    queryset = SyncRun.objects.select_related("target_node", "source_node").all()
    filterset_fields = ["run_type", "status"]


class SyncConflictViewSet(AccountScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = SyncConflictSerializer
    permission_classes = [IsAuthenticated, CanManageSync]
    queryset = SyncConflict.objects.all()
    filterset_fields = ["status", "entity_type", "resolution"]

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, CanStartFullSync])
    def resolve(self, request, pk=None):
        """Marca o conflito como decidido. Não reaplica nada sozinho."""
        from django.utils import timezone

        conflito = self.get_object()
        conflito.status = request.data.get("status", ConflictStatus.RESOLVED)
        conflito.notes = request.data.get("notes", "")[:2000]
        conflito.resolved_by = request.user
        conflito.resolved_at = timezone.now()
        conflito.save(update_fields=["status", "notes", "resolved_by", "resolved_at"])
        return Response(SyncConflictSerializer(conflito).data)
