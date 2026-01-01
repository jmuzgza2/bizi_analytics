from pathlib import Path
import os
import environ # <--- 1. Importante para leer el .env

# Inicializar environ
env = environ.Env()
# Leer el archivo .env que está en la raíz del proyecto (bizi_analytics/.env)
# La ruta es: settings.py -> config -> src -> bizi_analytics (.env)
BASE_DIR = Path(__file__).resolve().parent.parent
environ.Env.read_env(os.path.join(BASE_DIR.parent, '.env'))


# --- 2. USAR LA CLAVE DEL .ENV ---
SECRET_KEY = env('SECRET_KEY')

# --- 3. USAR EL MODO DEBUG DEL .ENV ---
DEBUG = env.bool('DEBUG', default=False)

ALLOWED_HOSTS = ["*"]


# --- 4. REGISTRAR TUS APPS (ESTO ES LO QUE FALLABA EN MAKEMIGRATIONS) ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # --- TUS APPS NUEVAS ---
    'rest_framework',  # La API
    'core',            # Los Modelos (Estacion, Captura...)
    'api',             # Las Vistas
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

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# --- 5. CONECTAR A DOCKER (ESTO ES LO QUE FALLARÍA EN MIGRATE) ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'bizi'),
        'USER': os.getenv('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'password'),
        
        # ESTA ES LA CLAVE:
        # Si no encuentra la variable, usa 'localhost' (para cuando corres sin Docker)
        # Pero dentro de Docker, leerá 'db' del archivo .env
        'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
        
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
    }
}


# ... (El resto del archivo hacia abajo: Password validators, Internationalization, Static files... DÉJALO IGUAL) ...
LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'Europe/Madrid'
USE_I18N = True
USE_TZ = True
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'