"""
Mixins de viewset que implementam o isolamento multi-tenant e a auditoria.

Preferencialmente use as classes-base de `apps.core.viewsets` (que ja combinam
estes mixins). Eles ficam aqui separados para permitir composicoes especiais.
"""
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError

from apps.core.access import is_tenant_admin
from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import set_current_account


def model_has_field(model, field_name):
    """True se o model possui um campo concreto com esse nome (sem tocar no banco)."""
    return any(field.name == field_name for field in model._meta.fields)


class TenantQuerySetMixin:
    """Restringe o queryset ao escopo do usuario: conta, e (nao-admin) restaurante/filial.

    Admin/superuser enxerga a conta inteira e pode filtrar por restaurante/filial via
    query params; demais perfis ficam limitados ao proprio restaurante/filial do perfil.
    Nunca ha escopo global: sem conta no request, um model com campo `account`
    devolve vazio (ver get_queryset).
    """

    tenant_branch_field = "branch"
    tenant_restaurant_field = "restaurant"

    def get_queryset(self):
        base_queryset = super().get_queryset()
        model = base_queryset.model
        include_deleted = self._wants_deleted_records()
        if hasattr(model, "all_objects"):
            queryset = model.all_objects.all()
            if model_has_field(model, "deleted_at") and not include_deleted:
                queryset = queryset.filter(deleted_at__isnull=True)
        else:
            queryset = base_queryset
        queryset = self._apply_delta_filter(queryset)

        user = self.request.user
        account = getattr(self.request, "account", None)

        if account is not None:
            set_current_account(account)
            if model_has_field(queryset.model, "account"):
                queryset = queryset.filter(account=account)
        elif model_has_field(queryset.model, "account"):
            # Sem conta no request (superusuário sem perfil e sem X-Account-ID)
            # a API não serve dados de conta nenhuma — devolver o queryset sem
            # filtro aqui vazava todas as contas para o frontend. Mesmo
            # comportamento do TenantManager, que também devolve none() quando
            # não há conta atual. Ver tudo é papel do /admin, isento do
            # TenantMiddleware.
            return queryset.none()

        if not user.is_authenticated:
            return queryset.none()

        if is_tenant_admin(user):
            return self._apply_admin_scope_filters(queryset)

        profile = getattr(user, "profile", None)
        if not profile:
            return queryset.none()

        model_is_restaurant_scoped = (
            queryset.model._meta.label == "restaurants.Restaurant"
            or model_has_field(queryset.model, self.tenant_restaurant_field)
        )
        if model_is_restaurant_scoped and not profile.restaurant_id:
            return queryset.none()

        filters = {}
        if profile.restaurant_id:
            if queryset.model._meta.label == "restaurants.Restaurant":
                filters["id"] = profile.restaurant_id
            elif model_has_field(queryset.model, self.tenant_restaurant_field):
                filters[f"{self.tenant_restaurant_field}_id"] = profile.restaurant_id
        return queryset.filter(**filters) if filters else queryset

    def soft_delete_scope(self, queryset):
        """Aplica (ou nao) o recorte de registros excluidos.

        Exposto para os viewsets que montam o proprio queryset: e o unico jeito
        de o delta sync enxergar uma exclusao, ja que um registro apagado
        apenas some da listagem normal.
        """
        if not model_has_field(queryset.model, "deleted_at") or self._wants_deleted_records():
            return queryset
        return queryset.filter(deleted_at__isnull=True)

    def _wants_deleted_records(self):
        """O cliente pediu explicitamente os registros excluidos?

        Serve ao delta sync do PDV (`?updated_after=...&include_deleted=1`):
        sem isso o terminal offline nunca ficaria sabendo que um produto foi
        removido na retaguarda — ele simplesmente pararia de aparecer na
        listagem, e o registro antigo continuaria vendavel no caixa. So vale
        junto de `updated_after`, para nao mudar o comportamento de nenhuma
        listagem normal da aplicacao.
        """
        params = self.request.query_params
        return bool(params.get("updated_after")) and str(
            params.get("include_deleted", "")
        ).lower() in {"1", "true", "yes"}

    def _apply_delta_filter(self, queryset):
        """Restringe a `updated_at > updated_after`, quando informado.

        E o que permite o Caixa Principal reconciliar depois de horas offline
        sem baixar a base inteira de novo (sincronizacao incremental). Um valor
        invalido e ignorado: melhor devolver a listagem completa do que negar
        os dados ao caixa por causa de um parametro malformado.
        """
        raw = self.request.query_params.get("updated_after")
        if not raw or not model_has_field(queryset.model, "updated_at"):
            return queryset
        moment = parse_datetime(raw)
        if moment is None:
            return queryset
        if timezone.is_naive(moment):
            moment = timezone.make_aware(moment, timezone.get_default_timezone())
        return queryset.filter(updated_at__gt=moment)

    def filter_queryset(self, queryset):
        """Aplica o recorte incremental depois dos filtros normais.

        Fica aqui, e nao so em `get_queryset`, porque alguns viewsets montam o
        proprio queryset sem chamar `super()` — e o delta sync precisa valer
        para todos, senao o Caixa Principal rebaixaria justamente o cardapio
        (o maior deles) por inteiro a cada reconexao.
        """
        return self._apply_delta_filter(super().filter_queryset(queryset))

    def get_object(self):
        obj = super().get_object()
        account = getattr(self.request, "account", None)
        if account is not None and hasattr(obj, "account_id") and obj.account_id != account.id:
            from django.http import Http404

            raise Http404()
        return obj

    def _apply_admin_scope_filters(self, queryset):
        restaurant_id = self.request.query_params.get(self.tenant_restaurant_field)
        branch_id = self.request.query_params.get(self.tenant_branch_field)
        filters = {}

        if restaurant_id:
            if queryset.model._meta.label == "restaurants.Restaurant":
                filters["id"] = restaurant_id
            elif model_has_field(queryset.model, self.tenant_restaurant_field):
                filters[f"{self.tenant_restaurant_field}_id"] = restaurant_id

        if branch_id:
            if queryset.model._meta.label == "restaurants.Branch":
                filters["id"] = branch_id
            elif model_has_field(queryset.model, self.tenant_branch_field):
                filters[f"{self.tenant_branch_field}_id"] = branch_id

        return queryset.filter(**filters) if filters else queryset


