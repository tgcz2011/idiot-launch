#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
早读悬浮按钮。
在早读/晚读时间段内显示在屏幕上方，始终置顶，点击打开早读浏览器窗口。
"""
import tkinter as tk
import time
import json
import os
import subprocess
import sys

from src.morning_browser import load_morning_config, PERSISTENT_CONFIG_PATH, TEMP_CONFIG_PATH


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
    """早读悬浮按钮。"""

    def __init__(self, root, on_click=None):
        self.root = root
        self.on_click = on_click
        self.win = None
        self._visible = False
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._check_interval = 30000  # 30秒检查一次时间段

    def _create_window(self):
        """创建悬浮按钮窗口。"""
        self.win = tk.Toplevel(self.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="#2F6B4F")

        # 按钮内容
        frame = tk.Frame(self.win, bg="#2F6B4F", padx=16, pady=10)
        frame.pack()

        tk.Label(frame, text="📖", font=("Segoe UI Emoji", 20),
                 bg="#2F6B4F", fg="white").pack()
        tk.Label(frame, text="早晚读", font=("Microsoft YaHei UI", 11, "bold"),
                 bg="#2F6B4F", fg="white").pack(pady=(2, 0))

        # 圆角效果（用 Canvas 画）
        self.win.update_idletasks()
        w = self.win.winfo_width()
        h = self.win.winfo_height()

        # 默认位置：屏幕右上角
        sw = self.win.winfo_screenwidth()
        x = sw - w - 20
        y = 80
        self.win.geometry(f"+{x}+{y}")

        # 点击事件
        frame.bind("<Button-1>", self._on_click)
        for child in frame.winfo_children():
            child.bind("<Button-1>", self._on_click)

        # 拖动
        frame.bind("<ButtonPress-3>", self._start_drag)  # 右键拖动
        frame.bind("<B3-Motion>", self._on_drag)
        for child in frame.winfo_children():
            child.bind("<ButtonPress-3>", self._start_drag)
            child.bind("<B3-Motion>", self._on_drag)

        # hover 效果
        frame.bind("<Enter>", lambda e: frame.configure(bg="#3a8a65"))
        frame.bind("<Leave>", lambda e: frame.configure(bg="#2F6B4F"))
        for child in frame.winfo_children():
            child.bind("<Enter>", lambda e: frame.configure(bg="#3a8a65"))
            child.bind("<Leave>", lambda e: frame.configure(bg="#2F6B4F"))

    def _on_click(self, event):
        """点击按钮。"""
        if self.on_click:
            self.on_click()

    def _start_drag(self, event):
        """开始拖动（右键）。"""
        self._drag_start_x = event.x_root - self.win.winfo_x()
        self._drag_start_y = event.y_root - self.win.y()

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
    """打开早读浏览器窗口（独立进程）。"""
    if config is None:
        config = load_morning_config()

    # 检查是否已配置班级
    if not config.get("grade") or not config.get("class_number"):
        return False

    # 启动独立进程
    run_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run.py")
    config_json = json.dumps(config, ensure_ascii=False)

    if getattr(sys, "frozen", False):
        exe = sys.executable
        creationflags = 0x00000008 | 0x08000000
        subprocess.Popen([exe, "--morning-browser", config_json],
                         creationflags=creationflags, close_fds=True)
    else:
        creationflags = 0x00000008 | 0x08000000
        subprocess.Popen([sys.executable, run_py, "--morning-browser", config_json],
                         creationflags=creationflags, close_fds=True)
    return True
