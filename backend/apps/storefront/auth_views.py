"""
Autenticação do EDITOR do storefront.

O editor mora em outro aplicativo (o servidor Nuxt, em outra porta/domínio) e
precisa da própria sessão. Ele não pode simplesmente reaproveitar o login do
painel por dois motivos:

1. **Colisão de cookie.** Painel e editor batem no mesmo backend, então os
   cookies caem no mesmo domínio. Com o mesmo nome, abrir o editor derrubaria a
   sessão do painel na outra aba — e faria as duas telas agirem como o último
   usuário que entrou. Aqui os cookies são `sf_*` (ver `apps.core.cookies`), e o
   header `X-Auth-Scope: storefront` diz ao backend qual ler.

2. **Escopo de tenant.** O editor abre por endereço público (`/burger/editor/`),
   e o slug do site vem da URL — ou seja, de fora. Quem decide se aquele site é
   do usuário é o servidor, nunca o cliente: `_resolve_site` cruza o slug com os
   sites que o usuário realmente pode editar e devolve 403 quando não bate. Sem
   isso, bastaria trocar o slug na barra de endereço para abrir o editor do
   restaurante do vizinho.

O que sai daqui é sempre o MÍNIMO: identidade do usuário, permissões dele e os
sites da conta dele. Nada de listar contas, restaurantes ou usuários.
"""
from rest_framework import status
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.serializers import StarChefTokenObtainPairSerializer, resolve_enabled_modules
from apps.core.access import is_tenant_admin
from apps.core.cookies import SCOPE_STOREFRONT, clear_auth_cookies, refresh_cookie_name, set_auth_cookies
from apps.core.modules import MODULE_ECOMMERCE
from apps.storefront.models import MenuSite
from apps.storefront.permissions import ALL_STOREFRONT_PERMISSIONS, PERM_VIEW, has_storefront_permission


def editable_sites_for(user, account):
    """Sites que o usuário pode editar. Nunca de outra conta, nunca de outro restaurante.

    É a MESMA regra do `TenantQuerySetMixin` aplicada ao `MenuSite`, escrita
    aqui porque esta view não é um viewset: admin da conta enxerga a conta
    inteira; os demais, só o próprio restaurante. Perfil sem restaurante e sem
    papel de admin não edita site nenhum — `MenuSite.restaurant` é obrigatório,
    então não existe site "da conta toda" para ele herdar.
    """
    if account is None or not user or not user.is_authenticated:
        return MenuSite.all_objects.none()

    sites = MenuSite.all_objects.filter(account=account, deleted_at__isnull=True)
    if is_tenant_admin(user):
        return sites

    profile = getattr(user, "profile", None)
    if not profile or not profile.restaurant_id:
        return sites.none()
    return sites.filter(restaurant_id=profile.restaurant_id)


def _account_of(user, request=None):
    account = getattr(request, "account", None) if request is not None else None
    if account is not None:
        return account
    profile = getattr(user, "profile", None)
    return profile.account if profile and profile.account_id else None


def _site_payload(site):
    return {"id": str(site.id), "slug": site.slug, "name": site.name, "is_active": site.is_active}


def _user_payload(user, account, sites):
    """Identidade + o que o editor precisa para se comportar. Nada além disso.

    Repare no que NÃO está aqui: id de outros usuários, lista de restaurantes da
    conta, dados de assinatura. O editor não precisa, e o que não é enviado não
    vaza.
    """
    profile = getattr(user, "profile", None)
    return {
        "user": {
            "id": str(user.id),
            "username": user.username,
            "name": user.get_full_name() or user.username,
            "email": user.email,
            "is_superuser": user.is_superuser,
            "is_account_admin": is_tenant_admin(user),
        },
        # Campos PLANOS (`account_id`, e não `account: {...}`) pelo mesmo motivo
        # do `/auth/me/` do painel: o `TenantResponseSafetyMiddleware` trata
        # qualquer chave `account` do corpo como marcador de tenant e compara o
        # valor com a conta da requisição. Um objeto aninhado ali não bate com
        # o id, e a resposta inteira era bloqueada como vazamento (404).
        "account_id": str(account.id) if account else None,
        "account_name": account.name if account else None,
        "restaurant_id": str(profile.restaurant_id) if profile and profile.restaurant_id else None,
        "restaurant_name": profile.restaurant.trade_name if profile and profile.restaurant_id else None,
        "enabled_modules": resolve_enabled_modules(user, account),
        # Só os códigos do storefront: o editor não decide nada com base em
        # permissão de estoque ou de caixa, e mandar a lista inteira daria a
        # quem inspecionar a resposta um mapa do que aquele usuário faz no ERP.
        "permissions": sorted(
            code for code in ALL_STOREFRONT_PERMISSIONS if has_storefront_permission(user, code)
        ),
        "sites": [_site_payload(site) for site in sites],
    }


