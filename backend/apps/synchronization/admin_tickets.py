"""Emissão de bilhetes temporários pelo Admin da nuvem."""
from datetime import timedelta

from django import forms
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from apps.accounts.models import Account
from apps.restaurants.models import Restaurant
from apps.synchronization.models import SyncEnrollmentTicket
from apps.synchronization.services import crypto


class TicketIssueForm(forms.ModelForm):
    class Meta:
        model = SyncEnrollmentTicket
        fields = ("account", "restaurant", "label")

    def clean(self):
        dados = super().clean()
        conta = dados.get("account")
        restaurante = dados.get("restaurant")
        if restaurante and conta and restaurante.account_id != conta.id:
            self.add_error("restaurant", "Este restaurante pertence a outra conta.")
        return dados


@admin.register(SyncEnrollmentTicket)
class SyncEnrollmentTicketAdmin(ModelAdmin):
    """Mostra o código apenas na confirmação da emissão; o banco guarda hash."""

    form = TicketIssueForm
    list_display = ("label", "account", "restaurant", "estado", "created_at", "expires_at", "used_at")
    list_filter = ("account",)
    search_fields = ("label", "account__name")
    #: Ao consultar um bilhete emitido, tudo é só leitura.
    CAMPOS_DO_BILHETE = ("account", "restaurant", "label", "created_by", "created_at",
                         "expires_at", "used_at", "used_by_node", "used_from_ip")

    def get_fields(self, request, obj=None):
        return ("account", "restaurant", "label") if obj is None else self.CAMPOS_DO_BILHETE

    def get_readonly_fields(self, request, obj=None):
        # Na EMISSÃO os três campos precisam ser digitáveis: com eles em
        # `readonly_fields` o formulário saía vazio e salvar estourava 500
        # (`account_id` nulo).
        return () if obj is None else self.CAMPOS_DO_BILHETE

    @admin.display(description="Estado")
    def estado(self, obj):
        if obj.used_at:
            return "usado"
        return "aberto" if obj.utilizavel else "vencido"

    def _admin_da_conta(self, user):
        perfil = getattr(user, "profile", None)
        return bool(
            user.is_staff
            and perfil
            and perfil.is_active
            and perfil.role.is_active
            and perfil.role.is_account_admin
        )

    def has_add_permission(self, request):
        return super().has_add_permission(request) or self._admin_da_conta(request.user)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        perfil = getattr(request.user, "profile", None)
        if self._admin_da_conta(request.user):
            return queryset.filter(account_id=perfil.account_id)
        return queryset.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        perfil = getattr(request.user, "profile", None)
        if not request.user.is_superuser and self._admin_da_conta(request.user):
            if db_field.name == "account":
                kwargs["queryset"] = Account.objects.filter(pk=perfil.account_id)
            elif db_field.name == "restaurant":
                kwargs["queryset"] = Restaurant.all_objects.filter(account_id=perfil.account_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_change_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if change:
            return
        codigo = obj.novo_codigo()
        obj.code_hash = crypto.hash_token(codigo)
        obj.created_by = request.user
        obj.expires_at = timezone.now() + timedelta(
            minutes=SyncEnrollmentTicket.VALIDADE_PADRAO_MINUTOS
        )
        super().save_model(request, obj, form, change)
        self.message_user(
            request,
            format_html(
                'Bilhete emitido. Copie agora: <code>{}</code>. '
                'Ele expira em 30 minutos e só pode matricular uma loja.',
                codigo,
            ),
            level="SUCCESS",
        )
