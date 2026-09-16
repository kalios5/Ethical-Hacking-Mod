#define _GNU_SOURCE

#include <dlfcn.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

static const char *visible_file = "/watched/file.txt";
static const char *backing_file = "/watched/.file.txt.regular";

static int (*real_open_fn)(const char *pathname, int flags, ...) = NULL;
static int (*real_openat_fn)(int dirfd, const char *pathname, int flags, ...) = NULL;
static FILE *(*real_fopen_fn)(const char *pathname, const char *mode) = NULL;
static int (*real_stat_fn)(const char *pathname, struct stat *statbuf) = NULL;
static int (*real_lstat_fn)(const char *pathname, struct stat *statbuf) = NULL;

static void load_symbols(void)
{
    if (real_open_fn != NULL) {
        return;
    }
    real_open_fn = dlsym(RTLD_NEXT, "open");
    real_openat_fn = dlsym(RTLD_NEXT, "openat");
    real_fopen_fn = dlsym(RTLD_NEXT, "fopen");
    real_stat_fn = dlsym(RTLD_NEXT, "stat");
    real_lstat_fn = dlsym(RTLD_NEXT, "lstat");
}

static const char *redirect_path(const char *path)
{
    if (path != NULL && strcmp(path, visible_file) == 0) {
        return backing_file;
    }
    return path;
}

int open(const char *pathname, int flags, ...)
{
    mode_t mode = 0;
    va_list ap;

    load_symbols();

    if ((flags & O_CREAT) != 0) {
        va_start(ap, flags);
        mode = (mode_t)va_arg(ap, int);
        va_end(ap);
        return real_open_fn(redirect_path(pathname), flags, mode);
    }

    return real_open_fn(redirect_path(pathname), flags);
}

int openat(int dirfd, const char *pathname, int flags, ...)
{
    mode_t mode = 0;
    va_list ap;

    load_symbols();

    if ((flags & O_CREAT) != 0) {
        va_start(ap, flags);
        mode = (mode_t)va_arg(ap, int);
        va_end(ap);
        return real_openat_fn(dirfd, redirect_path(pathname), flags, mode);
    }

    return real_openat_fn(dirfd, redirect_path(pathname), flags);
}

FILE *fopen(const char *pathname, const char *mode)
{
    load_symbols();
    return real_fopen_fn(redirect_path(pathname), mode);
}

int stat(const char *pathname, struct stat *statbuf)
{
    load_symbols();
    return real_stat_fn(redirect_path(pathname), statbuf);
}

int lstat(const char *pathname, struct stat *statbuf)
{
    load_symbols();
    return real_lstat_fn(redirect_path(pathname), statbuf);
}
