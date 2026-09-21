from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-9$jzlf@w%m()am_y7mi$83gxlk#8z55vp2!h4&r-p0608c90$8'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'configs',
    'users',
    'gateway',
    'ninja'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'robinhood.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'robinhood.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = 'static/'


# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.console.EmailBackend',
    },
}

AUTH_USER_MODEL = "users.User"
DEFAULT_PHONE_REGION = "IR"

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


REDIS_URL = env("REDIS_URL", default="")
CACHES = (
    {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
    if REDIS_URL else
    {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)