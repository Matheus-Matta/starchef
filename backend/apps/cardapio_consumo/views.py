from datetime import date

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.cardapio_consumo.agenda import proximas_datas
from apps.cardapio_consumo.execucao import JaExecutado, executar
from apps.cardapio_consumo.models import CardapioConsumo
from apps.cardapio_consumo.previsao import previsao_para
from apps.cardapio_consumo.quem_executa import BaixaSoNaNuvem, este_servidor_executa
from apps.cardapio_consumo.serializers import CardapioConsumoSerializer, ExecucaoCardapioSerializer
from apps.core.modules import MODULE_LOGISTICA
from apps.core.viewsets import BaseTenantViewSet


class CardapioConsumoViewSet(BaseTenantViewSet):
    required_module = MODULE_LOGISTICA
    serializer_class = CardapioConsumoSerializer
    queryset = CardapioConsumo.objects.select_related("local").prefetch_related(
        "itens__ingredient", "itens__product").all()
    filterset_fields = ["ativo", "frequencia", "local"]
    search_fields = ["nome"]
    ordering_fields = ["nome", "created_at"]

    @action(detail=True, methods=["get"])
    def previsao(self, request, pk=None):
        """Precisa × saldo de agora × falta, para a próxima data (ou `?data=`)."""
        cardapio = self.get_object()
        data = self._data(request) or next(iter(proximas_datas(cardapio, timezone.localdate(), 1)), None)
        linhas, avisos = previsao_para([cardapio], cardapio.local)
        return Response({"data": data.isoformat() if data else None, "linhas": linhas, "avisos": avisos,
                         "baixa_aqui": este_servidor_executa()})

    @action(detail=True, methods=["post"])
    def executar(self, request, pk=None):
        """Executa HOJE, fora do horário — para começar sem esperar o agendador."""
        cardapio = self.get_object()
        try:
            execucao = executar(cardapio, timezone.localdate(), user=request.user)
        except (JaExecutado, BaixaSoNaNuvem) as exc:
            # 409: é estado do servidor, não entrada errada — reenviar não muda nada.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(ExecucaoCardapioSerializer(execucao).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def historico(self, request, pk=None):
        execucoes = self.get_object().execucoes.filter(deleted_at__isnull=True)[:60]
        return Response(ExecucaoCardapioSerializer(execucoes, many=True).data)

    @staticmethod
    def _data(request):
        try:
            return date.fromisoformat(request.query_params.get("data", ""))
        except ValueError:
            return None
