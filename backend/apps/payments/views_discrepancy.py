"""Rotas da divergência de vendas e do relatório das sessões selecionadas."""
import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework import status as http
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.core.access import is_tenant_admin
from apps.core.audit import record_audit
from apps.core.mixins import TenantQuerySetMixin
from apps.core.models import AuditLog
from apps.core.permissions import effective_permission_codes
from apps.core.viewsets import BaseTenantViewSet
from apps.payments.discrepancy import SalesDiscrepancy
from apps.payments.discrepancy_report import MAXIMO_DE_SESSOES, relatorio
from apps.payments.discrepancy_serializers import SalesDiscrepancySerializer
from apps.payments.models import CashRegister

#: Quem consulta; quem registra; quem analisa, regulariza e cancela.
VER = {"cash.view", "cash.manage", "cash.approve"}
REGISTRAR = {"cash.manage", "cash.approve"}
DECIDIR = {"cash.approve"}


def _exigir(request, codigos, mensagem):
    if is_tenant_admin(request.user):
        return
    tem = effective_permission_codes(request.user)
    if "*" not in tem and not (codigos & set(tem)):
        raise PermissionDenied(mensagem)


def _e_uuid(valor):
    try:
        uuid.UUID(str(valor))
    except ValueError:
        return False
    return True


def _ids(request):
    """`?cash_registers=a,b,c` — ids separados por vírgula."""
    bruto = request.query_params.get("cash_registers") or ""
    return [i.strip() for i in bruto.split(",") if i.strip()]


class SalesDiscrepancyViewSet(BaseTenantViewSet):
    serializer_class = SalesDiscrepancySerializer
    queryset = SalesDiscrepancy.objects.select_related("cash_register__cash_station", "created_by").all()
    filterset_fields = ["status", "cash_register"]
    ordering_fields = ["created_at", "amount"]
    # Não se apaga: o que foi registrado errado é CANCELADO, com motivo.
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        consulta = super().get_queryset()
        ids = [i for i in _ids(self.request) if _e_uuid(i)]
        return consulta.filter(cash_register_id__in=ids) if _ids(self.request) else consulta

    def list(self, request, *args, **kwargs):
        _exigir(request, VER, "Sem permissão para ver as divergências de caixa.")
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        _exigir(request, VER, "Sem permissão para ver as divergências de caixa.")
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        _exigir(request, REGISTRAR, "Registrar divergência exige gerenciar o caixa.")
        return super().create(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        _exigir(request, REGISTRAR, "Editar divergência exige gerenciar o caixa.")
        if self.get_object().status != SalesDiscrepancy.STATUS_OPEN:
            return Response({"detail": "Só a divergência aberta pode ser editada."}, status=http.HTTP_409_CONFLICT)
        if "cash_register" in request.data:
            raise ValidationError({"cash_register": "A sessão de caixa não muda depois de registrada."})
        return super().partial_update(request, *args, **kwargs)

    def _transicao(self, request, *, de, para, campos):
        """Trava, RELÊ o estado depois da trava e só então decide (409 se mudou)."""
        _exigir(request, DECIDIR, "Analisar ou regularizar divergência exige aprovar operações do caixa.")
        alvo = self.get_object()
        with transaction.atomic():
            linha = SalesDiscrepancy.all_objects.select_for_update().get(pk=alvo.pk)
            if linha.status not in de:
                return Response(
                    {"detail": f"A divergência está {linha.get_status_display().lower()}: nada a fazer."},
                    status=http.HTTP_409_CONFLICT,
                )
            linha.status = para
            for nome, valor in campos.items():
                setattr(linha, nome, valor)
            linha.updated_by = request.user
            linha.save()
            record_audit(
                action=AuditLog.ACTION_UPDATED, instance=linha, actor=request.user,
                reason=campos.get("regularization_note") or campos.get("cancel_reason") or "",
                metadata={"event": f"sales_discrepancy_{para}"},
            )
        return Response(self.get_serializer(linha).data)

    @action(detail=True, methods=["post"], url_path="review")
    def review(self, request, pk=None):
        agora = timezone.now()
        return self._transicao(
            request, de={SalesDiscrepancy.STATUS_OPEN}, para=SalesDiscrepancy.STATUS_REVIEWED,
            campos={"reviewed_by": request.user, "reviewed_at": agora},
        )

    @action(detail=True, methods=["post"], url_path="regularize")
    def regularize(self, request, pk=None):
        nota = str(request.data.get("note") or "").strip() if isinstance(request.data, dict) else ""
        if not nota:
            raise ValidationError({"note": "Descreva como foi regularizado (ex.: protocolo da denúncia espontânea)."})
        return self._transicao(
            request, de={SalesDiscrepancy.STATUS_OPEN, SalesDiscrepancy.STATUS_REVIEWED},
            para=SalesDiscrepancy.STATUS_REGULARIZED,
            campos={"regularized_by": request.user, "regularized_at": timezone.now(), "regularization_note": nota},
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        motivo = str(request.data.get("reason") or "").strip() if isinstance(request.data, dict) else ""
        if not motivo:
            raise ValidationError({"reason": "Informe por que a divergência está sendo cancelada."})
        return self._transicao(
            request, de={SalesDiscrepancy.STATUS_OPEN, SalesDiscrepancy.STATUS_REVIEWED},
            para=SalesDiscrepancy.STATUS_CANCELLED,
            campos={"cancelled_by": request.user, "cancelled_at": timezone.now(), "cancel_reason": motivo},
        )


class CashDiscrepancyReportViewSet(TenantQuerySetMixin, viewsets.GenericViewSet):
    """`GET /cash-discrepancy-report/?cash_registers=a,b` — as sessões selecionadas."""

    queryset = CashRegister.objects.all()

    def list(self, request):
        _exigir(request, VER, "Sem permissão para ver as divergências de caixa.")
        ids = _ids(request)
        if not ids or len(ids) > MAXIMO_DE_SESSOES:
            raise ValidationError({"cash_registers": f"Selecione de 1 a {MAXIMO_DE_SESSOES} sessões de caixa."})
        if not all(_e_uuid(i) for i in ids):
            # Id torto iria estourar dentro da consulta (500): é entrada errada.
            raise ValidationError({"cash_registers": "Sessão de caixa inválida."})
        dados = relatorio(self.get_queryset().filter(pk__in=ids))
        return Response(dados)
