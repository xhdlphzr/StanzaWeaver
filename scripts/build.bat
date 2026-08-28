@echo off
rem ============================================================
rem  build.bat - 构建 StanzaWeaver 的 Docker 镜像
rem
rem  用法:
rem    scripts\build.bat                        默认 tag=stanzaweaver:latest
rem    scripts\build.bat -b docker.m.daocloud.io/library/python:3.14-slim
rem    scripts\build.bat -t stanzaweaver:1.0.0 -n
rem
rem  选项:
rem    -t, --tag <tag>         镜像标签（默认 stanzaweaver:latest）
rem    -b, --base-image <img>  基础镜像（默认 python:3.14-slim）
rem    -n, --no-cache          不使用 BuildKit 缓存，完整重建
rem    -h, --help              显示本帮助
rem ============================================================
@setlocal enabledelayedexpansion

set "TAG=stanzaweaver:latest"
set "BASE_IMAGE=python:3.14-slim"
set "NO_CACHE="

:parse
if "%~1"=="" goto :parsed
if /I "%~1"=="-t"      (set "TAG=%~2"       & shift & shift & goto :parse)
if /I "%~1"=="--tag"   (set "TAG=%~2"       & shift & shift & goto :parse)
if /I "%~1"=="-b"      (set "BASE_IMAGE=%~2" & shift & shift & goto :parse)
if /I "%~1"=="--base-image" (set "BASE_IMAGE=%~2" & shift & shift & goto :parse)
if /I "%~1"=="-n"      (set "NO_CACHE=--no-cache" & shift & goto :parse)
if /I "%~1"=="--no-cache" (set "NO_CACHE=--no-cache" & shift & goto :parse)
if /I "%~1"=="-h"      goto :usage
if /I "%~1"=="--help"  goto :usage
echo Unknown argument: %~1
goto :usage

:parsed
cd /d "%~dp0\.."
if not exist Dockerfile (
    echo [build] 错误: 项目根目录未找到 Dockerfile
    exit /b 1
)

echo [build] Building %TAG% ^(base image: %BASE_IMAGE%^)%NO_CACHE%

set "BUILD_ARGS=-t %TAG%"
if defined NO_CACHE set "BUILD_ARGS=%BUILD_ARGS% %NO_CACHE%"
if /I not "%BASE_IMAGE%"=="python:3.14-slim" set "BUILD_ARGS=%BUILD_ARGS% --build-arg BASE_IMAGE=%BASE_IMAGE%"
set "BUILD_ARGS=%BUILD_ARGS% ."

docker build %BUILD_ARGS%
if errorlevel 1 (
        echo [build] 错误: docker build 失败
    exit /b 1
)

echo [build] Done: %TAG%
exit /b 0

:usage
echo.
echo 用法:
echo   build.bat [-t tag] [-b base-image] [-n] [-h]
echo.
echo   -t, --tag ^<tag^>         镜像标签（默认 stanzaweaver:latest）
echo   -b, --base-image ^<img^>  基础镜像（默认 python:3.14-slim）
echo   -n, --no-cache          不使用 BuildKit 缓存，完整重建
echo   -h, --help             显示本帮助
exit /b 0
