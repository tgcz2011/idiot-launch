# -*- coding: utf-8 -*-
"""
Idiot Launch 后端（HTTP API + 守护线程 + 托盘 + 悬浮球）。

前后端分离：
  * 本进程：127.0.0.1 随机端口 HTTP API、daemon 线程（更新/快捷方式/清理）、
    托盘图标、早晚读悬浮球（tkinter 线程）。
  * Flutter 前端：读 %TEMP%\\idiot_launch_backend_port 连接本进程。
  * 子进程：--countdown-app（壁纸/屏保）、--morning-browser（早晚读浏览器）。

进程退出原则：托盘"退出"必须让所有线程/子进程都结束，
所以最后用 os._exit()，而不是在线程里 sys.exit()（那只结束当前线程，
历史 bug：点了"退出"图标消失、进程还在）。
"""
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import (  # noqa: E402
    LAUNCHER_VERSION,
    UPDATE_DIR,
    apply_launcher_update_now,
    compare_versions,
    exit_for_update,
    get_daemon_status,
    get_morning_students,
    is_morning_logged_in,
    is_running,
    launch_countdown,
    launch_custom,
    launch_settings,
    load_settings,
    load_state,
    log_daemon,
    open_folder,
    open_morning_reading,
    pending_update_info,
    quit_countdown,
    save_settings,
    send_command,
    set_notifier,
    signal_daemon_quit,
    verify_morning_login,
    disk_free_gb,
)
from src import morning_config  # noqa: E402

# CD 配置目录指向 D 盘（与 launch_countdown 的环境变量保持一致）
os.environ["COUNTDOWN_CONFIG_DIR"] = os.path.join(UPDATE_DIR, "countdown")
from countdown_app import config as cd_config  # noqa: E402
from countdown_app.version import VERSION as CD_VERSION  # noqa: E402

PORT_FILE = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                         "idiot_launch_backend_port")
PID_FILE = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                        "idiot_launch_backend_pid")
MORNING_BROWSER_PID = os.path.join(UPDATE_DIR, "morning_browser.pid")

_server = None
_tray_icon = None
_quitting = False


