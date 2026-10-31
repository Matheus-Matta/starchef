from django.contrib.auth import get_user_model

from apps.restaurants.command_reset import zerar_comandas


def run_command_reset_job(job):
    """Processa todas as comandas do job e guarda o resumo para o sino."""
    result = {"reset": [], "skipped": list(job.payload.get("skipped", []))}
    User = get_user_model()
    for group in job.payload.get("groups", []):
        approved_by = None
        if group.get("authorized_by_id"):
            approved_by = User.objects.filter(pk=group["authorized_by_id"]).first()
        partial = zerar_comandas(
            group["ids"],
            account=job.account,
            user=job.requested_by,
            reason=job.payload["reason"],
            authorized=group["authorized"],
            authorized_by=approved_by,
        )
        result["reset"] += partial["reset"]
        result["skipped"] += partial["skipped"]
    return result
