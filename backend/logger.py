"""
统一日志模块：同时输出到控制台和文件，支持自动轮转和全局异常捕获。

日志文件路径（按优先级）：
  1. %APPDATA%/DouyinLiveDanmaku/logs/  (推荐，始终可写)
  2. ./logs/                              (当前目录兜底)
"""
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler


def _get_log_dir() -> str:
    """获取可写的日志目录"""
    if sys.platform == 'win32':
        appdata = os.environ.get('APPDATA') or os.environ.get('LOCALAPPDATA')
        if appdata:
            d = os.path.join(appdata, 'DouyinLiveDanmaku', 'logs')
            try:
                os.makedirs(d, exist_ok=True)
                return d
            except Exception:
                pass
    # 兜底：当前目录
    d = os.path.join(os.getcwd(), 'logs')
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


_LOG_DIR = _get_log_dir()
_LOG_FILE = os.path.join(_LOG_DIR, 'app.log')


def _setup_logger(name: str = 'DouyinLive') -> logging.Logger:
    """创建并配置 logger 实例"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 防止重复添加 handler
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(threadName)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 文件 handler（轮转，最大 10MB，保留 5 份）
    try:
        fh = RotatingFileHandler(_LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5,
                                 encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception:
        pass

    # 控制台 handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


logger = _setup_logger()


def get_log_path() -> str:
    return _LOG_FILE


# ── 全局异常钩子 ──

_original_excepthook = sys.excepthook
_original_threading_excepthook = threading.excepthook


def _global_excepthook(exc_type, exc_value, exc_traceback):
    """捕获主线程中未处理的异常"""
    logger.critical("未捕获的异常", exc_info=(exc_type, exc_value, exc_traceback))
    if _original_excepthook:
        _original_excepthook(exc_type, exc_value, exc_traceback)


def _thread_excepthook(args):
    """捕获子线程中未处理的异常"""
    logger.critical("线程中未捕获的异常",
                    exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    if _original_threading_excepthook:
        _original_threading_excepthook(args)


def install_exception_hooks():
    """安装全局异常钩子（线程安全）"""
    sys.excepthook = _global_excepthook
    threading.excepthook = _thread_excepthook
    logger.info(f"全局异常钩子已安装，日志文件: {_LOG_FILE}")
