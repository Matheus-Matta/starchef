"""Restaura o acesso de um usuário de plataforma (superadmin) a uma conta.

Serve para o cenário em que os flags `is_staff`/`is_superuser` foram removidos
sem querer, ou o perfil que liga o usuário à conta foi excluído/desativado —
situação em que a pessoa perde tanto o /admin quanto o app (a API exige conta
vinculada, ver TenantMiddleware.resolve_account).

    python manage.py restore_platform_admin --user-id 1
    python manage.py restore_platform_admin --username dono --account-slug minha-conta
    python manage.py restore_platform_admin --user-id 1 --dry-run
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Account, UserProfile
from apps.core.tenant import tenant_context
from apps.restaurants.models import Branch, Restaurant


class Command(BaseCommand):
    help = "Devolve is_staff/is_superuser e o vínculo de conta a um usuário de plataforma."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, default=None, help="ID do usuário (pk).")
        parser.add_argument("--username", default=None, help="Alternativa ao --user-id.")
        parser.add_argument(
            "--account-slug",
            default=None,
            help="Conta a vincular. Padrão: a conta mais antiga (a inicial).",
        )
        parser.add_argument(
            "--profile-type",
            default=UserProfile.PROFILE_ADMIN,
            choices=[choice[0] for choice in UserProfile.PROFILE_CHOICES],
        )
        parser.add_argument(
            "--no-superuser",
            action="store_false",
            dest="superuser",
            default=True,
            help="Só restaura o vínculo de conta, sem tocar em is_superuser/is_staff.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Só mostra o diagnóstico.")

    def handle(self, *args, **options):
        user = self._resolve_user(options)
        account = self._resolve_account(options)
        profile = UserProfile.all_objects.filter(user=user).first()

        self.stdout.write("Estado atual:")
        self.stdout.write(
            f"  usuário #{user.pk} {user.username} — ativo={user.is_active} "
            f"staff={user.is_staff} superuser={user.is_superuser}"
        )
        if profile is None:
            self.stdout.write("  perfil: NENHUM (usuário sem conta vinculada)")
        else:
            self.stdout.write(
                f"  perfil: conta={profile.account.slug} tipo={profile.profile_type} "
                f"ativo={profile.is_active} excluído={bool(profile.deleted_at)}"
            )
        self.stdout.write(f"  conta alvo: {account.slug} ({account.name})")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("dry-run: nada foi alterado."))
            return

        if options["superuser"]:
            user.is_active = True
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=["is_active", "is_staff", "is_superuser"])

        with tenant_context(account):
            restaurant = (
                Restaurant.all_objects.filter(account=account, deleted_at__isnull=True)
                .order_by("created_at")
                .first()
            )
            branch = (
                Branch.all_objects.filter(account=account, restaurant=restaurant, deleted_at__isnull=True)
                .order_by("created_at")
                .first()
                if restaurant
                else None
            )
            profile = profile or UserProfile(user=user)
            profile.account = account
            profile.profile_type = options["profile_type"]
            profile.is_active = True
            profile.deleted_at = None  # desfaz o soft delete, se houver
            # Restaurante/filial só são preenchidos quando o perfil não tem:
            # um superadmin com escopo próprio não é rebaixado por engano.
            if restaurant and not profile.restaurant_id:
                profile.restaurant = restaurant
            if branch and not profile.branch_id:
                profile.branch = branch
            profile.save()

        self.stdout.write(self.style.SUCCESS("Restaurado:"))
        self.stdout.write(
            f"  #{user.pk} {user.username} — staff={user.is_staff} superuser={user.is_superuser}"
        )
        self.stdout.write(
            f"  perfil {profile.profile_type} na conta {account.slug} — "
            f"restaurante={getattr(profile.restaurant, 'trade_name', None)} "
            f"filial={getattr(profile.branch, 'name', None)}"
        )

    def _resolve_user(self, options):
        User = get_user_model()
        if options["user_id"] is not None:
            user = User.objects.filter(pk=options["user_id"]).first()
            if user is None:
                raise CommandError(f"Usuário #{options['user_id']} não encontrado.")
            return user
        if options["username"]:
            user = User.objects.filter(username=options["username"]).first()
            if user is None:
                raise CommandError(f"Usuário '{options['username']}' não encontrado.")
            return user
        raise CommandError("Informe --user-id ou --username.")

    def _resolve_account(self, options):
        accounts = Account.objects.order_by("created_at")
        if options["account_slug"]:
            account = accounts.filter(slug=options["account_slug"]).first()
            if account is None:
                disponiveis = ", ".join(accounts.values_list("slug", flat=True)) or "(nenhuma)"
                raise CommandError(
                    f"Conta '{options['account_slug']}' não encontrada. Disponíveis: {disponiveis}"
                )
            return account
        account = accounts.first()
        if account is None:
            raise CommandError("Nenhuma conta cadastrada.")
        return account
