@echo off
rem ============================================================
rem  run.bat - 运行 StanzaWeaver 的 Docker 容器（Web 服务）
rem
rem  用法:
rem    scripts\run.bat                    前台运行
rem    scripts\run.bat -d -l              后台运行并跟随日志
rem    scripts\run.bat -p 8080            自定义宿主机端口
rem    scripts\run.bat --no-volume        不挂载持久化数据卷
rem
rem  选项:
rem    -i, --image <img>    镜像标签（默认 stanzaweaver:latest）
rem    -n, --name <name>    容器名（默认 stanzaweaver）
rem    -p, --port <port>    宿主机端口（默认 5000）
rem    -v, --volume <vol>   数据卷名（默认 stanzaweaver-data）
rem    -d, --detach         后台运行
rem    -l, --logs           跟随容器日志
rem        --no-volume      不挂载数据卷
rem    -h, --help           显示本帮助
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

rem 清理同名旧容器（避免端口/名称冲突）
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
    echo [run] 错误: docker run 失败
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
echo 用法:
echo   run.bat [-i image] [-n name] [-p port] [-v volume] [-d] [-l] [--no-volume] [-h]
echo.
echo   -i, --image ^<img^>    镜像标签（默认 stanzaweaver:latest）
echo   -n, --name ^<name^>    容器名（默认 stanzaweaver）
echo   -p, --port ^<port^>    宿主机端口（默认 5000）
echo   -v, --volume ^<vol^>   数据卷名（默认 stanzaweaver-data）
echo   -d, --detach         后台运行
echo   -l, --logs           跟随容器日志
echo       --no-volume      不挂载数据卷
echo   -h, --help           显示本帮助
exit /b 0
