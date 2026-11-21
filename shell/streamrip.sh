#!/bin/sh
export STREAMRIP_CONFIG=${STREAMRIP_CONFIG:-/config/config.toml}
export STREAMRIP_URLLIST=${STREAMRIP_URLLIST:-/config/url.list}
cd /app
. /app/.venv/bin/activate
rip --config-path ${STREAMRIP_CONFIG} file ${STREAMRIP_URLLIST}
#sleep infinity
