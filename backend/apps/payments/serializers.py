from rest_framework import serializers
from django.db.models import Sum

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer

from apps.payments.models import CashMovement, CashRegister, CashStation, PdvTerminal, Payment, PaymentMethod


class PdvTerminalSerializer(TenantModelSerializer):
    label = serializers.CharField(read_only=True)
    restaurant_name = serializers.CharField(source="restaurant.trade_name", read_only=True, default=None)

    class Meta:
        model = PdvTerminal
        fields = "__all__"
        # `installation_id` é a identidade da instalação: quem a define é o
        # próprio terminal, no primeiro contato. Aceitar reescrita pela API
        # permitiria "virar" outro terminal e herdar a sessão dele.
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "installation_id", "last_seen_at"]


class CashStationSerializer(TenantModelSerializer):
    operator_names = serializers.SerializerMethodField()
    current_session = serializers.SerializerMethodField()
    recent_sessions = serializers.SerializerMethodField()

    class Meta:
        model = CashStation
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def get_operator_names(self, obj):
        return [user.get_full_name() or user.username for user in obj.operators.all()]

    def validate_operators(self, operators):
        if not operators:
            raise serializers.ValidationError("Vincule pelo menos um usuário ao caixa.")
        request = self.context.get("request")
        account = getattr(request, "account", None)
        invalid = [user for user in operators if getattr(getattr(user, "profile", None), "account_id", None) != getattr(account, "id", None)]
        if invalid:
            raise serializers.ValidationError("Selecione somente usuários vinculados a esta conta.")
        # Cada usuário só pode estar vinculado a um caixa ativo por vez.
        conflicts = []
        for user in operators:
            others = user.cash_stations.filter(is_active=True)
            if self.instance is not None:
                others = others.exclude(pk=self.instance.pk)
            other = others.first()
            if other is not None:
                conflicts.append(f"{user.get_full_name() or user.username} (já em {other.name})")
        if conflicts:
            raise serializers.ValidationError(
                "Cada usuário só pode estar vinculado a um caixa por vez. " + "; ".join(conflicts) + "."
            )
        return operators

    def _session_data(self, session):
        if not session:
            return None
        from apps.payments.terminals import terminal_label_of

        return {
            "id": session.id,
            "status": session.status,
            "operator": session.opened_by.get_full_name() or session.opened_by.username,
            "opened_by": session.opened_by_id,
            # Sem isto a tela não consegue dizer QUEM e DE ONDE está com o
            # caixa — a mensagem de bloqueio viraria "já está aberto" e ponto.
            "opened_terminal": session.opened_terminal_id,
            "opened_terminal_label": terminal_label_of(session),
            "opened_at": session.opened_at,
            "closed_at": session.closed_at,
            "opening_amount": session.opening_amount,
            "actual_amount": session.actual_amount,
            "difference_amount": session.difference_amount,
        }

    def get_current_session(self, obj):
        if hasattr(obj, "prefetched_sessions"):
            return self._session_data(
                next((item for item in obj.prefetched_sessions if item.status not in CashRegister.FINAL_STATUSES), None)
            )
        session = (
            CashRegister.active_sessions(obj.sessions)
            .select_related("opened_by", "opened_terminal")
            .order_by("-opened_at")
            .first()
        )
        return self._session_data(session)

    def get_recent_sessions(self, obj):
        if hasattr(obj, "prefetched_sessions"):
            return [self._session_data(session) for session in obj.prefetched_sessions[:10]]
        return [
            self._session_data(session)
            for session in obj.sessions.select_related("opened_by", "opened_terminal").order_by("-opened_at")[:10]
        ]


class PaymentMethodSerializer(TenantModelSerializer):
    # Cada restaurante recebe o mesmo conjunto padrão de métodos
    # (apps/payments/defaults.py), então a listagem tem vários "Dinheiro"/"PIX"
    # homônimos: sem o nome do restaurante não dá para saber qual é qual.
    restaurant_name = serializers.CharField(source="restaurant.trade_name", read_only=True, default=None)

    class Meta:
        model = PaymentMethod
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class PaymentSerializer(TenantModelSerializer):
    payment_method_name = serializers.CharField(source="payment_method.name", read_only=True)
    payment_method_type = serializers.CharField(source="payment_method.method_type", read_only=True)

    class Meta:
        model = Payment
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "paid_at", "status"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Subtipo débito/crédito é obrigatório para cartão e proibido nos demais
        # métodos (STC-061). O tipo vem do próprio método de pagamento escolhido.
        method = attrs.get("payment_method") or getattr(self.instance, "payment_method", None)
        subtype = attrs.get("card_subtype", getattr(self.instance, "card_subtype", ""))
        if method and method.method_type == PaymentMethod.TYPE_CARD:
            if not subtype:
                raise serializers.ValidationError({"card_subtype": "Selecione débito ou crédito para pagamento com cartão."})
        elif subtype:
            raise serializers.ValidationError({"card_subtype": "Subtipo só se aplica a pagamento com cartão."})
        return attrs


class CashMovementSerializer(TenantModelSerializer):
    class Meta:
        model = CashMovement
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS


class CashRegisterSerializer(TenantModelSerializer):
    movements = CashMovementSerializer(many=True, read_only=True)
    current_balance = serializers.SerializerMethodField()
    opened_by_name = serializers.SerializerMethodField()
    terminal_label = serializers.SerializerMethodField()
    cash_station_name = serializers.CharField(source="cash_station.name", read_only=True, default=None)

    class Meta:
        model = CashRegister
        fields = "__all__"
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "opened_at",
            "closed_at",
            "expected_amount",
            "difference_amount",
            # Dono da sessão: definido na abertura e alterado só pela
            # transferência gerencial, nunca por um PATCH do próprio terminal.
            "opened_by",
            "opened_terminal",
            "closed_terminal",
            "opened_terminal_label",
            "closed_terminal_label",
        ]

    def get_opened_by_name(self, obj):
        from apps.payments.terminals import operator_label

        return operator_label(obj.opened_by)

    def get_terminal_label(self, obj):
        from apps.payments.terminals import terminal_label_of

        return terminal_label_of(obj)

    def get_current_balance(self, obj):
        prefetched = getattr(obj, "_prefetched_objects_cache", {}).get("movements")
        if prefetched is not None:
            return sum((movement.amount for movement in prefetched if movement.status == "approved"), 0)
        return (
            obj.movements.filter(status="approved").aggregate(
                value=Sum("amount")
            )["value"]
            or 0
        )


