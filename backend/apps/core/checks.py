"""
Checagens de configuração do sistema.

`manage.py check` e o `runserver` avisam sobre problemas de configuração antes
de alguém tropeçar neles em produção. São **avisos**, nunca erros: um `Error`
aqui impediria o processo de subir, e a regra do armazenamento de mídia é
justamente a contrária — falta de credencial degrada o upload, não derruba o
sistema (ver `apps.core.storage`).
"""
from django.core.checks import Warning as CheckWarning
from django.core.checks import register


@register("storage")
def check_media_storage(app_configs, **kwargs):
    """Avisa quando o S3 está configurado pela metade.

    O sintoma sem este aviso: tudo sobe normalmente, ninguém percebe nada, e
    dias depois o primeiro restaurante que tenta trocar a foto de um prato
    recebe um 503. O deploy é o momento certo de descobrir isso.
    """
    from apps.core.storage import media_storage

    if media_storage.is_ready:
        return []

    return [
        CheckWarning(
            f"Armazenamento de mídia indisponível: {media_storage.unavailable_reason}",
            hint=(
                "O sistema sobe normalmente e a leitura de imagens continua funcionando, "
                "mas QUALQUER upload vai falhar com HTTP 503 até estas variáveis serem "
                "definidas. Para usar o disco local, deixe AWS_STORAGE_BUCKET_NAME vazio."
            ),
            id="core.W001",
        )
    ]
