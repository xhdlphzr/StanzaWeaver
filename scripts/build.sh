# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

#!/usr/bin/env bash
#
# build.sh - build the StanzaWeaver Docker image
#
# Usage:
#   ./scripts/build.sh                     # default tag=stanzaweaver:latest
#   ./scripts/build.sh -b docker.m.daocloud.io/library/python:3.15-slim   # regional mirror
#   ./scripts/build.sh -t stanzaweaver:1.0.0 -n                            # custom tag + no cache
#
# Options:
#   -t, --tag <tag>        image tag (default stanzaweaver:latest)
#   -b, --base-image <img> base image (default python:3.15-slim)
#   -n, --no-cache         clean rebuild, skipping the BuildKit cache
#   -h, --help             show help
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

TAG="stanzaweaver:latest"
BASE_IMAGE="python:3.15-slim"
NO_CACHE=""

usage() {
    sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -t|--tag)           TAG="$2"; shift 2 ;;
        -b|--base-image)    BASE_IMAGE="$2"; shift 2 ;;
        -n|--no-cache)      NO_CACHE="--no-cache"; shift ;;
        -h|--help)          usage ;;
        *) echo "Unknown argument: $1"; usage ;;
    esac
done

if [[ ! -f Dockerfile ]]; then
    echo "[build] Error: Dockerfile not found in the project root" >&2
    exit 1
fi

echo "[build] Building $TAG (base image: $BASE_IMAGE${NO_CACHE:+, no-cache})"

BUILD_ARGS=(-t "$TAG")
if [[ -n "$NO_CACHE" ]]; then
    BUILD_ARGS+=("$NO_CACHE")
fi
if [[ "$BASE_IMAGE" != "python:3.15-slim" ]]; then
    BUILD_ARGS+=(--build-arg "BASE_IMAGE=$BASE_IMAGE")
fi
BUILD_ARGS+=(.)

docker build "${BUILD_ARGS[@]}"

echo "[build] Done: $TAG"
