# -*- coding: utf-8 -*-
"""主程序：托盘图标 + 设置界面 + 空闲检测 + 播放器子进程管理 + 单实例接管。

进程模型（参考 Lively）：
  主进程(本文件) ── 托盘/设置/空闲检测
    ├─ player wallpaper  （壁纸，常驻，嵌入桌面）
    └─ player screensaver（屏保，空闲触发，输入即退）

单实例：命名互斥量 CountdownDesktop_Single。若已有实例在运行，
新实例通过命名事件 CountdownDesktop_Quit 通知旧实例优雅退出
（超时则按 PID 文件强杀进程树），然后接管启动——后启动的实例
覆盖先启动的实例效果（GUI↔CLI 均可互相接管）。

--quit 命令：不启动 GUI，直接通知运行中的实例优雅退出（同上机制），
供其他软件/脚本调用；退出码 0=成功（或无实例），1=失败。

命令行参数（单次有效，不写入长期配置）：见 app/cli.py。
"""
import ctypes
import logging
import os
import subprocess
import sys
import time

log = logging.getLogger("main")

# 本次启动的命令行覆盖项（单次有效，不写入长期配置）；播放器子进程透传复用
_CLI_OVERRIDES = {}
_CLI_PROBLEMS = []

MUTEX_NAME = "CountdownDesktop_Single"
QUIT_EVENT_NAME = "CountdownDesktop_Quit"
SHOW_SETTINGS_EVENT_NAME = "CountdownDesktop_ShowSettings"
SWITCH_EXAM_EVENT_NAME = "CountdownDesktop_SwitchExam"
SWITCH_CMD_FILE = os.path.join(os.environ.get("TEMP", "."), "countdown_switch.json")
PID_FILE = "main.pid"  # 位于 config_dir() 下

WAIT_OBJECT_0 = 0
EVENT_MODIFY_STATE = 0x0002


def _setup_logging() -> None:
    from . import config
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        filename=os.path.join(config.config_dir(), "main.log"),
        encoding="utf-8",
    )


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _module_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _asset_path(name: str) -> str:
    """定位打包资源（图标等）。合并到 IL 后资源在 countdown_app/assets/。"""
    # 优先找模块同目录的 assets/（开发态和 onedir 都适用）
    p = os.path.join(_module_dir(), "assets", name)
    if os.path.exists(p):
        return p
    # PyInstaller onefile 时的 _MEIPASS
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        p = os.path.join(meipass, "countdown_app", "assets", name)
        if os.path.exists(p):
            return p
    # 兜底：IL 安装目录下的 assets
    return os.path.join(_base_dir(), "assets", name)


def _spawn_cmd(mode: str) -> list:
    from . import cli
    # 合并到 IL 后，用同一个 Python 解释器启动播放器子进程
    base = [sys.executable, "-m", "countdown_app.player", mode]
    # 把本次启动的 CLI 覆盖透传给播放器，保证壁纸/屏保用同一覆盖配置
    return base + cli.serialize(_CLI_OVERRIDES)


def _pid_path() -> str:
    from . import config
    return os.path.join(config.config_dir(), PID_FILE)


# ---------------- Win32 命名事件（跨进程退出信号） ----------------
def _create_quit_event():
    """创建/打开命名退出事件（手动重置，初始无信号），返回句柄。"""
    h = ctypes.windll.kernel32.CreateEventW(None, True, False, QUIT_EVENT_NAME)
    if h:
        # 若打开的是已有事件，显式重置为无信号
        ctypes.windll.kernel32.ResetEvent(h)
    return h or None


def _open_quit_event():
    """打开已存在的命名退出事件，返回句柄或 None。"""
    h = ctypes.windll.kernel32.OpenEventW(EVENT_MODIFY_STATE, False, QUIT_EVENT_NAME)
    return h or None


def _set_event(h) -> None:
    ctypes.windll.kernel32.SetEvent(h)


def _event_signaled(h) -> bool:
    """非阻塞检查事件是否已触发。"""
    return ctypes.windll.kernel32.WaitForSingleObject(h, 0) == WAIT_OBJECT_0


def _close_handle(h) -> None:
    if h:
        ctypes.windll.kernel32.CloseHandle(h)


