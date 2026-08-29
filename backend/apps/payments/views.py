from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Prefetch
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.core.access import is_tenant_admin
from apps.core.modules import MODULE_FINANCEIRO
from apps.core.viewsets import BaseTenantViewSet, ReadOnlyTenantViewSet
from apps.payments.models import CashMovement, CashRegister, CashStation, PdvTerminal, Payment, PaymentMethod
from apps.payments.serializers import (
    CashMovementSerializer,
    CashRegisterSerializer,
    CashStationSerializer,
    PaymentMethodSerializer,
    PaymentSerializer,
    PdvTerminalSerializer,
)
from apps.payments.services import (
    approve_cash_operation,
    close_cash_register,
    create_cash_movement,
    open_cash_register,
    transfer_cash_session,
)
from apps.payments.terminals import (
    CashSessionConflict,
    CashSessionForbidden,
    active_session_for_station,
    installation_id_from_request,
    occupied_message,
    other_terminal_message,
    session_belongs_to,
    session_conflict_payload,
    terminal_from_request,
)

User = get_user_model()


def cash_session_error_response(exc):
    """Converte os erros de posse/conflito no envelope que a tela consome.

    A mensagem é sempre a da exceção — ela sabe se o caso é "este caixa está
    com outra pessoa" ou "você já está em outro caixa". O bloco `session` vai
    junto para a tela conseguir montar o aviso (e o botão de transferência)
    sem reinterpretar texto.
    """
    session = getattr(exc, "session", None)
    payload = session_conflict_payload(session) if session is not None else {"session": None}
    payload["code"] = getattr(exc, "error_code", "invalid")
    payload["message"] = " ".join(exc.messages)
    payload["detail"] = payload["message"]
    http_status = (
        status.HTTP_409_CONFLICT if isinstance(exc, CashSessionConflict) else status.HTTP_403_FORBIDDEN
    )
    return Response(payload, status=http_status)


class CashApprovalRateThrottle(UserRateThrottle):
    """Limita tentativas de senha sem reduzir o tráfego normal do PDV."""

    scope = "cash_approval"


class PaymentMethodViewSet(BaseTenantViewSet):
    serializer_class = PaymentMethodSerializer
    queryset = PaymentMethod.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["method_type", "is_active"]
    search_fields = ["name"]


class PaymentViewSet(ReadOnlyTenantViewSet):
    required_module = MODULE_FINANCEIRO  # historico analitico de pagamentos (o recebimento em si e do PDV/base)
    serializer_class = PaymentSerializer
    queryset = Payment.objects.select_related("restaurant", "branch", "order", "payment_method").all()
    filterset_fields = ["order", "payment_method", "status"]
    ordering_fields = ["paid_at", "amount"]


