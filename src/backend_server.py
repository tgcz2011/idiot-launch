# -*- coding: utf-8 -*-
"""
Idiot Launch 后端 HTTP API 服务器。

前后端分离架构：
- Python 后端（本文件）：启动本地 HTTP 服务器（127.0.0.1:随机端口），
  暴露倒计时/早读/更新/状态等 API；后台线程运行 daemon 逻辑（更新检查、快捷方式守护）。
- Flutter 前端：读取端口文件连接后端，纯 GUI。

端口写入 D:\\IdiotLaunch\\data\\backend_port，前端启动时读取。
"""
import json
import os
import sys
import time
import threading
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# 确保 src 目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import (
    LAUNCHER_VERSION,
    UPDATE_DIR,
    launch_countdown,
    launch_custom,
    quit_countdown,
    is_running,
    launch_settings,
    open_morning_reading,
    verify_morning_login,
    is_morning_logged_in,
    get_morning_students,
    get_daemon_status,
    load_state,
    save_state,
    send_command,
    apply_launcher_update_now,
    log_daemon,
)
from src.morning_browser import (
    load_morning_config,
    save_morning_config,
    clear_temp_morning_config,
)

# CD 配置目录指向 D 盘（与 launch_countdown 的 _countdown_env 一致）
os.environ["COUNTDOWN_CONFIG_DIR"] = os.path.join(UPDATE_DIR, "countdown")
from countdown_app import config as cd_config
from countdown_app.version import VERSION as CD_VERSION

BACKEND_PORT_FILE = os.path.join(UPDATE_DIR, "backend_port")
BACKEND_PID_FILE = os.path.join(UPDATE_DIR, "backend_pid")


