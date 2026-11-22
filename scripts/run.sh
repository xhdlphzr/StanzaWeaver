# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

#!/usr/bin/env bash
#
# run.sh - run the StanzaWeaver Docker container (web service)
#
# Usage:
#   ./scripts/run.sh                    # run in the foreground
#   ./scripts/run.sh -d -l              # run detached and follow logs
#   ./scripts/run.sh -p 8080            # custom host port
#   ./scripts/run.sh --no-volume        # do not mount the data volume (data is not persisted)
#
# Options:
#   -i, --image <img>   image tag (default stanzaweaver:latest)
#   -n, --name <name>   container name (default stanzaweaver)
#   -p, --port <port>   host port mapping (default 5000)
#   -v, --volume <vol>  volume name (default stanzaweaver-data)
#   -d, --detach        run detached
#   -l, --logs          follow logs (Ctrl+C exits, container keeps running)
#       --no-volume     do not mount the data volume
#   -h, --help          show help
set -euo pipefail

IMAGE="stanzaweaver:latest"
NAME="stanzaweaver"
PORT=5000
VOLUME="stanzaweaver-data"
DETACH=""
LOGS=""
NO_VOLUME=""

usage() {
    sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--image)      IMAGE="$2"; shift 2 ;;
        -n|--name)       NAME="$2"; shift 2 ;;
        -p|--port)       PORT="$2"; shift 2 ;;
        -v|--volume)     VOLUME="$2"; shift 2 ;;
        -d|--detach)     DETACH="-d"; shift ;;
        -l|--logs)       LOGS="1"; shift ;;
        --no-volume)     NO_VOLUME="1"; shift ;;
        -h|--help)       usage ;;
        *) echo "Unknown argument: $1"; usage ;;
    esac
done

echo "[run] Starting container $NAME (image: $IMAGE, port: $PORT)"

if [[ -z "$NO_VOLUME" ]]; then
    docker volume create "$VOLUME" >/dev/null 2>&1 || true
fi

# Remove any old container with the same name (avoids port/name conflicts)
docker rm -f "$NAME" >/dev/null 2>&1 || true

RUN_ARGS=(run --name "$NAME" -p "${PORT}:5000" --restart unless-stopped)
if [[ -n "$NO_VOLUME" ]]; then
    RUN_ARGS+=(--rm)
else
    RUN_ARGS+=(-v "${VOLUME}:/home/stanzaweaver/.stanza_weaver")
fi
RUN_ARGS+=(-e STANZAWEAVER_HOST=0.0.0.0 -e STANZAWEAVER_PORT=5000)
if [[ -n "$DETACH" ]]; then
    RUN_ARGS+=("$DETACH")
fi
RUN_ARGS+=("$IMAGE")

docker "${RUN_ARGS[@]}"

echo "[run] Open: http://localhost:${PORT}"

if [[ -n "$LOGS" ]]; then
    echo "[run] Following logs (Ctrl+C to exit; the container keeps running)..."
    docker logs -f "$NAME"
fi
