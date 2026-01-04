# 1. IMAGEN BASE
FROM python:3.12-slim

# 2. VARIABLES DE ENTORNO
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Configuración de UV para poner el entorno virtual en una ruta segura
ENV UV_PROJECT_ENVIRONMENT="/opt/venv"
ENV PATH="/opt/venv/bin:$PATH"

# 3. DEPENDENCIAS DEL SISTEMA
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 4. INSTALAR UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 5. DIRECTORIO DE TRABAJO
WORKDIR /app

# 6. INSTALACIÓN DE LIBRERÍAS
# Copiamos solo los ficheros de dependencias primero (para aprovechar la caché de Docker)
COPY pyproject.toml uv.lock ./

# Instalamos las librerías (incluyendo gunicorn y whitenoise que añadiste)
RUN uv sync 

# 7. COPIAR EL CÓDIGO FUENTE
# IMPORTANTE: Copiamos el CONTENIDO de 'src' dentro de '/app'
# Así queda igual que tu volumen de desarrollo (./src:/app)
COPY src/ .

# 8. COPIAR Y CONFIGURAR EL ENTRYPOINT
# Copiamos el script que acabamos de crear a la raíz del sistema
COPY entrypoint.sh /entrypoint.sh
# Le damos permisos de ejecución (vital para Linux)
RUN chmod +x /entrypoint.sh

# 9. COMANDO DE ARRANQUE
# Usamos ENTRYPOINT para que el script tome el control total
ENTRYPOINT ["/entrypoint.sh"]