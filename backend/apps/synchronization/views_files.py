"""Rotas HTTP da transferência de arquivo (§16).

Autenticadas por TOKEN DE NÓ, não por JWT de usuário: quem chama é um servidor.
Todas checam que o nó autenticado é parte da transferência — o `id` na URL
nunca é prova de nada.

    POST /api/v1/sync/files/                 abre ou retoma; devolve o offset
    PUT  /api/v1/sync/files/<id>/chunk/      grava um pedaço no offset dado
    POST /api/v1/sync/files/<id>/complete/   confere e move para o destino
    GET  /api/v1/sync/files/<id>/            estado (para retomar)
    GET  /api/v1/sync/files/<id>/download/   baixa a partir de ?offset=
"""
import logging

from django.http import Http404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.synchronization.models.transfer import SyncFileTransfer
from apps.synchronization.node_auth import NodeTokenAuthentication, node_of
from apps.synchronization.serializers_files import (
    UPLOAD,
    OpenTransferSerializer,
    TransferSerializer,
)
from apps.synchronization.services import files, nodes
from apps.synchronization.views_files_download import DownloadMixin

logger = logging.getLogger(__name__)


class NodeRouteMixin:
    authentication_classes = [NodeTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def _indisponivel(self, erro):
        """503 com o motivo real: a culpa é do servidor, e retentar resolve.

        Um 500 "erro interno" aqui obriga alguém a abrir o log do container
        para descobrir que era permissão de volume ou disco cheio.
        """
        logger.error("sync-file: área de trabalho indisponível — %s", erro)
        return Response(
            {"code": "transfer_unavailable", "message": str(erro)},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def transferencia_do_no(self, pk, no):
        """A transferência, SE o nó autenticado for uma das duas pontas."""
        transferencia = SyncFileTransfer.objects.filter(pk=pk).first()
        if transferencia is None:
            raise Http404
        if no.id not in (transferencia.source_node_id, transferencia.target_node_id):
            # 404, não 403: confirmar que o id existe já entrega informação a
            # quem está varrendo.
            logger.warning("sync-file: nó %s pediu transferência alheia %s", no.id, pk)
            raise Http404
        return transferencia


class SyncFileOpenView(NodeRouteMixin, APIView):
    """Abre ou retoma. A resposta diz de qual offset continuar."""

    def post(self, request):
        no = node_of(request)
        entrada = OpenTransferSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data

        # Quem chama é sempre UMA das pontas; a outra somos nós. `upload`
        # significa que o arquivo está vindo para cá, `download` que está indo
        # para lá — e é isso que define origem e destino do registro.
        proprio = nodes.self_node()
        empurrando = dados["direction"] == UPLOAD
        origem, destino = (no, proprio) if empurrando else (proprio, no)

        try:
            transferencia, offset = files.open_transfer(
                account_id=no.account_id,
                source_node=origem,
                target_node=destino,
                entity_type=dados["entity_type"],
                entity_id=dados["entity_id"],
                field_name=dados["field_name"],
                storage_path=dados["storage_path"],
                total_bytes=dados["total_bytes"],
                checksum=dados["checksum"],
                content_type=dados.get("content_type", ""),
            )
        except files.TransferRejected as erro:
            return Response({"detail": str(erro)}, status=status.HTTP_400_BAD_REQUEST)
        except files.TransferUnavailable as erro:
            return self._indisponivel(erro)

        corpo = TransferSerializer(transferencia).data
        corpo["offset"] = offset
        corpo["chunk_bytes"] = files.CHUNK_BYTES
        return Response(corpo, status=status.HTTP_201_CREATED)


class SyncFileChunkView(NodeRouteMixin, APIView):
    """Grava um pedaço. O corpo é binário puro; o offset vai no cabeçalho."""

    parser_classes = []  # bytes crus: nenhum parser do DRF deve tocar no corpo

    def put(self, request, pk):
        no = node_of(request)
        transferencia = self.transferencia_do_no(pk, no)
        try:
            offset = int(request.META.get("HTTP_X_SYNC_OFFSET", ""))
        except ValueError:
            return Response({"detail": "Cabeçalho X-Sync-Offset ausente ou inválido."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            novo = files.write_chunk(transferencia, offset, request.body)
        except files.TransferRejected as erro:
            return self._desalinhado(transferencia, erro)
        except files.TransferUnavailable as erro:
            return self._indisponivel(erro)
        return Response({"offset": novo, "total_bytes": transferencia.total_bytes})

    def _desalinhado(self, transferencia, erro):
        """409 com o offset certo — para o cliente se realinhar, não desistir.

        O offset vai também num CABEÇALHO porque o corpo passa pelo envelope de
        erro da API (`apps.core.envelope`), que reescreve a estrutura. O
        formato `code` + `message` é o que o envelope preserva com os extras,
        mas o cabeçalho é o que um cliente de máquina pode ler sem depender
        desse detalhe.
        """
        esperado = transferencia.received_bytes
        resposta = Response(
            {
                "code": "offset_mismatch",
                "message": str(erro),
                "expected_offset": esperado,
            },
            status=status.HTTP_409_CONFLICT,
        )
        resposta["X-Sync-Expected-Offset"] = str(esperado)
        return resposta


class SyncFileCompleteView(NodeRouteMixin, APIView):
    """Confere tamanho e checksum, move e associa."""

    def post(self, request, pk):
        no = node_of(request)
        transferencia = self.transferencia_do_no(pk, no)
        try:
            files.finish(transferencia)
        except files.TransferRejected as erro:
            return Response({"detail": str(erro)}, status=status.HTTP_400_BAD_REQUEST)
        except files.TransferUnavailable as erro:
            return self._indisponivel(erro)
        return Response(TransferSerializer(transferencia).data)


class SyncFileStatusView(NodeRouteMixin, APIView):
    """Estado da transferência — é o que permite retomar depois de uma queda."""

    def get(self, request, pk):
        no = node_of(request)
        transferencia = self.transferencia_do_no(pk, no)
        corpo = TransferSerializer(transferencia).data
        corpo["offset"] = transferencia.received_bytes
        corpo["chunk_bytes"] = files.CHUNK_BYTES
        return Response(corpo)


class SyncFileDownloadView(DownloadMixin, NodeRouteMixin, APIView):
    """Serve o binário a partir do offset pedido, para quem está recebendo."""

    def get(self, request, pk):
        no = node_of(request)
        transferencia = self.transferencia_do_no(pk, no)
        return self.download(request, transferencia)