# ── HTTP ──────────────────────────────────────────────
class ApiHandler(BaseHTTPRequestHandler):
    server_version = "IdiotLaunch/" + LAUNCHER_VERSION

    def log_message(self, fmt, *args):
        pass  # 不往 stderr 写（打包后 stderr 是 None）

    # ---- 工具 ----
    def _send_json(self, data, status=200):
        try:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError):
            body = b'{"error":"internal"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # 只服务本机前端；不再放开给任意网页（历史实现是 *，任何网页都能调 /api/quit）
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if length <= 0 or length > 1 << 20:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ---- GET ----
    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")

        if path == "/api/version":
            self._send_json({"version": LAUNCHER_VERSION, "backend": "ok",
                             "cd_version": CD_VERSION})

        elif path == "/api/status":
            state = load_state()
            cfg = morning_config.load()
            daemon = get_daemon_status() or {}
            dl = state.get("launcher_download") or {}
            info = pending_update_info()
            settings = load_settings()
            morning_class = ""
            if cfg.get("grade") and cfg.get("class_number"):
                morning_class = f"{cfg['grade']}-{cfg['class_number']}"
            self._send_json({
                "version": LAUNCHER_VERSION,
                "cd_version": CD_VERSION,
                "countdown_running": is_running(),
                "morning_logged_in": is_morning_logged_in(),
                "morning_class": morning_class,
                "daemon_running": bool(daemon),
                "daemon_activity": daemon.get("activity", ""),
                "daemon_detail": daemon.get("detail", ""),
                "daemon_progress": float(daemon.get("progress", 0) or 0),
                "pending_update": info["version"] if info else None,
                "pending_ready": bool(info),
                "has_update": bool(info),
                "downloading": dl.get("status") == "downloading",
                "download_progress": float(dl.get("progress", 0) or 0),
                "download_status": dl.get("status", ""),
                "release_notes": state.get("launcher_release_notes", ""),
                "last_check_at": state.get("launcher_last_check", 0),
                "activate_requested": bool(state.get("activate_requested", False)),
                "settings": settings,
                "data_dir": UPDATE_DIR,
                "disk_free_gb": disk_free_gb(),
                "installed": os.path.isfile(
                    os.path.join(r"D:\IdiotLaunch", "IdiotLaunch.exe")),
            })

        elif path == "/api/settings":
            self._send_json({"success": True, "settings": load_settings(),
                             "data_dir": UPDATE_DIR})

        elif path == "/api/morning/config":
            cfg = morning_config.load()
            self._send_json({
                "logged_in": is_morning_logged_in(),
                "grade": cfg.get("grade"),
                "class_number": cfg.get("class_number"),
                "persistent": cfg.get("persistent", True),
                "periods": cfg.get("periods") or {},
            })

        elif path == "/api/morning/students":
            try:
                students = get_morning_students()
                self._send_json({
                    "success": True,
                    "students": students,
                    "error": "" if students else "没有取到学生名单（可能是网络问题或尚未配置）",
                })
            except Exception as e:
                log_daemon(f"获取学生列表异常: {type(e).__name__}: {e}")
                self._send_json({"success": False, "students": [], "error": str(e)})

        elif path == "/api/update/status":
            state = load_state()
            daemon = get_daemon_status() or {}
            dl = state.get("launcher_download") or {}
            info = pending_update_info()
            self._send_json({
                "current_version": LAUNCHER_VERSION,
                "daemon": daemon,
                "daemon_activity": daemon.get("activity", ""),
                "daemon_detail": daemon.get("detail", ""),
                "pending_version": info["version"] if info else None,
                "pending_ready": bool(info),
                "has_update": bool(info),
                "downloading": dl.get("status") == "downloading",
                "download_progress": float(dl.get("progress", 0) or 0),
                "download_status": dl.get("status", ""),
                "release_notes": state.get("launcher_release_notes", ""),
                "last_check_at": state.get("launcher_last_check", 0),
            })

        elif path == "/api/cd/config":
            try:
                cfg = cd_config.load()
            except Exception as e:
                cfg = {}
                log_daemon(f"读取 CD 配置失败: {e}")
            self._send_json({
                "success": True,
                "config": cfg,
                "cd_version": CD_VERSION,
                "exam_types": cd_config.EXAM_TYPES,
                "exam_labels": cd_config.EXAM_LABELS,
                "fit_modes": cd_config.FIT_MODES,
                "fit_labels": cd_config.FIT_LABELS,
                "default_url": cd_config.DEFAULT_URL,
                "running": is_running(),
            })

        else:
            self._send_json({"error": "not found"}, 404)

    # ---- POST ----
    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        body = self._read_body()

        if path == "/api/countdown/start":
            exam = str(body.get("exam", "zhongkao"))
            ok = launch_countdown(exam)
            self._send_json({"success": ok, "exam": exam,
                             "error": "" if ok else "启动失败，请查看日志"})

        elif path == "/api/countdown/stop":
            ok = quit_countdown()
            self._send_json({"success": ok,
                             "error": "" if ok else "倒计时未能正常退出"})

        elif path == "/api/countdown/settings":
            self._send_json({"success": launch_settings()})

        elif path == "/api/countdown/custom":
            self._send_json({"success": launch_custom()})

        elif path == "/api/morning/login":
            grade = str(body.get("grade", "")).strip()
            class_number = str(body.get("class_number", "")).strip()
            password = str(body.get("password", ""))
            persistent = bool(body.get("persistent", True))
            if not grade or not class_number or not password:
                self._send_json({"success": False, "error": "请填写年级、班级号和密码"})
                return
            ok, periods, err = verify_morning_login(grade, class_number, password)
            if ok:
                data = {"grade": grade, "class_number": class_number,
                        "password": password}
                if periods:
                    data["periods"] = periods
                saved = morning_config.save(data, persistent=persistent)
                if not saved:
                    err = "账号有效，但配置保存失败（D 盘不可写？）"
                    ok = False
            self._send_json({"success": ok, "periods": periods, "error": err})

        elif path == "/api/morning/logout":
            morning_config.clear_all()
            try:
                from src.morning_api_client import clear_cache
                clear_cache()
            except Exception as e:
                log_daemon(f"清理早读缓存失败: {e}")
            self._send_json({"success": True})

        elif path == "/api/morning/open":
            self._send_json({"success": open_morning_reading()})

        elif path == "/api/activate":
            st = load_state()
            st["activate_requested"] = True
            from src.core import save_state
            save_state(st)
            self._send_json({"success": True})

        elif path == "/api/activate/clear":
            st = load_state()
            st["activate_requested"] = False
            from src.core import save_state
            save_state(st)
            self._send_json({"success": True})

        elif path == "/api/update/check":
            send_command("check_updates")
            self._send_json({"success": True, "message": "正在检查更新"})

        elif path == "/api/update/install":
            info = pending_update_info()
            if not info:
                self._send_json({
                    "success": False,
                    "message": "更新包还没有下载好，请先点「检查更新」",
                })
                return
            # 先回包，再启动安装程序并退出（安装包需要独占文件）
            self._send_json({"success": True, "version": info["version"],
                             "message": "正在启动更新程序"})

            def _apply():
                time.sleep(1.2)
                if apply_launcher_update_now():
                    exit_for_update()
                else:
                    log_daemon("一键更新启动失败")

            threading.Thread(target=_apply, daemon=True).start()

        elif path == "/api/settings":
            saved = save_settings(body)
            self._send_json({"success": True, "settings": saved})

        elif path == "/api/notify":
            title = str(body.get("title", "傻瓜启动器"))
            message = str(body.get("message", ""))
            once_per_boot = bool(body.get("once_per_boot", False))
            shown = True
            if once_per_boot:
                from src.core import boot_id, save_state

                st = load_state()
                current = boot_id()
                shown = int(st.get("tray_hint_boot", 0)) != current
                if shown:
                    st["tray_hint_boot"] = current
                    save_state(st)
            if shown:
                tray_notify(title, message)
            self._send_json({"success": True, "shown": shown})

        elif path == "/api/open-folder":
            target = str(body.get("path", UPDATE_DIR))
            if not os.path.isdir(target):
                target = UPDATE_DIR
            self._send_json({"success": open_folder(target)})

        elif path == "/api/cd/config":
            try:
                cfg = body.get("config") or {}
                cd_config.save(cfg)
                self._send_json({"success": True, "restart_required": is_running()})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})

        elif path == "/api/cd/test-screensaver":
            try:
                env = os.environ.copy()
                env["COUNTDOWN_CONFIG_DIR"] = os.path.join(UPDATE_DIR, "countdown")
                subprocess.Popen(
                    [sys.executable, "--countdown-app", "player", "screensaver"],
                    creationflags=0x00000008, close_fds=True, env=env)
                self._send_json({"success": True})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})

        elif path == "/api/quit":
            self._send_json({"success": True})
            threading.Thread(target=_shutdown_everything,
                             kwargs={"reason": "api"}, daemon=True).start()

        else:
            self._send_json({"error": "not found"}, 404)


