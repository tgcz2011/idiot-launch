"""Idiot Launch 入口脚本。
无参数 = GUI 模式；--daemon = 后台更新守护进程（无窗口）。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    if "--daemon" in sys.argv:
        from src.core import daemon_run
        sys.exit(daemon_run())
    else:
        from src.main import main
        main()
