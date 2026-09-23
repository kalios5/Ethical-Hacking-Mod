#!/usr/bin/env bash
MONITOR_BIN="/app/plugins/escape_script/minimal-monitor"
PRELOAD_LIB="/app/plugins/escape_script/libwatchedfile.so"
PIDFILE="/var/run/platform_monitor.pid"

is_running() {
    # Check pidfile exists and the PID in it is still alive
    if [[ -f "$PIDFILE" ]]; then
        local pid
        pid=$(cat "$PIDFILE")
        if kill -0 "$pid" 2>/dev/null; then
            return 0   # still running
        fi
    fi
    return 1   # not running
}

if is_running; then
    echo "[$(date)] Monitor already running — nothing to do"
    exit 0
fi

# Not running — start it
echo "[$(date)] Monitor not found — starting"
LD_PRELOAD="$PRELOAD_LIB" "$MONITOR_BIN" &
echo $! > "$PIDFILE"
echo "[$(date)] Monitor started — PID $(cat $PIDFILE)"