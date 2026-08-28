@echo off
rem ============================================================
rem  run.bat - Run StanzaWeaver Docker container (Web service)
rem
rem  Usage:
rem    scripts\run.bat                    foreground
rem    scripts\run.bat -d -l              detached + follow logs
rem    scripts\run.bat -p 8080            custom host port
rem    scripts\run.bat --no-volume        no persistent volume
rem
rem  Options:
rem    -i, --image <img>    image tag (default stanzaweaver:latest)
rem    -n, --name <name>    container name (default stanzaweaver)
rem    -p, --port <port>    host port (default 5000)
rem    -v, --volume <vol>   volume name (default stanzaweaver-data)
rem    -d, --detach         run in background
rem    -l, --logs           follow container logs
rem        --no-volume      do not mount volume
rem    -h, --help           show this help
rem ============================================================
@setlocal enabledelayedexpansion

set "IMAGE=stanzaweaver:latest"
set "NAME=stanzaweaver"
set "PORT=5000"
set "VOLUME=stanzaweaver-data"
set "DETACH="
set "LOGS="
set "NO_VOLUME="

:parse
if "%~1"=="" goto :parsed
if /I "%~1"=="-i"      (set "IMAGE=%~2"    & shift & shift & goto :parse)
if /I "%~1"=="--image" (set "IMAGE=%~2"    & shift & shift & goto :parse)
if /I "%~1"=="-n"      (set "NAME=%~2"     & shift & shift & goto :parse)
if /I "%~1"=="--name"  (set "NAME=%~2"     & shift & shift & goto :parse)
if /I "%~1"=="-p"      (set "PORT=%~2"     & shift & shift & goto :parse)
if /I "%~1"=="--port"  (set "PORT=%~2"     & shift & shift & goto :parse)
if /I "%~1"=="-v"      (set "VOLUME=%~2"   & shift & shift & goto :parse)
if /I "%~1"=="--volume" (set "VOLUME=%~2"  & shift & shift & goto :parse)
if /I "%~1"=="-d"      (set "DETACH=-d"    & shift & goto :parse)
if /I "%~1"=="--detach" (set "DETACH=-d"   & shift & goto :parse)
if /I "%~1"=="-l"      (set "LOGS=1"       & shift & goto :parse)
if /I "%~1"=="--logs"  (set "LOGS=1"       & shift & goto :parse)
if /I "%~1"=="--no-volume" (set "NO_VOLUME=1" & shift & goto :parse)
if /I "%~1"=="-h"      goto :usage
if /I "%~1"=="--help"  goto :usage
echo Unknown argument: %~1
goto :usage

:parsed
echo [run] Starting container %NAME% ^(image: %IMAGE%, port: %PORT%^)

if not defined NO_VOLUME (
    docker volume create %VOLUME% >nul 2>&1
)

rem Remove old container with the same name
docker rm -f %NAME% >nul 2>&1

set "RUN_ARGS=run --name %NAME% -p %PORT%:5000 --restart unless-stopped"
if defined NO_VOLUME (
    set "RUN_ARGS=%RUN_ARGS% --rm"
) else (
    set "RUN_ARGS=%RUN_ARGS% -v %VOLUME%:/home/stanzaweaver/.stanza_weaver"
)
set "RUN_ARGS=%RUN_ARGS% -e STANZAWEAVER_HOST=0.0.0.0 -e STANZAWEAVER_PORT=5000"
if defined DETACH set "RUN_ARGS=%RUN_ARGS% -d"
set "RUN_ARGS=%RUN_ARGS% %IMAGE%"

docker %RUN_ARGS%
if errorlevel 1 (
    echo [run] ERROR: docker run failed
    exit /b 1
)

echo [run] Access: http://localhost:%PORT%

if defined LOGS (
    echo [run] Following logs ^(Ctrl+C exits, container keeps running^)...
    docker logs -f %NAME%
)
exit /b 0

:usage
echo.
echo Usage:
echo   run.bat [-i image] [-n name] [-p port] [-v volume] [-d] [-l] [--no-volume] [-h]
echo.
echo   -i, --image ^<img^>    image tag (default stanzaweaver:latest)
echo   -n, --name ^<name^>    container name (default stanzaweaver)
echo   -p, --port ^<port^>    host port (default 5000)
echo   -v, --volume ^<vol^>   volume name (default stanzaweaver-data)
echo   -d, --detach         run in background
echo   -l, --logs           follow container logs
echo       --no-volume      do not mount volume
echo   -h, --help           show this help
exit /b 0
