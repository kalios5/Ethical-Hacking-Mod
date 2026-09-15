attack flow for docker escape
1) transfer statically linked minimal-monitor(monitor.c) and libwatchedfile.so(watched_preload.c)
2) export LD_PRELOAD=/path/to/libwatchedfile.so to load the libs
3) execute minimal-monitor
4) 