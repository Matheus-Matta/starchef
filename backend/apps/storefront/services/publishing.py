"""
Publicação, versionamento e aplicação de template.

Duas invariantes sustentam todo este módulo:

1. **Editar nunca publica.** O editor grava em `draft_data`; o público lê
   `published_data`. Só a ação explícita de publicar move um para o outro.
2. **Publicar nunca destrói.** Antes de sobrescrever o que está no ar, o
   conteúdo publicado vira uma `MenuPageVersion`. É o que torna o rollback
   possível — sem isso, publicar uma página quebrada seria irreversível.

Tudo roda dentro de uma transação, e o cache público só é invalidado depois do
commit: invalidar antes deixaria a janela em que uma leitura repopula o cache
com o conteúdo antigo e o marca como novo.
"""
from django.db import transaction
from django.utils import timezone

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.storefront.builder_schema import BuilderValidationError, validate_project_data
from apps.storefront.models import MenuPage, MenuPageVersion
from apps.storefront.services.cache import invalidate_storefront

# Quantas versões manter por página. O histórico serve para voltar atrás em
# horas/dias, não para ser um sistema de controle de versão: sem teto, uma
# página editada todo dia acumularia JSON indefinidamente.
VERSION_RETENTION = 30


def snapshot_version(page, data, *, user=None, origin=MenuPageVersion.ORIGIN_PUBLISH, label=""):
    """Congela `data` como uma nova versão da página. Devolve a versão criada."""
    if not data:
        return None
    last_number = (
        MenuPageVersion.all_objects.filter(page=page).order_by("-number").values_list("number", flat=True).first() or 0
    )
    version = MenuPageVersion.all_objects.create(
        account=page.account,
        restaurant=page.restaurant,
        page=page,
        number=last_number + 1,
        origin=origin,
        label=label[:150],
        data=data,
        created_by=user if getattr(user, "is_authenticated", False) else None,
        updated_by=user if getattr(user, "is_authenticated", False) else None,
    )
    _prune_versions(page)
    return version


def _prune_versions(page):
    keep = list(
        MenuPageVersion.all_objects.filter(page=page)
        .order_by("-number")
        .values_list("id", flat=True)[:VERSION_RETENTION]
    )
    MenuPageVersion.all_objects.filter(page=page).exclude(id__in=keep).delete()


@transaction.atomic
def publish_page(page, *, user=None, request=None):
    """Copia o rascunho para a versão pública, versionando o que sai do ar."""
    page = MenuPage.all_objects.select_for_update().get(pk=page.pk)

    if not page.draft_data:
        raise BuilderValidationError({"draft_data": "Não há conteúdo para publicar nesta página."})
    if not page.site.is_active:
        raise BuilderValidationError({"site": "O site está inativo. Ative-o antes de publicar."})

    # Revalida na publicação, e não só no salvamento: o rascunho pode ter
    # entrado por um caminho que não passou pelo serializer (importação,
    # template aplicado por script, ajuste direto no banco).
    validated = validate_project_data(page.draft_data)

    previous = page.published_data
    if previous:
        snapshot_version(page, previous, user=user, origin=MenuPageVersion.ORIGIN_PUBLISH, label="Versão publicada anterior")

    page.published_data = validated
    page.draft_data = validated
    page.status = MenuPage.STATUS_PUBLISHED
    page.published_at = timezone.now()
    page.published_by = user if getattr(user, "is_authenticated", False) else None
    page.updated_by = user if getattr(user, "is_authenticated", False) else None
    page.save(
        update_fields=[
            "published_data", "draft_data", "status", "published_at", "published_by", "updated_by", "updated_at",
        ]
    )

    site = page.site
    if site.published_at is None:
        site.published_at = page.published_at
        site.save(update_fields=["published_at", "updated_at"])

    record_audit(
        action=AuditLog.ACTION_UPDATED,
        instance=page,
        actor=user,
        request=request,
        reason="Página do storefront publicada.",
        metadata={"storefront_action": "publish", "page_slug": page.slug, "site_slug": site.slug},
    )
    transaction.on_commit(lambda: invalidate_storefront(page.restaurant_id, reason="publish"))
    return page


