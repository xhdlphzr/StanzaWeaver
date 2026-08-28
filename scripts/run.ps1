<#
.SYNOPSIS
运行 StanzaWeaver Docker 容器。

.DESCRIPTION
以 Web 服务方式启动容器：端口映射到宿主机、数据卷持久化
（~/.stanza_weaver：配置/词库/历史/日志）、STANZAWEAVER_HOST=0.0.0.0。
容器内无 pywebview 时 app.py 自动回退到纯 HTTP 服务。

.EXAMPLE
.\scripts\docker-run.ps1                 # 前台运行

.EXAMPLE
.\scripts\docker-run.ps1 -Detach         # 后台运行
.\scripts\docker-run.ps1 -Detach -Logs   # 后台运行并跟随日志

.EXAMPLE
.\scripts\docker-run.ps1 -Port 8080 -NoVolume
#>
[CmdletBinding()]
param(
    # 镜像标签
    [string]$Image = "stanzaweaver:latest",
    # 容器名
    [string]$Name = "stanzaweaver",
    # 宿主机映射端口
    [int]$Port = 5000,
    # 数据卷名（持久化配置/词库/历史/日志）
    [string]$Volume = "stanzaweaver-data",
    # 后台运行
    [switch]$Detach,
    # 运行后跟随容器日志（配合 -Detach 使用）
    [switch]$Logs,
    # 不挂载数据卷（容器内数据不持久化）
    [switch]$NoVolume
)

$ErrorActionPreference = "Stop"

Write-Host "[run] 启动容器 $Name (镜像: $Image, 端口: $Port)" -ForegroundColor Cyan

# 确保数据卷存在
if (-not $NoVolume) {
    docker volume create $Volume | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "创建数据卷 $Volume 失败"
    }
}

# 清理同名旧容器（避免端口/名称冲突）
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
    throw "docker run 失败 (exit code $LASTEXITCODE)"
}

Write-Host "[run] 访问: http://localhost:$Port" -ForegroundColor Green

if ($Logs) {
    Write-Host "[run] 跟随日志 (Ctrl+C 退出，容器保持运行)..." -ForegroundColor DarkGray
    docker logs -f $Name
}