def quit_running_instance() -> int:
    """优雅退出已运行的实例（供 --quit 命令使用，不启动 GUI）。

    流程：检测是否有实例在运行 → 发命名退出事件 → 等待优雅退出（5s）
    → 超时则按 PID 文件强杀进程树（3s）→ 返回。

    返回 0 = 成功（或本就无实例运行），1 = 无法退出。
    """
    from . import win32
    # 1) 检测是否有实例在运行
    mutex = win32.create_single_instance_mutex(MUTEX_NAME)
    if mutex is not None:
        ctypes.windll.kernel32.CloseHandle(mutex)
        log.info("quit requested but no instance running")
        print("Countdown Desktop: 没有正在运行的实例。")
        return 0

    log.info("quit requested, signaling running instance to exit")
    print("Countdown Desktop: 正在通知运行中的实例退出...")

    # 2) 优雅：触发命名退出事件
    App._signal_old_to_quit()
    if App._wait_mutex(5.0):
        log.info("running instance exited gracefully")
        print("Countdown Desktop: 已优雅退出。")
        return 0

    # 3) 兜底：按 PID 文件强杀进程树
    log.warning("graceful quit timeout, force killing")
    print("Countdown Desktop: 优雅退出超时，强制结束进程...")
    App._force_kill_old()
    if App._wait_mutex(3.0):
        log.info("running instance force killed")
        print("Countdown Desktop: 已强制退出。")
        return 0

    log.error("failed to quit running instance")
    print("Countdown Desktop: 无法退出运行中的实例，请手动结束进程。")
    return 1


