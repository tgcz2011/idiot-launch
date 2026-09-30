#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Material Three 风格的计时器对话框。
包含：滚轮时间选择器、倒计时（结束转正计时+声音+1/5变红）、秒表（记次）。
"""
import tkinter as tk
from tkinter import ttk
import time
import math
import threading

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


class WheelPicker(tk.Canvas):
    """Material Three 风格滚轮选择器。
    显示上下渐隐的数字，鼠标滚轮或拖动切换，平滑动画。
    """
    ITEM_HEIGHT = 56  # 每个数字的高度
    VISIBLE_COUNT = 5  # 可见数字数量（上2+当前+下2）

    def __init__(self, parent, values, width=100, height=200,
                 on_change=None, **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=M3_SURFACE, highlightthickness=0, **kwargs)
        self.values = values
        self.on_change = on_change
        self._index = 0
        self._offset = 0.0  # 动画偏移量（像素）
        self._target_offset = 0.0
        self._animating = False
        self._drag_start_y = None
        self._drag_start_offset = 0
        self._center_y = height // 2

        # 绑定事件
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Button-4>", lambda e: self._scroll(-1))  # Linux
        self.bind("<Button-5>", lambda e: self._scroll(1))   # Linux
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

    def set(self, value):
        if value in self.values:
            self._index = self.values.index(value)
            self._offset = 0
            self._target_offset = 0
            self._draw()

    def get_index(self):
        return self._index

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
        h = self.winfo_height() or 200
        self._center_y = h // 2

        # 绘制选中区域背景（圆角矩形效果）
        pad_x = 8
        self.create_rectangle(
            pad_x, self._center_y - self.ITEM_HEIGHT // 2,
            w - pad_x, self._center_y + self.ITEM_HEIGHT // 2,
            fill=M3_SURFACE_VARIANT, outline="",
        )

        # 绘制上下分割线
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

        # 绘制数字
        half = self.VISIBLE_COUNT // 2
        for i in range(-half, half + 1):
            idx = self._index + i
            if idx < 0 or idx >= len(self.values):
                continue
            y = self._center_y + i * self.ITEM_HEIGHT + self._offset
            # 距离中心越远，字体越小、越透明
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
            self.create_text(
                w // 2, y, text=text,
                font=("Roboto", font_size, "bold"),
                fill=color,
            )


class CountdownDialog:
    """倒计时对话框：Material Three 风格，结束转正计时，1/5 变红，结束声音。"""

    def __init__(self, parent):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.title("倒计时")
        self.win.configure(bg=M3_BACKGROUND)
        self.win.resizable(False, False)
        self.win.geometry("380x480")

        # 状态
        self._running = False
        self._paused = False
        self._total_seconds = 0
        self._remaining = 0
        self._count_up = False  # 结束后正计时
        self._count_up_seconds = 0
        self._start_time = 0
        self._pause_elapsed = 0
        self._timer_id = None
        self._red_threshold = 0  # 剩余时间小于此值变红

        self._build_ui()
        self._center_window()

    def _center_window(self):
        self.win.update_idletasks()
        w = self.win.winfo_width()
        h = self.win.winfo_height()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.win.geometry(f"+{x}+{y}")

    def _build_ui(self):
        # 标题栏
        title_bar = tk.Frame(self.win, bg=M3_PRIMARY, height=48)
        title_bar.pack(fill="x", side="top")
        title_bar.pack_propagate(False)
        tk.Label(
            title_bar, text="倒计时", font=("Microsoft YaHei UI", 16, "bold"),
            bg=M3_PRIMARY, fg=M3_ON_PRIMARY,
        ).pack(side="left", padx=16)
        tk.Label(
            title_bar, text="×", font=("Arial", 20, "bold"),
            bg=M3_PRIMARY, fg=M3_ON_PRIMARY, cursor="hand2",
        ).pack(side="right", padx=16)
        # 绑定关闭
        for widget in title_bar.winfo_children():
            if widget.cget("text") == "×":
                widget.bind("<Button-1>", lambda e: self._close())

        # 内容区
        content = tk.Frame(self.win, bg=M3_BACKGROUND, padx=24, pady=16)
        content.pack(fill="both", expand=True)

        # 选择器区域（未开始时显示）
        self.picker_frame = tk.Frame(content, bg=M3_BACKGROUND)
        self.picker_frame.pack(fill="x", pady=(0, 16))

        picker_container = tk.Frame(self.picker_frame, bg=M3_SURFACE,
                                    highlightthickness=1,
                                    highlightbackground=M3_OUTLINE)
        picker_container.pack()

        row = tk.Frame(picker_container, bg=M3_SURFACE)
        row.pack(padx=8, pady=8)

        self.hour_picker = WheelPicker(row, list(range(24)), width=90, height=180)
        self.hour_picker.pack(side="left", padx=(4, 2))

        colon = tk.Label(row, text=":", font=("Roboto", 36, "bold"),
                         bg=M3_SURFACE, fg=M3_ON_SURFACE_VARIANT)
        colon.pack(side="left", padx=2)

        self.min_picker = WheelPicker(row, list(range(60)), width=90, height=180)
        self.min_picker.pack(side="left", padx=(2, 4))

        # 快捷选择
        quick_frame = tk.Frame(self.picker_frame, bg=M3_BACKGROUND)
        quick_frame.pack(fill="x", pady=(8, 0))
        for text, mins in [("5分钟", 5), ("10分钟", 10), ("30分钟", 30), ("1小时", 60)]:
            btn = tk.Label(
                quick_frame, text=text, font=("Microsoft YaHei UI", 9),
                bg=M3_SURFACE_VARIANT, fg=M3_ON_SURFACE_VARIANT,
                padx=10, pady=4, cursor="hand2",
            )
            btn.pack(side="left", padx=3)
            btn.bind("<Button-1>", lambda e, m=mins: self._quick_set(m))

        # 显示区域（运行时显示）
        self.display_frame = tk.Frame(content, bg=M3_BACKGROUND)
        # 不 pack，运行时才显示

        self.time_label = tk.Label(
            self.display_frame, text="00:00:00",
            font=("Roboto", 56, "bold"),
            bg=M3_BACKGROUND, fg=M3_ON_SURFACE,
        )
        self.time_label.pack(pady=(20, 8))

        self.mode_label = tk.Label(
            self.display_frame, text="倒计时中",
            font=("Microsoft YaHei UI", 12),
            bg=M3_BACKGROUND, fg=M3_ON_SURFACE_VARIANT,
        )
        self.mode_label.pack()

        # 按钮区域
        btn_frame = tk.Frame(content, bg=M3_BACKGROUND)
        btn_frame.pack(side="bottom", fill="x", pady=(16, 0))

        self.start_btn = self._make_button(
            btn_frame, "开始", M3_PRIMARY, M3_ON_PRIMARY, self._start,
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.pause_btn = self._make_button(
            btn_frame, "暂停", M3_TERTIARY, M3_ON_PRIMARY, self._pause,
        )
        # 不默认显示

        self.reset_btn = self._make_button(
            btn_frame, "重置", M3_SURFACE_VARIANT, M3_ON_SURFACE_VARIANT,
            self._reset,
        )
        self.reset_btn.pack(side="right", expand=True, fill="x", padx=(6, 0))

    def _make_button(self, parent, text, bg, fg, cmd):
        btn = tk.Label(
            parent, text=text, font=("Microsoft YaHei UI", 13, "bold"),
            bg=bg, fg=fg, padx=20, pady=12, cursor="hand2",
        )
        btn.bind("<Button-1>", lambda e: cmd())
        btn.bind("<Enter>", lambda e: btn.configure(bg=self._lighten(bg)))
        btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
        return btn

    def _lighten(self, color):
        # 简单的颜色变亮
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        r = min(255, r + 30)
        g = min(255, g + 30)
        b = min(255, b + 30)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _quick_set(self, minutes):
        h = minutes // 60
        m = minutes % 60
        self.hour_picker.set_index(h)
        self.min_picker.set_index(m)

    def _start(self):
        if self._running and not self._paused:
            return
        if not self._running:
            # 新开始
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
            # 切换显示
            self.picker_frame.pack_forget()
            self.display_frame.pack(fill="x", pady=(10, 0))
            self.start_btn.pack_forget()
            self.pause_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))
        else:
            # 从暂停恢复
            self._start_time = time.time() - self._pause_elapsed
        self._running = True
        self._paused = False
        self._tick()

    def _pause(self):
        if not self._running or self._paused:
            return
        self._paused = True
        self._pause_elapsed = time.time() - self._start_time
        if self._timer_id:
            self.win.after_cancel(self._timer_id)
            self._timer_id = None
        self.pause_btn.configure(text="继续")
        self.mode_label.configure(text="已暂停")

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
        self.mode_label.configure(text="倒计时中")
        self.pause_btn.configure(text="暂停")
        self.display_frame.pack_forget()
        self.picker_frame.pack(fill="x", pady=(0, 16))
        self.pause_btn.pack_forget()
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

    def _tick(self):
        if not self._running or self._paused:
            return
        elapsed = time.time() - self._start_time
        if not self._count_up:
            self._remaining = max(0, self._total_seconds - int(elapsed))
            self._update_display(self._remaining)
            # 1/5 变红
            if self._remaining <= self._red_threshold:
                self.time_label.configure(fg=M3_ERROR)
            else:
                self.time_label.configure(fg=M3_ON_SURFACE)
            if self._remaining == 0:
                self._on_finish()
        else:
            self._count_up_seconds = int(elapsed) - self._total_seconds
            self._update_display(self._count_up_seconds, count_up=True)
        self._timer_id = self.win.after(200, self._tick)

    def _update_display(self, seconds, count_up=False):
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        text = f"{h:02d}:{m:02d}:{s:02d}"
        self.time_label.configure(text=text)
        if count_up:
            self.mode_label.configure(text="正计时中（已超时）")

    def _on_finish(self):
        # 播放声音
        self._play_alarm()
        self._count_up = True
        self.mode_label.configure(text="时间到！正计时中")
        self.time_label.configure(fg=M3_ERROR)

    def _play_alarm(self):
        try:
            import winsound
            # 播放三声提示音
            for _ in range(3):
                winsound.Beep(880, 300)
                time.sleep(0.1)
        except Exception:
            pass

    def _close(self):
        if self._timer_id:
            self.win.after_cancel(self._timer_id)
        self.win.destroy()


class StopwatchDialog:
    """秒表对话框：Material Three 风格，支持记次。"""

    def __init__(self, parent):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.title("秒表")
        self.win.configure(bg=M3_BACKGROUND)
        self.win.resizable(False, False)
        self.win.geometry("380x520")

        self._running = False
        self._paused = False
        self._start_time = 0
        self._elapsed = 0
        self._laps = []
        self._timer_id = None

        self._build_ui()
        self._center_window()

    def _center_window(self):
        self.win.update_idletasks()
        w = self.win.winfo_width()
        h = self.win.winfo_height()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.win.geometry(f"+{x}+{y}")

    def _build_ui(self):
        # 标题栏
        title_bar = tk.Frame(self.win, bg=M3_PRIMARY, height=48)
        title_bar.pack(fill="x", side="top")
        title_bar.pack_propagate(False)
        tk.Label(
            title_bar, text="秒表", font=("Microsoft YaHei UI", 16, "bold"),
            bg=M3_PRIMARY, fg=M3_ON_PRIMARY,
        ).pack(side="left", padx=16)
        close_lbl = tk.Label(
            title_bar, text="×", font=("Arial", 20, "bold"),
            bg=M3_PRIMARY, fg=M3_ON_PRIMARY, cursor="hand2",
        )
        close_lbl.pack(side="right", padx=16)
        close_lbl.bind("<Button-1>", lambda e: self._close())

        # 内容区
        content = tk.Frame(self.win, bg=M3_BACKGROUND, padx=24, pady=16)
        content.pack(fill="both", expand=True)

        # 时间显示
        self.time_label = tk.Label(
            content, text="00:00:00.00",
            font=("Roboto", 44, "bold"),
            bg=M3_BACKGROUND, fg=M3_ON_SURFACE,
        )
        self.time_label.pack(pady=(16, 8))

        # 按钮区域
        btn_frame = tk.Frame(content, bg=M3_BACKGROUND)
        btn_frame.pack(fill="x", pady=(8, 12))

        self.start_btn = self._make_button(
            btn_frame, "开始", M3_PRIMARY, M3_ON_PRIMARY, self._start,
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.lap_btn = self._make_button(
            btn_frame, "记次", M3_TERTIARY, M3_ON_PRIMARY, self._lap,
        )

        self.reset_btn = self._make_button(
            btn_frame, "重置", M3_SURFACE_VARIANT, M3_ON_SURFACE_VARIANT,
            self._reset,
        )
        self.reset_btn.pack(side="right", expand=True, fill="x", padx=(6, 0))

        # 记次列表
        list_label = tk.Label(
            content, text="记次记录", font=("Microsoft YaHei UI", 11, "bold"),
            bg=M3_BACKGROUND, fg=M3_ON_SURFACE_VARIANT, anchor="w",
        )
        list_label.pack(fill="x", pady=(8, 4))

        list_container = tk.Frame(content, bg=M3_SURFACE, highlightthickness=1,
                                  highlightbackground=M3_OUTLINE)
        list_container.pack(fill="both", expand=True)

        # 表头
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

        # 可滚动的记次列表
        self.lap_list_frame = tk.Frame(list_container, bg=M3_SURFACE)
        self.lap_list_frame.pack(fill="both", expand=True)

        self.lap_canvas = tk.Canvas(self.lap_list_frame, bg=M3_SURFACE,
                                    highlightthickness=0)
        self.lap_scroll = ttk.Scrollbar(self.lap_list_frame, orient="vertical",
                                        command=self.lap_canvas.yview)
        self.lap_inner = tk.Frame(self.lap_canvas, bg=M3_SURFACE)

        self.lap_inner.bind(
            "<Configure>",
            lambda e: self.lap_canvas.configure(
                scrollregion=self.lap_canvas.bbox("all")
            ),
        )
        self.lap_canvas.create_window((0, 0), window=self.lap_inner, anchor="nw")
        self.lap_canvas.configure(yscrollcommand=self.lap_scroll.set)
        self.lap_canvas.pack(side="left", fill="both", expand=True)
        self.lap_scroll.pack(side="right", fill="y")

    def _make_button(self, parent, text, bg, fg, cmd):
        btn = tk.Label(
            parent, text=text, font=("Microsoft YaHei UI", 13, "bold"),
            bg=bg, fg=fg, padx=20, pady=12, cursor="hand2",
        )
        btn.bind("<Button-1>", lambda e: cmd())
        btn.bind("<Enter>", lambda e: btn.configure(bg=self._lighten(bg)))
        btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
        return btn

    def _lighten(self, color):
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        r = min(255, r + 30)
        g = min(255, g + 30)
        b = min(255, b + 30)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _start(self):
        if self._running and not self._paused:
            return
        if not self._running:
            self._start_time = time.time()
            self._elapsed = 0
            self.start_btn.configure(text="暂停")
            self.lap_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))
            self.reset_btn.pack_forget()
        else:
            self._start_time = time.time() - self._elapsed
            self.start_btn.configure(text="暂停")
        self._running = True
        self._paused = False
        self._tick()

    def _pause(self):
        if not self._running or self._paused:
            return
        self._paused = True
        self._elapsed = time.time() - self._start_time
        if self._timer_id:
            self.win.after_cancel(self._timer_id)
            self._timer_id = None
        self.start_btn.configure(text="继续")
        self.lap_btn.pack_forget()
        self.reset_btn.pack(side="right", expand=True, fill="x", padx=(6, 0))

    def _lap(self):
        if not self._running or self._paused:
            return
        total = time.time() - self._start_time
        lap_time = total - sum(l[1] for l in self._laps)
        self._laps.append((lap_time, total))
        self._add_lap_row(len(self._laps), lap_time, total)

    def _add_lap_row(self, num, lap_time, total):
        row = tk.Frame(self.lap_inner, bg=M3_SURFACE)
        row.pack(fill="x")
        # 交替背景色
        if num % 2 == 0:
            row.configure(bg="#F5F2F8")
            bg = "#F5F2F8"
        else:
            bg = M3_SURFACE
        tk.Label(row, text=str(num), font=("Roboto", 10),
                 bg=bg, fg=M3_ON_SURFACE_VARIANT, width=4).pack(side="left", padx=4, pady=4)
        tk.Label(row, text=self._format_time(lap_time), font=("Roboto", 10),
                 bg=bg, fg=M3_ON_SURFACE, width=12).pack(side="left", padx=4, pady=4)
        tk.Label(row, text=self._format_time(total), font=("Roboto", 10),
                 bg=bg, fg=M3_ON_SURFACE_VARIANT, width=12).pack(side="left", padx=4, pady=4)
        # 滚动到底部
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
        # 清空记次列表
        for widget in self.lap_inner.winfo_children():
            widget.destroy()

    def _tick(self):
        if not self._running or self._paused:
            return
        self._elapsed = time.time() - self._start_time
        self.time_label.configure(text=self._format_time(self._elapsed, with_ms=True))
        self._timer_id = self.win.after(30, self._tick)

    def _format_time(self, seconds, with_ms=False):
        h = int(seconds) // 3600
        m = (int(seconds) % 3600) // 60
        s = int(seconds) % 60
        if with_ms:
            ms = int((seconds - int(seconds)) * 100)
            return f"{h:02d}:{m:02d}:{s:02d}.{ms:02d}"
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _close(self):
        if self._timer_id:
            self.win.after_cancel(self._timer_id)
        self.win.destroy()
