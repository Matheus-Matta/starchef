import os
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parents[2]

SECRET_KEY = config("DJANGO_SECRET_KEY", default="unsafe-dev-key")
SETTINGS_MODULE = os.getenv("DJANGO_SETTINGS_MODULE", "")
DEBUG = config("DJANGO_DEBUG", default=SETTINGS_MODULE.endswith(".development"), cast=bool)
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

INSTALLED_APPS = [
    "daphne",
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "channels",
    "apps.core",
    "apps.accounts",
    "apps.restaurants",
    "apps.customers",
    "apps.menu",
    "apps.orders",
    "apps.kitchen",
    "apps.payments",
    "apps.invoices",
    "apps.stock",
    "apps.printers",
    "apps.reports",
    "apps.data_exchange",
    "apps.integrations",
    "apps.sla",
    "apps.notifications",
    "apps.realtime",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.TenantMiddleware",
    # Depois do tenant: a deduplicação é por conta, então precisa da conta já
    # resolvida em `request.account`.
    "apps.core.idempotency.IdempotencyMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.TenantResponseSafetyMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

# Este backend serve o Django admin (o app fica no frontend Vue). Apos o login
# sem `?next=`, redireciona para a home do admin em vez do default /accounts/profile/,
# que nao existe e retornava "pagina nao encontrada".
LOGIN_REDIRECT_URL = "/admin/"
LOGIN_URL = "/admin/login/"
FIRST_ACCESS_TOKEN = config("DJANGO_FIRST_ACCESS_TOKEN", default="")
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:5173").rstrip("/")

EMAIL_BACKEND = config("DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = config("DJANGO_EMAIL_HOST", default="localhost")
EMAIL_PORT = config("DJANGO_EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("DJANGO_EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("DJANGO_EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("DJANGO_EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_USE_SSL = config("DJANGO_EMAIL_USE_SSL", default=False, cast=bool)
DEFAULT_FROM_EMAIL = config("DJANGO_DEFAULT_FROM_EMAIL", default="StarChef <no-reply@localhost>")
PASSWORD_RESET_TIMEOUT_MINUTES = config("PASSWORD_RESET_TIMEOUT_MINUTES", default=30, cast=int)

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

USE_SQLITE_DATABASE = config("USE_SQLITE_DATABASE", default=DEBUG, cast=bool)


def build_database_settings(use_sqlite):
    if use_sqlite:
        # Ancora o SQLite em BASE_DIR sempre. Um SQLITE_DB_NAME relativo seria
        # resolvido contra o cwd, criando bancos diferentes conforme o diretorio
        # de onde o comando roda (raiz vs backend/). Aqui garantimos um unico local.
        sqlite_name = config("SQLITE_DB_NAME", default="db.sqlite3")
        sqlite_path = Path(sqlite_name)
        if not sqlite_path.is_absolute():
            sqlite_path = BASE_DIR / sqlite_path
        return {
            "DATABASES": {
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": str(sqlite_path),
                }
            }
        }

    return {
        "DATABASES": {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": config("POSTGRES_DB", default="starchef"),
                "USER": config("POSTGRES_USER", default="starchef"),
                "PASSWORD": config("POSTGRES_PASSWORD", default="starchef"),
                "HOST": config("POSTGRES_HOST", default="localhost"),
                "PORT": config("POSTGRES_PORT", default="5432"),
                "CONN_MAX_AGE": config("POSTGRES_CONN_MAX_AGE", default=60, cast=int),
                "CONN_HEALTH_CHECKS": config("POSTGRES_CONN_HEALTH_CHECKS", default=True, cast=bool),
            }
        }
    }


globals().update(build_database_settings(USE_SQLITE_DATABASE))

REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")
USE_LOCAL_MEMORY_SERVICES = config("USE_LOCAL_MEMORY_SERVICES", default=DEBUG, cast=bool)

def build_runtime_service_settings(use_local_memory):
    if use_local_memory:
        return {
            "CACHES": {
                "default": {
                    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                    "LOCATION": "starchef-local-cache",
                }
            },
            "CHANNEL_LAYERS": {
                "default": {
                    "BACKEND": "channels.layers.InMemoryChannelLayer",
                }
            },
            "CELERY_BROKER_URL": "memory://",
            "CELERY_RESULT_BACKEND": "cache+memory://",
            "CELERY_TASK_ALWAYS_EAGER": True,
            "CELERY_TASK_EAGER_PROPAGATES": True,
        }

    return {
        "CACHES": {
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": REDIS_URL,
            }
        },
        "CHANNEL_LAYERS": {
            "default": {
                "BACKEND": "channels_redis.core.RedisChannelLayer",
                "CONFIG": {"hosts": [REDIS_URL]},
            }
        },
        "CELERY_BROKER_URL": config("CELERY_BROKER_URL", default="redis://localhost:6379/1"),
        "CELERY_RESULT_BACKEND": config("CELERY_RESULT_BACKEND", default="redis://localhost:6379/2"),
        "CELERY_TASK_ALWAYS_EAGER": False,
        "CELERY_TASK_EAGER_PROPAGATES": False,
    }


globals().update(build_runtime_service_settings(USE_LOCAL_MEMORY_SERVICES))

CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "America/Sao_Paulo"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        # Lê o JWT do header Authorization (compat) OU do cookie httpOnly.
        "apps.core.authentication.CookieJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
        "apps.core.permissions.HasTenantAccess",
        "apps.core.permissions.HasModulePermission",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardResultsSetPagination",
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "apps.data_exchange.filters.AdvancedFieldFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    # Rate limiting global: toda requisição passa por Anon/UserRateThrottle. Os
    # limites vêm de env (default: 60/min anônimo, 2000/h por usuário) para poder
    # ajustar em produção sem redeploy. Escopos sensíveis (login, refresh de token,
    # aprovação de caixa) têm limites próprios definidos nas views.
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": config("THROTTLE_RATE_ANON", default="60/min"),
        "user": config("THROTTLE_RATE_USER", default="2000/hour"),
        "login": config("THROTTLE_RATE_LOGIN", default="10/min"),
        "token_refresh": config("THROTTLE_RATE_TOKEN_REFRESH", default="30/min"),
        "password_reset": config("THROTTLE_RATE_PASSWORD_RESET", default="5/min"),
        "password_reset_confirm": config("THROTTLE_RATE_PASSWORD_RESET_CONFIRM", default="10/min"),
        "device_poll": config("THROTTLE_RATE_DEVICE_POLL", default="180/min"),
        "cash_approval": config("THROTTLE_RATE_CASH_APPROVAL", default="10/min"),
        # Cardápio público: IP compartilhado por muitos clientes (WiFi do restaurante).
        "public_menu": config("THROTTLE_RATE_PUBLIC_MENU", default="600/min"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    # Trocar a senha invalida imediatamente access/refresh tokens anteriores.
    "CHECK_REVOKE_TOKEN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "StarChef API",
    "DESCRIPTION": "API REST versionada para gestao de restaurantes.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

CORS_ALLOWED_ORIGINS = config(
    "DJANGO_CORS_ALLOWED_ORIGINS",
    default="http://localhost:5173,http://127.0.0.1:5173",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True
# Necessário para o Django aceitar mutações vindas do front (cookies) cross-origin.
CSRF_TRUSTED_ORIGINS = config(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=",".join(CORS_ALLOWED_ORIGINS),
    cast=Csv(),
)

# ── Cookies de autenticação (tokens JWT em httpOnly) ─────────────────────────
# Access/refresh vivem em cookies httpOnly (não expostos ao JS). `sc_session` é
# uma flag legível que sinaliza sessão ativa. Em prod use HTTPS (Secure=True).
JWT_AUTH_COOKIE = config("DJANGO_JWT_AUTH_COOKIE", default="sc_access")
JWT_AUTH_REFRESH_COOKIE = config("DJANGO_JWT_REFRESH_COOKIE", default="sc_refresh")
AUTH_SESSION_COOKIE = "sc_session"
AUTH_COOKIE_SECURE = config("DJANGO_AUTH_COOKIE_SECURE", default=not DEBUG, cast=bool)
AUTH_COOKIE_SAMESITE = config("DJANGO_AUTH_COOKIE_SAMESITE", default="Lax")
AUTH_COOKIE_DOMAIN = config("DJANGO_AUTH_COOKIE_DOMAIN", default="")  # "" -> host-only

# Cookies do Django (sessão/CSRF) seguros em produção.
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

UNFOLD = {
    "SITE_TITLE": "StarChef Admin",
    "SITE_HEADER": "StarChef",
    "SITE_SUBHEADER": "Gestao operacional do restaurante",
    "SITE_SYMBOL": "restaurant",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": "Plataforma (SaaS)",
                "separator": True,
                "items": [
                    {"title": "Contas", "icon": "apartment", "link": "/admin/accounts/account/"},
                    {"title": "Planos", "icon": "workspace_premium", "link": "/admin/accounts/plan/"},
                    {"title": "Assinaturas", "icon": "card_membership", "link": "/admin/accounts/subscription/"},
                    {"title": "Config global", "icon": "settings", "link": "/admin/accounts/globalsystemconfig/"},
                ],
            },
            {
                "title": "Acesso & Auditoria",
                "separator": True,
                "items": [
                    {"title": "Usuarios", "icon": "group", "link": "/admin/auth/user/"},
                    {"title": "Perfis de usuario", "icon": "badge", "link": "/admin/accounts/userprofile/"},
                    {"title": "Perfis de acesso", "icon": "admin_panel_settings", "link": "/admin/accounts/role/"},
                    {"title": "Permissoes", "icon": "key", "link": "/admin/accounts/permission/"},
                    {"title": "Auditoria", "icon": "manage_search", "link": "/admin/core/auditlog/"},
                ],
            },
            {
                "title": "Cadastros base",
                "separator": True,
                "items": [
                    {"title": "Restaurantes", "icon": "storefront", "link": "/admin/restaurants/restaurant/"},
                    {"title": "Filiais", "icon": "store", "link": "/admin/restaurants/branch/"},
                    {"title": "Clientes", "icon": "person", "link": "/admin/customers/customer/"},
                    {"title": "Enderecos de clientes", "icon": "location_on", "link": "/admin/customers/customeraddress/"},
                ],
            },
            {
                "title": "Operacao",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Pedidos", "icon": "receipt_long", "link": "/admin/orders/order/"},
                    {"title": "Itens do pedido", "icon": "restaurant_menu", "link": "/admin/orders/orderitem/"},
                    {"title": "Rodadas de producao", "icon": "layers", "link": "/admin/orders/orderbatch/"},
                    {"title": "Mesas", "icon": "table_restaurant", "link": "/admin/restaurants/table/"},
                    {"title": "Setores de mesa", "icon": "grid_view", "link": "/admin/restaurants/tablesector/"},
                    {"title": "Comandas", "icon": "receipt", "link": "/admin/restaurants/command/"},
                    {"title": "Estacoes KDS", "icon": "kitchen", "link": "/admin/kitchen/kdsstation/"},
                    {"title": "Caixa", "icon": "point_of_sale", "link": "/admin/payments/cashregister/"},
                    {"title": "Mov. de caixa", "icon": "account_balance_wallet", "link": "/admin/payments/cashmovement/"},
                ],
            },
            {
                "title": "Cardapio",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Produtos", "icon": "fastfood", "link": "/admin/menu/product/"},
                    {"title": "Categorias", "icon": "category", "link": "/admin/menu/productcategory/"},
                    {"title": "Variacoes", "icon": "tune", "link": "/admin/menu/productvariation/"},
                    {"title": "Adicionais", "icon": "add_circle", "link": "/admin/menu/productaddon/"},
                    {"title": "Ingredientes", "icon": "nutrition", "link": "/admin/menu/ingredient/"},
                    {"title": "Receitas", "icon": "menu_book", "link": "/admin/menu/recipe/"},
                ],
            },
            {
                "title": "Hardware",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Impressoras", "icon": "print", "link": "/admin/printers/printer/"},
                    {"title": "Balancas", "icon": "scale", "link": "/admin/printers/scale/"},
                    {"title": "Leituras da balanca", "icon": "monitor_weight", "link": "/admin/printers/scalereading/"},
                    {"title": "Jobs de impressao", "icon": "list_alt", "link": "/admin/printers/printjob/"},
                ],
            },
            {
                "title": "Modulo E-commerce",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Cardapios digitais", "icon": "book_online", "link": "/admin/menu/menu/"},
                    {"title": "Itens do cardapio", "icon": "format_list_bulleted", "link": "/admin/menu/menuitem/"},
                ],
            },
            {
                "title": "Modulo Entrega",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Zonas de entrega", "icon": "map", "link": "/admin/restaurants/deliveryzone/"},
                    {"title": "Entregadores", "icon": "two_wheeler", "link": "/admin/restaurants/deliveryman/"},
                ],
            },
            {
                "title": "Modulo Financeiro",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Formas de pagamento", "icon": "credit_card", "link": "/admin/payments/paymentmethod/"},
                    {"title": "Pagamentos", "icon": "payments", "link": "/admin/payments/payment/"},
                    {"title": "Notas fiscais", "icon": "description", "link": "/admin/invoices/invoice/"},
                    {"title": "Config fiscal", "icon": "settings_applications", "link": "/admin/invoices/fiscalconfig/"},
                    {"title": "Perfis fiscais", "icon": "rule", "link": "/admin/invoices/fiscalprofile/"},
                ],
            },
            {
                "title": "Modulo Logistica",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Movimentacoes de estoque", "icon": "inventory_2", "link": "/admin/stock/stockmovement/"},
                    {"title": "Locais de estoque", "icon": "warehouse", "link": "/admin/stock/stocklocation/"},
                ],
            },
        ],
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
    },
}
