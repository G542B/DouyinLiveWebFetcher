#!/usr/bin/env python
# coding: utf-8
import os
import sys
import signal
import threading
import time
import webbrowser

# 打包环境下：确保内嵌 Python 的 site-packages 在 sys.path 中
# 嵌入式 Python 的 ._pth 文件存在时，PYTHONPATH 环境变量会被忽略，
# 需要手动将 site-packages 添加到 sys.path，否则 numpy/sentence-transformers 等包无法导入
def _ensure_site_packages():
    python_exe = sys.executable
    if python_exe and os.path.basename(python_exe).lower() == 'python.exe':
        python_dir = os.path.dirname(python_exe)
        site_pkg = os.path.join(python_dir, 'Lib', 'site-packages')
        if os.path.isdir(site_pkg) and site_pkg not in sys.path:
            sys.path.insert(0, site_pkg)
            print(f"[Run] 已添加 site-packages 到 sys.path: {site_pkg}")

_ensure_site_packages()

# 存储子进程的列表
_child_processes = []
_shutdown_event = threading.Event()


def signal_handler(signum, frame):
    """信号处理函数"""
    print(f"\n[Run] 接收到信号 {signum}，正在停止所有服务...")
    _shutdown_event.set()


def start_backend():
    """直接在当前进程启动后端服务"""
    import traceback
    print("启动后端服务...")
    print(f"[Run] Python 路径: {sys.executable}")
    print(f"[Run] 当前脚本: {__file__}")
    print(f"[Run] 工作目录: {os.getcwd()}")
    
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from backend.app import run_server
        run_server()
    except Exception as e:
        print(f"[Run] 启动后端服务失败: {e}")
        print(f"[Run] 错误堆栈:\n{traceback.format_exc()}")
        raise


def start_frontend():
    """启动前端开发服务"""
    print("启动前端服务...")
    import subprocess
    frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
    if sys.platform == "win32":
        cmd = ["cmd.exe", "/c", "cd /d " + frontend_dir + " && npm run dev"]
        proc = subprocess.Popen(cmd, shell=True)
    else:
        cmd = ["bash", "-c", "cd " + frontend_dir + " && npm run dev"]
        proc = subprocess.Popen(cmd, shell=True)
    _child_processes.append(proc)
    return proc


def build_frontend():
    """构建前端（生产模式）"""
    print("构建前端...")
    import subprocess
    frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
    if sys.platform == "win32":
        cmd = ["cmd.exe", "/c", "cd /d " + frontend_dir + " && npm install && npm run build"]
        subprocess.run(cmd, shell=True, check=True)
    else:
        cmd = ["bash", "-c", "cd " + frontend_dir + " && npm install && npm run build"]
        subprocess.run(cmd, shell=True, check=True)


def cleanup():
    """清理所有子进程"""
    print("[Run] 正在清理子进程...")
    for proc in _child_processes:
        try:
            if proc.poll() is None:  # 进程还在运行
                if sys.platform == "win32":
                    proc.terminate()
                    # Windows 下强制杀死
                    try:
                        import subprocess
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], 
                                      capture_output=True, timeout=2)
                    except:
                        pass
                else:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except:
                        proc.kill()
            print(f"[Run] 子进程 {proc.pid} 已停止")
        except Exception as e:
            print(f"[Run] 停止子进程失败: {e}")
    _child_processes.clear()
    print("[Run] 清理完成")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="抖音直播弹幕抓取器")
    parser.add_argument("--dev", action="store_true", help="开发模式（同时启动前后端）")
    parser.add_argument("--build", action="store_true", help="构建前端")
    parser.add_argument("--serve", action="store_true", help="启动后端服务（使用构建好的前端）")
    args = parser.parse_args()

    # 注册信号处理器
    if sys.platform != 'win32':
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    if args.build:
        build_frontend()
    elif args.serve:
        print("服务已启动，请访问 http://localhost:8000")
        print("按 Ctrl+C 停止服务\n")
        try:
            start_backend()
        except KeyboardInterrupt:
            print("\n正在停止...")
        finally:
            cleanup()
    elif args.dev:
        # 开发模式：后端在主线程，前端在子进程
        print("开发模式启动中...")
        
        # 启动前端
        frontend_proc = None
        try:
            frontend_proc = start_frontend()
            time.sleep(3)
            
            print("\n服务已启动!")
            print("前端地址: http://localhost:5173")
            print("后端地址: http://localhost:8000")
            print("\n按 Ctrl+C 停止服务\n")
            
            # 启动后端
            start_backend()
        except KeyboardInterrupt:
            print("\n正在停止...")
        finally:
            cleanup()
    else:
        print("使用方法:")
        print("  python run.py --dev    # 开发模式")
        print("  python run.py --build  # 构建前端")
        print("  python run.py --serve  # 启动生产服务")


if __name__ == "__main__":
    main()
