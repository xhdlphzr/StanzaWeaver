# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

# StanzaWeaver Docker 镜像
# 以 Web 服务方式运行（无 GUI）：python app.py 在容器中自动回退到 HTTP 服务。
#
# 构建:  docker build -t stanzaweaver .
#   （无法直连 Docker Hub 时，可用国内镜像加速器前缀：
#     docker build --build-arg BASE_IMAGE=docker.m.daocloud.io/library/python:3.14-slim -t stanzaweaver . ）
# 运行:  docker run --rm -p 5000:5000 \
#            -e STANZAWEAVER_HOST=0.0.0.0 \
#            -v stanzaweaver-data:/home/stanzaweaver/.stanza_weaver \
#            stanzaweaver
# 访问:  http://localhost:5000 （安全设计仅接受 localhost/127.0.0.1 的 Host 头）
#
# 依赖管理使用 uv：仅 COPY pyproject.toml + uv.lock 以利用 Docker 层缓存，
# dev 依赖（pytest/ruff/mypy/pyinstaller 等）不进镜像，保持镜像精简。

ARG BASE_IMAGE=python:3.14-slim
FROM ${BASE_IMAGE}

# 复制 uv（与官方 uv 镜像同版本可写死 tag 以便复用层缓存）
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    STANZAWEAVER_HOST=127.0.0.1 \
    STANZAWEAVER_PORT=5000 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 创建非 root 运行用户
RUN groupadd -r stanzaweaver \
    && useradd -r -g stanzaweaver -d /home/stanzaweaver -m stanzaweaver

# 先装依赖（利用层缓存；uv 在基础镜像内直接使用系统 Python 3.14）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# 复制源码（排除 .dockerignore 中的内容）
COPY --chown=stanzaweaver:stanzaweaver . .

# 预创建用户数据目录并授权：命名卷首次挂载 ~/.stanza_weaver 时
# Docker 会继承镜像中该目录的属主，否则卷归 root 导致非 root 用户无权限写
RUN mkdir -p /home/stanzaweaver/.stanza_weaver/logs \
    && chown -R stanzaweaver:stanzaweaver /home/stanzaweaver

# 健康检查：/api/import-status 返回 JSON 即存活
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/import-status', timeout=5)"

USER stanzaweaver

EXPOSE 5000

# 容器内无 GUI：直接启动 HTTP 服务（绕开 pywebview 窗口分支）
CMD ["python", "-u", "-c", "from app import start_server; start_server()"]