@transaction.atomic
def unpublish_page(page, *, user=None, request=None):
    """Tira a página do ar sem perder o rascunho nem o histórico."""
    page = MenuPage.all_objects.select_for_update().get(pk=page.pk)
    if page.published_data:
        snapshot_version(page, page.published_data, user=user, origin=MenuPageVersion.ORIGIN_PUBLISH, label="Retirada do ar")
    page.published_data = {}
    page.status = MenuPage.STATUS_DRAFT
    page.published_at = None
    page.updated_by = user if getattr(user, "is_authenticated", False) else None
    page.save(update_fields=["published_data", "status", "published_at", "updated_by", "updated_at"])

    record_audit(
        action=AuditLog.ACTION_UPDATED,
        instance=page,
        actor=user,
        request=request,
        reason="Página do storefront retirada do ar.",
        metadata={"storefront_action": "unpublish", "page_slug": page.slug},
    )
    transaction.on_commit(lambda: invalidate_storefront(page.restaurant_id, reason="unpublish"))
    return page


@transaction.atomic
def restore_version(page, version, *, user=None, request=None, publish=False):
    """Traz uma versão do histórico de volta para o rascunho.

    Por padrão a restauração para no rascunho: quem restaura ainda olha o
    resultado no editor antes de decidir publicar. `publish=True` faz o
    rollback completo (é o "desfazer" de uma publicação ruim).
    """
    page = MenuPage.all_objects.select_for_update().get(pk=page.pk)
    if version.page_id != page.id:
        raise BuilderValidationError({"version": "Esta versão pertence a outra página."})

    validated = validate_project_data(version.data)

    # Guarda o rascunho atual antes de sobrescrevê-lo: restaurar não pode
    # apagar em silêncio o trabalho que estava em andamento.
    if page.draft_data and page.draft_data != validated:
        snapshot_version(page, page.draft_data, user=user, origin=MenuPageVersion.ORIGIN_RESTORE, label=f"Rascunho antes de restaurar v{version.number}")

    page.draft_data = validated
    page.updated_by = user if getattr(user, "is_authenticated", False) else None
    page.save(update_fields=["draft_data", "updated_by", "updated_at"])

    record_audit(
        action=AuditLog.ACTION_UPDATED,
        instance=page,
        actor=user,
        request=request,
        reason=f"Versão v{version.number} restaurada.",
        metadata={"storefront_action": "restore", "version_number": version.number, "publish": bool(publish)},
    )

    if publish:
        return publish_page(page, user=user, request=request)

    transaction.on_commit(lambda: invalidate_storefront(page.restaurant_id, reason="restore"))
    return page


@transaction.atomic
def apply_template(page, template, *, user=None, request=None):
    """Copia o conteúdo de um template para o rascunho da página.

    A cópia é o ponto: depois de aplicada, a página não guarda vínculo algum
    com o template. Editar o template no futuro não mexe em nenhuma página já
    criada, e a página não "quebra" se o template for desativado.
    """
    page = MenuPage.all_objects.select_for_update().get(pk=page.pk)
    if not template.is_active:
        raise BuilderValidationError({"template": "Este modelo não está disponível."})

    validated = validate_project_data(template.project_data)

    if page.draft_data:
        snapshot_version(page, page.draft_data, user=user, origin=MenuPageVersion.ORIGIN_MANUAL, label=f"Antes de aplicar '{template.name}'")

    page.draft_data = validated
    page.updated_by = user if getattr(user, "is_authenticated", False) else None
    page.save(update_fields=["draft_data", "updated_by", "updated_at"])

    record_audit(
        action=AuditLog.ACTION_UPDATED,
        instance=page,
        actor=user,
        request=request,
        reason=f"Modelo '{template.name}' aplicado à página.",
        metadata={"storefront_action": "apply_template", "template_slug": template.slug},
    )
    return page
