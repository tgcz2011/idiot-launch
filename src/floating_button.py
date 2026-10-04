#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""早读悬浮球。

只在早读/晚读时间段内出现，始终置顶，点击打开早晚读浏览器。
改进点（对照原实现）：
  * 透明色键画真正的圆形（原来背景和圆同色，看起来是个方块）；
  * 左键拖动可换位置并限制在屏幕内，右键弹菜单（可以隐藏/打开）；
  * 拖动距离很小才算"点击"，不会再出现"想拖动结果打开浏览器"。
"""
import ctypes
import os
import subprocess
import sys
import time

from src import morning_config

DATA_DIR = morning_config.DATA_DIR
MORNING_BROWSER_PID = os.path.join(DATA_DIR, "morning_browser.pid")


def resource_path(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, relative)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), relative)


def _parse_time(time_str) -> int:
    try:
        parts = str(time_str).split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return -1


def is_in_reading_period(config) -> bool:
    periods = (config or {}).get("periods") or {}
    if not periods:
        return False
    now = time.localtime()
    current = now.tm_hour * 60 + now.tm_min
    for key in ("morning", "evening"):
        seg = periods.get(key) or {}
        start = _parse_time(seg.get("start", ""))
        end = _parse_time(seg.get("end", ""))
        if start >= 0 and end >= 0 and start <= current <= end:
            return True
    return False


class FloatingButton:
    """早读悬浮球。"""

    SIZE = 56

    def __init__(self, root, on_click=None):
        import tkinter as tk

        self._tk = tk
        self.root = root
        self.on_click = on_click
        self.win = None
        self._visible = False
        self._icon = None
        self._canvas = None
        self._bg = "#2F6B4F"
        self._hover = "#3A8A65"
        self._key = "#FF00FE"  # 透明色键
        self._drag_dx = 0
        self._drag_dy = 0
        self._moved = 0

    # ---- 图标 ----
    def _load_icon(self):
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

    # ---- 窗口 ----
    def _create_window(self):
        size = self.SIZE
        self.win = self._tk.Toplevel(self.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=self._key)
        try:
            self.win.attributes("-transparentcolor", self._key)
        except Exception:
            pass  # 个别系统不支持色键，退化成方形也不算致命

        canvas = self._tk.Canvas(self.win, width=size, height=size,
                                 bg=self._key, highlightthickness=0)
        canvas.pack()
        canvas.create_oval(2, 2, size - 2, size - 2, fill=self._bg, outline="",
                           tags="ball")
        icon = self._load_icon()
        if icon:
            canvas.create_image(size // 2, size // 2, image=icon)
        canvas.create_text(size // 2, size - 9, text="早读", fill="#FFFFFF",
                           font=("Microsoft YaHei", 8), tags="label")

        sw = self.win.winfo_screenwidth()
        self.win.geometry(f"{size}x{size}+{sw - size - 24}+80")

        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_motion)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        canvas.bind("<Button-3>", self._show_menu)
        canvas.bind("<Enter>", lambda e: self._paint(self._hover))
        canvas.bind("<Leave>", lambda e: self._paint(self._bg))
        self._canvas = canvas

    def _paint(self, color: str):
        try:
            self._canvas.itemconfigure("ball", fill=color)
            self._canvas.configure(bg=color if color != self._bg else self._key)
        except Exception:
            pass

    # ---- 交互 ----
    def _on_press(self, event):
        self._drag_dx = event.x_root - self.win.winfo_x()
        self._drag_dy = event.y_root - self.win.winfo_y()
        self._moved = 0

    def _on_motion(self, event):
        x = event.x_root - self._drag_dx
        y = event.y_root - self._drag_dy
        self._moved += abs(event.x_root - (self.win.winfo_x() + self._drag_dx))
        # 限制在屏幕内，避免拖出去再也找不到
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = max(0, min(x, sw - self.SIZE))
        y = max(0, min(y, sh - self.SIZE))
        self.win.geometry(f"+{x}+{y}")

    def _on_release(self, event):
        # 位移很小才算点击（阈值 6px）
        if self._moved < 6 and self.on_click:
            self.on_click()

    def _show_menu(self, event):
        menu = self._tk.Menu(self.win, tearoff=0)
        menu.add_command(label="打开早晚读", command=self._click)
        menu.add_command(label="隐藏悬浮球（下次启动恢复）", command=self.hide)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _click(self):
        if self.on_click:
            self.on_click()

    # ---- 显示/隐藏 ----
    def show(self):
        if self._visible:
            return
        self._visible = True
        self._create_window()

    def hide(self):
        self._visible = False
        if self.win:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None

    def update_visibility(self):
        if is_in_reading_period(morning_config.load()):
            if not self._visible:
                self.show()
        elif self._visible:
            self.hide()


# ── 打开早晚读浏览器 ──────────────────────────────────
def _process_alive(pid: int) -> bool:
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
    except Exception:
        pass
    return False


def _focus_browser_window(pid: int) -> bool:
    """把已有早晚读窗口提到前台。"""
    user32 = ctypes.windll.user32
    found = []

    def _cb(hwnd, _):
        try:
            wpid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
            if wpid.value != pid:
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if "早晚读" in buf.value:
                found.append(hwnd)
                return False
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(
            ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(_cb),
            None)
        if found:
            user32.ShowWindowAsync(found[0], 9)  # SW_RESTORE
            user32.SetForegroundWindow(found[0])
            return True
    except Exception:
        pass
    return False


def open_morning_browser(config=None) -> bool:
    """打开早晚读浏览器（单开：已运行则激活）。

    不再把配置（含密码）拼到命令行：Windows 上任何进程都能看到别的进程
    命令行，等于把班级密码广播出去。子进程直接读 D 盘配置文件。
    """
    # 1. 已有实例 → 激活
    try:
        if os.path.isfile(MORNING_BROWSER_PID):
            with open(MORNING_BROWSER_PID, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            if pid and _process_alive(pid):
                if _focus_browser_window(pid):
                    return True
                # 进程在但没有窗口（还在启动），等一会儿再看
                for _ in range(10):
                    time.sleep(0.3)
                    if _focus_browser_window(pid):
                        return True
    except Exception:
        pass

    # 2. 启动新进程
    run_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "run.py")
    creationflags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
    try:
        if getattr(sys, "frozen", False):
            proc = subprocess.Popen([sys.executable, "--morning-browser"],
                                    creationflags=creationflags, close_fds=True)
        else:
            proc = subprocess.Popen([sys.executable, run_py, "--morning-browser"],
                                    creationflags=creationflags, close_fds=True)
    except Exception as e:
        try:
            from src.core import log_daemon

            log_daemon(f"启动早晚读浏览器失败: {type(e).__name__}: {e}")
        except Exception:
            pass
        return False

    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(MORNING_BROWSER_PID, "w", encoding="utf-8") as f:
            f.write(str(proc.pid))
    except Exception:
        pass
    return True