def _check_can_open_editor(user, account):
    """Módulo licenciado + permissão de ver o site. 403 com motivo específico."""
    if not user.is_superuser and not (account and account.has_module(MODULE_ECOMMERCE)):
        raise PermissionDenied("O módulo de e-commerce não está habilitado para a sua conta.")
    if not has_storefront_permission(user, PERM_VIEW):
        raise PermissionDenied("Seu perfil não tem permissão para editar o site do cardápio.")


def _resolve_site(user, account, slug):
    """Cruza o slug pedido com os sites do usuário.

    A mensagem é a mesma para "não existe" e "é de outro restaurante" de
    propósito: distinguir os dois casos transformaria este endpoint num
    verificador de quais slugs existem na plataforma.
    """
    if not slug:
        return None
    site = editable_sites_for(user, account).filter(slug=slug).first()
    if site is None:
        raise PermissionDenied("Este site não pertence ao seu restaurante.")
    return site


class StorefrontLoginView(TokenObtainPairView):
    """Login do editor. Mesmas credenciais do painel, cookies e checagens próprios."""

    serializer_class = StarChefTokenObtainPairSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0])

        user = serializer.user
        account = _account_of(user)
        _check_can_open_editor(user, account)

        # O site pedido é verificado ANTES de a sessão existir: entrar e só
        # então descobrir que o site é de outro restaurante deixaria o usuário
        # logado numa tela que ele não pode usar.
        site = _resolve_site(user, account, str(request.data.get("site") or "").strip())
        sites = editable_sites_for(user, account)

        payload = _user_payload(user, account, sites)
        if site is not None:
            payload["site"] = _site_payload(site)

        response = Response(payload, status=status.HTTP_200_OK)
        return set_auth_cookies(
            response,
            access=serializer.validated_data.get("access"),
            refresh=serializer.validated_data.get("refresh"),
            scope=SCOPE_STOREFRONT,
        )


class StorefrontRefreshView(TokenRefreshView):
    """Renova o access do editor lendo o refresh do cookie `sf_refresh`."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token_refresh"

    def post(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        if not data.get("refresh"):
            data["refresh"] = request.COOKIES.get(refresh_cookie_name(SCOPE_STOREFRONT)) or ""

        # Sem refresh nenhum não há o que renovar: é "não está logado" (401), e
        # não "mandou o corpo errado" (400). O editor usa esse 401 para decidir
        # entre mostrar o formulário e seguir direto para o canvas — um 400 o
        # faria tratar sessão expirada como erro de programação.
        if not data["refresh"]:
            raise NotAuthenticated("Sessão do editor não encontrada.")

        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0])

        response = Response({"detail": "ok"}, status=status.HTTP_200_OK)
        return set_auth_cookies(
            response,
            access=serializer.validated_data.get("access"),
            refresh=serializer.validated_data.get("refresh"),
            scope=SCOPE_STOREFRONT,
        )


class StorefrontLogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.COOKIES.get(refresh_cookie_name(SCOPE_STOREFRONT))
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except TokenError:
                pass  # já inválido/expirado — encerrar a sessão mesmo assim
        response = Response(status=status.HTTP_204_NO_CONTENT)
        # Só os cookies DO EDITOR: sair do editor não pode deslogar o painel.
        return clear_auth_cookies(response, scope=SCOPE_STOREFRONT)


class StorefrontSessionView(APIView):
    """Quem sou eu, o que posso, e este site é meu?

    O editor chama isto antes de montar a tela. Com `?site=<slug>` a resposta
    também confirma (ou nega, com 403) que aquele endereço é do usuário — é o
    guarda da rota `/{slug}/editor/`.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        account = _account_of(user, request)
        _check_can_open_editor(user, account)

        site = _resolve_site(user, account, str(request.query_params.get("site") or "").strip())
        payload = _user_payload(user, account, editable_sites_for(user, account))
        if site is not None:
            payload["site"] = _site_payload(site)
        return Response(payload)
