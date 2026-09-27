from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])

# ── Apps ─────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "ninja",
    "configs",
    "users",
    "gateway",
    "embeddings",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "robinhood.urls"

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

WSGI_APPLICATION = "robinhood.wsgi.application"
ASGI_APPLICATION = "robinhood.asgi.application"

# ── Database (PostgreSQL + pgvector) ─────────────────────────────────────
# DATABASE_URL=postgres://user:pw@127.0.0.1:5432/robinhood
DATABASES = {"default": {**env.db("DATABASE_URL"), "CONN_MAX_AGE": 0}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

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
MEDIA_ROOT = BASE_DIR / "media"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

AUTH_USER_MODEL = "users.User"
DEFAULT_PHONE_REGION = "IR"

# ── Secrets for the API ──────────────────────────────────────────────────
ADMIN_API_TOKEN = env("ADMIN_API_TOKEN")
INTERNAL_TOKEN = env("INTERNAL_TOKEN")

# ── LLM providers ────────────────────────────────────────────────────────
def _keys(name):
    return [k.strip() for k in env.list(name, default=[]) if k.strip()]


LLM_KEYS = {
    "cerebras": _keys("CEREBRAS_API_KEYS"),
    "groq": _keys("GROQ_API_KEYS"),
    "gemini": _keys("GEMINI_API_KEYS"),
    "cloudflare": _keys("CLOUDFLARE_API_KEYS"),
    "openrouter": _keys("OPENROUTER_API_KEYS"),
    "huggingface": _keys("HF_TOKENS"),
}

CLOUDFLARE_ACCOUNT_ID = env("CLOUDFLARE_ACCOUNT_ID", default="")
OUTBOUND_PROXY = env("OUTBOUND_PROXY", default="")

LLM_MAX_TOKENS = env.int("LLM_MAX_TOKENS", default=1024)
LLM_TIMEOUT_SECONDS = env.float("LLM_TIMEOUT_SECONDS", default=25.0)
HISTORY_TOKEN_BUDGET = env.int("HISTORY_TOKEN_BUDGET", default=3000)
HISTORY_MAX_MESSAGES = 40

DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."
PLATFORM_SYSTEM_PROMPT = env("PLATFORM_SYSTEM_PROMPT", default="")

# ── Cache / rate limits (Redis) ──────────────────────────────────────────
REDIS_URL = env("REDIS_URL", default="")
CACHES = (
    {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
    if REDIS_URL else
    {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)

# ── RAG ──────────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
EMBED_MODEL_DIR = env("EMBED_MODEL_DIR")
EMBEDDER_URL = env("EMBEDDER_URL", default="http://127.0.0.1:9100")
SERVE_EMBEDDER = env.bool("SERVE_EMBEDDER", default=False)  # True only for the dedicated embedder process

RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP = 1200, 250
RAG_TOP_K = 5
RAG_MIN_SCORE = env.float("RAG_MIN_SCORE", default=0.78)   # e5 scores cluster high; tune in testing
RAG_MAX_FILE_BYTES = 100 * 1024 * 1024
RAG_MAX_CHUNKS_PER_KEY = 20000

# ── Celery ───────────────────────────────────────────────────────────────
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/2")
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
# must exceed the task time_limit, or long ingests get redelivered twice
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 6 * 3600}