# ============================================================
# MAIS_IA — Dockerfile del Backend (Hardened)
# Multi-stage build optimizado para producción.
#
# Seguridad aplicada:
# - Proceso corre como usuario no-root 'appuser' (UID 1001)
# - Sin privilegios escalados (no-new-privileges vía runtime flag)
# - Directorio de uploads con ownership exclusivo de appuser
# ============================================================

# --- Stage 1: Dependencias ---
FROM python:3.11-slim AS dependencies

WORKDIR /tmp

# Instalar dependencias del sistema necesarias para compilar asyncpg
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Stage 2: Runtime ---
FROM python:3.11-slim AS runtime

# Crear usuario no-root antes de cualquier operación con archivos
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/sh --create-home appuser

WORKDIR /app

# Solo las libs runtime necesarias (sin compiladores)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# Copiar dependencias pre-compiladas del stage anterior
COPY --from=dependencies /install /usr/local

# Copiar código fuente con ownership del usuario de la app
COPY --chown=appuser:appgroup . .

# Crear directorio de uploads con permisos exclusivos para appuser
RUN mkdir -p /app/uploads && chown -R appuser:appgroup /app/uploads

# Cambiar al usuario no-root
USER appuser

# Puerto de la API
EXPOSE 8000

# Health check del contenedor
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:8000/api/v1/health || exit 1

# Ejecutar con Uvicorn (workers configurables via ENV)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
