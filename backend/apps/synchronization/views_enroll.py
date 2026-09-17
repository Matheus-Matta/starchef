"""A rota de matrícula: o primeiro contato de um backend de loja.

Fica separada das demais views porque é a ÚNICA da sincronização aberta sem
token — quem chama ainda não tem nenhum. Ela autentica por usuário e senha no
próprio corpo, e devolve o pacote de credenciais cifrado com o segredo de
matrícula.
"""
import logging

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.synchronization.constants import RunType
from apps.synchronization.serializers import EnrollRequestSerializer
from apps.synchronization.services import enrollment, guard

logger = logging.getLogger(__name__)


class SyncEnrollView(APIView):
    """`POST /api/v1/sync/enroll/` — a loja se matricula e pede a carga inicial.

    Autentica pelo corpo (usuário e senha de superadmin/admin da conta) porque
    quem chama ainda NÃO tem token nenhum: é o primeiro contato da instalação.
    O pacote de credenciais volta cifrado com o segredo de matrícula.
    """

    permission_classes = [AllowAny]
    throttle_scope = "sync_enroll"

    def post(self, request):
        entrada = EnrollRequestSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data

        try:
            no, envelope, run = enrollment.enroll(
                username=dados["username"],
                password=dados["password"],
                account_id=dados["account_id"],
                enrollment_secret=dados["enrollment_secret"],
                node_name=dados["node_name"],
                restaurant_id=dados.get("restaurant_id"),
                cloud_wss_url=dados.get("cloud_wss_url", ""),
                existing_node_id=dados.get("existing_node_id"),
                client_ip=request.META.get("REMOTE_ADDR"),
            )
        except enrollment.EnrollmentRefused as erro:
            return Response({"detail": str(erro)}, status=status.HTTP_403_FORBIDDEN)
        except guard.SyncDisabled as erro:
            return Response({"detail": str(erro)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        from apps.synchronization.tasks.bootstrap import run_bootstrap

        transaction.on_commit(lambda: run_bootstrap.delay(str(run.id)))
        return Response(
            {
                "node_id": str(no.id),
                "pair_id": str(no.pair_id),
                "run_id": str(run.id),
                "run_type": RunType.FULL,
                "package": envelope,
            },
            status=status.HTTP_201_CREATED,
        )
