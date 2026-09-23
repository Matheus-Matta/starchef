"""`POST /api/v1/sync/fiscal/` — a nuvem transmite a nota em nome da loja.

A loja monta o documento; aqui ele é entregue ao provedor com a credencial da
nuvem, e a resposta volta crua para quem sabe interpretá-la.

**Três operações nomeadas, nunca um proxy.** A tentação é aceitar `(método,
caminho, corpo)` e deixar a loja endereçar o provedor. Seria entregar a chave
mestra por outro buraco: o mesmo token que emite nota também faz
`DELETE /v2/empresas/{id}`. Aqui só existe transmitir, consultar e cancelar UM
documento, e o caminho é montado deste lado.

**O escopo é do nó.** A configuração fiscal usada é a da loja daquele nó,
nunca a que o corpo pedir. Uma loja transmite como a própria empresa ou não
transmite.
"""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.synchronization.node_auth import NodeTokenAuthentication, node_of
from apps.synchronization.services import fiscal_relay, guard

logger = logging.getLogger(__name__)


class SyncFiscalRelayView(APIView):
    """Transmite, consulta ou cancela UM documento fiscal da loja do nó."""

    authentication_classes = [NodeTokenAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    # Uma venda, um pedido. Folgado para o balcão mais cheio e estreito para
    # quem varra com um token capturado.
    throttle_scope = "sync_fiscal"

    def post(self, request):
        no = node_of(request)
        if no is None:
            return Response(
                {"detail": "Esta rota é exclusiva de nó de sincronização."},
                status=status.HTTP_403_FORBIDDEN,
            )

        operacao = str(request.data.get("operation") or "").strip()
        referencia = str(request.data.get("reference") or "").strip()
        modelo = str(request.data.get("document_model") or "").strip()
        if not referencia or not modelo:
            return Response(
                {"detail": "Informe a referência e o modelo do documento."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            guard.ensure_enabled()
            codigo, dados = fiscal_relay.executar(
                no,
                operacao=operacao,
                reference=referencia,
                document_model=modelo,
                payload=request.data.get("payload"),
                reason=str(request.data.get("reason") or ""),
            )
        except fiscal_relay.RelayRecusado as erro:
            logger.warning("sync-fiscal: recusado para o nó %s — %s", no.id, erro)
            return Response({"detail": str(erro)}, status=status.HTTP_409_CONFLICT)
        except guard.SyncDisabled as erro:
            return Response({"detail": str(erro)}, status=status.HTTP_403_FORBIDDEN)
        except Exception as erro:  # noqa: BLE001 — a loja precisa poder tentar de novo
            # Falha ao FALAR com o provedor não diz nada sobre o documento. 503
            # é o que a loja traduz em indisponibilidade, e indisponibilidade é
            # a única família que autoriza retentativa.
            logger.warning("sync-fiscal: falha ao transmitir pelo nó %s — %s", no.id, erro)
            return Response(
                {"detail": f"Falha ao falar com o provedor fiscal: {erro}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # O QUE foi transmitido nunca vai para o log; QUEM pediu, sempre.
        logger.warning(
            "sync-fiscal: %s concluída para o nó %s (conta %s) ref=%s provedor=%s",
            operacao, no.id, no.account_id, referencia, codigo,
        )
        return Response({"status_code": codigo, "data": dados})
