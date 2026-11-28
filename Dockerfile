# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

# StanzaWeaver Docker image
# Runs as a web service (no GUI): python app.py falls back to HTTP in a container.
#
# Build: docker build -t stanzaweaver .
#   (If Docker Hub is unreachable, prefix with a regional mirror:
#     docker build --build-arg BASE_IMAGE=docker.m.daocloud.io/library/python:3.15-slim -t stanzaweaver . )
# Run:   docker run --rm -p 5000:5000 \
#            -e STANZAWEAVER_HOST=0.0.0.0 \
#            -v stanzaweaver-data:/home/stanzaweaver/.stanza_weaver \
#            stanzaweaver
# Open:  http://localhost:5000
#        (the security design accepts only localhost/127.0.0.1 Host headers)
#
# Dependencies are managed with uv: only pyproject.toml + uv.lock are COPYed to use
# Docker layer caching; dev dependencies (pytest/ruff/mypy/pyinstaller, etc.) stay
# out of the image to keep it slim.

ARG BASE_IMAGE=python:3.15-slim
FROM ${BASE_IMAGE}

# Copy uv (same version as the official uv image; pin the tag to reuse the layer cache)
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    STANZAWEAVER_HOST=127.0.0.1 \
    STANZAWEAVER_PORT=5000 \
    STANZAWEAVER_TEMPLATES_DIR=/home/stanzaweaver/.stanza_weaver/templates \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Create a non-root runtime user
RUN groupadd -r stanzaweaver \
    && useradd -r -g stanzaweaver -d /home/stanzaweaver -m stanzaweaver

# Install dependencies first (uses the layer cache; uv uses the base image's
# system Python 3.15)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Copy the source (excludes entries in .dockerignore)
COPY --chown=stanzaweaver:stanzaweaver . .

# Pre-create the user data directory and chown it: on first mount of the named
# volume at ~/.stanza_weaver, Docker inherits the image directory's owner;
# otherwise the volume is root-owned and the non-root user cannot write.
RUN mkdir -p /home/stanzaweaver/.stanza_weaver/logs \
    && chown -R stanzaweaver:stanzaweaver /home/stanzaweaver

# Health check: alive if /api/import-status returns JSON
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/import-status', timeout=5)"

USER stanzaweaver

EXPOSE 5000

# No GUI inside the container: start the HTTP service directly
# (bypass the pywebview window branch)
CMD ["python", "-u", "-c", "from app import start_server; start_server()"]