# ── 进程/托盘管理 ─────────────────────────────────────
def tray_notify(title: str, message: str) -> bool:
    """通过托盘图标弹气泡（Windows 通知区）。失败返回 False。"""
    icon = _tray_icon
    if icon is None:
        return False
    try:
        icon.notify(message, title)
        return True
    except Exception as e:
        log_daemon(f"托盘通知失败: {type(e).__name__}: {e}")
        return False


def _find_main_window():
    """枚举所有顶层窗口，找 Flutter 主窗口（标题含"傻瓜启动器"）。

    注意：不能用 IsWindowVisible 过滤 —— 点 ✕ 之后窗口是隐藏状态，
    而"从托盘把窗口叫回来"正是它唯一的用途（历史 bug：隐藏后永远叫不回来）。
    """
    user32 = ctypes.windll.user32
    found = []

    def _cb(hwnd, _):
        try:
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if "傻瓜启动器" in buf.value or "idiot_launch" in buf.value.lower():
                found.append(hwnd)
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(
            ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(_cb),
            None)
    except Exception:
        pass
    return found[0] if found else 0


def _show_main_window() -> bool:
    hwnd = _find_main_window()
    if not hwnd:
        # 前端进程可能已经没了：直接把它拉起来
        exe = os.path.join(r"D:\IdiotLaunch", "IdiotLaunch.exe")
        if os.path.isfile(exe):
            try:
                subprocess.Popen([exe], creationflags=0x00000008, close_fds=True)
                return True
            except Exception as e:
                log_daemon(f"重新启动前端失败: {e}")
        return False
    try:
        user32 = ctypes.windll.user32
        # ShowWindowAsync：不阻塞托盘线程（ShowWindow 在跨线程时会等待）
        user32.ShowWindowAsync(hwnd, 5)   # SW_SHOW
        user32.ShowWindowAsync(hwnd, 9)   # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception as e:
        log_daemon(f"显示主窗口失败: {e}")
        return False


