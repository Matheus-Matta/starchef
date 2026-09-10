"""Validacao central dos arquivos de imagem enviados pelo painel."""
import hashlib

from django.conf import settings
from rest_framework import serializers

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": {"jpg", "jpeg"},
    "image/png": {"png"},
}
ALLOWED_EXTENSIONS = {
    extension
    for extensions in ALLOWED_IMAGE_TYPES.values()
    for extension in extensions
}
DETECTED_CONTENT_TYPES = {
    "jpeg": "image/jpeg",
    "png": "image/png",
}


def validate_image_upload(uploaded, *, max_bytes=None):
    """Confere tamanho, extensao, MIME e o conteudo real com Pillow."""
    max_bytes = max_bytes or getattr(settings, "IMAGE_UPLOAD_MAX_BYTES", 8 * 1024 * 1024)
    if uploaded.size > max_bytes:
        raise serializers.ValidationError(
            f"A imagem tem {uploaded.size // 1024} KB e o limite e {max_bytes // 1024} KB."
        )

    name = (uploaded.name or "").strip()
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise serializers.ValidationError(
            "Formato nao aceito. Envie JPG, JPEG ou PNG."
        )

    declared = (getattr(uploaded, "content_type", "") or "").lower().split(";")[0]
    if declared and declared not in ALLOWED_IMAGE_TYPES:
        raise serializers.ValidationError(f"Tipo de arquivo nao aceito: {declared}.")
    if declared and extension not in ALLOWED_IMAGE_TYPES[declared]:
        raise serializers.ValidationError(
            "A extensao do arquivo nao corresponde ao tipo enviado."
        )

    try:
        from PIL import Image as PillowImage

        uploaded.seek(0)
        with PillowImage.open(uploaded) as image:
            image.verify()
        uploaded.seek(0)
        with PillowImage.open(uploaded) as image:
            width, height = image.size
            detected = (image.format or "").lower()
    except Exception as exc:  # noqa: BLE001 - Pillow usa excecoes variadas
        raise serializers.ValidationError("O arquivo enviado nao e uma imagem valida.") from exc
    finally:
        try:
            uploaded.seek(0)
        except (AttributeError, ValueError):
            pass

    detected_type = DETECTED_CONTENT_TYPES.get(detected, f"image/{detected}")
    if detected_type not in ALLOWED_IMAGE_TYPES:
        raise serializers.ValidationError("O formato real da imagem nao e aceito.")
    if declared and declared != detected_type:
        raise serializers.ValidationError(
            "O conteudo da imagem nao corresponde ao tipo de arquivo informado."
        )
    if extension not in ALLOWED_IMAGE_TYPES[detected_type]:
        raise serializers.ValidationError(
            "O conteudo da imagem nao corresponde a extensao do arquivo."
        )

    digest = hashlib.sha256()
    for chunk in uploaded.chunks():
        digest.update(chunk)
    uploaded.seek(0)
    return {
        "original_name": name[:255],
        "content_type": detected_type,
        "size": uploaded.size,
        "width": width,
        "height": height,
        "checksum": digest.hexdigest(),
    }