class ApiHandler(BaseHTTPRequestHandler):
    """HTTP API 处理器。"""

    def log_message(self, format, *args):
        # 静默，不打印到 stderr
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/version":
            self._send_json({"version": LAUNCHER_VERSION, "backend": "ok"})

        elif path == "/api/status":
            state = load_state()
            morning_cfg = load_morning_config()
            morning_class = ""
            if morning_cfg.get("grade") and morning_cfg.get("class_number"):
                morning_class = f"{morning_cfg['grade']}-{morning_cfg['class_number']}"
            daemon_status = get_daemon_status()
            pending = state.get("pending_version")
            downloaded = state.get("downloaded_version")
            self._send_json({
                "version": LAUNCHER_VERSION,
                "countdown_running": is_running(),
                "morning_logged_in": is_morning_logged_in(),
                "morning_class": morning_class,
                "daemon_running": daemon_status == "running",
                "daemon": daemon_status,
                "pending_update": pending,
                "has_update": bool(pending) and pending != LAUNCHER_VERSION,
                "downloading": state.get("downloading", False),
                "download_progress": state.get("download_progress", 0.0),
                "activate_requested": state.get("activate_requested", False),
            })

        elif path == "/api/morning/config":
            cfg = load_morning_config()
            self._send_json({
                "logged_in": is_morning_logged_in(),
                "grade": cfg.get("grade"),
                "class_number": cfg.get("class_number"),
                "persistent": cfg.get("persistent", True),
            })

        elif path == "/api/morning/students":
            students = get_morning_students()
            self._send_json({"success": True, "students": students})

        elif path == "/api/update/status":
            state = load_state()
            pending = state.get("pending_version")
            self._send_json({
                "daemon": get_daemon_status(),
                "daemon_running": get_daemon_status() == "running",
                "pending_version": pending,
                "downloaded_version": state.get("downloaded_version"),
                "has_update": bool(pending) and pending != LAUNCHER_VERSION,
                "downloading": state.get("downloading", False),
                "download_progress": state.get("download_progress", 0.0),
            })

        elif path == "/api/cd/config":
            # 获取 Countdown Desktop 配置
            cfg = cd_config.load()
            self._send_json({
                "success": True,
                "config": cfg,
                "cd_version": CD_VERSION,
                "exam_types": cd_config.EXAM_TYPES,
                "exam_labels": cd_config.EXAM_LABELS,
                "fit_modes": cd_config.FIT_MODES,
                "fit_labels": cd_config.FIT_LABELS,
                "default_url": cd_config.DEFAULT_URL,
            })

        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = self._read_body()

        if path == "/api/countdown/start":
            exam = body.get("exam", "zhongkao")
            ok = launch_countdown(exam)
            self._send_json({"success": ok, "exam": exam})

        elif path == "/api/countdown/stop":
            quit_countdown()
            self._send_json({"success": True})

        elif path == "/api/countdown/settings":
            launch_settings()
            self._send_json({"success": True})

        elif path == "/api/countdown/custom":
            launch_custom()
            self._send_json({"success": True})

        elif path == "/api/morning/login":
            # 支持 identity（如 "2024-1-1"）或 grade+class_number 两种格式
            identity = str(body.get("identity", "")).strip()
            if identity and "-" in identity:
                parts = identity.split("-")
                grade = parts[0]
                class_number = "-".join(parts[1:]) if len(parts) > 2 else parts[1]
            else:
                grade = str(body.get("grade", ""))
                class_number = str(body.get("class_number", ""))
            password = str(body.get("password", ""))
            persistent = body.get("persistent", True)
            ok, periods, err = verify_morning_login(grade, class_number, password)
            if ok:
                config_data = {
                    "grade": grade,
                    "class_number": class_number,
                    "password": password,
                    "persistent": persistent,
                }
                if periods:
                    config_data["periods"] = periods
                save_morning_config(config_data)
            self._send_json({
                "success": ok,
                "periods": periods,
                "error": err,
            })

        elif path == "/api/morning/logout":
            clear_temp_morning_config()
            # 同时删除持久配置
            try:
                persistent_path = os.path.join(UPDATE_DIR, "morning_config.json")
                if os.path.exists(persistent_path):
                    os.remove(persistent_path)
            except Exception:
                pass
            self._send_json({"success": True})

        elif path == "/api/morning/open":
            try:
                open_morning_reading()
                self._send_json({"success": True})
            except Exception as e:
                log_daemon(f"打开早读失败: {e}")
                self._send_json({"success": False, "error": str(e)})

        elif path == "/api/activate":
            # 非首实例请求激活首实例窗口
            state = load_state()
            state["activate_requested"] = True
            save_state(state)
            self._send_json({"success": True})

        elif path == "/api/activate/clear":
            state = load_state()
            state["activate_requested"] = False
            save_state(state)
            self._send_json({"success": True})

        elif path == "/api/update/check":
            send_command("check_updates")
            self._send_json({"success": True, "message": "检查更新已触发"})

        elif path == "/api/update/install":
            apply_launcher_update_now()
            self._send_json({"success": True, "message": "更新已触发"})

        elif path == "/api/cd/config":
            # 保存 Countdown Desktop 配置
            try:
                cfg = body.get("config", {})
                cd_config.save(cfg)
                # 如果壁纸配置变化，通过命名事件通知 CD 主进程重启播放器
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})

        elif path == "/api/cd/test-screensaver":
            # 立即测试屏保（启动 player screensaver 子进程）
            try:
                env = os.environ.copy()
                env["COUNTDOWN_CONFIG_DIR"] = os.path.join(UPDATE_DIR, "countdown")
                subprocess.Popen(
                    [sys.executable, "--countdown-app", "player", "screensaver"],
                    creationflags=0x00000008, close_fds=True, env=env,
                )
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})

        elif path == "/api/quit":
            # 后端退出（前端卸载时调用）
            self._send_json({"success": True})
            threading.Thread(target=_shutdown, daemon=True).start()

        else:
            self._send_json({"error": "not found"}, 404)


_server = None


