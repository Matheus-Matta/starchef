from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Account, UserProfile
from apps.core.management.commands._demo_seed import (
    DEFAULT_ACCOUNT_SLUG,
    DEFAULT_BRANCH_NAME,
    DEFAULT_EMAIL,
    DEFAULT_PASSWORD,
    DEFAULT_RESTAURANT_NAME,
    DEFAULT_USERNAME,
    ensure_base_tenant,
    ensure_role,
    ensure_tenant_user,
)
from apps.core.tenant import tenant_context
from apps.restaurants.models import Branch, Restaurant


class Command(BaseCommand):
    help = "Create or update a Django user with a correctly configured tenant profile."

    def add_arguments(self, parser):
        parser.add_argument("--account-slug", default=DEFAULT_ACCOUNT_SLUG)
        parser.add_argument("--account-name", default="StarChef Demo")
        parser.add_argument("--username", default=DEFAULT_USERNAME)
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--password", default=DEFAULT_PASSWORD)
        parser.add_argument("--first-name", default="Admin")
        parser.add_argument("--last-name", default="Demo")
        parser.add_argument("--phone", default="")
        parser.add_argument(
            "--profile-type",
            default=UserProfile.PROFILE_ADMIN,
            choices=[choice[0] for choice in UserProfile.PROFILE_CHOICES],
        )
        parser.add_argument("--role-code", default=None)
        parser.add_argument("--role-name", default=None)
        parser.add_argument("--restaurant-id", default=None)
        parser.add_argument("--restaurant-name", default=DEFAULT_RESTAURANT_NAME)
        parser.add_argument("--branch-id", default=None)
        parser.add_argument("--branch-name", default=DEFAULT_BRANCH_NAME)
        parser.add_argument("--staff", action="store_true", default=True)
        parser.add_argument("--no-staff", action="store_false", dest="staff")
        parser.add_argument("--superuser", action="store_true", default=True)
        parser.add_argument("--no-superuser", action="store_false", dest="superuser")
        parser.add_argument(
            "--create-tenant",
            action="store_true",
            help="Create a minimal account, restaurant and branch when the account slug does not exist.",
        )

    def handle(self, *args, **options):
        account = Account.objects.filter(slug=options["account_slug"]).first()
        if account is None:
            if not options["create_tenant"]:
                raise CommandError(
                    f"Account '{options['account_slug']}' not found. Run seed_demo first or use --create-tenant."
                )
            account, _, _ = ensure_base_tenant(
                account_slug=options["account_slug"],
                account_name=options["account_name"],
                restaurant_name=options["restaurant_name"],
                branch_name=options["branch_name"],
            )

        restaurant = self._resolve_restaurant(account, options)
        branch = self._resolve_branch(account, restaurant, options)
        role_code = options["role_code"] or options["profile_type"]
        role_name = options["role_name"] or role_code.replace("_", " ").title()
        role = ensure_role(account, code=role_code, name=role_name, restaurant=restaurant)

        user = ensure_tenant_user(
            account=account,
            username=options["username"],
            email=options["email"],
            password=options["password"],
            first_name=options["first_name"],
            last_name=options["last_name"],
            profile_type=options["profile_type"],
            restaurant=restaurant,
            branch=branch,
            role=role,
            phone=options["phone"],
            is_staff=options["staff"],
            is_superuser=options["superuser"],
        )

        self.stdout.write(self.style.SUCCESS("Tenant user ready."))
        self.stdout.write(f"username: {user.username}")
        self.stdout.write(f"email: {user.email}")
        self.stdout.write(f"account: {account.slug} ({account.name})")
        self.stdout.write(f"restaurant: {restaurant.trade_name if restaurant else '-'}")
        self.stdout.write(f"branch: {branch.name if branch else '-'}")
        self.stdout.write(f"profile_type: {options['profile_type']}")

    def _resolve_restaurant(self, account, options):
        with tenant_context(account):
            queryset = Restaurant.all_objects.filter(account=account)
            if options["restaurant_id"]:
                restaurant = queryset.filter(pk=options["restaurant_id"]).first()
                if restaurant is None:
                    raise CommandError("Restaurant not found for this account.")
                return restaurant

            if options["restaurant_name"]:
                restaurant = queryset.filter(trade_name=options["restaurant_name"]).first()
                if restaurant:
                    return restaurant

            restaurant = queryset.filter(is_active=True).order_by("trade_name").first()
            if restaurant is None:
                raise CommandError("No restaurant found for this account. Use seed_demo or --create-tenant.")
            return restaurant

    def _resolve_branch(self, account, restaurant, options):
        with tenant_context(account):
            queryset = Branch.all_objects.filter(account=account, restaurant=restaurant)
            if options["branch_id"]:
                branch = queryset.filter(pk=options["branch_id"]).first()
                if branch is None:
                    raise CommandError("Branch not found for this account and restaurant.")
                return branch

            if options["branch_name"]:
                branch = queryset.filter(name=options["branch_name"]).first()
                if branch:
                    return branch

            return queryset.filter(is_active=True).order_by("name").first()
