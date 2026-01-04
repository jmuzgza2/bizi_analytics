#!/bin/sh

set -e

echo "🚀 Iniciando Script de Entrada..."

echo "📦 Aplicando migraciones..."
python manage.py migrate --noinput

echo "🎨 Recolectando archivos estáticos..."
python manage.py collectstatic --noinput

# --- NUEVO BLOQUE: Verificar si hay un comando específico ---
# Si Docker recibe un 'command' (como iniciar_monitor), lo ejecutamos aquí y terminamos.
if [ "$#" -gt 0 ]; then
    echo "🤖 Ejecutando comando personalizado: $@"
    exec "$@"
fi
# -----------------------------------------------------------

# Si no hay comando, arrancamos el servidor web por defecto
if [ "$DEBUG" = "True" ] || [ "$DEBUG" = "true" ] || [ "$DEBUG" = "1" ]; then
    echo "🛠️ MODO DESARROLLO: Arrancando runserver..."
    exec python manage.py runserver 0.0.0.0:8000
else
    echo "🌍 MODO PRODUCCIÓN: Arrancando Gunicorn..."
    # Asegúrate de que 'core.wsgi' es correcto para tu proyecto
    exec gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 3
fi