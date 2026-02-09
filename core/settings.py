"""
Django settings for core project - PRODUCTION READY
"""
from pathlib import Path
import environ
import os
import sys
from django.utils.translation import gettext_lazy as _

# 1. Setup do django-environ
env = environ.Env(
    # Castings e defaults
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ['127.0.0.1', 'localhost']),
    # GARANTIA: Default explícito caso a ENV falhe
    CSRF_TRUSTED_ORIGINS=(list, ['https://alka.gg', 'https://www.alka.gg']),
    ENABLE_ANALYTICS=(bool, False),
    BETA_ACTIVE=(bool, True), 
)

# Lê .env local se existir
BASE_DIR = Path(__file__).resolve().parent.parent
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# 2. Segurança Core
SECRET_KEY = env('DJANGO_SECRET_KEY') 
DEBUG = env('DEBUG')

ALLOWED_HOSTS = env('ALLOWED_HOSTS')

# FIX CRÍTICO: Usar env.list para forçar parsing correto de lista separada por vírgula
# Se no Railway estiver "https://alka.gg,https://www.alka.gg", o env.list resolve.
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=['https://alka.gg', 'https://www.alka.gg'])

# Headers de Proxy (Railway/Cloudflare)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
else:
    # Dev settings
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_SSL_REDIRECT = False

# Application definition
INSTALLED_APPS = [
    'vault', 
    
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.sites',
    'dbbackup',

    # Third-party
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.openid',
    'allauth.socialaccount.providers.steam',
    'django_ratelimit',
]

SITE_ID = 1

# Middleware Pipeline
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    
    # --- STATIC FILES ---
    'whitenoise.middleware.WhiteNoiseMiddleware', 
    
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware', 
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    
    # --- BETA GATEKEEPER ---
    'core.middleware.BetaAccessMiddleware', 
    
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'vault.context_processors.analytics_settings', 
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Database
DATABASES = {
    'default': env.db('DATABASE_URL', default='sqlite:///db.sqlite3')
}
DATABASES['default']['CONN_MAX_AGE'] = 600 

AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

# I18N
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_L10N = True
USE_TZ = True

LANGUAGES = [
    ('pt-br', _('Português')),
    ('en', _('English')),
    ('es', _('Español')),
]
LOCALE_PATHS = [BASE_DIR / 'locale']

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [ BASE_DIR / 'static' ]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Redis & Celery
REDIS_URL = env('REDIS_URL', default='redis://127.0.0.1:6379/1')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'IGNORE_EXCEPTIONS': True, 
        }
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Auth
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
SOCIALACCOUNT_ADAPTER = 'vault.adapters.AlkahestSocialAdapter'
ACCOUNT_LOGIN_METHODS = {'email', 'username'}
ACCOUNT_EMAIL_VERIFICATION = "optional"
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
LOGIN_REDIRECT_URL = 'dashboard'
LOGIN_URL = '/login/'
LOGOUT_REDIRECT_URL = 'login'

SOCIALACCOUNT_PROVIDERS = {
    'steam': {
        'APP': {
            'client_id': '12345',
            'secret': env('STEAM_API_KEY', default=''), 
            'key': ''
        }
    }
}

# Analytics
ENABLE_ANALYTICS = env('ENABLE_ANALYTICS')
POSTHOG_API_KEY = env('POSTHOG_API_KEY', default='')
POSTHOG_HOST = env('POSTHOG_HOST', default='https://app.posthog.com')

# Beta Flag
BETA_ACTIVE = env('BETA_ACTIVE')

# --- DEBUG LOGGER ---
# Isso vai aparecer nos logs do Railway e nos dirá a verdade
import sys
print("="*50, file=sys.stderr)
print(f"DEBUG PROD: ALLOWED_HOSTS (raw env) = {env('ALLOWED_HOSTS')}", file=sys.stderr)
print(f"DEBUG PROD: CSRF_TRUSTED_ORIGINS (final) = {CSRF_TRUSTED_ORIGINS}", file=sys.stderr)
print(f"DEBUG PROD: BETA_ACTIVE = {BETA_ACTIVE}", file=sys.stderr)
print("="*50, file=sys.stderr)
