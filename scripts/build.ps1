

# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

<#
.SYNOPSIS
构建 StanzaWeaver Docker 镜像。

.DESCRIPTION
在项目根目录执行 docker build，自动切换到项目目录。
无法直连 Docker Hub 时可用 -BaseImage 指定国内镜像加速器前缀；
如需彻底重建（排除 BuildKit 缓存干扰）用 -NoCache。

.EXAMPLE
.\scripts\docker-build.ps1

.EXAMPLE
.\scripts\docker-build.ps1 -BaseImage docker.m.daocloud.io/library/python:3.14-slim

.EXAMPLE
.\scripts\docker-build.ps1 -NoCache -Tag stanzaweaver:1.0.0
#>
[CmdletBinding()]
param(
    # 镜像标签（默认 stanzaweaver:latest）
    [string]$Tag = "stanzaweaver:latest",
    # 基础镜像（默认官方 python:3.14-slim；国内可传加速器前缀，如 docker.m.daocloud.io/library/python:3.14-slim）
    [string]$BaseImage = "python:3.14-slim",
    # 彻底重建（跳过 BuildKit 缓存，耗时较长但确保与当前文件一致）
    [switch]$NoCache
)

$ErrorActionPreference = "Stop"

# 定位项目根目录（脚本位于 <root>/scripts/）
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Test-Path -LiteralPath "Dockerfile")) {
    throw "在项目根目录未找到 Dockerfile，请确认脚本位于 <项目根>/scripts/ 下"
}

$cacheNote = if ($NoCache) { "，无缓存模式" } else { "" }
Write-Host "[build] 构建 $Tag (基础镜像: $BaseImage)$cacheNote" -ForegroundColor Cyan

$buildArgs = @("-t", $Tag)
if ($NoCache) {
    $buildArgs += "--no-cache"
}
if ($BaseImage -ne "python:3.14-slim") {
    $buildArgs += "--build-arg", "BASE_IMAGE=$BaseImage"
}
$buildArgs += "."

docker build @buildArgs
if ($LASTEXITCODE -ne 0) {
    throw "docker build 失败 (exit code $LASTEXITCODE)"
}

Write-Host "[build] 完成: $Tag" -ForegroundColor Green
