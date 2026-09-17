"""Serializadores da API de gerenciamento da sincronização.

Nenhum deles expõe segredo: `credential_hash` e a chave não aparecem em lugar
nenhum, e o `secret_fingerprint` sai truncado — ele serve para conferir que os
dois lados têm a mesma chave, não para reconstruí-la.
"""
from rest_framework import serializers

from apps.synchronization.constants import RunType
from apps.synchronization.models import SyncConflict, SyncEvent, SyncNode, SyncRun
from apps.synchronization.services import enrollment


class SyncNodeSerializer(serializers.ModelSerializer):
    pending_events = serializers.SerializerMethodField()
    dead_events = serializers.SerializerMethodField()
    fingerprint = serializers.SerializerMethodField()

    class Meta:
        model = SyncNode
        fields = [
            "id", "pair_id", "account", "restaurant", "node_type", "environment",
            "name", "endpoint", "status", "is_active", "is_self", "app_version",
            "schema_version", "protocol_version", "last_seen_at", "last_sync_at",
            "last_sent_cursor", "last_received_cursor", "last_error",
            "pending_events", "dead_events", "fingerprint", "created_at", "updated_at",
        ]
        read_only_fields = [
            "pair_id", "status", "is_self", "app_version", "schema_version",
            "protocol_version", "last_seen_at", "last_sync_at", "last_sent_cursor",
            "last_received_cursor", "last_error",
        ]

    def get_pending_events(self, obj):
        return SyncEvent.objects.pending_outbound(obj).count()

    def get_dead_events(self, obj):
        from apps.synchronization.constants import EventStatus

        return SyncEvent.objects.filter(source_node=obj, status=EventStatus.DEAD).count()

    def get_fingerprint(self, obj):
        return obj.secret_fingerprint[:12] if obj.secret_fingerprint else ""


class SyncEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncEvent
        fields = [
            "id", "event_id", "direction", "sequence", "entity_type", "entity_id",
            "operation", "entity_version", "status", "attempts", "next_attempt_at",
            "last_error", "created_at", "sent_at", "received_at", "applied_at",
            "acknowledged_at",
        ]
        read_only_fields = fields


class SyncEventDetailSerializer(SyncEventSerializer):
    """Com o payload. É o que o resgate manual lê."""

    class Meta(SyncEventSerializer.Meta):
        fields = SyncEventSerializer.Meta.fields + ["payload", "payload_checksum"]
        read_only_fields = fields


class SyncRunSerializer(serializers.ModelSerializer):
    progress_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = SyncRun
        fields = [
            "id", "run_type", "status", "target_node", "source_node", "manifest",
            "current_entity", "total_entities", "processed_entities", "total_records",
            "processed_records", "failed_records", "progress_percent", "snapshot_cursor",
            "initiated_by", "reason", "started_at", "completed_at", "error", "created_at",
        ]
        read_only_fields = fields


class SyncConflictSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncConflict
        fields = [
            "id", "entity_type", "entity_id", "local_version", "remote_version",
            "local_payload", "remote_payload", "resolution", "status", "notes",
            "resolved_by", "resolved_at", "created_at",
        ]
        read_only_fields = [
            "entity_type", "entity_id", "local_version", "remote_version",
            "local_payload", "remote_payload", "resolved_by", "resolved_at", "created_at",
        ]


class StartRunSerializer(serializers.Serializer):
    run_type = serializers.ChoiceField(
        choices=[RunType.BOOTSTRAP, RunType.FULL], default=RunType.BOOTSTRAP
    )
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class EnrollRequestSerializer(serializers.Serializer):
    """A matrícula de um nó local. Só entra por HTTPS."""

    username = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    account_id = serializers.UUIDField()
    enrollment_secret = serializers.CharField(
        write_only=True, min_length=enrollment.MIN_SEGREDO
    )
    node_name = serializers.CharField(max_length=120)
    restaurant_id = serializers.UUIDField(required=False, allow_null=True)
    cloud_wss_url = serializers.CharField(required=False, allow_blank=True)
    existing_node_id = serializers.UUIDField(required=False, allow_null=True)
