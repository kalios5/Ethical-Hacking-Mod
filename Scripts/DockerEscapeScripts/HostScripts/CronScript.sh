#!/usr/bin/env bash
# =============================================================================
# collect_logs.sh
# Host-side log collection for the SaaS platform.
# Pulls app.log from each running tenant container to a central host directory.
#
# Runs as root via cron — this is the CopyEscape trigger:
#   - docker cp runs with root authority on the host
#   - copies from a RUNNING container (required for the race condition)
#   - source path /logs/app.log is the disguised directory the malicious
#     plugin arms the trap in
#
# Cron entry (every 2 minutes, as root):
#   */2 * * * * /usr/local/bin/collect_logs.sh >> /var/log/collector.log 2>&1
# =============================================================================

set -euo pipefail

# ── configuration ─────────────────────────────────────────────────────────────

CONTAINER_NAME="${CONTAINER_NAME:-tenant_app}"
CONTAINER_LOG_FILE="/logs/app.log"
HOST_LOG_DIR="/var/platform/logs/${CONTAINER_NAME}"

# ── logging ───────────────────────────────────────────────────────────────────

TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

log() {
    echo "[${TIMESTAMP}] [collect_logs] $*"
}

# ── sanity checks ─────────────────────────────────────────────────────────────

if ! command -v docker &>/dev/null; then
    log "ERROR: docker not found on PATH"
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    log "WARNING: not running as root"
    log "         docker cp will carry only current user authority"
    log "         CopyEscape root-level write path will not be reachable"
fi

# ── check container is running ────────────────────────────────────────────────

if ! docker ps \
        --filter "name=${CONTAINER_NAME}" \
        --filter "status=running" \
        --format "{{.Names}}" \
    | grep -q "^${CONTAINER_NAME}$"; then
    log "SKIP: container '${CONTAINER_NAME}' is not running"
    exit 0
fi

log "Container '${CONTAINER_NAME}' is running — starting collection"

# ── prepare host destination ──────────────────────────────────────────────────

mkdir -p "${HOST_LOG_DIR}"
DEST_FILE="${HOST_LOG_DIR}/app.log"

log "Source : ${CONTAINER_NAME}:${CONTAINER_LOG_FILE}"
log "Dest   : ${DEST_FILE}"

# ── docker cp ─────────────────────────────────────────────────────────────────
# Vulnerable operation — CVE-2026-17106 (CopyEscape).
# Capture stderr so the exact error message is logged on failure.
# ─────────────────────────────────────────────────────────────────────────────

DOCKER_ERR="$(mktemp)"

if docker cp \
    "${CONTAINER_NAME}:${CONTAINER_LOG_FILE}" \
    "${DEST_FILE}" \
    2>"${DOCKER_ERR}"; then

    log "OK: collected ${CONTAINER_LOG_FILE} → ${DEST_FILE}"
    rm -f "${DOCKER_ERR}"

else
    EXIT_CODE=$?
    ERROR_MSG="$(cat "${DOCKER_ERR}")"
    rm -f "${DOCKER_ERR}"

    log "ERROR: docker cp failed (exit ${EXIT_CODE})"
    log "       command : docker cp ${CONTAINER_NAME}:${CONTAINER_LOG_FILE} ${DEST_FILE}"
    log "       message : ${ERROR_MSG}"
    exit 1
fi

log "Collection complete"