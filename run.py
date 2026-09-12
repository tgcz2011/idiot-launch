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
        # 启动前检查 Idiot Launch 自我更新（仅 frozen 模式）。
        # 如果有待更新，此函数会生成 VBS 替换器并 sys.exit，不会返回。
        if getattr(sys, "frozen", False):
            from src.core import apply_launcher_update_if_pending
            apply_launcher_update_if_pending()
        from src.main import main
        main()
