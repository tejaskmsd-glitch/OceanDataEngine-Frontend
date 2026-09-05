#!/usr/bin/env bash
# Validate/lint the Dockerfiles. Uses hadolint if installed (or via docker),
# otherwise performs a minimal structural sanity check.
set -euo pipefail

DOCKERFILES=(
    docker/api.Dockerfile
    docker/worker.Dockerfile
    docker/airflow.Dockerfile
    docker/dashboard.Dockerfile
)

lint_one() {
    local f="$1"
    if command -v hadolint >/dev/null 2>&1; then
        echo "hadolint ${f}"
        hadolint --failure-threshold error "${f}"
    elif command -v docker >/dev/null 2>&1; then
        echo "hadolint (docker) ${f}"
        docker run --rm -i hadolint/hadolint hadolint --failure-threshold error - < "${f}"
    else
        echo "basic-check ${f}"
        grep -qE '^FROM ' "${f}" || { echo "  ERROR: no FROM in ${f}"; exit 1; }
    fi
}

for f in "${DOCKERFILES[@]}"; do
    [ -f "${f}" ] || { echo "missing: ${f}"; exit 1; }
    lint_one "${f}"
done
echo "Dockerfile validation complete."
