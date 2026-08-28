# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

#!/usr/bin/env bash
#
# build.sh - 构建 StanzaWeaver Docker 镜像
#
# 用法:
#   ./scripts/build.sh                     # 默认 tag=stanzaweaver:latest
#   ./scripts/build.sh -b docker.m.daocloud.io/library/python:3.14-slim   # 国内加速器
#   ./scripts/build.sh -t stanzaweaver:1.0.0 -n                            # 指定 tag + 无缓存
#
# 选项:
#   -t, --tag <tag>        镜像标签 (默认 stanzaweaver:latest)
#   -b, --base-image <img> 基础镜像 (默认 python:3.14-slim)
#   -n, --no-cache         跳过 BuildKit 缓存彻底重建
#   -h, --help             显示帮助
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

TAG="stanzaweaver:latest"
BASE_IMAGE="python:3.14-slim"
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
        *) echo "未知参数: $1"; usage ;;
    esac
done

if [[ ! -f Dockerfile ]]; then
    echo "[build] 错误: 项目根目录未找到 Dockerfile" >&2
    exit 1
fi

echo "[build] 构建 $TAG (基础镜像: $BASE_IMAGE${NO_CACHE:+，无缓存})"

BUILD_ARGS=(-t "$TAG")
if [[ -n "$NO_CACHE" ]]; then
    BUILD_ARGS+=("$NO_CACHE")
fi
if [[ "$BASE_IMAGE" != "python:3.14-slim" ]]; then
    BUILD_ARGS+=(--build-arg "BASE_IMAGE=$BASE_IMAGE")
fi
BUILD_ARGS+=(.)

docker build "${BUILD_ARGS[@]}"

echo "[build] 完成: $TAG"
