"""Idiot Launch 入口脚本。
无参数 = GUI 模式；--server = 后端 HTTP API 服务器（Flutter 前端模式）；
--daemon = 后台更新守护进程（无窗口）；--quit-daemon = 通知 daemon 优雅退出；
--quit = 优雅退出后端服务器（安装/卸载时调用，不导入 GUI）；
--countdown-app = 运行 Countdown Desktop（已合并到本项目，共享 Python 运行时）；
--morning-browser = 运行早读内嵌浏览器（独立进程）。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    if "--server" in sys.argv:
        from src.backend_server import main as backend_main
        backend_main()
    elif "--quit" in sys.argv:
        # 优雅退出后端服务器（安装/卸载时调用，不导入任何 GUI 模块）
        import urllib.request
        import json
        port_file = r"D:\IdiotLaunch\data\backend_port"
        try:
            with open(port_file, "r") as f:
                port = f.read().strip()
            if port:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/api/quit", method="POST")
                urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass
        # 兼容旧版 daemon：发送命名事件
        try:
            import ctypes
            evt = ctypes.windll.kernel32.OpenEventW(0x1F0003, False, "IdiotLaunch_Quit")
            if evt:
                ctypes.windll.kernel32.SetEvent(evt)
                ctypes.windll.kernel32.CloseHandle(evt)
        except Exception:
            pass
        sys.exit(0)
    elif "--daemon" in sys.argv:
        from src.core import daemon_run
        sys.exit(daemon_run())
    elif "--quit-daemon" in sys.argv:
        from src.core import signal_daemon_quit
        ok = signal_daemon_quit()
        sys.exit(0 if ok else 1)
    elif "--countdown-app" in sys.argv:
        # 运行 Countdown Desktop（已合并），移除 --countdown-app 标记后传给 CD
        sys.argv = [a for a in sys.argv if a != "--countdown-app"]
        # 如果第一个参数是 player，则运行播放器子进程
        if len(sys.argv) > 1 and sys.argv[1] == "player":
            mode = sys.argv[2] if len(sys.argv) > 2 else "wallpaper"
            from countdown_app.player import run
            sys.exit(run(mode))
        from countdown_app.main import run
        sys.exit(run())
    elif "--morning-browser" in sys.argv:
        # 运行早读内嵌浏览器
        from src.morning_browser import main
        main()
    else:
        # 启动前检查 Idiot Launch 自我更新（仅 frozen 模式）。
        # 如果有待更新，此函数会生成 VBS 替换器并 sys.exit，不会返回。
        if getattr(sys, "frozen", False):
            from src.core import apply_launcher_update_if_pending
            if apply_launcher_update_if_pending():
                sys.exit(0)
        from src.main import main
        main()
