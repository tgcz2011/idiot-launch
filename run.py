"""Idiot Launch 入口。

  （无参数）          被后端 exe 双击时给出提示，不做任何事
  --server            后端 HTTP API（Flutter 前端连接它）
  --daemon            仅后台更新守护进程
  --quit-daemon       通知 daemon 优雅退出
  --quit              通知后端整体退出（安装/卸载/更新前调用）
  --countdown-app     Countdown Desktop（壁纸/屏保/设置，已合并进本项目）
  --morning-browser   早晚读内嵌浏览器（独立进程）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _notify_and_exit() -> None:
    """双击后端 exe：告诉用户该点哪个图标，而不是静默消失。"""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            "这是傻瓜启动器的后台组件，不能单独使用。\n\n"
            "请双击桌面或 D 盘根目录的「傻瓜启动器」图标。",
            "傻瓜启动器", 0x00000040)  # MB_ICONINFORMATION
    except Exception:
        pass
    sys.exit(0)


def _quit_backend() -> int:
    """请求后端整体退出。优先 HTTP（能真正走完整清理），失败再发命名事件。"""
    import urllib.request

    port_file = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                             "idiot_launch_backend_port")
    ok = False
    try:
        with open(port_file, "r", encoding="utf-8") as f:
            port = f.read().strip()
        if port:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/quit", method="POST")
            urllib.request.urlopen(req, timeout=5)
            ok = True
    except Exception:
        ok = False

    # 兼容旧版/兜底：命名事件
    try:
        import ctypes

        evt = ctypes.windll.kernel32.OpenEventW(0x0002, False, "IdiotLaunch_Quit")
        if evt:
            ctypes.windll.kernel32.SetEvent(evt)
            ctypes.windll.kernel32.CloseHandle(evt)
    except Exception:
        pass
    return 0 if ok else 1


def main() -> None:
    argv = sys.argv[1:]

    if "--server" in argv:
        from src.core import setup_logging

        setup_logging("backend")
        from src.backend_server import main as backend_main

        backend_main()

    elif "--quit" in argv:
        sys.exit(_quit_backend())

    elif "--daemon" in argv:
        from src.core import daemon_run, setup_logging

        setup_logging("daemon")
        sys.exit(daemon_run())

    elif "--quit-daemon" in argv:
        from src.core import signal_daemon_quit

        sys.exit(0 if signal_daemon_quit() else 1)

    elif "--countdown-app" in argv:
        from src.core import setup_logging

        setup_logging("countdown")
        rest = [a for a in argv if a != "--countdown-app"]
        if rest and rest[0] == "player":
            mode = rest[1] if len(rest) > 1 else "wallpaper"
            from countdown_app.player import run

            sys.exit(run(mode))
        sys.argv = [sys.argv[0], *rest]
        from countdown_app.main import run

        sys.exit(run())

    elif "--morning-browser" in argv:
        from src.core import setup_logging

        setup_logging("morning")
        from src.morning_browser import main as browser_main

        browser_main()

    else:
        _notify_and_exit()


if __name__ == "__main__":
    main()
