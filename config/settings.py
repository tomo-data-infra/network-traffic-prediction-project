"""
Django settings for the Network Traffic Project.
Optimized for production-ready security, explicit JST handling, and environment isolation.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory Resolution
BASE_DIR = Path(__file__).resolve().parent.parent

# Load local environment configuration profile
load_dotenv(BASE_DIR / '.env')

# ---- SECURITY CONFIGURATIONS ----
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("[FATAL] SECRET_KEY environment variable is missing from the configuration profile.")

# Control environment flags via environment variables (defaults to False for safety)
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')

# Limit host parameters for deployment security
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')

# ---- APPLICATION INSTANCES ----
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-Party Packages
    'corsheaders',
    'rest_framework',
    # Local Feature Applications
    'calendar_api',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

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

WSGI_APPLICATION = 'config.wsgi.application'

# ---- DATABASE INFRASTRUCTURE CONFIGURATION ----
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': DB_NAME,
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
    }
}

# ---- SEMANTIC LAYER CONFIGURATION (CUBE CORE) ----
CUBE_API_SECRET = os.getenv('CUBE_API_SECRET')
CUBE_API_URL = os.getenv('CUBE_API_URL')

# ---- LOCAL LLM CONFIGURATION (OLLAMA) ----
OLLAMA_API_URL = os.getenv('OLLAMA_API_URL')

# ---- CASCADING INFRASTRUCTURE DEPLOYMENT TARGETS ----
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
REMOTE_GPU_USER = os.getenv('REMOTE_GPU_USER')
REMOTE_GPU_SERVER_IP = os.getenv('REMOTE_GPU_SERVER_IP')
LOCAL_FORWARD_PORT = os.getenv('LOCAL_FORWARD_PORT')
REMOTE_LLM_PORT = os.getenv('REMOTE_LLM_PORT')

# ---- CORE REGULATORY & REGIONALIZATIONS ----
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Tokyo'  # Bound strictly to JST for consistent network metrics
USE_I18N = True
USE_TZ = True  # Ensures Django stores timestamps in UTC internally, but tracks JST input

# ---- SECURITY AND ACCESS POLICIES ----
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATIC_URL = 'static/'

# Restrict Cross-Origin Requests to the local frontend instance
CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', '').split(',')

# System password validators
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
