#!/usr/bin/env bash
# =============================================================================
# collect_logs.sh
# Host-side log collection job for the SaaS platform.
# Runs as root via cron. Copies logs from every running tenant container
# to a central host directory using docker cp.
#
# Cron entry (runs every 2 minutes as root):
#   */2 * * * * /usr/local/bin/collect_logs.sh >> /var/log/collector.log 2>&1
#
# This is the CopyEscape trigger:
#   - Runs as root         → docker cp carries root authority on the host
#   - Copies from running containers → the race condition in CVE-2026-17106
#                            can fire (stopped containers block the race)
#   - Fixed source path    → /var/log/app/ inside every tenant container,
#                            the directory the malicious plugin writes to
# =============================================================================

set -euo pipefail

# ---------------- configuration ----------------

# Path inside every container where tenant app logs live.
# This is the directory the malicious plugin plants the trap in.
CONTAINER_LOG_PATH="/log"

# Host-side destination root. Each container gets its own subdirectory.
HOST_LOG_ROOT="/logs"

# Only collect from containers whose names match this prefix,
# so the collector doesn't touch unrelated containers.
TENANT_PREFIX="app"

# How long (seconds) to wait between collection cycles when
# running in loop mode (--loop flag). Cron mode ignores this.
LOOP_INTERVAL=120

# -----------------------------------------------

TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"
SCRIPT_NAME="$(basename "$0")"

log() {
    echo "[$TIMESTAMP] [$SCRIPT_NAME] $*"
}

# ----------- sanity checks -----------

if ! command -v docker &>/dev/null; then
    log "ERROR: docker CLI not found on PATH"
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    log "WARNING: not running as root — docker cp will carry only current user authority"
    log "         Root code execution path (runc overwrite) will not be reachable"
fi

# ----------- core collection function -----------

collect_once() {
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"

    log "---- collection cycle starting at $timestamp ----"

    # Discover all running containers whose names match the tenant prefix.
    # docker ps -q gives only IDs; --filter name= matches a substring.
    mapfile -t CONTAINER_IDS < <(
        docker ps \
            --filter "name=${TENANT_PREFIX}" \
            --filter "status=running" \
            --format "{{.ID}}"
    )

    if [[ ${#CONTAINER_IDS[@]} -eq 0 ]]; then
        log "No running tenant containers found — nothing to collect"
        return 0
    fi

    log "Found ${#CONTAINER_IDS[@]} running tenant container(s)"

    local success=0
    local failed=0

    for CONTAINER_ID in "${CONTAINER_IDS[@]}"; do

        # Resolve a human-readable name for logging and directory naming.
        CONTAINER_NAME="$(docker inspect \
            --format '{{.Name}}' "$CONTAINER_ID" | sed 's|^/||')"

        # Destination on the host for this container's logs.
        DEST_DIR="${HOST_LOG_ROOT}/${CONTAINER_NAME}"
        mkdir -p "$DEST_DIR"

        log "Collecting from container: $CONTAINER_NAME ($CONTAINER_ID)"
        log "  Source : ${CONTAINER_ID}:${CONTAINER_LOG_PATH}"
        log "  Dest   : ${DEST_DIR}"

        # -------------------------------------------------------
        # This is the vulnerable operation — CVE-2026-17106.
        #
        # docker cp copies from a RUNNING container.
        # The container controls the filesystem at CONTAINER_LOG_PATH.
        # A malicious plugin can plant a race + symlink trap there so
        # that this extraction writes outside DEST_DIR.
        #
        # Runs with root authority because the script runs as root,
        # which is what enables the /usr/bin/runc overwrite path.
        # -------------------------------------------------------
        if docker cp \
            "${CONTAINER_ID}:${CONTAINER_LOG_PATH}/." \
            "${DEST_DIR}/"; then

            log "  [OK] Collected logs from $CONTAINER_NAME"
            ((success++)) || true
        else
            log "  [WARN] docker cp failed for $CONTAINER_NAME — container may have exited"
            ((failed++)) || true
        fi

    done

    log "Cycle complete — success: $success  failed: $failed"
    log "---- collection cycle finished ----"
}

# ----------- entry point -----------

# Support two modes:
#   (default / cron)  run one collection cycle and exit.
#                     Designed to be invoked by cron every N minutes.
#   --loop            run continuously with LOOP_INTERVAL sleep between
#                     cycles. Useful for foreground testing.

case "${1:-once}" in
    --loop)
        log "Starting in loop mode (interval: ${LOOP_INTERVAL}s)"
        while true; do
            collect_once
            log "Sleeping ${LOOP_INTERVAL}s until next cycle"
            sleep "$LOOP_INTERVAL"
        done
        ;;
    once|*)
        collect_once
        ;;
esac