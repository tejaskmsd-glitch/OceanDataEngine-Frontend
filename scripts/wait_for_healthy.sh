#!/usr/bin/env bash
# Wait until a compose service reports a healthy status (or timeout).
# Usage: wait_for_healthy.sh <service> [timeout_seconds]
set -euo pipefail

SERVICE="${1:?service name required}"
TIMEOUT="${2:-120}"
COMPOSE="docker compose"

echo "Waiting up to ${TIMEOUT}s for '${SERVICE}' to become healthy..."
elapsed=0
while [ "${elapsed}" -lt "${TIMEOUT}" ]; do
    cid="$(${COMPOSE} ps -q "${SERVICE}" 2>/dev/null || true)"
    if [ -n "${cid}" ]; then
        status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${cid}" 2>/dev/null || echo unknown)"
        if [ "${status}" = "healthy" ] || [ "${status}" = "running" ]; then
            # Prefer healthy; accept running only if no healthcheck is defined.
            if [ "${status}" = "healthy" ]; then
                echo "'${SERVICE}' is healthy."
                exit 0
            fi
        fi
        echo "  ${SERVICE}: ${status} (${elapsed}s)"
    fi
    sleep 3
    elapsed=$((elapsed + 3))
done

echo "Timed out waiting for '${SERVICE}' to become healthy." >&2
exit 1
