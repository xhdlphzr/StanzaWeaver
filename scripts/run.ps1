

# Copyright (c) 2026 xhdlphzr
# SPDX-License-Identifier: MIT

<#
.SYNOPSIS
Run the StanzaWeaver Docker container.

.DESCRIPTION
Starts the container as a web service: host port mapping and data volume persistence
(~/.stanza_weaver: config/lexicon/history/logs), STANZAWEAVER_HOST=0.0.0.0.
Without pywebview inside the container, app.py falls back to a plain HTTP service.

.EXAMPLE
.\scripts\docker-run.ps1                 # run in the foreground

.EXAMPLE
.\scripts\docker-run.ps1 -Detach         # run detached
.\scripts\docker-run.ps1 -Detach -Logs   # run detached and follow logs

.EXAMPLE
.\scripts\docker-run.ps1 -Port 8080 -NoVolume
#>
[CmdletBinding()]
param(
    # Image tag
    [string]$Image = "stanzaweaver:latest",
    # Container name
    [string]$Name = "stanzaweaver",
    # Host port mapping
    [int]$Port = 5000,
    # Volume name (persists config/lexicon/history/logs)
    [string]$Volume = "stanzaweaver-data",
    # Run detached
    [switch]$Detach,
    # Follow container logs after starting (use with -Detach)
    [switch]$Logs,
    # Do not mount the data volume (container data is not persisted)
    [switch]$NoVolume
)

$ErrorActionPreference = "Stop"

Write-Host "[run] Starting container $Name (image: $Image, port: $Port)" -ForegroundColor Cyan

# Ensure the data volume exists
if (-not $NoVolume) {
    docker volume create $Volume | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create data volume $Volume"
    }
}

# Remove any old container with the same name (avoids port/name conflicts)
docker rm -f $Name 2>$null | Out-Null

$runArgs = @("run", "--name", $Name, "-p", "${Port}:5000", "--restart", "unless-stopped")
if ($NoVolume) {
    $runArgs += "--rm"
} else {
    $runArgs += "-v", "${Volume}:/home/stanzaweaver/.stanza_weaver"
}
$runArgs += "-e", "STANZAWEAVER_HOST=0.0.0.0"
$runArgs += "-e", "STANZAWEAVER_PORT=5000"
if ($Detach) {
    $runArgs += "-d"
}
$runArgs += $Image

docker @runArgs
if ($LASTEXITCODE -ne 0) {
    throw "docker run failed (exit code $LASTEXITCODE)"
}

Write-Host "[run] Open: http://localhost:$Port" -ForegroundColor Green

if ($Logs) {
    Write-Host "[run] Following logs (Ctrl+C to exit; the container keeps running)..." -ForegroundColor DarkGray
    docker logs -f $Name
}
