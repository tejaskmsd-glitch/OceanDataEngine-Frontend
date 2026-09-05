# =============================================================================
# dashboard.Dockerfile — builds the React + TypeScript + Vite ops dashboard and
# serves the static bundle via nginx. The dashboard is a read-only observability
# UI that consumes the same public API/events as external consumers.
# NOTE: dashboard SOURCE is owned by another workstream; this file only builds
# and serves it — it does not modify dashboard source.
# =============================================================================

# ---- build stage ----------------------------------------------------------
FROM node:22.12.0-bookworm-slim AS build
WORKDIR /app

# Install deps from the lockfile-equivalent (package.json is source-owned).
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm ci || npm install

COPY dashboard/ ./

# Vite reads VITE_* at build time; passed as build args from compose.
ARG VITE_API_BASE_URL
ARG VITE_WS_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_WS_BASE_URL=${VITE_WS_BASE_URL}
RUN npm run build

# ---- runtime stage ---------------------------------------------------------
FROM nginx:1.27.3-alpine AS runtime
RUN apk add --no-cache curl
COPY docker/dashboard/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD curl -fsS http://localhost/ || exit 1

COPY <<-"EOF" /docker-entrypoint.sh
#!/bin/sh
cat <<JSON > /usr/share/nginx/html/config.js
window.__RUNTIME_CONFIG__ = {
  "API_BASE_URL": "${VITE_API_BASE_URL:-http://localhost:8000}",
  "WS_BASE_URL": "${VITE_WS_BASE_URL:-ws://localhost:8000}"
};
JSON
exec nginx -g "daemon off;"
EOF
RUN chmod +x /docker-entrypoint.sh

CMD ["/docker-entrypoint.sh"]
