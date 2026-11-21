#!/bin/sh
set -eu

PUID=${PUID:-1029}
PGID=${PGID:-100}

case "$PUID" in
    *[!0-9]*)
        echo "PUID must contain only digits" >&2
        exit 1
        ;;
esac

case "$PGID" in
    *[!0-9]*)
        echo "PGID must contain only digits" >&2
        exit 1
        ;;
esac

export HOME=/config
exec su-exec "$PUID:$PGID" env HOME=/config "$@"
