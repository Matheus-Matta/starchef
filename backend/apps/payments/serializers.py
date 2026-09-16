from rest_framework import serializers
from django.db.models import Q, Sum

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
            # A INSTALACAO, e nao so a chave do terminal: e por ela que o PDV
            # offline confere se a sessao e desta maquina, do mesmo jeito que
            # `session_belongs_to` confere aqui.
            "opened_terminal_installation_id": (
                session.opened_terminal.installation_id if session.opened_terminal_id else ""
            ),
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
    """Movimento da gaveta com quem, onde e por que — o que o relatorio de
    caixa e a tabela do painel mostram sem precisar abrir a auditoria."""

    operator_name = serializers.SerializerMethodField()
    authorized_by_name = serializers.SerializerMethodField()
    terminal_label = serializers.SerializerMethodField()
    cash_station_name = serializers.CharField(
        source="cash_register.cash_station.name", read_only=True, default=None
    )
    order_sequence = serializers.IntegerField(source="payment.order.sequence", read_only=True, default=None)
    payment_method_name = serializers.CharField(
        source="payment.payment_method.name", read_only=True, default=None
    )
    authorization = serializers.SerializerMethodField()
    manager_reason = serializers.SerializerMethodField()

    class Meta:
        model = CashMovement
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def get_operator_name(self, obj):
        from apps.payments.terminals import operator_label

        return operator_label(obj.operator) if obj.operator_id else ""

    def get_authorized_by_name(self, obj):
        from apps.payments.terminals import operator_label

        return operator_label(obj.authorized_by) if obj.authorized_by_id else ""

    def get_terminal_label(self, obj):
        # O terminal de quem lancou viaja no metadata (o mesmo header
        # X-Terminal-Id das outras operacoes); movimentos antigos caem no
        # terminal que abriu a sessao.
        label = str((obj.metadata or {}).get("terminal_name") or "").strip()
        if label:
            return label
        return obj.cash_register.opened_terminal_label or ""

    def get_authorization(self, obj):
        meta = obj.metadata or {}
        if obj.status != "approved":
            return "pending"
        if meta.get("authorized_by_cash_password"):
            return "cash_password"
        if obj.authorized_by_id:
            return "manager"
        return "automatic"

    def get_manager_reason(self, obj):
        return str((obj.metadata or {}).get("manager_reason") or "")


class CashRegisterSerializer(TenantModelSerializer):
    movements = serializers.SerializerMethodField()
    sales = serializers.SerializerMethodField()
    current_balance = serializers.SerializerMethodField()
    opened_by_name = serializers.SerializerMethodField()
    terminal_label = serializers.SerializerMethodField()
    # O PDV offline espelha `session_belongs_to`: sem a instalacao de quem
    # abriu, a regra "cada terminal cuida do proprio caixa" nao existe do lado
    # de fora do servidor — o terminal secundario adotava a sessao do
    # principal por nao ter com o que comparar.
    opened_terminal_installation_id = serializers.SerializerMethodField()
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

    def get_opened_terminal_installation_id(self, obj):
        return obj.opened_terminal.installation_id if obj.opened_terminal_id else ""

    def get_movements(self, obj):
        """Movimentos em ordem cronologica, cada um com o saldo da gaveta
        DEPOIS dele (`balance_after`) — e o que o operador confere na tabela e
        no relatorio, em vez de somar de cabeca."""
        prefetched = getattr(obj, "_prefetched_objects_cache", {}).get("movements")
        movements = list(prefetched) if prefetched is not None else list(obj.movements.all())
        movements.sort(key=lambda movement: (movement.created_at, str(movement.pk)))
        running = 0
        rows = []
        for movement in movements:
            if movement.status == "approved":
                running += movement.amount
            row = CashMovementSerializer(movement, context=self.context).data
            row["balance_after"] = str(running)
            rows.append(row)
        return rows

    def get_sales(self, obj):
        """Todo recebimento da sessao, em qualquer forma de pagamento.

        `movements` so conhece o dinheiro (e o troco que saiu da gaveta). O
        relatorio de fechamento impresso pelo PDV precisa das vendas por
        forma — dinheiro, credito, debito, PIX, voucher — para o operador
        conferir os comprovantes da maquininha, nao so a gaveta. O vinculo e
        o `metadata.cash_register` gravado no recebimento; pagamentos antigos
        em dinheiro entram pelo `CashMovement` que os aponta.
        """
        session_id = str(obj.pk)
        payments = (
            Payment.objects.filter(status=Payment.STATUS_APPROVED)
            .filter(Q(metadata__cash_register=session_id) | Q(cash_movements__cash_register_id=obj.pk))
            .select_related("payment_method", "order")
            .distinct()
            .order_by("paid_at")
        )
        return [
            {
                "id": str(payment.pk),
                "order": str(payment.order_id),
                "order_sequence": payment.order.sequence,
                "payment_method": str(payment.payment_method_id),
                "payment_method_name": payment.payment_method.name,
                "method_type": payment.payment_method.method_type,
                "card_subtype": payment.card_subtype,
                "amount": str(payment.amount),
                "change_amount": str(payment.change_amount),
                "paid_at": payment.paid_at,
            }
            for payment in payments
        ]

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