class App:
    def __init__(self):
        from PySide6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu,
                                       QMessageBox)
        from PySide6.QtGui import QIcon
        from PySide6.QtCore import QTimer, Qt
        from . import config, win32, cli

        win32.set_process_dpi_awareness()
        self.qapp = QApplication(sys.argv)
        self.qapp.setQuitOnLastWindowClosed(False)

        if "-h" in sys.argv or "--help" in sys.argv:
            QMessageBox.information(None, "Countdown Desktop", cli.USAGE)
            raise SystemExit(0)
        if _CLI_PROBLEMS:
            QMessageBox.warning(
                None, "Countdown Desktop",
                "以下命令行参数无法识别，已忽略：\n" + "\n".join(_CLI_PROBLEMS))

        # 单实例 + 接管：若已有实例在运行，通知其退出后接管
        self.quit_event = None
        self.quit_timer = None
        self.mutex = self._acquire_mutex_with_takeover()
        if self.mutex is None:
            raise SystemExit(0)
        self._write_pid()
        self._init_quit_event()
        self._init_show_settings_event()
        self._init_switch_exam_event()

        self.cfg = config.load()
        cli.apply(_CLI_OVERRIDES, self.cfg)   # CLI 覆盖只改内存，不落盘
        self.wallpaper_proc = None
        self.screensaver_proc = None
        self.settings_dialog = None

        icon_path = _asset_path("icon.ico")
        if not os.path.exists(icon_path):
            icon_path = ""
        tray_path = _asset_path("icon-tray.ico")
        if not os.path.exists(tray_path):
            tray_path = icon_path
        self.icon_colored = QIcon(icon_path) if icon_path else self.qapp.style().standardIcon(
            self.qapp.style().StandardPixmap.SP_ComputerIcon)
        # 深色任务栏用白色 glyph（icon-tray），浅色任务栏回退彩色主图标
        self.icon_tray = QIcon(tray_path) if tray_path else self.icon_colored

        self.tray = QSystemTrayIcon(self.icon_colored)
        self.tray.setToolTip("Countdown Desktop")
        self.menu = QMenu()
        self.act_settings = self.menu.addAction("设置", lambda: self.open_settings("general"))
        self.act_startup = self.menu.addAction(
            "开机自启", lambda: self.set_autostart(self.act_startup.isChecked()))
        self.act_startup.setCheckable(True)
        self.act_startup.setChecked(bool(self.cfg.get("run_at_startup")))
        self.menu.addSeparator()
        self.act_save = self.menu.addAction("立即启动屏保", self.start_screensaver)
        self.act_refresh = self.menu.addAction("刷新壁纸", self.refresh_wallpaper)
        self.menu.addSeparator()
        self.menu.addAction("退出", self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        # 托盘就绪后按系统主题定图标（深色任务栏用白 glyph）
        self._apply_tray_icon_for_theme()

        # 空闲检测
        self.timer = QTimer()
        self.timer.timeout.connect(self._idle_tick)
        self.timer.start(5000)

        # 监听系统主题切换（WM_SETTINGCHANGE "ImmersiveColorSet"），热切换托盘图标
        self._theme_filter = _ThemeChangeFilter(self)
        self.qapp.installNativeEventFilter(self._theme_filter)

        if self.cfg["wallpaper"]["enabled"]:
            self.start_wallpaper()
        # --settings：启动后自动弹出设置窗口（供外部启动器一键唤起）
        if _CLI_OVERRIDES.get("settings"):
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.open_settings("general"))

    # ---------------- 单实例接管 ----------------
    def _write_pid(self) -> None:
        try:
            with open(_pid_path(), "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
        except OSError:
            log.exception("write pid failed")

    def _remove_pid(self) -> None:
        try:
            os.remove(_pid_path())
        except OSError:
            pass

    def _init_quit_event(self) -> None:
        """创建退出事件并启动轮询定时器，接收新实例的退出信号。"""
        self.quit_event = _create_quit_event()
        if self.quit_event is None:
            log.warning("create quit event failed: %s", ctypes.get_last_error())
            return
        from PySide6.QtCore import QTimer
        self.quit_timer = QTimer()
        self.quit_timer.timeout.connect(self._check_quit_event)
        self.quit_timer.timeout.connect(self._check_show_settings_event)
        self.quit_timer.timeout.connect(self._check_switch_exam_event)
        self.quit_timer.start(250)
        log.info("quit event listening (%s)", QUIT_EVENT_NAME)

    def _check_quit_event(self) -> None:
        if self.quit_event is not None and _event_signaled(self.quit_event):
            log.info("quit event signaled by another instance, exiting")
            self.quit()

    def _init_show_settings_event(self) -> None:
        """创建设置弹出事件，复用 quit_timer 轮询。"""
        h = ctypes.windll.kernel32.CreateEventW(None, True, False, SHOW_SETTINGS_EVENT_NAME)
        if h:
            ctypes.windll.kernel32.ResetEvent(h)
            self.show_settings_event = h
            log.info("show-settings event listening (%s)", SHOW_SETTINGS_EVENT_NAME)
        else:
            self.show_settings_event = None
            log.warning("create show-settings event failed: %s", ctypes.get_last_error())

    def _check_show_settings_event(self) -> None:
        if self.show_settings_event is not None and _event_signaled(self.show_settings_event):
            ctypes.windll.kernel32.ResetEvent(self.show_settings_event)
            log.info("show-settings event signaled, opening settings")
            self.open_settings("general")

    def _init_switch_exam_event(self) -> None:
        """创建切换考试事件，复用 quit_timer 轮询。"""
        h = ctypes.windll.kernel32.CreateEventW(None, True, False, SWITCH_EXAM_EVENT_NAME)
        if h:
            ctypes.windll.kernel32.ResetEvent(h)
            self.switch_exam_event = h
            log.info("switch-exam event listening (%s)", SWITCH_EXAM_EVENT_NAME)
        else:
            self.switch_exam_event = None
            log.warning("create switch-exam event failed: %s", ctypes.get_last_error())

    def _check_switch_exam_event(self) -> None:
        if self.switch_exam_event is None or not _event_signaled(self.switch_exam_event):
            return
        ctypes.windll.kernel32.ResetEvent(self.switch_exam_event)
        import json as _json
        try:
            with open(SWITCH_CMD_FILE, "r", encoding="utf-8") as f:
                overrides = _json.load(f)
            log.info("switch-exam event signaled: %s", overrides)
            self.apply_overrides_and_restart(overrides)
        except Exception:
            log.exception("read switch cmd file failed")

    def apply_overrides_and_restart(self, overrides: dict) -> None:
        """应用 CLI 覆盖参数并重启壁纸/屏保进程（供已有实例切换考试类型）。"""
        global _CLI_OVERRIDES
        from . import cli
        # 合并到全局覆盖，确保 _spawn_cmd 透传给壁纸/屏保子进程的参数正确
        # （否则已有实例用 --settings 启动时，_CLI_OVERRIDES 里没有 exam，子进程会读本地配置）
        _CLI_OVERRIDES.update(overrides)
        cli.apply(overrides, self.cfg)
        # 壁纸：根据配置决定启动/停止/重启（即使之前没运行，启用了也要启动）
        wallpaper_enabled = self.cfg.get("wallpaper", {}).get("enabled", True)
        wallpaper_running = self.wallpaper_proc is not None and self.wallpaper_proc.poll() is None
        if wallpaper_enabled:
            if wallpaper_running:
                self.stop_wallpaper()
            self.start_wallpaper()
        elif wallpaper_running:
            self.stop_wallpaper()
            self._restore_wallpaper()
        # 屏保：只有正在运行时才用新配置重启，不主动启动
        # （否则切换考试类型时系统已空闲很久，屏保会立即弹出打断用户）
        screensaver_running = (hasattr(self, "screensaver_proc") and self.screensaver_proc
                               and self.screensaver_proc.poll() is None)
        if screensaver_running:
            self.screensaver_proc.terminate()
            try:
                self.screensaver_proc.wait(timeout=3)
            except Exception:
                self.screensaver_proc.kill()
            self.screensaver_proc = None
            self.start_screensaver()
        log.info("overrides applied and players restarted")

    def _acquire_mutex_with_takeover(self):
        """获取单实例互斥量；若被占用，通知旧实例退出后接管。

        返回 mutex 句柄或 None（接管失败）。
        """
        from . import win32
        mutex = win32.create_single_instance_mutex(MUTEX_NAME)
        if mutex is not None:
            return mutex

        log.info("another instance running, attempting takeover")
        # 1) 优雅：触发命名退出事件，旧实例的轮询定时器会调用 quit()
        self._signal_old_to_quit()
        if self._wait_mutex(5.0):
            log.info("takeover succeeded (graceful)")
            return win32.create_single_instance_mutex(MUTEX_NAME)

        # 2) 兜底：按 PID 文件强杀旧进程树（含播放器子进程）
        log.warning("graceful takeover timeout, force killing old instance")
        self._force_kill_old()
        if self._wait_mutex(3.0):
            log.info("takeover succeeded (force)")
            return win32.create_single_instance_mutex(MUTEX_NAME)

        QMessageBox.warning(
            None, "Countdown Desktop",
            "无法接管已运行的实例，请手动退出后重试。")
        return None

    @staticmethod
    def _signal_old_to_quit() -> None:
        """打开旧实例的命名退出事件并触发。"""
        h = _open_quit_event()
        if h is None:
            log.warning("quit event not found, old instance may not be listening")
            return
        _set_event(h)
        _close_handle(h)
        log.info("quit event signaled to old instance")


    @staticmethod
    def _signal_show_settings() -> None:
        """通知已运行的实例弹出设置窗口（不关闭、不接管）。"""
        h = ctypes.windll.kernel32.OpenEventW(EVENT_MODIFY_STATE, False, SHOW_SETTINGS_EVENT_NAME)
        if not h:
            log.warning("show-settings event not found, running instance may be old version")
            return
        ctypes.windll.kernel32.SetEvent(h)
        ctypes.windll.kernel32.CloseHandle(h)
        log.info("show-settings event signaled to running instance")

    @staticmethod
    def _signal_switch_exam(overrides: dict) -> None:
        """已有实例运行时：写命令文件 + 发命名事件，通知其切换考试类型。"""
        import json as _json
        try:
            with open(SWITCH_CMD_FILE, "w", encoding="utf-8") as f:
                _json.dump(overrides, f)
        except Exception:
            log.exception("write switch cmd file failed")
        h = ctypes.windll.kernel32.OpenEventW(EVENT_MODIFY_STATE, False, SWITCH_EXAM_EVENT_NAME)
        if not h:
            log.warning("switch-exam event not found, running instance may be old version")
            return
        ctypes.windll.kernel32.SetEvent(h)
        ctypes.windll.kernel32.CloseHandle(h)
        log.info("switch-exam event signaled: %s", overrides)

    @staticmethod
    def _signal_switch_exam(overrides: dict) -> None:
        """已有实例运行时：写命令文件 + 发命名事件，通知其切换考试类型。"""
        import json as _json
        try:
            with open(SWITCH_CMD_FILE, "w", encoding="utf-8") as f:
                _json.dump(overrides, f)
        except Exception:
            log.exception("write switch cmd file failed")
        h = ctypes.windll.kernel32.OpenEventW(EVENT_MODIFY_STATE, False, SWITCH_EXAM_EVENT_NAME)
        if not h:
            log.warning("switch-exam event not found, running instance may be old version")
            return
        ctypes.windll.kernel32.SetEvent(h)
        ctypes.windll.kernel32.CloseHandle(h)
        log.info("switch-exam event signaled: %s", overrides)

    @staticmethod
    def _wait_mutex(timeout: float) -> bool:
        """轮询等待互斥量释放。"""
        from . import win32
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.2)
            m = win32.create_single_instance_mutex(MUTEX_NAME)
            if m is not None:
                # 拿到了就先释放，让调用方统一获取（避免句柄泄漏）
                ctypes.windll.kernel32.CloseHandle(m)
                return True
        return False

    @staticmethod
    def _force_kill_old() -> None:
        """按 PID 文件强杀旧主进程及其子进程树。强杀前先还原壁纸，避免 WorkerW 层残留。"""
        # 强杀前先还原壁纸（旧进程的壁纸窗口可能还附着在 WorkerW 上）
        try:
            from . import win32
            if win32.refresh_desktop_wallpaper():
                log.info("wallpaper restored before force kill")
        except Exception:
            log.exception("restore wallpaper before force kill failed")
        try:
            with open(_pid_path(), "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
        except (OSError, ValueError):
            log.warning("pid file missing/invalid, skip force kill")
            return
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
            log.info("force killed old instance pid=%s", pid)
        except (subprocess.TimeoutExpired, OSError):
            log.exception("force kill old pid=%s failed", pid)
        # 强杀后再还原一次兜底
        try:
            from . import win32
            win32.refresh_desktop_wallpaper()
        except Exception:
            pass

    # ---------------- 托盘图标 ----------------
    def _apply_tray_icon_for_theme(self) -> None:
        from . import win32
        light = False
        try:
            light = win32.system_uses_light_theme()
        except Exception:
            log.exception("read theme failed")
        self.tray.setIcon(self.icon_colored if light else self.icon_tray)
        self.tray.setToolTip("Countdown Desktop")

    def on_theme_changed(self) -> None:
        log.info("system theme changed, refresh tray icon")
        self._apply_tray_icon_for_theme()

    # ---------------- 壁纸 ----------------
    def start_wallpaper(self) -> None:
        cmd = _spawn_cmd("wallpaper")
        log.info("spawn wallpaper player: %s", cmd)
        self.wallpaper_proc = subprocess.Popen(
            cmd, creationflags=subprocess.CREATE_NO_WINDOW)

    def stop_wallpaper(self) -> None:
        if self.wallpaper_proc and self.wallpaper_proc.poll() is None:
            self.wallpaper_proc.terminate()
            try:
                self.wallpaper_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.wallpaper_proc.kill()
        self.wallpaper_proc = None

    def _restore_wallpaper(self) -> None:
        """退出/关壁纸后强制 explorer 重绘壁纸层（否则桌面白屏）。

        本软件从不修改系统壁纸值（只叠加窗口），因此直接把当前壁纸
        原样重设一次即可：不依赖快照（无跨进程配置同步问题），
        也不会回滚用户中途更换的壁纸。terminate() 强杀播放器时
        events.closed 不会触发，故由主进程负责重绘。
        """
        try:
            from . import win32
            if win32.refresh_desktop_wallpaper():
                log.info("desktop wallpaper refreshed")
        except Exception:
            log.exception("refresh wallpaper failed")

    def refresh_wallpaper(self) -> None:
        self.stop_wallpaper()
        from . import config, cli
        self.cfg = config.load()
        # 刷新后重新套用本次启动的 CLI 覆盖（单次有效）
        cli.apply(_CLI_OVERRIDES, self.cfg)
        if self.cfg["wallpaper"]["enabled"]:
            self.start_wallpaper()

    # ---------------- 屏保 ----------------
    def start_screensaver(self) -> None:
        if self.screensaver_proc and self.screensaver_proc.poll() is None:
            return
        if not self.cfg["screensaver"]["enabled"]:
            return
        cmd = _spawn_cmd("screensaver")
        log.info("spawn screensaver player")
        self.screensaver_proc = subprocess.Popen(
            cmd, creationflags=subprocess.CREATE_NO_WINDOW)

    def screensaver_active(self) -> bool:
        return self.screensaver_proc is not None and self.screensaver_proc.poll() is None

    def _idle_tick(self) -> None:
        from . import win32
        if not self.cfg["screensaver"]["enabled"]:
            return
        if self.screensaver_active():
            return
        try:
            timeout = float(self.cfg["screensaver"]["timeout"])
        except (TypeError, ValueError):
            timeout = 600.0
        if win32.last_input_idle_seconds() >= timeout:
            log.info("idle %.0fs >= %.0fs, start screensaver",
                     win32.last_input_idle_seconds(), timeout)
            self.start_screensaver()

    # ---------------- 托盘/设置 ----------------
    def _on_tray_activated(self, reason):
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            # 托盘单击多为查状态/改自启等常规操作，落到通用页
            self.open_settings("general")

    def set_autostart(self, enable: bool) -> None:
        """统一自启入口：注册表 + 配置 + 托盘勾选态同步（设置页与托盘共用）。"""
        from . import win32, config
        if enable == bool(self.cfg.get("run_at_startup")):
            self.act_startup.setChecked(enable)
            return
        exe = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(
            os.path.join(_base_dir(), "run.py"))
        try:
            win32.set_autostart(enable, exe)
        except OSError:
            log.exception("set_autostart failed")
            enable = bool(self.cfg.get("run_at_startup"))
        self.cfg["run_at_startup"] = enable
        config.save(self.cfg)
        self.act_startup.setChecked(enable)

    def open_settings(self, page: str = "wallpaper") -> None:
        from .settings import SettingsDialog
        if self.settings_dialog is None or not self.settings_dialog.isVisible():
            self.settings_dialog = SettingsDialog(self)
        if hasattr(self.settings_dialog, "goto_page"):
            self.settings_dialog.goto_page(page)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def restart_wallplayer_if_needed(self, changed: bool) -> None:
        if changed:
            was_running = self.wallpaper_proc is not None
            self.stop_wallpaper()
            if self.cfg["wallpaper"]["enabled"]:
                self.start_wallpaper()
            elif was_running:
                # 关闭壁纸（不退出软件）：立刻还原桌面壁纸
                self._restore_wallpaper()

    def quit(self) -> None:
        log.info("quit")
        if self.quit_timer is not None:
            self.quit_timer.stop()
        _close_handle(self.quit_event)
        _close_handle(self.show_settings_event)
        self.stop_wallpaper()
        self._restore_wallpaper()
        if self.screensaver_active():
            self.screensaver_proc.terminate()
        self.tray.hide()
        self._remove_pid()
        self.qapp.quit()

    def exec_(self) -> int:
        return self.qapp.exec()


def run() -> int:
    global _CLI_OVERRIDES, _CLI_PROBLEMS
    _setup_logging()

    # --quit：纯退出命令，不启动 GUI，直接通知运行中的实例优雅退出
    if "--quit" in sys.argv:
        return quit_running_instance()
    # --settings：若已有实例在运行，发事件通知它弹出设置后退出（不接管、不关闭倒计时）
    if "--settings" in sys.argv:
        from . import win32
        mutex = win32.create_single_instance_mutex(MUTEX_NAME)
        if mutex is None:
            App._signal_show_settings()
            print("Countdown Desktop: 已通知运行中的实例打开设置窗口")
            return 0
        ctypes.windll.kernel32.CloseHandle(mutex)

    from . import cli
    _CLI_OVERRIDES, _CLI_PROBLEMS = cli.parse_argv(sys.argv)
    log.info("=== main start, pid=%d, cli overrides=%s ===", os.getpid(),
             _CLI_OVERRIDES or "-")
    if _CLI_PROBLEMS:
        log.warning("unknown cli args ignored: %s", _CLI_PROBLEMS)
    # 已有实例运行且传入了覆盖参数（如 --exam）：通知已有实例切换后退出，不接管
    if _CLI_OVERRIDES:
        from . import win32
        _mutex = win32.create_single_instance_mutex(MUTEX_NAME)
        if _mutex is None:
            App._signal_switch_exam(_CLI_OVERRIDES)
            print("Countdown Desktop: 已通知运行中的实例切换配置")
            return 0
        ctypes.windll.kernel32.CloseHandle(_mutex)
    app = App()
    return app.exec_()


# 主题过滤器依赖：Qt 原生事件基类 + win32 消息结构（仅非 Windows 平台缺失，程序本身只跑在 Windows）
from PySide6.QtCore import QAbstractNativeEventFilter  # noqa: E402
import ctypes.wintypes  # noqa: E402


class _ThemeChangeFilter(QAbstractNativeEventFilter):
    """监听 WM_SETTINGCHANGE（系统主题切换），通知托盘换图标。"""

    WM_SETTINGCHANGE = 0x001A

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == self.WM_SETTINGCHANGE:
                buf = ctypes.c_wchar_p(msg.lParam) if msg.lParam else None
                if buf and buf.value == "ImmersiveColorSet":
                    try:
                        self.app_ref.on_theme_changed()
                    except Exception:
                        log.exception("on_theme_changed failed")
        return False