class CashStationViewSet(BaseTenantViewSet):
    serializer_class = CashStationSerializer
    queryset = CashStation.objects.select_related("restaurant").prefetch_related(
        "operators",
        Prefetch(
            "sessions",
            queryset=CashRegister.objects.select_related("opened_by").order_by("-opened_at"),
            to_attr="prefetched_sessions",
        ),
    ).all()
    filterset_fields = ["is_active"]
    search_fields = ["name", "code"]
    ordering_fields = ["name", "code", "created_at"]

    def destroy(self, request, *args, **kwargs):
        station = self.get_object()
        if station.sessions.exclude(status__in=[
            CashRegister.STATUS_CLOSED,
            CashRegister.STATUS_CLOSED_DIFFERENCE,
            CashRegister.STATUS_CANCELLED,
        ]).exists():
            return Response(
                {"detail": "Feche o caixa antes de excluí-lo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


class CashRegisterViewSet(BaseTenantViewSet):
    serializer_class = CashRegisterSerializer
    queryset = CashRegister.objects.select_related("restaurant", "branch", "opened_by", "closed_by").prefetch_related("movements").all()
    filterset_fields = ["status", "opened_by", "station"]
    ordering_fields = ["opened_at", "closed_at"]

    @action(detail=False, methods=["post"], url_path="open")
    def open(self, request):
        station = CashStation.objects.filter(
            pk=request.data.get("cash_station"),
            account=getattr(request, "account", None),
        ).select_related("restaurant").first()
        if station is None:
            return Response({"detail": "Selecione um caixa cadastrado no restaurante."}, status=status.HTTP_400_BAD_REQUEST)
        profile = getattr(request.user, "profile", None)
        if not is_tenant_admin(request.user) and getattr(profile, "restaurant_id", None) != station.restaurant_id:
            return Response({"detail": "O caixa selecionado não pertence ao seu restaurante."}, status=status.HTTP_403_FORBIDDEN)
        terminal = terminal_from_request(request, restaurant=station.restaurant)
        try:
            cash_register = open_cash_register(
                restaurant=station.restaurant,
                cash_station=station,
                user=request.user,
                opening_amount=request.data.get("opening_amount", 0),
                notes=request.data.get("notes", ""),
                station=request.data.get("station", "PDV principal"),
                device_identifier=installation_id_from_request(request),
                terminal=terminal,
            )
        except (CashSessionConflict, CashSessionForbidden) as exc:
            return cash_session_error_response(exc)
        except IntegrityError:
            # A `UniqueConstraint` parcial pegou uma corrida que escapou da
            # trava (outro processo, replay da fila). O caixa está ocupado —
            # nunca um 500.
            occupied = active_session_for_station(station)
            if occupied is not None:
                return cash_session_error_response(
                    CashSessionConflict(occupied_message(occupied), session=occupied)
                )
            return Response(
                {"detail": "Não foi possível abrir o caixa agora. Tente novamente."},
                status=status.HTTP_409_CONFLICT,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(cash_register).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="current")
    def current(self, request):
        """A sessão DESTE operador NESTE terminal — e nada além disso.

        Antes, qualquer operador vinculado ao caixa retomava a sessão que outra
        pessoa tinha aberto: logout não fecha o caixa, mas isso não faz da
        sessão um bem coletivo. Agora a retomada exige o mesmo dono (regra 4:
        reiniciar o terminal ou logar de novo continua funcionando), e uma
        sessão de terceiro vira um 409 explicando quem está com o caixa.
        """
        queryset = self.get_queryset()
        restaurant_id = request.query_params.get("restaurant")
        if restaurant_id:
            queryset = queryset.filter(restaurant_id=restaurant_id)
        installation_id = installation_id_from_request(request)

        active = CashRegister.active_sessions(queryset).select_related(
            "opened_by", "opened_terminal", "cash_station"
        )
        register = active.filter(opened_by=request.user).order_by("-opened_at").first()
        if register is not None:
            if session_belongs_to(register, user=request.user, installation_id=installation_id):
                return Response(self.get_serializer(register).data)
            # Mesma pessoa, outra máquina: bloqueia e explica (regra 5).
            return cash_session_error_response(
                CashSessionForbidden(
                    other_terminal_message(register),
                    session=register,
                    code="cash_session_other_terminal",
                )
            )

        occupied = (
            active.filter(cash_station__operators=request.user, cash_station__is_active=True)
            .order_by("-opened_at")
            .first()
        )
        if occupied is not None:
            return cash_session_error_response(
                CashSessionConflict(occupied_message(occupied), session=occupied)
            )
        # Sem filtro por restaurante, o caixa aberto em outra unidade aparecia
        # como "aberto" ao trocar de restaurante no PDV — o caixa é físico e
        # pertence a uma única unidade.
        return Response(
            {"detail": "O operador não possui uma sessão de caixa em andamento."},
            status=status.HTTP_404_NOT_FOUND,
        )

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        cash_register = self.get_object()
        try:
            cash_register = close_cash_register(
                cash_register=cash_register,
                user=request.user,
                actual_amount=request.data["actual_amount"],
                notes=request.data.get("notes", ""),
                terminal=terminal_from_request(request, restaurant=cash_register.restaurant),
                installation_id=installation_id_from_request(request),
            )
        except (CashSessionConflict, CashSessionForbidden) as exc:
            return cash_session_error_response(exc)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(cash_register).data)

    def _movement(self, request, movement_type, destination_field):
        cash_register = self.get_object()
        try:
            movement = create_cash_movement(
                cash_register=cash_register,
                user=request.user,
                movement_type=movement_type,
                amount=request.data.get("amount", 0),
                reason=request.data.get("reason", ""),
                destination=request.data.get(destination_field, ""),
                terminal=terminal_from_request(request, restaurant=cash_register.restaurant),
                installation_id=installation_id_from_request(request),
            )
        except (CashSessionConflict, CashSessionForbidden) as exc:
            return cash_session_error_response(exc)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CashMovementSerializer(movement).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="withdrawal")
    def withdrawal(self, request, pk=None):
        return self._movement(request, CashMovement.TYPE_WITHDRAWAL, "destination")

    @action(detail=True, methods=["post"], url_path="supply")
    def supply(self, request, pk=None):
        return self._movement(request, CashMovement.TYPE_SUPPLY, "source")

    @action(
        detail=True,
        methods=["post"],
        url_path="transfer",
        throttle_classes=[CashApprovalRateThrottle],
    )
    def transfer(self, request, pk=None):
        """Transferência gerencial da sessão para outro operador/terminal.

        É a válvula de escape da regra de dono: computador quebrado, operador
        ausente, navegador sem os dados, terminal reinstalado. Exige gerente
        (ou a senha de ações do caixa) e justificativa, e fica na auditoria.
        """
        cash_register = self.get_object()
        new_operator = None
        if request.data.get("new_operator"):
            new_operator = User.objects.filter(
                pk=request.data["new_operator"],
                profile__account=getattr(request, "account", None),
            ).first()
            if new_operator is None:
                return Response(
                    {"detail": "Selecione um operador desta conta para receber a sessão."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        try:
            transferred = transfer_cash_session(
                cash_register=cash_register,
                manager=request.user,
                reason=request.data.get("reason", ""),
                new_operator=new_operator,
                terminal=terminal_from_request(request, restaurant=cash_register.restaurant),
                cash_password=request.data.get("cash_password") or None,
            )
        except (CashSessionConflict, CashSessionForbidden) as exc:
            return cash_session_error_response(exc)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(transferred).data)

    @action(
        detail=True,
        methods=["post"],
        url_path="approve",
        throttle_classes=[CashApprovalRateThrottle],
    )
    def approve(self, request, pk=None):
        movement = None
        if request.data.get("movement"):
            movement = CashMovement.objects.filter(pk=request.data["movement"], cash_register=self.get_object()).first()
        try:
            result = approve_cash_operation(
                cash_register=self.get_object(), user=request.user,
                reason=request.data.get("reason", ""), movement=movement,
                cash_password_proof=request.data.get("cash_password_proof"),
                proof_nonce=request.data.get("proof_nonce", ""),
                cash_password=request.data.get("cash_password") or None,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        serializer = CashMovementSerializer(result) if movement else self.get_serializer(result)
        return Response(serializer.data)


class PdvTerminalViewSet(BaseTenantViewSet):
    """Terminais (instalações) que já operaram nesta conta.

    Serve para dar nome ao que hoje é só um UUID ("Balcão 01") e para revogar
    uma instalação que não deve mais abrir caixa. O cadastro em si nasce
    sozinho na primeira operação do terminal — pedir cadastro prévio deixaria
    um caixa novo sem conseguir abrir no primeiro dia.
    """

    serializer_class = PdvTerminalSerializer
    queryset = PdvTerminal.objects.select_related("restaurant").all()
    filterset_fields = ["is_active", "device_type", "role"]
    search_fields = ["name", "installation_id"]
    ordering_fields = ["name", "last_seen_at", "created_at"]
    ordering = ["name"]
