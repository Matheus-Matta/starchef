"""
Limites de tenancy (usuários e restaurantes) por conta.

Os limites ficam na própria conta (``Account.max_users`` / ``Account.max_restaurants``)
e são aplicados no CADASTRO desses itens (ver ``RestaurantViewSet`` e ``UserViewSet``).
Convenção: ``0 = ilimitado``.

Ao estourar o limite, levantamos ``LimitReached`` com uma mensagem PERSONALIZADA
(quantidade em uso, limite e o que fazer), que chega ao usuário no envelope de erro
padrão da API com ``error.code = "limit_reached"``.
"""
from apps.core.exceptions import LimitReached

UNLIMITED = 0


def restaurant_count(account):
    """Restaurantes não excluídos da conta (contam para o limite)."""
    from apps.restaurants.models import Restaurant

    return Restaurant.all_objects.filter(account=account, deleted_at__isnull=True).count()


def user_count(account):
    """Perfis de usuário não excluídos da conta (contam para o limite)."""
    from apps.accounts.models import UserProfile

    return UserProfile.all_objects.filter(account=account, deleted_at__isnull=True).count()


def _plural(quantidade, singular, plural):
    return singular if quantidade == 1 else plural


def assert_can_create_restaurant(account):
    """Garante que a conta ainda pode cadastrar um restaurante — senão, 409 amigável."""
    if account is None:
        return
    limit = account.max_restaurants or UNLIMITED
    if limit == UNLIMITED:
        return
    current = restaurant_count(account)
    if current >= limit:
        raise LimitReached(
            f"Limite de restaurantes atingido: seu plano permite {limit} "
            f"{_plural(limit, 'restaurante', 'restaurantes')} e você já tem {current}. "
            "Desative um restaurante existente ou faça upgrade do plano para cadastrar mais."
        )


def assert_can_create_user(account):
    """Garante que a conta ainda pode cadastrar um usuário — senão, 409 amigável."""
    if account is None:
        return
    limit = account.max_users or UNLIMITED
    if limit == UNLIMITED:
        return
    current = user_count(account)
    if current >= limit:
        raise LimitReached(
            f"Limite de usuários atingido: seu plano permite {limit} "
            f"{_plural(limit, 'usuário', 'usuários')} e você já tem {current}. "
            "Desative um usuário existente ou faça upgrade do plano para cadastrar mais."
        )
