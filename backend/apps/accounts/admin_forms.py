"""
Forms do admin de contas (tenant).

- Ao CRIAR uma conta: um unico formulario coleta os dados da conta, os dados do
  primeiro usuario administrador e os modulos ativos — provisionando tudo que a
  conta precisa para operar de uma so vez.
- Ao EDITAR: mostra apenas os dados da propria conta e os modulos como switches.
"""
from django import forms
from django.contrib.auth import get_user_model
from unfold.widgets import (
    UnfoldAdminEmailInputWidget,
    UnfoldAdminPasswordWidget,
    UnfoldAdminTextInputWidget,
    UnfoldBooleanSwitchWidget,
)

from apps.accounts.models import Account, UserProfile
from apps.core.modules import MODULE_CATALOG, OPTIONAL_MODULES

User = get_user_model()

# Campos de negocio da conta editaveis no admin (o enabled_modules e via switches).
ACCOUNT_FIELDS = [
    "name",
    "slug",
    "document",
    "email",
    "phone",
    "plan",
    "timezone",
    "default_currency",
    "status",
    "subscription_status",
    "is_active",
]

# Mapa campo-do-form -> chave do modulo. Um switch (BooleanField) por modulo opcional.
MODULE_FIELDS = {f"module_{key}": key for key in OPTIONAL_MODULES}
_MODULE_META = {m["key"]: m for m in MODULE_CATALOG}


def _module_switch_fields():
    """Constroi os BooleanField (switch) de cada modulo opcional."""
    fields = {}
    for field_name, module_key in MODULE_FIELDS.items():
        meta = _MODULE_META.get(module_key, {})
        fields[field_name] = forms.BooleanField(
            required=False,
            label=meta.get("label", module_key),
            help_text=meta.get("description", ""),
            widget=UnfoldBooleanSwitchWidget,
        )
    return fields


class AccountChangeForm(forms.ModelForm):
    """Edicao: dados da conta + switches de modulo."""

    # Injeta os switches de modulo dinamicamente (um por modulo opcional).
    locals().update(_module_switch_fields())

    class Meta:
        model = Account
        fields = ACCOUNT_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        enabled = set(self.instance.enabled_modules or []) if self.instance and self.instance.pk else set()
        for field_name, module_key in MODULE_FIELDS.items():
            self.fields[field_name].initial = module_key in enabled

    def save(self, commit=True):
        account = super().save(commit=False)
        # Os switches marcados viram a lista enabled_modules da conta.
        account.enabled_modules = [
            module_key for field_name, module_key in MODULE_FIELDS.items() if self.cleaned_data.get(field_name)
        ]
        if commit:
            account.save()
        return account


class AccountCreationForm(AccountChangeForm):
    """Criacao: conta + primeiro usuario administrador + modulos ativos."""

    admin_username = forms.CharField(label="Usuario (login)", max_length=150, widget=UnfoldAdminTextInputWidget)
    admin_email = forms.EmailField(label="Email", required=False, widget=UnfoldAdminEmailInputWidget)
    admin_first_name = forms.CharField(label="Nome", max_length=150, required=False, widget=UnfoldAdminTextInputWidget)
    admin_last_name = forms.CharField(label="Sobrenome", max_length=150, required=False, widget=UnfoldAdminTextInputWidget)
    admin_password = forms.CharField(label="Senha", min_length=8, widget=UnfoldAdminPasswordWidget)

    def clean_admin_username(self):
        username = self.cleaned_data["admin_username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Ja existe um usuario com este login.")
        return username

    def clean_admin_email(self):
        email = (self.cleaned_data.get("admin_email") or "").strip()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ja existe um usuario com este email.")
        return email

    def create_admin_user(self, account):
        """Cria o usuario admin e o vincula a conta (chamado apos a conta ser salva)."""
        user = User(
            username=self.cleaned_data["admin_username"],
            email=self.cleaned_data.get("admin_email", ""),
            first_name=self.cleaned_data.get("admin_first_name", ""),
            last_name=self.cleaned_data.get("admin_last_name", ""),
            is_active=True,
        )
        user.set_password(self.cleaned_data["admin_password"])
        user.save()
        UserProfile.objects.create(
            account=account,
            user=user,
            profile_type=UserProfile.PROFILE_ADMIN,
            is_active=True,
        )
        return user