class AuditCreateUpdateMixin:
    """Injeta conta/autor nos writes, valida o escopo do usuario e grava o AuditLog.

    O cliente nunca define `account` nem os campos de auditoria: eles vem sempre
    do usuario/contexto autenticado. Restaurante e filial informados sao validados
    contra o perfil (exceto para admin) e, se omitidos, herdados do perfil.
    """

    def perform_create(self, serializer):
        model_fields = {field.name for field in serializer.Meta.model._meta.fields}
        user = self.request.user
        profile = getattr(user, "profile", None)
        account = getattr(self.request, "account", None) or getattr(profile, "account", None)

        # Conta nunca vem do payload: e sempre a conta autenticada.
        serializer.validated_data.pop("account", None)

        extra = {}
        if "account" in model_fields:
            if not account:
                raise ValidationError({"account": "Contexto de conta e obrigatorio."})
            extra["account"] = account

        if serializer.Meta.model._meta.label == "restaurants.Restaurant" and profile and not is_tenant_admin(user):
            raise ValidationError({"restaurant": "Apenas admin pode criar restaurantes."})

        self._assert_scope_allowed(serializer)

        if "created_by" in model_fields:
            extra["created_by"] = user
        if "updated_by" in model_fields:
            extra["updated_by"] = user

        # Restaurante/filial quando nao informados (ausentes ou null) no payload.
        model = serializer.Meta.model
        if "restaurant" in model_fields and not serializer.validated_data.get("restaurant"):
            restaurant_optional = model._meta.get_field("restaurant").null
            inherited_restaurant = getattr(profile, "restaurant", None)
            if not restaurant_optional:
                # Restaurante obrigatorio: herda do perfil ou devolve erro claro
                # (em vez de um IntegrityError/409 que nao aponta para nenhum campo).
                if inherited_restaurant is not None:
                    extra["restaurant"] = inherited_restaurant
                else:
                    raise ValidationError(
                        {"restaurant": "Selecione um restaurante no seletor do topo antes de cadastrar."}
                    )
            # Restaurante opcional (recurso compartilhado, ex.: categorias/adicionais):
            # fica nulo — pertence a conta (a todos os restaurantes).

        if "branch" in model_fields and not serializer.validated_data.get("branch"):
            # A filial pertence a um restaurante: nunca herda a filial do perfil
            # quando um admin escolheu outro restaurante no formulário.
            selected_restaurant = serializer.validated_data.get("restaurant") or extra.get("restaurant")
            has_restaurant = bool(selected_restaurant)
            inherited_branch = getattr(profile, "branch", None)
            if has_restaurant:
                if inherited_branch is not None and inherited_branch.restaurant_id == selected_restaurant.id:
                    extra["branch"] = inherited_branch
                else:
                    branch_model = model._meta.get_field("branch").remote_field.model
                    extra["branch"] = (
                        branch_model.all_objects.filter(
                            account=account,
                            restaurant=selected_restaurant,
                            deleted_at__isnull=True,
                        )
                        .order_by("created_at")
                        .first()
                    )

        instance = serializer.save(**{k: v for k, v in extra.items() if v is not None})
        record_audit(action=AuditLog.ACTION_CREATED, instance=instance, actor=user, request=self.request)

    def perform_update(self, serializer):
        model_fields = {field.name for field in serializer.Meta.model._meta.fields}
        serializer.validated_data.pop("account", None)

        self._assert_scope_allowed(serializer)

        extra = {}
        if "updated_by" in model_fields:
            extra["updated_by"] = self.request.user

        instance = serializer.save(**extra)
        record_audit(action=AuditLog.ACTION_UPDATED, instance=instance, actor=self.request.user, request=self.request)

    def _assert_scope_allowed(self, serializer):
        """Impede que um usuario nao-admin grave em restaurante/filial fora do seu escopo."""
        data = serializer.validated_data
        user = self.request.user
        profile = getattr(user, "profile", None)
        if not profile or is_tenant_admin(user):
            return

        if "restaurant" in data:
            restaurant = data["restaurant"]
            if profile.restaurant_id and restaurant and restaurant.id != profile.restaurant_id:
                raise ValidationError({"restaurant": "Restaurante fora do escopo do usuario."})

        if "branch" in data:
            branch = data["branch"]
            if profile.branch_id and branch and branch.id != profile.branch_id:
                raise ValidationError({"branch": "Filial fora do escopo do usuario."})
            if profile.restaurant_id and branch and branch.restaurant_id != profile.restaurant_id:
                raise ValidationError({"branch": "Filial pertence a outro restaurante."})
