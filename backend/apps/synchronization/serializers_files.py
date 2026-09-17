"""Serializadores da transferência de arquivo."""
from rest_framework import serializers

from apps.synchronization.models.transfer import SyncFileTransfer
from apps.synchronization.services import files

UPLOAD = "upload"
DOWNLOAD = "download"


class OpenTransferSerializer(serializers.Serializer):
    """Abertura de uma transferência.

    `direction` é do ponto de vista de QUEM CHAMA: `upload` quando o nó está
    mandando o arquivo para cá, `download` quando está vindo buscar. Sem esse
    campo, origem e destino ficariam ambíguos e a mesma rota registraria o nó
    como as duas pontas da própria transferência.
    """

    direction = serializers.ChoiceField(choices=[UPLOAD, DOWNLOAD], default=UPLOAD)
    entity_type = serializers.CharField(max_length=80)
    entity_id = serializers.CharField(max_length=64)
    field_name = serializers.CharField(max_length=80)
    storage_path = serializers.CharField(max_length=500)
    total_bytes = serializers.IntegerField(min_value=1, max_value=files.max_bytes())
    checksum = serializers.RegexField(r"^[0-9a-f]{64}$", max_length=64)
    content_type = serializers.CharField(max_length=120, required=False, allow_blank=True)


class TransferSerializer(serializers.ModelSerializer):
    progress_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = SyncFileTransfer
        fields = [
            "id", "entity_type", "entity_id", "field_name", "storage_path",
            "content_type", "total_bytes", "received_bytes", "progress_percent",
            "checksum", "status", "attempts", "last_error", "created_at",
            "completed_at",
        ]
        read_only_fields = fields
