# --- Stage 1: Build frontend ---
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# --- Stage 2: Backend ---
FROM python:3.12-slim AS backend
WORKDIR /app

# Install minimal system deps (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (layer cache -- only re-runs when pyproject.toml changes)
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir ".[search]" \
    && pip wheel --no-deps --wheel-dir /app/dist .

# Create non-root user and data directory
RUN groupadd --gid 1000 kira \
    && useradd --uid 1000 --gid kira --shell /bin/bash --create-home kira \
    && mkdir -p /app/.kira \
    && chown -R kira:kira /app

# Declare volume so Docker initializes it with correct ownership from the image
VOLUME /app/.kira

USER kira

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "kira.web.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

# --- Stage 3: Frontend (nginx) ---
FROM nginx:1.27-alpine AS frontend

# Remove default config
RUN rm -f /etc/nginx/conf.d/default.conf

COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO /dev/null http://localhost:80/ || exit 1
