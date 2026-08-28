@echo off
rem ============================================================
rem  build.bat - Build StanzaWeaver Docker image
rem
rem  Usage:
rem    scripts\build.bat                        default tag=stanzaweaver:latest
rem    scripts\build.bat -b docker.m.daocloud.io/library/python:3.14-slim
rem    scripts\build.bat -t stanzaweaver:1.0.0 -n
rem
rem  Options:
rem    -t, --tag <tag>         image tag (default stanzaweaver:latest)
rem    -b, --base-image <img>  base image (default python:3.14-slim)
rem    -n, --no-cache          full rebuild without BuildKit cache
rem    -h, --help              show this help
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
    echo [build] ERROR: Dockerfile not found in project root
    exit /b 1
)

echo [build] Building %TAG% ^(base image: %BASE_IMAGE%^)%NO_CACHE%

set "BUILD_ARGS=-t %TAG%"
if defined NO_CACHE set "BUILD_ARGS=%BUILD_ARGS% %NO_CACHE%"
if /I not "%BASE_IMAGE%"=="python:3.14-slim" set "BUILD_ARGS=%BUILD_ARGS% --build-arg BASE_IMAGE=%BASE_IMAGE%"
set "BUILD_ARGS=%BUILD_ARGS% ."

docker build %BUILD_ARGS%
if errorlevel 1 (
    echo [build] ERROR: docker build failed
    exit /b 1
)

echo [build] Done: %TAG%
exit /b 0

:usage
echo.
echo Usage:
echo   build.bat [-t tag] [-b base-image] [-n] [-h]
echo.
echo   -t, --tag ^<tag^>         image tag (default stanzaweaver:latest)
echo   -b, --base-image ^<img^>  base image (default python:3.14-slim)
echo   -n, --no-cache          full rebuild without BuildKit cache
echo   -h, --help              show this help
exit /b 0
