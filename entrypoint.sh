#!/bin/sh

# Si ocurre algún error, el script se detiene inmediatamente
set -e

echo "🚀 Iniciando Script de Entrada..."

# 1. Aplicar migraciones a la Base de Datos
echo "📦 Aplicando migraciones..."
python manage.py migrate --noinput

# 2. Recolectar Archivos Estáticos
# Esto mueve los CSS/JS a la carpeta 'staticfiles' para que WhiteNoise los sirva
echo "🎨 Recolectando archivos estáticos..."
python manage.py collectstatic --noinput

# 3. Decidir qué servidor arrancar según la variable DEBUG
# Comprobamos si DEBUG es True, true o 1
if [ "$DEBUG" = "True" ] || [ "$DEBUG" = "true" ] || [ "$DEBUG" = "1" ]; then
    echo "🛠️ MODO DESARROLLO: Arrancando runserver..."
    exec python manage.py runserver 0.0.0.0:8000
else
    echo "🌍 MODO PRODUCCIÓN: Arrancando Gunicorn..."
    # IMPORTANTE: Cambia 'core.wsgi' por el nombre de tu carpeta de proyecto
    # Si tu carpeta de settings se llama 'habemusbizi', pon 'habemusbizi.wsgi:application'
    exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
fi