#!/usr/bin/env bash
# =============================================================================
# collect_logs.sh
# Host-side log collection for the SaaS platform.
# Pulls app.log from each running tenant container to a central host directory.
#
# Runs as root via cron — this is the CopyEscape trigger:
#   - docker cp runs with root authority on the host
#   - copies from a RUNNING container (required for the race condition)
#   - source path /var/log/app/app.log is the directory the malicious
#     plugin writes its trap to
#
# Cron entry (every 2 minutes, as root):
#   */2 * * * * /usr/local/bin/collect_logs.sh >> /var/log/collector.log 2>&1
# =============================================================================

set -euo pipefail

# ── configuration ─────────────────────────────────────────────────────────────

# Name of the container to pull logs from.
# Set via environment or default to the tenant container name.
CONTAINER_NAME="${CONTAINER_NAME:-tenant_app}"

# Path inside the container where the app writes logs.
# This is the directory the malicious plugin plants the CopyEscape trap in.
CONTAINER_LOG_FILE="/var/log/app/app.log"

# Host-side directory where logs are collected.
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
# This is the vulnerable operation — CVE-2026-17106 (CopyEscape).
#
# The container controls the filesystem at CONTAINER_LOG_FILE.
# If the malicious plugin has planted the race + symlink trap in
# /var/log/app/, this docker cp call fires the exploit:
#
#   1. Docker daemon walks the container filesystem
#   2. Monitor inside the container detects the approach via inotify
#   3. Monitor performs the two rename operations at the right moment
#   4. Daemon produces a poisoned tar archive
#   5. docker cp CLI extracts it, follows the symlink
#   6. Writes outside DEST_FILE — overwrites /usr/bin/runc on the host
#
# Runs as root → write reaches system executables → RCE on host.
# ─────────────────────────────────────────────────────────────────────────────

if docker cp \
    "${CONTAINER_NAME}:${CONTAINER_LOG_FILE}" \
    "${DEST_FILE}"; then

    log "OK: collected ${CONTAINER_LOG_FILE} → ${DEST_FILE}"

else
    log "WARN: docker cp failed — container may have exited mid-collection"
    exit 1
fi

log "Collection complete"