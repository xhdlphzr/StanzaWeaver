"""应用日志系统（logging + RotatingFileHandler）。

- 文件输出：~/.stanza_weaver/logs/stanza.log，RotatingFileHandler 轮转——
  单个日志文件达到 max_bytes 后自动轮转，保留 backup_count 个备份文件
  （stanza.log.1、stanza.log.2 ...）；超出数量的最旧备份被覆盖，
  即"达到定量后新增直接覆盖旧日志 + 保留定量备份"。
- 控制台输出：同步保留（桌面应用启动时可见）。
- 每个模块通过 get_logger(__name__) 获取命名 logger；日志目录可用
  环境变量 STANZAWEAVER_LOG_DIR 覆盖。
"""

import logging
import logging.handlers
import os
from pathlib import Path

DEFAULT_DIR = Path.home() / ".stanza_weaver" / "logs"
DEFAULT_FILENAME = "stanza.log"
DEFAULT_MAX_BYTES = 1 * 1024 * 1024  # 单个日志文件上限 1 MiB
DEFAULT_BACKUP_COUNT = 5  # 保留的轮转备份份数

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_configured = False


def get_logs_dir() -> Path:
    """返回日志目录（可用环境变量 STANZAWEAVER_LOG_DIR 覆盖）。

    Returns:
        日志目录路径。
    """
    env = os.environ.get("STANZAWEAVER_LOG_DIR")
    if env:
        return Path(env)
    return DEFAULT_DIR


def setup_logging(
    logs_dir: Path | None = None,
    level: int = logging.INFO,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> logging.Logger:
    """配置全局日志系统（幂等，仅首次调用生效）。

    同时挂载文件 RotatingFileHandler 与控制台 StreamHandler 到 root logger；
    各模块的命名 logger 通过传播输出到两者。

    Args:
        logs_dir: 日志目录（缺省用 get_logs_dir()）。
        level: 日志级别。
        max_bytes: 单个日志文件大小上限（达到即轮转）。
        backup_count: 保留的轮转备份份数（超出部分被覆盖）。

    Returns:
        应用的根 logger（名为 "stanzaweaver"）。
    """
    global _configured
    if _configured:
        return logging.getLogger("stanzaweaver")
    _configured = True

    logs_dir = logs_dir or get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / DEFAULT_FILENAME

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    app_logger = logging.getLogger("stanzaweaver")
    app_logger.debug(
        "日志系统已初始化: %s (max_bytes=%s, backup_count=%s)",
        log_file,
        max_bytes,
        backup_count,
    )
    return app_logger


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger（自动按模块名组织）。

    Args:
        name: logger 名，惯例传 __name__。

    Returns:
        logging.Logger 实例。
    """
    return logging.getLogger(name)
