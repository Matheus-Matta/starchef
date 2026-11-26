"""O CSC da NFC-e para o StarChef Desktop: `GET /fiscal/config/{id}/desktop-csc/`.

O desktop emite com o comunicador dele, que guarda só o certificado A1 e a
senha (digitados no próprio computador). O CSC entra em cada pedido de emissão,
e quem o tem é o cadastro fiscal daqui — `csc_token` é só de escrita na API
comum, então o desktop não tinha de onde tirá-lo e o operador digitava de novo.

Quem pode: o administrador da conta, ou quem é da MESMA loja da configuração.
Nunca o de outra loja da conta. Cada entrega fica na auditoria (quem, quando).
Vale o segredo emprestado da nuvem (`segredos_de`), como na emissão daqui.
"""
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.access import is_tenant_admin
from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.invoices.models import FiscalConfig


def pode_receber(user, config):
    if is_tenant_admin(user):
        return True
    profile = getattr(user, "profile", None)
    return bool(profile and profile.restaurant_id and str(profile.restaurant_id) == str(config.restaurant_id))


class CscDoDesktopMixin:
    @action(detail=True, methods=["get"], url_path="desktop-csc")
    def desktop_csc(self, request, pk=None):
        """O ID e o código do CSC desta configuração de NFC-e. 404 fora da loja de quem pede."""
        from apps.invoices.emission_secrets import segredos_de

        config = self.get_object()
        if not pode_receber(request.user, config):
            return Response({"detail": "Configuracao fiscal nao encontrada."}, status=status.HTTP_404_NOT_FOUND)
        if config.document_model != FiscalConfig.MODEL_NFCE:
            return Response({"detail": "So a NFC-e (modelo 65) usa CSC."}, status=status.HTTP_400_BAD_REQUEST)
        segredos = segredos_de(config)
        record_audit(action=AuditLog.ACTION_PRINTED, instance=config, actor=request.user, request=request,
                     reason="CSC entregue ao StarChef Desktop", metadata={"event": "desktop_csc_delivered"})
        return Response({"csc_id": segredos.csc_id, "csc_token": segredos.csc_token,
                         "configured": bool(segredos.csc_id and segredos.csc_token)})
