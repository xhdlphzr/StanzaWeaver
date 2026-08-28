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

ARG BASE_IMAGE=python:3.14-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STANZAWEAVER_HOST=127.0.0.1 \
    STANZAWEAVER_PORT=5000

WORKDIR /app

# 创建非 root 运行用户
RUN groupadd -r stanzaweaver \
    && useradd -r -g stanzaweaver -d /home/stanzaweaver -m stanzaweaver

# 先装依赖（利用层缓存；--no-cache-dir 避免 pip 缓存写入镜像层）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

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
