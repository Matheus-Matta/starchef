"""Rotas da transferência de arquivo, montadas em `/api/v1/sync/files/`."""
from django.urls import path

from apps.synchronization.views_files import (
    SyncFileChunkView,
    SyncFileCompleteView,
    SyncFileDownloadView,
    SyncFileOpenView,
    SyncFileStatusView,
)

urlpatterns = [
    path("", SyncFileOpenView.as_view(), name="sync-file-open"),
    path("<uuid:pk>/", SyncFileStatusView.as_view(), name="sync-file-status"),
    path("<uuid:pk>/chunk/", SyncFileChunkView.as_view(), name="sync-file-chunk"),
    path("<uuid:pk>/complete/", SyncFileCompleteView.as_view(), name="sync-file-complete"),
    path("<uuid:pk>/download/", SyncFileDownloadView.as_view(), name="sync-file-download"),
]
