import sys
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "corsheaders",
    # Local
    "apps.core",
    "apps.accounts",
    "apps.subscriptions",
    "apps.support",
    "apps.review",
    "apps.security",
    "apps.orchestrator",
    "apps.widget",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"transaction_mode": "IMMEDIATE", "timeout": 5},
    },
}

# Keep the template SQLite default; PostgreSQL is selected by DATABASE_URL.
if env("DATABASE_URL", default=""):
    DATABASES["default"] = env.db("DATABASE_URL")

CSRF_FAILURE_VIEW = "apps.core.errors.csrf_failure"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "apps.core.errors.api_exception_handler",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Security thresholds (UAH and counts). Policy reads these; nothing is hardcoded there.
AUTO_REFUND_LIMIT = env.int("AUTO_REFUND_LIMIT", default=50)
HARD_REFUND_LIMIT = env.int("HARD_REFUND_LIMIT", default=1000)
DAILY_REFUND_LIMIT = env.int("DAILY_REFUND_LIMIT", default=2000)
RISKY_ACTIONS_PER_HOUR = env.int("RISKY_ACTIONS_PER_HOUR", default=5)
IDEMPOTENCY_WINDOW_SEC = env.int("IDEMPOTENCY_WINDOW_SEC", default=120)
POLICY_REVIEW_HIGH_RISK = env.bool("POLICY_REVIEW_HIGH_RISK", default=True)
POLICY_REVIEW_VIP = env.bool("POLICY_REVIEW_VIP", default=True)

# LLM. The key comes only from the environment (.env is git-ignored); never log or return it.
LLM_PROVIDER = env("LLM_PROVIDER", default="mock")  # deepseek | mock
LLM_API_KEY = env("LLM_API_KEY", default="")
LLM_BASE_URL = env("LLM_BASE_URL", default="https://api.deepseek.com")
LLM_MODEL = env("LLM_MODEL", default="deepseek-chat")
LLM_TIMEOUT = env.int("LLM_TIMEOUT", default=20)
# One customer message may spend at most this long on model calls in total.
LLM_TOTAL_DEADLINE_SEC = env.int("LLM_TOTAL_DEADLINE_SEC", default=30)
LLM_MAX_CALLS_PER_MESSAGE = env.int("LLM_MAX_CALLS_PER_MESSAGE", default=8)
LLM_MAX_OUTPUT_TOKENS = env.int("LLM_MAX_OUTPUT_TOKENS", default=1500)
# Tests must never reach the network, whatever .env says.
if sys.argv[1:2] == ["test"] or "pytest" in sys.modules:
    LLM_PROVIDER = "mock"

# The agent pipeline behind the customer chat. Off: every message goes straight to a human.
ORCHESTRATOR_ENABLED = env.bool("ORCHESTRATOR_ENABLED", default=True)
# The Responder LLM writes every reply from the customer's facts; the manifest text is the fallback.
ORCHESTRATOR_LLM_RESPONDER = env.bool("ORCHESTRATOR_LLM_RESPONDER", default=True)

# Which product the pipeline acts on: "dev" is the built-in domain (apps.subscriptions and
# apps.support); "mcp" is an external product behind the execution server (execution/ at the
# repository root).
ORCHESTRATOR_GATEWAY = env("ORCHESTRATOR_GATEWAY", default="dev")
EXECUTION_URL = env("EXECUTION_URL", default="http://127.0.0.1:9000")
EXECUTION_TENANT = env("EXECUTION_TENANT", default="cloudbox")  # its key in products.toml
EXECUTION_SECRET = env("EXECUTION_SECRET", default="")  # signs customer tokens; never logged
EXECUTION_SERVICE_KEY = env("EXECUTION_SERVICE_KEY", default="")
# Our username -> the customer's id in the product. Defaults map the seed_demo accounts onto the
# cloudbox mock (same situations: unapplied payment, Pro with renewal, double charge).
EXECUTION_CUSTOMERS = env.dict(
    "EXECUTION_CUSTOMERS",
    default={"paid_plus": "c-101", "active_pro": "c-102", "refund_review": "c-103"},
)

# The embeddable widget (apps.widget): each product signs its customers' widget tokens with its own
# secret, never with EXECUTION_SECRET. Format: WIDGET_SECRETS=cloudbox=...,shopx=...
WIDGET_SECRETS = env.dict("WIDGET_SECRETS", default={})
