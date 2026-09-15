#!/bin/sh
unset LD_PRELOAD
exec /usr/local/bin/minimal-monitor "$@"
