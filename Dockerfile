# 1. IMAGEN BASE
FROM python:3.12-slim

# 2. VARIABLES DE ENTORNO
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# --- CORRECCIÓN 1: Definir una ruta segura para el venv ---
# Lo ponemos en /opt/venv para que el volumen de tu código no lo tape
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
COPY pyproject.toml uv.lock ./

# --- CORRECCIÓN 2: uv usará automáticamente la variable UV_PROJECT_ENVIRONMENT ---
RUN uv sync --frozen

# 7. COPIAR EL CÓDIGO (Esto se sobrescribirá con el volumen en dev, pero está bien para prod)
COPY . .

# 8. COMANDO
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]