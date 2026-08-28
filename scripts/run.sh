# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

#!/usr/bin/env bash
#
# run.sh - 运行 StanzaWeaver Docker 容器（Web 服务）
#
# 用法:
#   ./scripts/run.sh                    # 前台运行
#   ./scripts/run.sh -d -l              # 后台运行并跟随日志
#   ./scripts/run.sh -p 8080            # 自定义宿主机端口
#   ./scripts/run.sh --no-volume        # 不挂载数据卷（数据不持久化）
#
# 选项:
#   -i, --image <img>   镜像标签 (默认 stanzaweaver:latest)
#   -n, --name <name>   容器名 (默认 stanzaweaver)
#   -p, --port <port>   宿主机映射端口 (默认 5000)
#   -v, --volume <vol>  数据卷名 (默认 stanzaweaver-data)
#   -d, --detach        后台运行
#   -l, --logs          运行后跟随日志 (Ctrl+C 退出，容器保持运行)
#       --no-volume     不挂载数据卷
#   -h, --help          显示帮助
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
        *) echo "未知参数: $1"; usage ;;
    esac
done

echo "[run] 启动容器 $NAME (镜像: $IMAGE, 端口: $PORT)"

if [[ -z "$NO_VOLUME" ]]; then
    docker volume create "$VOLUME" >/dev/null 2>&1 || true
fi

# 清理同名旧容器（避免端口/名称冲突）
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

echo "[run] 访问: http://localhost:${PORT}"

if [[ -n "$LOGS" ]]; then
    echo "[run] 跟随日志 (Ctrl+C 退出，容器保持运行)..."
    docker logs -f "$NAME"
fi
