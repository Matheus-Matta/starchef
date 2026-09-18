"""`POST /api/v1/sync/credentials/` — a loja pede o segredo de emissão.

POST e não GET de propósito: entregar credencial é um ato auditável, não a
leitura de um recurso. GET convida cache de proxy, histórico de navegador e
log de servidor com a URL completa — e nenhum deles deveria encostar nisso.
"""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.synchronization.node_auth import NodeTokenAuthentication, node_of
from apps.synchronization.services import credentials, guard

logger = logging.getLogger(__name__)


class SyncCredentialsView(APIView):
    """Devolve o envelope cifrado com o segredo de emissão daquele nó."""

    authentication_classes = [NodeTokenAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    # A loja pede quando vai emitir e guarda em memória por alguns minutos.
    # Um pedido por minuto é folgado para o uso legítimo e estreito para quem
    # esteja varrendo com um token capturado.
    throttle_scope = "sync_credentials"

    def post(self, request):
        no = node_of(request)
        if no is None:
            return Response(
                {"detail": "Esta rota é exclusiva de nó de sincronização."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            guard.ensure_enabled()
            pacote = credentials.montar_pacote(no)
            envelope = credentials.cifrar_para(no, pacote)
        except credentials.CredentialsUnavailable as erro:
            logger.warning("sync-credenciais: recusado para o nó %s — %s", no.id, erro)
            return Response({"detail": str(erro)}, status=status.HTTP_409_CONFLICT)
        except guard.SyncDisabled as erro:
            return Response({"detail": str(erro)}, status=status.HTTP_403_FORBIDDEN)

        # O QUE foi entregue nunca vai para o log; QUEM pediu, sempre.
        logger.warning(
            "sync-credenciais: entregue ao nó %s (conta %s) ip=%s",
            no.id, no.account_id, self._ip(request),
        )
        return Response({"node_id": str(no.id), "envelope": envelope})

    def _ip(self, request):
        encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
        return encaminhado.split(",")[0].strip() or request.META.get("REMOTE_ADDR")
