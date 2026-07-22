from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer

from apps.sla.models import ServiceLevelAgreement


class ServiceLevelAgreementSerializer(TenantModelSerializer):
    restaurant_names = serializers.SerializerMethodField()

    class Meta:
        model = ServiceLevelAgreement
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def get_restaurant_names(self, obj):
        return [r.trade_name for r in obj.restaurants.all()]

    def validate(self, attrs):
        attrs = super().validate(attrs)

        # O alerta deve disparar antes (ou junto) do tempo-alvo (STC-066).
        target = attrs.get("target_minutes", getattr(self.instance, "target_minutes", None))
        alert = attrs.get("alert_minutes", getattr(self.instance, "alert_minutes", None))
        if target is not None and alert is not None and alert > target:
            raise serializers.ValidationError(
                {"alert_minutes": "O limite de alerta deve ser menor ou igual ao tempo-alvo."}
            )

        # Conflito: um restaurante não pode ter dois SLAs ativos do mesmo tipo.
        restaurants = attrs.get("restaurants")
        sla_type = attrs.get("sla_type", getattr(self.instance, "sla_type", None))
        if restaurants:
            conflicting = ServiceLevelAgreement.objects.filter(sla_type=sla_type, is_active=True, restaurants__in=restaurants)
            if self.instance is not None:
                conflicting = conflicting.exclude(pk=self.instance.pk)
            names = sorted({r.trade_name for r in restaurants if conflicting.filter(restaurants=r).exists()})
            if names:
                raise serializers.ValidationError(
                    {"restaurants": f"Já existe um SLA ativo deste tipo para: {', '.join(names)}."}
                )
        return attrs
