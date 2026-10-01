#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Material Three 风格的计时器对话框。
自定义标题栏（无原生窗口边框），支持拖动。
"""
import tkinter as tk
from tkinter import ttk
import time
import os
import sys

from src.core import resource_path

# Material Three 配色
M3_BACKGROUND = "#FEF7FF"
M3_SURFACE = "#FFFFFF"
M3_SURFACE_VARIANT = "#E7E0EC"
M3_PRIMARY = "#6750A4"
M3_ON_PRIMARY = "#FFFFFF"
M3_ON_SURFACE = "#1D1B20"
M3_ON_SURFACE_VARIANT = "#49454F"
M3_OUTLINE = "#79747E"
M3_ERROR = "#B3261E"
M3_TERTIARY = "#7D5260"


class _CustomTitleBar:
    """自定义标题栏：紫色背景 + 标题 + 全屏/× 按钮，支持拖动。"""

    def __init__(self, parent, title, on_close, on_fullscreen=None):
        self.parent = parent
        self.on_close = on_close
        self._drag_start_x = 0
        self._drag_start_y = 0

        self.bar = tk.Frame(parent, bg=M3_PRIMARY, height=44)
        self.bar.pack(fill="x", side="top")
        self.bar.pack_propagate(False)

        tk.Label(
            self.bar, text=title, font=("Microsoft YaHei UI", 14, "bold"),
            bg=M3_PRIMARY, fg=M3_ON_PRIMARY,
        ).pack(side="left", padx=16)

        close_btn = tk.Label(
            self.bar, text="×", font=("Arial", 22, "bold"),
            bg=M3_PRIMARY, fg=M3_ON_PRIMARY, cursor="hand2",
            padx=12, pady=0,
        )
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: on_close())
        close_btn.bind("<Enter>", lambda e: close_btn.configure(bg="#7C5DBD"))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(bg=M3_PRIMARY))

        if on_fullscreen:
            fs_btn = tk.Label(
                self.bar, text="⛶", font=("Arial", 16, "bold"),
                bg=M3_PRIMARY, fg=M3_ON_PRIMARY, cursor="hand2",
                padx=12, pady=0,
            )
            fs_btn.pack(side="right")
            fs_btn.bind("<Button-1>", lambda e: on_fullscreen())
            fs_btn.bind("<Enter>", lambda e: fs_btn.configure(bg="#7C5DBD"))
            fs_btn.bind("<Leave>", lambda e: fs_btn.configure(bg=M3_PRIMARY))

        # 拖动
        for widget in (self.bar,) + tuple(self.bar.winfo_children()):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)
        # × / 全屏按钮不触发拖动
        close_btn.bind("<ButtonPress-1>", lambda e: on_close())
        if on_fullscreen:
            fs_btn.bind("<ButtonPress-1>", lambda e: on_fullscreen())

    def _start_drag(self, event):
        self._drag_start_x = event.x_root - self.parent.winfo_x()
        self._drag_start_y = event.y_root - self.parent.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self._drag_start_x
        y = event.y_root - self._drag_start_y
        self.parent.geometry(f"+{x}+{y}")


class WheelPicker(tk.Canvas):
    """Material Three 风格滚轮选择器。"""
    ITEM_HEIGHT = 56
    VISIBLE_COUNT = 5

    def __init__(self, parent, values, width=100, height=180, on_change=None, **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=M3_SURFACE, highlightthickness=0, **kwargs)
        self.values = values
        self.on_change = on_change
        self._index = 0
        self._offset = 0.0
        self._target_offset = 0.0
        self._animating = False
        self._drag_start_y = None
        self._drag_start_offset = 0
        self._center_y = height // 2

        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Button-4>", lambda e: self._scroll(-1))
        self.bind("<Button-5>", lambda e: self._scroll(1))
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Configure>", self._on_configure)
        self._draw()

    def _on_configure(self, event):
        self._center_y = event.height // 2
        self._draw()

    def get(self):
        return self.values[self._index]

    def set_index(self, idx):
        self._index = max(0, min(len(self.values) - 1, idx))
        self._offset = 0
        self._target_offset = 0
        self._draw()

    def _scroll(self, direction):
        new_idx = self._index + direction
        if 0 <= new_idx < len(self.values):
            self._index = new_idx
            self._target_offset = -direction * self.ITEM_HEIGHT
            self._start_animation()
            if self.on_change:
                self.on_change(self.values[self._index])

    def _on_mousewheel(self, event):
        direction = -1 if event.delta > 0 else 1
        self._scroll(direction)

    def _on_press(self, event):
        self._drag_start_y = event.y
        self._drag_start_offset = self._offset
        self._animating = False

    def _on_drag(self, event):
        if self._drag_start_y is None:
            return
        delta = event.y - self._drag_start_y
        self._offset = self._drag_start_offset + delta
        self._draw()

    def _on_release(self, event):
        if self._drag_start_y is None:
            return
        delta = event.y - self._drag_start_y
        steps = round(delta / self.ITEM_HEIGHT)
        if steps != 0:
            new_idx = self._index - steps
            new_idx = max(0, min(len(self.values) - 1, new_idx))
            self._index = new_idx
            if self.on_change:
                self.on_change(self.values[self._index])
        self._target_offset = 0
        self._drag_start_y = None
        self._start_animation()

    def _start_animation(self):
        if self._animating:
            return
        self._animating = True
        self._animate()

    def _animate(self):
        diff = self._target_offset - self._offset
        if abs(diff) < 0.5:
            self._offset = self._target_offset
            self._animating = False
            self._draw()
            return
        self._offset += diff * 0.25
        self._draw()
        self.after(16, self._animate)

    def _draw(self):
        self.delete("all")
        w = self.winfo_width() or 100
        h = self.winfo_height() or 180
        self._center_y = h // 2

        pad_x = 8
        self.create_rectangle(
            pad_x, self._center_y - self.ITEM_HEIGHT // 2,
            w - pad_x, self._center_y + self.ITEM_HEIGHT // 2,
            fill=M3_SURFACE_VARIANT, outline="",
        )
        self.create_line(
            pad_x + 4, self._center_y - self.ITEM_HEIGHT // 2,
            w - pad_x - 4, self._center_y - self.ITEM_HEIGHT // 2,
            fill=M3_OUTLINE, width=1,
        )
        self.create_line(
            pad_x + 4, self._center_y + self.ITEM_HEIGHT // 2,
            w - pad_x - 4, self._center_y + self.ITEM_HEIGHT // 2,
            fill=M3_OUTLINE, width=1,
        )

        half = self.VISIBLE_COUNT // 2
        for i in range(-half, half + 1):
            idx = self._index + i
            if idx < 0 or idx >= len(self.values):
                continue
            y = self._center_y + i * self.ITEM_HEIGHT + self._offset
            dist = abs(i)
            if dist == 0:
                font_size = 32
                color = M3_ON_SURFACE
            elif dist == 1:
                font_size = 22
                color = M3_ON_SURFACE_VARIANT
            else:
                font_size = 16
                color = "#9B959E"
            text = str(self.values[idx]).zfill(2)
            self.create_text(w // 2, y, text=text,
                             font=("Roboto", font_size, "bold"), fill=color)


def _format_time(seconds, with_ms=False):
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    if with_ms:
        ms = int((seconds - int(seconds)) * 100)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:02d}"
    return f"{h:02d}:{m:02d}:{s:02d}"


class CountdownDialog:
    """倒计时对话框：自定义标题栏，紧凑布局，支持全屏。"""

    def __init__(self, parent):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.title("倒计时")
        self.win.configure(bg=M3_BACKGROUND)
        self.win.resizable(False, False)
        self.win.overrideredirect(True)  # 去掉原生标题栏
        self.win.geometry("360x300")

        self._running = False
        self._paused = False
        self._total_seconds = 0
        self._remaining = 0
        self._count_up = False
        self._count_up_seconds = 0
        self._start_time = 0
        self._pause_elapsed = 0
        self._timer_id = None
        self._red_threshold = 0
        self._fullscreen = False
        self._normal_geom = "360x300"

        # 自定义标题栏
        self.title_bar = _CustomTitleBar(self.win, "倒计时", self._close, self._toggle_fullscreen)

        self._build_ui()
        self._center_window()

    def _center_window(self):
        self.win.update_idletasks()
        w = self.win.winfo_width()
        h = self.win.winfo_height()
        x = (self.win.winfo_screenwidth() - w) // 2
        y = (self.win.winfo_screenheight() - h) // 2
        self.win.geometry(f"+{x}+{y}")

    def _build_ui(self):
        content = tk.Frame(self.win, bg=M3_BACKGROUND, padx=20, pady=14)
        content.pack(fill="both", expand=True)

        # 选择器区域
        self.picker_frame = tk.Frame(content, bg=M3_BACKGROUND)
        self.picker_frame.pack(fill="x")

        picker_container = tk.Frame(self.picker_frame, bg=M3_SURFACE,
                                    highlightthickness=1,
                                    highlightbackground=M3_OUTLINE)
        picker_container.pack()

        row = tk.Frame(picker_container, bg=M3_SURFACE)
        row.pack(padx=6, pady=6)

        self.hour_picker = WheelPicker(row, list(range(24)), width=80, height=160)
        self.hour_picker.pack(side="left", padx=(2, 1))

        tk.Label(row, text=":", font=("Roboto", 32, "bold"),
                 bg=M3_SURFACE, fg=M3_ON_SURFACE_VARIANT).pack(side="left", padx=1)

        self.min_picker = WheelPicker(row, list(range(60)), width=80, height=160)
        self.min_picker.pack(side="left", padx=(1, 2))

        # 快捷选择
        quick_frame = tk.Frame(self.picker_frame, bg=M3_BACKGROUND)
        quick_frame.pack(fill="x", pady=(8, 0))
        for text, mins in [("5分钟", 5), ("10分钟", 10), ("30分钟", 30), ("1小时", 60)]:
            btn = tk.Label(quick_frame, text=text, font=("Microsoft YaHei UI", 9),
                           bg=M3_SURFACE_VARIANT, fg=M3_ON_SURFACE_VARIANT,
                           padx=8, pady=3, cursor="hand2")
            btn.pack(side="left", padx=2)
            btn.bind("<Button-1>", lambda e, m=mins: self._quick_set(m))

        # 显示区域（运行时）
        self.display_frame = tk.Frame(content, bg=M3_BACKGROUND)

        self.time_label = tk.Label(
            self.display_frame, text="00:00:00",
            font=("Roboto", 52, "bold"),
            bg=M3_BACKGROUND, fg=M3_ON_SURFACE,
        )
        self.time_label.pack(pady=(4, 8))

        btn_row = tk.Frame(self.display_frame, bg=M3_BACKGROUND)
        btn_row.pack(fill="x")

        self.pause_btn = self._make_button(
            btn_row, "暂停", M3_TERTIARY, M3_ON_PRIMARY, self._toggle_pause,
        )
        self.pause_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.reset_btn = self._make_button(
            btn_row, "重置", M3_SURFACE_VARIANT, M3_ON_SURFACE_VARIANT, self._reset,
        )
        self.reset_btn.pack(side="right", expand=True, fill="x", padx=(6, 0))

        # 底部开始按钮
        self.start_btn = self._make_button(
            content, "开始倒计时", M3_PRIMARY, M3_ON_PRIMARY, self._start,
        )
        self.start_btn.pack(side="bottom", fill="x", pady=(8, 0))

    def _make_button(self, parent, text, bg, fg, cmd):
        btn = tk.Label(parent, text=text, font=("Microsoft YaHei UI", 13, "bold"),
                       bg=bg, fg=fg, padx=16, pady=10, cursor="hand2")
        btn.bind("<Button-1>", lambda e: cmd())
        btn.bind("<Enter>", lambda e: btn.configure(bg=self._lighten(bg)))
        btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
        return btn

    def _lighten(self, color):
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        return f"#{min(255,r+30):02x}{min(255,g+30):02x}{min(255,b+30):02x}"

    def _quick_set(self, minutes):
        self.hour_picker.set_index(minutes // 60)
        self.min_picker.set_index(minutes % 60)

    def _start(self):
        if self._running:
            return
        h = self.hour_picker.get()
        m = self.min_picker.get()
        self._total_seconds = h * 3600 + m * 60
        if self._total_seconds == 0:
            return
        self._remaining = self._total_seconds
        self._red_threshold = self._total_seconds // 5
        self._count_up = False
        self._count_up_seconds = 0
        self._start_time = time.time()
        self._pause_elapsed = 0
        self._running = True
        self._paused = False

        self.picker_frame.pack_forget()
        self.start_btn.pack_forget()
        self.display_frame.pack(fill="x", pady=(4, 0))
        self.pause_btn.configure(text="暂停")
        # 紧凑：运行时缩小窗口，去掉底部空白
        if not self._fullscreen:
            self.win.geometry("360x212")
        self._tick()

    def _toggle_pause(self):
        if not self._running:
            return
        if self._paused:
            self._start_time = time.time() - self._pause_elapsed
            self._paused = False
            self.pause_btn.configure(text="暂停")
            self._tick()
        else:
            self._paused = True
            self._pause_elapsed = time.time() - self._start_time
            if self._timer_id:
                self.win.after_cancel(self._timer_id)
                self._timer_id = None
            self.pause_btn.configure(text="继续")

    def _reset(self):
        self._running = False
        self._paused = False
        if self._timer_id:
            self.win.after_cancel(self._timer_id)
            self._timer_id = None
        self._remaining = 0
        self._count_up = False
        self._count_up_seconds = 0
        self.time_label.configure(text="00:00:00", fg=M3_ON_SURFACE)
        self.display_frame.pack_forget()
        self.picker_frame.pack(fill="x")
        self.start_btn.pack(side="bottom", fill="x", pady=(8, 0))
        if not self._fullscreen:
            self.win.geometry(self._normal_geom)

    def _tick(self):
        if not self._running or self._paused:
            return
        elapsed = time.time() - self._start_time
        if not self._count_up:
            self._remaining = max(0, self._total_seconds - int(elapsed))
            self.time_label.configure(text=_format_time(self._remaining))
            if self._remaining <= self._red_threshold:
                self.time_label.configure(fg=M3_ERROR)
            else:
                self.time_label.configure(fg=M3_ON_SURFACE)
            if self._remaining == 0:
                self._on_finish()
        else:
            self._count_up_seconds = int(elapsed) - self._total_seconds
            self.time_label.configure(text=_format_time(self._count_up_seconds))
        self._timer_id = self.win.after(200, self._tick)

    def _on_finish(self):
        self._play_alarm()
        self._count_up = True
        self.time_label.configure(fg=M3_ERROR)

    def _play_alarm(self):
        """播放倒计时结束铃声（assets/alarm.wav）。"""
        try:
            import winsound
            path = resource_path(os.path.join("assets", "alarm.wav"))
            if os.path.isfile(path):
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                for _ in range(3):
                    winsound.Beep(880, 300)
                    time.sleep(0.1)
        except Exception:
            pass

    def _toggle_fullscreen(self):
        if self._fullscreen:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self):
        if self._fullscreen:
            return
        self._fullscreen = True
        self._normal_geom = self.win.geometry()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"{sw}x{sh}+0+0")
        self.win.attributes("-topmost", True)
        self.time_label.configure(font=("Roboto", 140, "bold"), pady=30)
        for btn in (self.pause_btn, self.reset_btn, self.start_btn):
            btn.configure(font=("Microsoft YaHei UI", 20, "bold"), pady=20)
        self.win.bind("<Escape>", lambda e: self._toggle_fullscreen())

    def _exit_fullscreen(self):
        if not self._fullscreen:
            return
        self._fullscreen = False
        self.win.geometry(self._normal_geom)
        self.win.attributes("-topmost", False)
        self.time_label.configure(font=("Roboto", 52, "bold"), pady=8)
        for btn in (self.pause_btn, self.reset_btn, self.start_btn):
            btn.configure(font=("Microsoft YaHei UI", 13, "bold"), pady=10)
        self.win.unbind("<Escape>")
        if self._running and not self._paused:
            self.win.geometry("360x212")

    def _close(self):
        if self._timer_id:
            self.win.after_cancel(self._timer_id)
        self.win.destroy()


class StopwatchDialog:
    """秒表对话框：自定义标题栏，支持记次，支持全屏。"""

    def __init__(self, parent):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.title("秒表")
        self.win.configure(bg=M3_BACKGROUND)
        self.win.resizable(False, False)
        self.win.overrideredirect(True)
        self.win.geometry("360x420")

        self._running = False
        self._paused = False
        self._start_time = 0
        self._elapsed = 0
        self._laps = []
        self._timer_id = None
        self._fullscreen = False
        self._normal_geom = "360x420"

        self.title_bar = _CustomTitleBar(self.win, "秒表", self._close, self._toggle_fullscreen)

        self._build_ui()
        self._center_window()

    def _center_window(self):
        self.win.update_idletasks()
        w = self.win.winfo_width()
        h = self.win.winfo_height()
        x = (self.win.winfo_screenwidth() - w) // 2
        y = (self.win.winfo_screenheight() - h) // 2
        self.win.geometry(f"+{x}+{y}")

    def _build_ui(self):
        content = tk.Frame(self.win, bg=M3_BACKGROUND, padx=20, pady=14)
        content.pack(fill="both", expand=True)

        self.time_label = tk.Label(
            content, text="00:00:00.00",
            font=("Roboto", 40, "bold"),
            bg=M3_BACKGROUND, fg=M3_ON_SURFACE,
        )
        self.time_label.pack(pady=(4, 8))

        btn_frame = tk.Frame(content, bg=M3_BACKGROUND)
        btn_frame.pack(fill="x", pady=(0, 8))

        self.start_btn = self._make_button(
            btn_frame, "开始", M3_PRIMARY, M3_ON_PRIMARY, self._toggle_start_pause,
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.lap_btn = self._make_button(
            btn_frame, "记次", M3_TERTIARY, M3_ON_PRIMARY, self._lap,
        )

        self.reset_btn = self._make_button(
            btn_frame, "重置", M3_SURFACE_VARIANT, M3_ON_SURFACE_VARIANT, self._reset,
        )

        # 记次列表
        list_label = tk.Label(
            content, text="记次记录", font=("Microsoft YaHei UI", 11, "bold"),
            bg=M3_BACKGROUND, fg=M3_ON_SURFACE_VARIANT, anchor="w",
        )
        list_label.pack(fill="x", pady=(2, 4))

        list_container = tk.Frame(content, bg=M3_SURFACE, highlightthickness=1,
                                  highlightbackground=M3_OUTLINE)
        list_container.pack(fill="both", expand=True)

        header = tk.Frame(list_container, bg=M3_SURFACE_VARIANT)
        header.pack(fill="x")
        tk.Label(header, text="#", font=("Microsoft YaHei UI", 9, "bold"),
                 bg=M3_SURFACE_VARIANT, fg=M3_ON_SURFACE_VARIANT,
                 width=4).pack(side="left", padx=4, pady=6)
        tk.Label(header, text="记次时间", font=("Microsoft YaHei UI", 9, "bold"),
                 bg=M3_SURFACE_VARIANT, fg=M3_ON_SURFACE_VARIANT,
                 width=12).pack(side="left", padx=4, pady=6)
        tk.Label(header, text="总时间", font=("Microsoft YaHei UI", 9, "bold"),
                 bg=M3_SURFACE_VARIANT, fg=M3_ON_SURFACE_VARIANT,
                 width=12).pack(side="left", padx=4, pady=6)

        self.lap_canvas = tk.Canvas(list_container, bg=M3_SURFACE, highlightthickness=0)
        self.lap_scroll = ttk.Scrollbar(list_container, orient="vertical",
                                        command=self.lap_canvas.yview)
        self.lap_inner = tk.Frame(self.lap_canvas, bg=M3_SURFACE)

        self.lap_inner.bind("<Configure>", lambda e: self.lap_canvas.configure(
            scrollregion=self.lap_canvas.bbox("all")))
        self.lap_canvas.create_window((0, 0), window=self.lap_inner, anchor="nw")
        self.lap_canvas.configure(yscrollcommand=self.lap_scroll.set)
        self.lap_canvas.pack(side="left", fill="both", expand=True)
        self.lap_scroll.pack(side="right", fill="y")

        self.lap_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.lap_inner.bind("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        self.lap_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _make_button(self, parent, text, bg, fg, cmd):
        btn = tk.Label(parent, text=text, font=("Microsoft YaHei UI", 13, "bold"),
                       bg=bg, fg=fg, padx=16, pady=10, cursor="hand2")
        btn.bind("<Button-1>", lambda e: cmd())
        btn.bind("<Enter>", lambda e: btn.configure(bg=self._lighten(bg)))
        btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
        return btn

    def _lighten(self, color):
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        return f"#{min(255,r+30):02x}{min(255,g+30):02x}{min(255,b+30):02x}"

    def _toggle_start_pause(self):
        if not self._running:
            self._start_time = time.time()
            self._elapsed = 0
            self._running = True
            self._paused = False
            self.start_btn.configure(text="暂停")
            self.lap_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))
            self.reset_btn.pack_forget()
            self._tick()
        elif not self._paused:
            self._paused = True
            self._elapsed = time.time() - self._start_time
            if self._timer_id:
                self.win.after_cancel(self._timer_id)
                self._timer_id = None
            self.start_btn.configure(text="继续")
            self.lap_btn.pack_forget()
            self.reset_btn.pack(side="right", expand=True, fill="x", padx=(6, 0))
        else:
            self._start_time = time.time() - self._elapsed
            self._paused = False
            self.start_btn.configure(text="暂停")
            self.reset_btn.pack_forget()
            self.lap_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))
            self._tick()

    def _lap(self):
        if not self._running or self._paused:
            return
        total = time.time() - self._start_time
        prev_total = sum(l[0] for l in self._laps)
        lap_time = total - prev_total
        self._laps.append((lap_time, total))
        self._add_lap_row(len(self._laps), lap_time, total)

    def _add_lap_row(self, num, lap_time, total):
        row = tk.Frame(self.lap_inner, bg=M3_SURFACE)
        row.pack(fill="x")
        bg = "#F5F2F8" if num % 2 == 0 else M3_SURFACE
        row.configure(bg=bg)
        tk.Label(row, text=str(num), font=("Roboto", 10),
                 bg=bg, fg=M3_ON_SURFACE_VARIANT, width=4).pack(side="left", padx=4, pady=4)
        tk.Label(row, text=_format_time(lap_time), font=("Roboto", 10),
                 bg=bg, fg=M3_ON_SURFACE, width=12).pack(side="left", padx=4, pady=4)
        tk.Label(row, text=_format_time(total), font=("Roboto", 10),
                 bg=bg, fg=M3_ON_SURFACE_VARIANT, width=12).pack(side="left", padx=4, pady=4)
        self.lap_canvas.yview_moveto(1.0)

    def _reset(self):
        self._running = False
        self._paused = False
        if self._timer_id:
            self.win.after_cancel(self._timer_id)
            self._timer_id = None
        self._elapsed = 0
        self._laps = []
        self.time_label.configure(text="00:00:00.00")
        self.start_btn.configure(text="开始")
        self.lap_btn.pack_forget()
        self.reset_btn.pack_forget()
        for widget in self.lap_inner.winfo_children():
            widget.destroy()

    def _tick(self):
        if not self._running or self._paused:
            return
        self._elapsed = time.time() - self._start_time
        self.time_label.configure(text=_format_time(self._elapsed, with_ms=True))
        self._timer_id = self.win.after(30, self._tick)

    def _toggle_fullscreen(self):
        if self._fullscreen:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self):
        if self._fullscreen:
            return
        self._fullscreen = True
        self._normal_geom = self.win.geometry()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"{sw}x{sh}+0+0")
        self.win.attributes("-topmost", True)
        self.time_label.configure(font=("Roboto", 120, "bold"), pady=30)
        for btn in (self.start_btn, self.lap_btn, self.reset_btn):
            btn.configure(font=("Microsoft YaHei UI", 20, "bold"), pady=20)
        self.win.bind("<Escape>", lambda e: self._toggle_fullscreen())

    def _exit_fullscreen(self):
        if not self._fullscreen:
            return
        self._fullscreen = False
        self.win.geometry(self._normal_geom)
        self.win.attributes("-topmost", False)
        self.time_label.configure(font=("Roboto", 40, "bold"), pady=8)
        for btn in (self.start_btn, self.lap_btn, self.reset_btn):
            btn.configure(font=("Microsoft YaHei UI", 13, "bold"), pady=10)
        self.win.unbind("<Escape>")

    def _close(self):
        if self._timer_id:
            self.win.after_cancel(self._timer_id)
        self.win.destroy()
