"""Rotas da API de sincronização, montadas em `/api/v1/sync/`."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.synchronization.views import (
    SyncConflictViewSet,
    SyncEventViewSet,
    SyncNodeViewSet,
    SyncRunViewSet,
)
from apps.synchronization.views_credentials import SyncCredentialsView
from apps.synchronization.views_fiscal_relay import SyncFiscalRelayView
from apps.synchronization.views_enroll import SyncEnrollView
from apps.synchronization.views_metrics import SyncMetricsView

# `SimpleRouter`, não `DefaultRouter`: o segundo registra o conversor de
# sufixo de formato (`.json`) no Django, e registrá-lo duas vezes — uma por
# router do projeto — emite RemovedInDjango60Warning e vira erro no Django 6.
# Esta API é de servidor para servidor: ninguém pede `/api/v1/sync/nodes.json`
# nem precisa da raiz navegável.
router = SimpleRouter()
router.register("nodes", SyncNodeViewSet, basename="sync-nodes")
router.register("events", SyncEventViewSet, basename="sync-events")
router.register("runs", SyncRunViewSet, basename="sync-runs")
router.register("conflicts", SyncConflictViewSet, basename="sync-conflicts")

urlpatterns = [
    # Primeiro contato da loja: sem token, autentica por usuário e senha no
    # corpo. Precisa vir ANTES do router para não ser engolida por ele.
    path("enroll/", SyncEnrollView.as_view(), name="sync-enroll"),
    # Segredo de emissão, emprestado sob demanda e nunca replicado. Autentica
    # por token de NÓ, como as métricas e a transferência de arquivo.
    path("credentials/", SyncCredentialsView.as_view(), name="sync-credentials"),
    path("fiscal/", SyncFiscalRelayView.as_view(), name="sync-fiscal"),
    # Métricas para o coletor e transferência de binário: autenticam por token
    # (de raspagem e de nó), não por JWT de usuário. Antes do router, pelo
    # mesmo motivo da matrícula.
    path("metrics/", SyncMetricsView.as_view(), name="sync-metrics"),
    path("files/", include("apps.synchronization.urls_files")),
    path("", include(router.urls)),
]