def _shutdown():
    global _server
    time.sleep(0.5)
    if _server:
        _server.shutdown()


def _daemon_loop():
    """后台线程：运行更新检查 + 快捷方式守护（复用 core.daemon 中的逻辑）。"""
    from src.core import daemon_run
    try:
        daemon_run()
    except Exception as e:
        log_daemon(f"daemon loop 异常: {e}")


def _floating_button_loop():
    """早读悬浮球线程：创建 tkinter root + FloatingButton，定期检查时间段。"""
    try:
        import tkinter as tk
        from src.floating_button import FloatingButton, open_morning_browser
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        btn = FloatingButton(root, on_click=lambda: open_morning_browser())

        def check():
            try:
                btn.update_visibility()
            except Exception as e:
                log_daemon(f"悬浮球检查异常: {e}")
            root.after(30000, check)

        root.after(1000, check)  # 1秒后首次检查
        root.mainloop()
    except Exception as e:
        log_daemon(f"悬浮球线程异常: {e}")


def _tray_icon_loop():
    """系统托盘图标线程：右键菜单（打开窗口/退出），左键无操作。"""
    try:
        import pystray
        from PIL import Image
        # 加载图标
        icon_path = None
        for name in ("assets/icon.png", "assets/icon_source.png", "assets/floating_icon.png"):
            p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), name)
            if os.path.isfile(p):
                icon_path = p
                break
        image = Image.open(icon_path) if icon_path else Image.new("RGB", (64, 64), (47, 107, 79))

        def _open_window(icon, item):
            """激活 Flutter 前端窗口。"""
            try:
                import ctypes
                user32 = ctypes.windll.user32
                # 查找窗口标题包含"傻瓜启动器"的窗口
                def callback(hwnd, _):
                    title = ctypes.create_unicode_buffer(256)
                    user32.GetWindowTextW(hwnd, title, 256)
                    if "傻瓜启动器" in title.value and user32.IsWindowVisible(hwnd):
                        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                        user32.SetForegroundWindow(hwnd)
                    return True
                user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(callback), None)
            except Exception as e:
                log_daemon(f"托盘打开窗口异常: {e}")

        def _quit(icon, item):
            """完全退出：停止托盘+后端服务器。"""
            icon.stop()
            try:
                if _server:
                    _server.shutdown()
            except Exception:
                pass
            os._exit(0)

        menu = pystray.Menu(
            pystray.MenuItem("打开窗口", _open_window, default=False),
            pystray.MenuItem("退出", _quit),
        )
        icon = pystray.Icon("IdiotLaunch", image, "傻瓜启动器", menu)
        icon.run()
    except Exception as e:
        log_daemon(f"托盘图标线程异常: {e}")


def main():
    """启动后端 HTTP 服务器。"""
    global _server
    os.makedirs(UPDATE_DIR, exist_ok=True)

    # 启动 daemon 后台线程（更新检查、快捷方式守护）
    threading.Thread(target=_daemon_loop, daemon=True).start()

    # 启动早读悬浮球线程
    threading.Thread(target=_floating_button_loop, daemon=True).start()

    # 启动系统托盘图标线程
    threading.Thread(target=_tray_icon_loop, daemon=True).start()

    # 启动 HTTP 服务器（随机端口）
    _server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
    port = _server.server_address[1]

    # 写入端口和 PID 文件
    try:
        with open(BACKEND_PORT_FILE, "w") as f:
            f.write(str(port))
        with open(BACKEND_PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

    log_daemon(f"后端 HTTP API 启动，端口={port}, pid={os.getpid()}")
    print(f"Idiot Launch backend started on port {port}", flush=True)

    try:
        _server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        # 清理端口文件
        try:
            if os.path.exists(BACKEND_PORT_FILE):
                os.remove(BACKEND_PORT_FILE)
        except Exception:
            pass
        log_daemon("后端 HTTP API 已退出")


if __name__ == "__main__":
    main()