def _confirm_quit() -> bool:
    """退出前的确认框（也顺便告诉老师"会一起关掉什么"）。"""
    text = ("退出傻瓜启动器？\n\n"
            "将一起关闭：倒计时/秒表小窗口、后台更新守护、早晚读悬浮球、早晚读浏览器窗口，"
            "并恢复桌面壁纸。\n\n"
            "如果你的电脑装了冰点还原，下次开机后需要重新双击桌面图标。")
    try:
        MB_YESNO = 0x00000004
        MB_ICONQUESTION = 0x00000020
        MB_TOPMOST = 0x00040000
        r = ctypes.windll.user32.MessageBoxW(
            None, text, "傻瓜启动器", MB_YESNO | MB_ICONQUESTION | MB_TOPMOST)
        return r == 6  # IDYES
    except Exception:
        return True


def _kill_process(pid: int) -> bool:
    """结束指定进程。只在映像名确实是本程序时才动手（PID 可能被复用）。"""
    if not pid or pid == os.getpid():
        return False
    try:
        PROCESS_TERMINATE = 0x0001
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        h = kernel32.OpenProcess(
            PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_uint(1024)
            exe = ""
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                exe = buf.value.lower()
            if exe and not (exe.endswith("idiotlaunch.exe")
                            or exe.endswith("idiotlaunchbackend.exe")):
                log_daemon(f"PID {pid} 是 {exe}，不是本程序，跳过")
                return False
            kernel32.TerminateProcess(h, 0)
            log_daemon(f"已结束进程 pid={pid} ({os.path.basename(exe) or '未知'})")
            return True
        finally:
            kernel32.CloseHandle(h)
    except Exception as e:
        log_daemon(f"结束进程 {pid} 失败: {type(e).__name__}: {e}")
        return False


def _find_frontend_pids() -> set:
    """通过"标题含傻瓜启动器"的窗口反查前端进程号。

    窗口被隐藏（收进托盘）也能枚举到，所以关窗之后照样找得出来。
    """
    user32 = ctypes.windll.user32
    pids = set()

    def _cb(hwnd, _):
        try:
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if "傻瓜启动器" in buf.value:
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value:
                    pids.add(int(pid.value))
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(
            ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(_cb),
            None)
    except Exception:
        pass
    return pids


def _kill_child_by_pid_file(path: str) -> None:
    try:
        if not os.path.isfile(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        _kill_process(pid)
    except Exception:
        pass


def _kill_frontend() -> None:
    """结束 Flutter 前端进程。

    必须做：倒计时/秒表子窗口和主窗口都在这个进程里。托盘"退出"如果不杀它，
    那些窗口会一直留在屏幕上（用户反馈："退出应用后倒计时等窗口完全没有结束"）。
    """
    for pid in _find_frontend_pids():
        _kill_process(pid)
    # 兜底：主窗口可能已经不在了，但 instance.pid 还记着（会校验映像名，安全）
    _kill_child_by_pid_file(os.path.join(UPDATE_DIR, "instance.pid"))


def _shutdown_everything(reason: str = "tray", confirmed: bool = True) -> None:
    """让整个程序真正退出：前端 + 托盘 + 守护 + 悬浮球 + 浏览器子进程 + 壁纸。"""
    global _quitting
    if _quitting:
        return
    _quitting = True
    log_daemon(f"开始退出（来源: {reason}）")

    if reason == "api":
        # 让 /api/quit 的响应先写回 socket，再动手退出
        time.sleep(0.4)

    if reason == "tray" and confirmed and not _confirm_quit():
        _quitting = False
        return

    # 1. 先关前端：倒计时/秒表子窗口在它自己的进程里，杀了它窗口才会消失
    _kill_frontend()

    try:
        if _tray_icon is not None:
            _tray_icon.stop()
    except Exception:
        pass

    # 2. 通知 daemon 线程优雅退出（保存状态）
    try:
        signal_daemon_quit()
    except Exception:
        pass

    # 2. 关闭倒计时壁纸/屏保，恢复桌面
    try:
        if is_running():
            quit_countdown(timeout=5.0)
    except Exception:
        pass

    # 3. 关掉早晚读浏览器子进程（同一个 exe，不能按映像名杀）
    _kill_child_by_pid_file(MORNING_BROWSER_PID)

    # 4. 停 HTTP 服务
    try:
        if _server:
            _server.shutdown()
    except Exception:
        pass

    # 5. 尽力把遥测队列发完
    try:
        from src.telemetry import flush
        flush(timeout=1.5)
    except Exception:
        pass

    log_daemon("进程退出")
    # 关键：os._exit 结束的是整个进程（所有线程），sys.exit 只结束当前线程
    os._exit(0)


def _tray_icon_loop():
    """系统托盘：打开窗口 / 检查更新 / 退出。"""
    global _tray_icon
    try:
        import pystray
        from PIL import Image

        icon_path = None
        for name in ("assets/icon.png", "assets/floating_icon_64.png",
                     "assets/icon_source.png", "assets/floating_icon.png"):
            p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             name)
            if os.path.isfile(p):
                icon_path = p
                break
        image = Image.open(icon_path) if icon_path else Image.new("RGB", (64, 64), (47, 107, 79))

        def _open(icon, item):
            if not _show_main_window():
                tray_notify("傻瓜启动器", "没有找到主窗口，请双击桌面的「傻瓜启动器」图标。")
            else:
                st = load_state()
                st["activate_requested"] = True
                from src.core import save_state
                save_state(st)

        def _check(icon, item):
            send_command("check_updates")
            tray_notify("傻瓜启动器", "已开始检查更新，稍后会在界面上提示结果。")

        def _quit(icon, item):
            _shutdown_everything(reason="tray")

        menu = pystray.Menu(
            pystray.MenuItem("打开主界面", _open, default=True),
            pystray.MenuItem("检查更新", _check),
            pystray.MenuItem("退出（结束后台）", _quit),
        )
        _tray_icon = pystray.Icon("IdiotLaunch", image, "傻瓜启动器", menu)
        _tray_icon.run()
    except Exception as e:
        log_daemon(f"托盘图标线程异常: {type(e).__name__}: {e}")


def _floating_button_loop():
    """早晚读悬浮球（tkinter 线程）。"""
    try:
        import tkinter as tk

        from src.floating_button import FloatingButton, open_morning_browser

        root = tk.Tk()
        root.withdraw()
        btn = FloatingButton(root, on_click=lambda: open_morning_browser())

        def check():
            try:
                btn.update_visibility()
            except Exception as e:
                log_daemon(f"悬浮球检查异常: {type(e).__name__}: {e}")
            root.after(30000, check)

        root.after(1000, check)
        root.mainloop()
    except Exception as e:
        log_daemon(f"悬浮球线程异常: {type(e).__name__}: {e}")


def _daemon_loop():
    from src.core import daemon_run

    try:
        daemon_run()
    except Exception as e:
        log_daemon(f"daemon loop 异常: {type(e).__name__}: {e}")


# ── 启动 ──────────────────────────────────────────────
def _another_backend_alive() -> bool:
    """已有后端在跑就别再起一个（否则会同时跑两个 daemon、重复下载）。"""
    try:
        with open(PORT_FILE, "r", encoding="utf-8") as f:
            port = int(f.read().strip())
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/version")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _write_runtime_files(port: int) -> None:
    try:
        with open(PORT_FILE, "w", encoding="utf-8") as f:
            f.write(str(port))
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        log_daemon(f"写入端口文件失败: {e}")


def main():
    global _server
    from src.core import setup_logging

    setup_logging("backend")
    os.makedirs(UPDATE_DIR, exist_ok=True)

    if _another_backend_alive():
        log_daemon("检测到已有后端在运行，本次启动直接退出")
        return

    set_notifier(tray_notify)

    threading.Thread(target=_daemon_loop, daemon=True, name="daemon").start()
    threading.Thread(target=_floating_button_loop, daemon=True, name="ball").start()
    threading.Thread(target=_tray_icon_loop, daemon=True, name="tray").start()

    _server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
    _server.daemon_threads = True
    port = _server.server_address[1]
    _write_runtime_files(port)
    log_daemon(f"后端 HTTP API 启动，端口={port}, pid={os.getpid()}")

    try:
        _server.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log_daemon(f"HTTP 服务异常退出: {type(e).__name__}: {e}")
    finally:
        for path in (PORT_FILE, PID_FILE):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        log_daemon("后端 HTTP API 已退出")


if __name__ == "__main__":
    main()
