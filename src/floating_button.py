#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
早读悬浮按钮。
在早读/晚读时间段内显示在屏幕上方，始终置顶，点击打开早读浏览器窗口。
"""
import time
import json
import os
import subprocess
import sys

from src.morning_browser import load_morning_config, PERSISTENT_CONFIG_PATH, TEMP_CONFIG_PATH


def resource_path(relative: str) -> str:
    """定位资源文件（开发态 / PyInstaller onedir）。"""
    import sys as _sys
    base = getattr(_sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, relative)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), relative)


def is_in_reading_period(config):
    """判断当前是否在早读/晚读时间段内。"""
    periods = config.get("periods", {})
    if not periods:
        return False

    now = time.localtime()
    current_minutes = now.tm_hour * 60 + now.tm_min

    # 早读
    morning = periods.get("morning", {})
    if morning:
        start = _parse_time(morning.get("start", "06:20"))
        end = _parse_time(morning.get("end", "07:00"))
        if start <= current_minutes <= end:
            return True

    # 晚读
    evening = periods.get("evening", {})
    if evening:
        start = _parse_time(evening.get("start", "17:45"))
        end = _parse_time(evening.get("end", "18:15"))
        if start <= current_minutes <= end:
            return True

    return False


def _parse_time(time_str):
    """解析 HH:MM 格式为分钟数。"""
    try:
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 0


class FloatingButton:
    """早读悬浮按钮：仅显示应用图标（手指点击图案）。"""

    def __init__(self, root, on_click=None):
        import tkinter as tk  # 延迟导入，避免后端（无 tkinter）导入本模块时崩溃
        self._tk = tk
        self.root = root
        self.on_click = on_click
        self.win = None
        self._visible = False
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._check_interval = 30000  # 30秒检查一次时间段
        self._icon = None

    def _load_icon(self):
        """加载悬浮球图标 PNG（应用图标，透明底）。"""
        if self._icon is not None:
            return self._icon
        for name in ("floating_icon.png", "floating_icon_64.png", "icon_source.png"):
            path = resource_path(os.path.join("assets", name))
            if os.path.isfile(path):
                try:
                    self._icon = self._tk.PhotoImage(file=path)
                    return self._icon
                except Exception:
                    continue
        return None

    def _create_window(self):
        """创建悬浮按钮窗口：圆形图标，无文字。"""
        self.win = self._tk.Toplevel(self.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="#2F6B4F")

        # 圆形容器（Canvas 画圆 + 图标）
        size = 56
        canvas = self._tk.Canvas(self.win, width=size, height=size,
                           bg="#2F6B4F", highlightthickness=0)
        canvas.pack()
        canvas.create_oval(2, 2, size - 2, size - 2, fill="#2F6B4F", outline="")

        icon = self._load_icon()
        if icon:
            canvas.create_image(size // 2, size // 2, image=icon)

        # 默认位置：屏幕右上角
        sw = self.win.winfo_screenwidth()
        x = sw - size - 24
        y = 80
        self.win.geometry(f"{size}x{size}+{x}+{y}")

        # 点击事件
        canvas.bind("<Button-1>", self._on_click)

        # 右键拖动
        canvas.bind("<ButtonPress-3>", self._start_drag)
        canvas.bind("<B3-Motion>", self._on_drag)

        # hover 效果（圆变色）
        canvas.bind("<Enter>", lambda e: self._set_canvas_color(canvas, "#3a8a65"))
        canvas.bind("<Leave>", lambda e: self._set_canvas_color(canvas, "#2F6B4F"))
        self._canvas = canvas

    def _set_canvas_color(self, canvas, color):
        canvas.itemconfigure(1, fill=color)
        canvas.configure(bg=color)

    def _on_click(self, event):
        """点击按钮。"""
        if self.on_click:
            self.on_click()

    def _start_drag(self, event):
        """开始拖动（右键）。"""
        self._drag_start_x = event.x_root - self.win.winfo_x()
        self._drag_start_y = event.y_root - self.win.winfo_y()

    def _on_drag(self, event):
        """拖动中。"""
        x = event.x_root - self._drag_start_x
        y = event.y_root - self._drag_start_y
        self.win.geometry(f"+{x}+{y}")

    def show(self):
        """显示悬浮按钮。"""
        if self._visible:
            return
        self._visible = True
        self._create_window()
        self._schedule_check()

    def hide(self):
        """隐藏悬浮按钮。"""
        self._visible = False
        if self.win:
            self.win.destroy()
            self.win = None

    def _schedule_check(self):
        """定期检查时间段。"""
        if not self._visible:
            return
        config = load_morning_config()
        if not is_in_reading_period(config):
            self.hide()
            return
        self.root.after(self._check_interval, self._schedule_check)

    def update_visibility(self):
        """根据时间段更新可见性。"""
        config = load_morning_config()
        if is_in_reading_period(config):
            if not self._visible:
                self.show()
        else:
            if self._visible:
                self.hide()


def open_morning_browser(config=None):
    """打开早读浏览器窗口（单开：已运行则激活，未运行则启动）。
    已登录（配置含年级/班级/密码）则自动登录；未登录则直接打开网页首页。
    """
    if config is None:
        config = load_morning_config()

    # 单开检测：检查 PID 文件
    pid_file = r"D:\IdiotLaunch\data\morning_browser.pid"
    try:
        if os.path.isfile(pid_file):
            existing_pid = int(open(pid_file).read().strip())
            # 用 ctypes 检测进程是否存在
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, existing_pid)
            if handle:
                kernel32.CloseHandle(handle)
                # 进程存在，激活窗口到前台
                import ctypes
                user32 = ctypes.windll.user32
                # 枚举窗口找到早读浏览器窗口并激活
                EnumWindows = user32.EnumWindows
                EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                GetWindowTextLength = user32.GetWindowTextLengthW
                GetWindowText = user32.GetWindowTextW
                GetWindowThreadProcessId = user32.GetWindowThreadProcessId
                IsWindowVisible = user32.IsWindowVisible

                found_hwnd = []

                def callback(hwnd, lParam):
                    if not IsWindowVisible(hwnd):
                        return True
                    pid = ctypes.c_ulong()
                    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value == existing_pid:
                        length = GetWindowTextLength(hwnd)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            GetWindowText(hwnd, buf, length + 1)
                            if "早晚读" in buf.value or "morning" in buf.value.lower():
                                found_hwnd.append(hwnd)
                                return False
                    return True

                EnumWindows(EnumWindowsProc(callback), 0)
                if found_hwnd:
                    hwnd = found_hwnd[0]
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    user32.SetForegroundWindow(hwnd)
                    return True
    except Exception:
        pass

    # 启动独立进程
    run_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run.py")
    config_json = json.dumps(config, ensure_ascii=False)

    if getattr(sys, "frozen", False):
        exe = sys.executable
        creationflags = 0x00000008 | 0x08000000
        proc = subprocess.Popen([exe, "--morning-browser", config_json],
                                creationflags=creationflags, close_fds=True)
    else:
        creationflags = 0x00000008 | 0x08000000
        proc = subprocess.Popen([sys.executable, run_py, "--morning-browser", config_json],
                                creationflags=creationflags, close_fds=True)

    # 写入 PID 文件
    try:
        os.makedirs(os.path.dirname(pid_file), exist_ok=True)
        with open(pid_file, "w") as f:
            f.write(str(proc.pid))
    except Exception:
        pass
    return True
