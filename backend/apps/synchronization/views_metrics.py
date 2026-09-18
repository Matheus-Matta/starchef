"""`GET /api/v1/sync/metrics/` — as métricas do §19.1 para o Prometheus.

Nunca aberta. Dois caminhos de acesso, e só eles: o token de raspagem
(`SYNC_METRICS_TOKEN`) ou um superusuário autenticado. Sem token configurado,
sobra o superusuário — a rota não "abre por padrão" em nenhum cenário.
"""
from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core import rls
from apps.synchronization.node_auth import metrics_token_ok
from apps.synchronization.services import guard, metrics

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


class SyncMetricsView(APIView):
    # AllowAny aqui é só para o DRF sair da frente: a autorização de verdade
    # está no `get`, porque o raspador não tem usuário e o superusuário não tem
    # token — são dois caminhos que nenhuma permission class cobre junto.
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        if not self._autorizado(request):
            return HttpResponse("não autorizado\n", status=401, content_type="text/plain")

        if not guard.is_enabled():
            # Responder 200 com zero seria mentir para o painel: um gráfico
            # chapado em zero é indistinguível de "tudo em dia".
            return HttpResponse(
                "# sincronização desligada nesta instalação (SYNC_ENABLED=false)\n",
                content_type=CONTENT_TYPE,
            )
        # As métricas contam TODAS as contas — é o que uma métrica de
        # plataforma é. Com RLS ligada e sem esta declaração, cada número
        # viraria zero e o painel diria "nenhuma fila pendente" para uma nuvem
        # com a fila cheia: o pior resultado possível para um alerta.
        with rls.escopo_da_plataforma("métricas de sincronização"):
            corpo = metrics.render()
        return HttpResponse(corpo, content_type=CONTENT_TYPE)

    def _autorizado(self, request):
        """Token de raspagem OU superusuário. Nesta ordem, e sem lista de auth.

        `authentication_classes` fica vazia de propósito: o token do coletor é
        um segredo simples, não um JWT, e a classe de autenticação do projeto
        levantaria 401 nele antes de qualquer código nosso rodar. Então os dois
        caminhos são testados aqui — o do coletor primeiro, porque é o comum, e
        o do JWT com a falha engolida, porque "não é um JWT válido" aqui
        significa "não é esse o caminho", não "acesso negado".
        """
        if metrics_token_ok(request):
            return True
        usuario = self._usuario_do_jwt(request)
        return bool(usuario and usuario.is_superuser)

    def _usuario_do_jwt(self, request):
        from apps.core.authentication import CookieJWTAuthentication

        try:
            resultado = CookieJWTAuthentication().authenticate(request)
        except Exception:  # noqa: BLE001 — token ausente ou inválido: outro caminho
            return None
        return resultado[0] if resultado else None
