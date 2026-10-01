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
    send_command,
    apply_launcher_update_now,
    log_daemon,
)
from src.morning_browser import (
    load_morning_config,
    save_morning_config,
    clear_temp_morning_config,
)

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
            self._send_json({
                "version": LAUNCHER_VERSION,
                "countdown_running": is_running(),
                "morning_logged_in": is_morning_logged_in(),
                "daemon": get_daemon_status(),
                "pending_update": state.get("pending_version"),
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
            self._send_json({
                "daemon": get_daemon_status(),
                "pending_version": state.get("pending_version"),
                "downloaded": state.get("downloaded_version"),
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
            grade = str(body.get("grade", ""))
            class_number = str(body.get("class_number", ""))
            password = str(body.get("password", ""))
            persistent = body.get("persistent", True)
            ok, periods, err = verify_morning_login(grade, class_number, password)
            if ok:
                save_morning_config({
                    "grade": grade,
                    "class_number": class_number,
                    "password": password,
                    "persistent": persistent,
                })
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
            open_morning_reading()
            self._send_json({"success": True})

        elif path == "/api/update/check":
            send_command("check_update")
            self._send_json({"success": True, "message": "检查更新已触发"})

        elif path == "/api/update/install":
            apply_launcher_update_now()
            self._send_json({"success": True, "message": "更新已触发"})

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


def main():
    """启动后端 HTTP 服务器。"""
    global _server
    os.makedirs(UPDATE_DIR, exist_ok=True)

    # 启动 daemon 后台线程（更新检查、快捷方式守护）
    threading.Thread(target=_daemon_loop, daemon=True).start()

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
