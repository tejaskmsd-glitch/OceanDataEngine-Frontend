#!/bin/sh
cat <<JSON > /usr/share/nginx/html/config.js
window.__RUNTIME_CONFIG__ = {
  "API_BASE_URL": "${VITE_API_BASE_URL:-http://localhost:8000}",
  "WS_BASE_URL": "${VITE_WS_BASE_URL:-ws://localhost:8000}"
};
JSON
exec nginx -g "daemon off;"
