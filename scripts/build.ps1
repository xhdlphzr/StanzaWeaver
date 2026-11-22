

# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

<#
.SYNOPSIS
Build the StanzaWeaver Docker image.

.DESCRIPTION
Runs docker build in the project root; switches to the project directory first.
If Docker Hub is unreachable, use -BaseImage to set a regional mirror prefix;
use -NoCache for a clean rebuild (avoiding BuildKit cache interference).

.EXAMPLE
.\scripts\docker-build.ps1

.EXAMPLE
.\scripts\docker-build.ps1 -BaseImage docker.m.daocloud.io/library/python:3.14-slim

.EXAMPLE
.\scripts\docker-build.ps1 -NoCache -Tag stanzaweaver:1.0.0
#>
[CmdletBinding()]
param(
    # Image tag (default stanzaweaver:latest)
    [string]$Tag = "stanzaweaver:latest",
    # Base image (default official python:3.14-slim; a regional mirror prefix
    # may be passed, e.g. docker.m.daocloud.io/library/python:3.14-slim)
    [string]$BaseImage = "python:3.14-slim",
    # Clean rebuild (skip BuildKit cache; slower but consistent with current files)
    [switch]$NoCache
)

$ErrorActionPreference = "Stop"

# Locate the project root (the script lives in <root>/scripts/)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Test-Path -LiteralPath "Dockerfile")) {
    throw "Dockerfile not found in the project root; make sure the script is under <project root>/scripts/"
}

$cacheNote = if ($NoCache) { ", no-cache mode" } else { "" }
Write-Host "[build] Building $Tag (base image: $BaseImage)$cacheNote" -ForegroundColor Cyan

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
    throw "docker build failed (exit code $LASTEXITCODE)"
}

Write-Host "[build] Done: $Tag" -ForegroundColor Green
