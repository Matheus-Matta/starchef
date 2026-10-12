"""`POST /orders/submit/` — a venda inteira num envio (ver `venda_inteira.py`)."""
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.response import Response


def responder(viewset, request):
    from apps.orders.command_item_launch import AnotacaoEmConflito
    from apps.orders.conflitos import ConflitoComDestino
    from apps.orders.venda_inteira import VendaEmConflito, executar
    from apps.payments.recebimento_por_uuid import RecebimentoEmConflito
    from apps.payments.serializers import PaymentSerializer
    from apps.payments.terminals import (
        CashSessionConflict,
        CashSessionForbidden,
        installation_id_from_request,
        terminal_from_request,
    )
    from apps.payments.views import cash_session_error_response

    restaurante = getattr(getattr(request.user, "profile", None), "restaurant", None)
    if restaurante is None:
        return Response({"detail": "Usuário sem restaurante vinculado."},
                        status=status.HTTP_400_BAD_REQUEST)
    simular = bool(request.data.get("simular"))
    from functools import partial

    from apps.orders.views import DISCOUNT_PERMISSION, _can_authorize_cancellation

    autorizar_desconto = partial(_can_authorize_cancellation, request, restaurante,
                                 restaurante.account_id, permission=DISCOUNT_PERMISSION)

    def montar(pedido, recebimentos, nova):
        return {
            "order": viewset.get_serializer(pedido).data,
            "payments": PaymentSerializer(recebimentos, many=True).data,
            "created": nova,
        }

    try:
        corpo = executar(
            restaurant=restaurante, user=request.user, dados=request.data, responder=montar,
            simular=simular, terminal=terminal_from_request(request, restaurant=restaurante),
            installation_id=installation_id_from_request(request),
            autorizar_desconto=autorizar_desconto,
        )
    except (CashSessionConflict, CashSessionForbidden) as exc:
        return cash_session_error_response(exc)
    except ConflitoComDestino as exc:
        # Com o código e o pedido: o PDV abre a conta certa em vez do erro.
        return exc.resposta()
    except (VendaEmConflito, RecebimentoEmConflito, AnotacaoEmConflito) as exc:
        # 409, não 400: o corpo está certo, o estado é que diverge — e o PDV
        # reenvia 400 para sempre.
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    except ValidationError as exc:
        return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
    codigo = status.HTTP_201_CREATED if corpo["created"] and not simular else status.HTTP_200_OK
    return Response(corpo, status=codigo)
