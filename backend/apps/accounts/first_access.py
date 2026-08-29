import secrets

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth import get_user_model, password_validation
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters

from apps.accounts.models import Account, FirstAccessState, Role, UserProfile
from apps.accounts.role_catalog import CODE_ADMIN

User = get_user_model()
LOCK_KEY = "starchef:first-access:create"


def first_access_available():
    # Instancias existentes antes desta feature tambem permanecem fechadas.
    return not (
        FirstAccessState.objects.exists()
        or Account.objects.exists()
        or User.objects.exists()
    )


class FirstAccessForm(forms.Form):
    account_name = forms.CharField(label="Nome da conta", max_length=150)
    account_slug = forms.SlugField(
        label="Identificador da conta",
        max_length=50,
        help_text="Somente letras minúsculas, números, hífen e sublinhado.",
    )
    account_email = forms.EmailField(label="E-mail da conta")
    first_name = forms.CharField(label="Nome", max_length=150)
    last_name = forms.CharField(label="Sobrenome", max_length=150, required=False)
    username = forms.CharField(label="Usuário superadmin", max_length=150)
    email = forms.EmailField(label="E-mail do superadmin")
    password1 = forms.CharField(label="Senha", strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirme a senha", strip=False, widget=forms.PasswordInput)
    setup_token = forms.CharField(
        label="Chave de primeiro acesso",
        strip=False,
        widget=forms.PasswordInput,
    )

    def clean_account_slug(self):
        return self.cleaned_data["account_slug"].lower()

    def clean_setup_token(self):
        supplied = self.cleaned_data["setup_token"]
        expected = settings.FIRST_ACCESS_TOKEN
        if not expected or not secrets.compare_digest(supplied, expected):
            raise forms.ValidationError("Chave de primeiro acesso inválida.")
        return supplied

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password1")
        if password and password != cleaned.get("password2"):
            self.add_error("password2", "As senhas não coincidem.")
        if password:
            candidate = User(
                username=cleaned.get("username", ""),
                email=cleaned.get("email", ""),
                first_name=cleaned.get("first_name", ""),
                last_name=cleaned.get("last_name", ""),
            )
            try:
                password_validation.validate_password(password, candidate)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned


@sensitive_post_parameters("password1", "password2", "setup_token")
@never_cache
@csrf_protect
def admin_login_or_first_access(request):
    if not first_access_available():
        return admin.site.login(request)

    if not settings.FIRST_ACCESS_TOKEN:
        return HttpResponse(
            "Primeiro acesso indisponível: configure DJANGO_FIRST_ACCESS_TOKEN no servidor.",
            status=503,
            content_type="text/plain; charset=utf-8",
        )

    form = FirstAccessForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not cache.add(LOCK_KEY, "locked", timeout=30):
            form.add_error(None, "Uma configuração já está em andamento. Tente novamente.")
        else:
            try:
                with transaction.atomic():
                    # Revalida dentro da transação para impedir reutilização do POST.
                    if not first_access_available():
                        return redirect("/admin/login/")

                    account = Account.objects.create(
                        name=form.cleaned_data["account_name"],
                        slug=form.cleaned_data["account_slug"],
                        email=form.cleaned_data["account_email"],
                        status=Account.STATUS_ACTIVE,
                        subscription_status=Account.SUBSCRIPTION_TRIAL,
                        is_active=True,
                    )
                    user = User.objects.create_superuser(
                        username=form.cleaned_data["username"],
                        email=form.cleaned_data["email"],
                        password=form.cleaned_data["password1"],
                        first_name=form.cleaned_data["first_name"],
                        last_name=form.cleaned_data["last_name"],
                    )
                    # `Account.objects.create` acima ja disparou o signal que
                    # provisiona os 4 perfis fixos da conta.
                    admin_role = Role.all_objects.filter(account=account, code=CODE_ADMIN).first()
                    UserProfile.objects.create(
                        account=account,
                        user=user,
                        profile_type=UserProfile.PROFILE_ADMIN,
                        role=admin_role,
                        is_active=True,
                    )
                    FirstAccessState.objects.create()
            finally:
                cache.delete(LOCK_KEY)

            messages.success(request, "Configuração inicial concluída. Entre com o superadmin criado.")
            return redirect("/admin/login/")

    return render(request, "accounts/first_access.html", {"form": form})
