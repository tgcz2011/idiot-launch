"""
main.py — Idiot Launch 主入口与 GUI
v1.3.0.0: 图标、右上角更新状态指示器、daemon 常驻启动、快捷方式自动重建。
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import sys
import os
import ctypes
import random

import pystray
from PIL import Image as PILImage

from src.timer_dialog import CountdownDialog, StopwatchDialog
from src.morning_browser import load_morning_config, save_morning_config, clear_temp_morning_config
from src.floating_button import FloatingButton, open_morning_browser, is_in_reading_period
from src.core import (
    launch_countdown,
    launch_custom,
    launch_settings,
    quit_countdown,
    is_running,
    start_daemon,
    is_daemon_running,
    ensure_shortcuts,
    get_daemon_status,
    load_state,
    send_command,
    resource_path,
    COUNTDOWN_VERSION,
    APP_NAME,
    LAUNCHER_VERSION,
    LAUNCHER_INSTALL_EXE,
    LAUNCHER_INSTALL_DIR,
    acquire_gui_mutex,
    signal_show_window,
    create_show_window_event,
    check_show_window_event,
    is_morning_logged_in,
    get_morning_students,
)

VERSION = LAUNCHER_VERSION

BG_COLOR = "#f0f2f5"
CARD_BG = "#ffffff"
BTN_ZHONGKAO = "#ef4444"
BTN_GAOKAO = "#3b82f6"
BTN_READING = "#22c55e"
BTN_KILL = "#64748b"
BTN_DISABLED = "#cbd5e1"
BTN_DISABLED_TEXT = "#f1f5f9"
BTN_HOVER_ZHONGKAO = "#dc2626"
BTN_HOVER_GAOKAO = "#2563eb"
BTN_HOVER_READING = "#16a34a"
BTN_HOVER_KILL = "#475569"
BTN_SETTINGS = "#a855f7"
BTN_HOVER_SETTINGS = "#9333ea"
BTN_COUNTDOWN = "#f97316"
BTN_HOVER_COUNTDOWN = "#ea580c"
BTN_STOPWATCH = "#14b8a6"
BTN_HOVER_STOPWATCH = "#0d9488"
TEXT_COLOR = "#1e293b"
STATUS_COLOR = "#64748b"
ACCENT_COLOR = "#6366f1"

# 更新状态指示器颜色
INDICATOR_IDLE = "#95a5a6"       # 灰色 - 空闲
INDICATOR_CHECKING = "#f39c12"   # 橙色 - 检查中
INDICATOR_DOWNLOADING = "#3498db" # 蓝色 - 下载中
INDICATOR_INSTALLING = "#9b59b6" # 紫色 - 安装中
INDICATOR_WAITING = "#e67e22"    # 深橙 - 等待中
INDICATOR_UPDATE_READY = "#2ecc71" # 绿色 - 有更新待应用
INDICATOR_UPDATING = "#8e44ad"    # 深紫 - 静默自我更新中


class HoverButton(tk.Canvas):
    def __init__(self, parent, text, subtext, color, hover_color, command,
                 width=340, height=80):
        super().__init__(parent, width=width, height=height, bg=CARD_BG,
                         highlightthickness=0)
        self.color = color
        self.hover_color = hover_color
        self.command = command
        self.text = text
        self.subtext = subtext
        self.width = width
        self.height = height
        self._enabled = True
        self._draw(color)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _draw(self, color, text_color="white", sub_alpha=0.85):
        self.delete("all")
        r = 18
        w, h = self.width, self.height
        # 阴影
        shadow_offset = 3
        shadow_color = "#d1d5db"
        self.create_rectangle(r + shadow_offset, shadow_offset, w - r + shadow_offset, h + shadow_offset, fill=shadow_color, outline="")
        self.create_rectangle(shadow_offset, r + shadow_offset, w + shadow_offset, h - r + shadow_offset, fill=shadow_color, outline="")
        self.create_oval(shadow_offset, shadow_offset, 2 * r + shadow_offset, 2 * r + shadow_offset, fill=shadow_color, outline="")
        self.create_oval(w - 2 * r + shadow_offset, shadow_offset, w + shadow_offset, 2 * r + shadow_offset, fill=shadow_color, outline="")
        self.create_oval(shadow_offset, h - 2 * r + shadow_offset, 2 * r + shadow_offset, h + shadow_offset, fill=shadow_color, outline="")
        self.create_oval(w - 2 * r + shadow_offset, h - 2 * r + shadow_offset, w + shadow_offset, h + shadow_offset, fill=shadow_color, outline="")
        # 按钮主体
        self.create_rectangle(r, 0, w - r, h, fill=color, outline="")
        self.create_rectangle(0, r, w, h - r, fill=color, outline="")
        self.create_oval(0, 0, 2 * r, 2 * r, fill=color, outline="")
        self.create_oval(w - 2 * r, 0, w, 2 * r, fill=color, outline="")
        self.create_oval(0, h - 2 * r, 2 * r, h, fill=color, outline="")
        self.create_oval(w - 2 * r, h - 2 * r, w, h, fill=color, outline="")
        self.create_text(w // 2, h // 2 - 8, text=self.text, fill=text_color,
                         font=("Microsoft YaHei UI", 18, "bold"))
        self.create_text(w // 2, h // 2 + 16, text=self.subtext,
                         fill=BTN_DISABLED_TEXT if not self._enabled else "white",
                         font=("Microsoft YaHei UI", 10))

    def _on_enter(self, event):
        if self._enabled:
            self._draw(self.hover_color)

    def _on_leave(self, event):
        if self._enabled:
            self._draw(self.color)

    def _on_click(self, event):
        if self._enabled and self.command:
            self.command()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        if enabled:
            self._draw(self.color)
            self.configure(cursor="")
        else:
            self._draw(BTN_DISABLED, text_color=BTN_DISABLED_TEXT)
            self.configure(cursor="arrow")


class UpdateIndicator(tk.Canvas):
    """右上角环形进度指示器：圆圈 = 粗略进度条，点击查看详情。

    空闲 → 完整淡灰环 + 中心灰点（一切正常）
    检查中 → 蓝色进度环
    下载中 → 蓝色进度环 + 中心百分比（daemon 实时上报进度）
    等待中 → 深橙进度环（等待倒计时退出）
    安装中/自我更新 → 紫环
    有更新待应用 → 绿色满环 + 中心 ↑
    """

    SIZE = 40
    RING_WIDTH = 4
    RING_GAP = 2          # 环与画布边缘的间隙
    BG_RING = "#e3e8ee"   # 背景环（浅灰）

    def __init__(self, parent, on_click):
        super().__init__(parent, width=self.SIZE, height=self.SIZE, bg=BG_COLOR,
                         highlightthickness=0, cursor="hand2")
        self.on_click = on_click
        self.current_color = INDICATOR_IDLE
        self.current_progress = 0
        self._last_center = "dot"
        self._draw_ring(INDICATOR_IDLE, 100, "dot")
        self.bind("<Button-1>", lambda e: on_click())

    def _draw_ring(self, color: str, progress: float, center: str):
        """画环形进度：progress 0-100，center 为中心内容（'dot'=小圆点 / 'pct'=百分比 / 其他文字）。"""
        self.delete("all")
        p = self.RING_GAP
        s = self.SIZE - self.RING_GAP
        # 背景环（整圈浅灰）
        self.create_arc(p, p, s, s, start=0, extent=359.9,
                        style="arc", outline=self.BG_RING, width=self.RING_WIDTH)
        # 进度环（从 12 点方向顺时针画 extent 度）
        extent = max(0.0, progress / 100 * 360)
        if extent >= 1.0:
            self.create_arc(p, p, s, s, start=90, extent=-extent,
                            style="arc", outline=color, width=self.RING_WIDTH)
        # 中心内容
        cx = cy = self.SIZE / 2
        if center == "dot":
            self.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=color, outline="")
        elif center:
            self.create_text(cx, cy, text=center, fill=color,
                             font=("Microsoft YaHei UI", 8, "bold"))
        self.current_color = color
        self.current_progress = progress

    def set_status(self, activity: str, detail: str = "", progress: float = 0):
        """根据 daemon 活动状态更新环形进度与颜色。"""
        color_map = {
            "idle": INDICATOR_IDLE,
            "starting": INDICATOR_IDLE,
            "stopped": INDICATOR_IDLE,
            "checking": INDICATOR_CHECKING,
            "downloading": INDICATOR_DOWNLOADING,
            "installing": INDICATOR_INSTALLING,
            "waiting": INDICATOR_WAITING,
            "updating": INDICATOR_UPDATING,
        }
        # 有已下载待应用的更新 → 绿色满环
        state = load_state()
        if state.get("pending_launcher_path"):
            if (self.current_color, self.current_progress) != (INDICATOR_UPDATE_READY, 100):
                self._draw_ring(INDICATOR_UPDATE_READY, 100, "↑")
            return
        color = color_map.get(activity, INDICATOR_IDLE)
        if activity in ("downloading", "installing", "updating", "waiting", "checking"):
            p = min(99, max(1, int(progress or 0)))
            center = f"{p}%" if activity == "downloading" else ""
            if (self.current_color, self.current_progress, self._last_center) != (color, p, center):
                self._draw_ring(color, p, center)
        else:
            if (self.current_color, self.current_progress) != (color, 100):
                self._draw_ring(color, 100, "dot")
        self._last_center = center if activity in ("downloading", "installing", "updating", "waiting", "checking") else "dot"


class ProgressDialog:
    def __init__(self, parent, title: str, subtitle: str = "",
                 hint: str = "教室电脑性能有限，请耐心等待，请勿关闭"):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="#ffffff")
        w, h = 380, 170
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        # 顶部蓝色条 + 右上角关闭按钮
        top_bar = tk.Frame(self.win, bg="#2980b9", height=28)
        top_bar.pack(fill="x", side="top")
        top_bar.pack_propagate(False)
        tk.Label(top_bar, text="", bg="#2980b9").pack(side="left", padx=10)
        close_btn = tk.Label(top_bar, text="×", font=("Arial", 14, "bold"),
                             bg="#2980b9", fg="white", cursor="hand2")
        close_btn.pack(side="right", padx=10)
        close_btn.bind("<Button-1>", lambda e: self.close())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg="#ffcccc"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg="white"))
        content = tk.Frame(self.win, bg="#ffffff", padx=30, pady=15)
        content.pack(fill="both", expand=True)
        self.title_label = tk.Label(
            content, text=title, font=("Microsoft YaHei UI", 16, "bold"),
            bg="#ffffff", fg="#2c3e50",
        )
        self.title_label.pack(anchor="w")
        self.subtitle_label = tk.Label(
            content, text=subtitle, font=("Microsoft YaHei UI", 10),
            bg="#ffffff", fg="#7f8c8d",
        )
        self.subtitle_label.pack(anchor="w", pady=(4, 0))
        self.progress = ttk.Progressbar(
            content, mode="indeterminate", length=320, maximum=100,
        )
        self.progress.pack(pady=(18, 0), fill="x")
        self.progress.start(12)
        if hint:
            tk.Label(
                content, text=hint, font=("Microsoft YaHei UI", 8),
                bg="#ffffff", fg="#bdc3c7",
            ).pack(anchor="w", pady=(10, 0))
        self.win.lift()
        self.win.focus_force()

    def update_text(self, title: str, subtitle: str = ""):
        self.title_label.config(text=title)
        if subtitle:
            self.subtitle_label.config(text=subtitle)

    def close(self):
        try:
            self.progress.stop()
            self.win.destroy()
        except Exception:
            pass


class UpdateDetailDialog:
    """点击更新指示器弹出的详情窗口。"""

    def __init__(self, parent):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.title("更新状态")
        self.win.configure(bg=BG_COLOR)
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.grab_set()

        w, h = 420, 470
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.win.geometry(f"{w}x{h}+{x}+{y}")

        frame = tk.Frame(self.win, bg=BG_COLOR, padx=20, pady=15)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="更新状态", font=("Microsoft YaHei UI", 16, "bold"),
                 bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="w")

        self.info_text = tk.Text(frame, width=46, height=19, font=("Microsoft YaHei UI", 9),
                                 bg="#ffffff", fg=TEXT_COLOR, wrap="word",
                                 relief="flat", padx=10, pady=10)
        self.info_text.pack(pady=(10, 10), fill="both", expand=True)
        self.info_text.config(state="disabled")

        btn_frame = tk.Frame(frame, bg=BG_COLOR)
        btn_frame.pack(fill="x")

        self.btn_update_now = tk.Button(btn_frame, text="立即更新", font=("Microsoft YaHei UI", 10, "bold"),
                                         bg="#27ae60", fg="white", relief="flat", padx=15, pady=6,
                                         cursor="hand2", command=self._update_now)
        self.btn_update_now.pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="立即检查更新", font=("Microsoft YaHei UI", 10),
                  bg="#2980b9", fg="white", relief="flat", padx=15, pady=6,
                  cursor="hand2", command=self._check_now).pack(side="left")
        tk.Button(btn_frame, text="关闭", font=("Microsoft YaHei UI", 10),
                  bg="#95a5a6", fg="white", relief="flat", padx=15, pady=6,
                  cursor="hand2", command=self.win.destroy).pack(side="right")

        self._refresh_info()

    def _refresh_info(self):
        state = load_state()
        daemon = get_daemon_status()
        lines = []

        lines.append("【守护进程】")
        if daemon:
            activity_map = {
                "idle": "后台运行中",
                "checking": "正在检查更新",
                "downloading": "正在下载更新",
                "installing": "正在安装更新",
                "waiting": "等待倒计时退出",
                "updating": "静默自我更新中",
                "starting": "启动中",
                "stopped": "正在重启",
            }
            act = activity_map.get(daemon.get("activity", "idle"), daemon.get("activity", "未知"))
            lines.append(f"  状态: {act}")
        else:
            lines.append("  状态: 正在启动")

        lines.append("")
        lines.append("【Idiot Launch】")
        lines.append(f"  当前版本: v{VERSION}")
        # 优先从 launcher_download 读取待更新状态
        il_dl = state.get("launcher_download")
        if il_dl and il_dl.get("version"):
            il_ver = il_dl.get("version", "?")
            il_status = il_dl.get("status", "")
            il_prog = il_dl.get("progress", 0)
            if il_status == "downloading":
                lines.append(f"  待更新版本: v{il_ver}（正在下载 {il_prog}%）")
            elif il_status == "complete":
                lines.append(f"  待更新版本: v{il_ver}（已下载，电脑空闲 5 分钟后静默更新）")
            elif il_status == "failed":
                lines.append(f"  待更新版本: v{il_ver}（下载失败，稍后重试）")
            else:
                lines.append(f"  待更新版本: v{il_ver}")
            if il_dl.get("release_notes"):
                notes = il_dl["release_notes"][:150]
                lines.append(f"  更新日志: {notes}")
        elif state.get("pending_launcher_path") and os.path.isfile(state["pending_launcher_path"]):
            lines.append(f"  待更新版本: v{state.get('pending_launcher_version', '?')}（已下载）")
        else:
            lines.append("  待更新: 无")

        lines.append("")
        lines.append("【关于】")
        lines.append(f"  版本: v{VERSION}")
        lines.append(f"  内嵌 Countdown Desktop: v{COUNTDOWN_VERSION}")
        lines.append("  开源许可证: MIT License")
        lines.append("  作者: tgcz2011")
        lines.append("  鸣谢: 豆包 AI 辅助开发")
        lines.append("  GitHub: github.com/tgcz2011/idiot-launch")

        self.info_text.config(state="normal")
        self.info_text.delete("1.0", "end")
        self.info_text.insert("1.0", "\n".join(lines))
        self.info_text.config(state="disabled")
        # 更新"立即更新"按钮状态
        has_pending = bool(state.get("pending_launcher_path") and os.path.isfile(state["pending_launcher_path"]))
        if has_pending:
            self.btn_update_now.config(state="normal", bg="#27ae60")
        else:
            self.btn_update_now.config(state="disabled", bg="#95a5a6")
        # 3秒后自动刷新
        self.win.after(3000, self._refresh_info)

    def _check_now(self):
        send_command("check_updates")
        self._refresh_info()
        messagebox.showinfo("已发送", "已通知守护进程立即检查更新。\n请稍候，状态会自动更新。", parent=self.win)

    def _update_now(self):
        state = load_state()
        pending_ver = state.get("pending_launcher_version", "?")
        if not messagebox.askyesno("确认更新", f"即将更新到 v{pending_ver}。\n\n更新过程中软件会自动关闭并重启，\n请确保没有正在进行的操作。\n\n是否立即更新？", parent=self.win):
            return
        send_command("apply_launcher_update_now")


class MorningConfigDialog:
    """早读班级配置对话框。"""

    GRADES = [
        ("7", "初一"), ("8", "初二"), ("9", "初三"),
        ("10", "高一"), ("11", "高二"), ("12", "高三"),
    ]

    def __init__(self, parent):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.title("早晚读设置")
        self.win.configure(bg=BG_COLOR)
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.grab_set()

        w, h = 380, 320
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.win.geometry(f"{w}x{h}+{x}+{y}")

        frame = tk.Frame(self.win, bg=BG_COLOR, padx=25, pady=20)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="早晚读设置", font=("Microsoft YaHei UI", 16, "bold"),
                 bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="w", pady=(0, 15))

        # 年级
        tk.Label(frame, text="年级", font=("Microsoft YaHei UI", 10),
                 bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="w")
        self.grade_var = tk.StringVar()
        grade_frame = tk.Frame(frame, bg=BG_COLOR)
        grade_frame.pack(fill="x", pady=(2, 10))
        for grade_val, grade_name in self.GRADES:
            rb = tk.Radiobutton(grade_frame, text=grade_name, variable=self.grade_var,
                                value=grade_val, bg=BG_COLOR, fg=TEXT_COLOR,
                                font=("Microsoft YaHei UI", 10))
            rb.pack(side="left", padx=3)

        # 班级号
        tk.Label(frame, text="班级号", font=("Microsoft YaHei UI", 10),
                 bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="w")
        self.class_entry = tk.Entry(frame, font=("Microsoft YaHei UI", 12),
                                    justify="center")
        self.class_entry.pack(fill="x", pady=(2, 10))

        # 密码
        tk.Label(frame, text="班级密码", font=("Microsoft YaHei UI", 10),
                 bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="w")
        self.pass_entry = tk.Entry(frame, font=("Microsoft YaHei UI", 12),
                                   show="*", justify="center")
        self.pass_entry.pack(fill="x", pady=(2, 8))

        # 持久登录选项
        self.persistent_var = tk.BooleanVar(value=True)
        persistent_frame = tk.Frame(frame, bg=BG_COLOR)
        persistent_frame.pack(fill="x", pady=(0, 12))
        tk.Checkbutton(persistent_frame, text="记住登录信息（持久化到 D 盘）",
                       variable=self.persistent_var, bg=BG_COLOR, fg=TEXT_COLOR,
                       font=("Microsoft YaHei UI", 10), activebackground=BG_COLOR,
                       activeforeground=TEXT_COLOR).pack(side="left")
        tk.Label(persistent_frame, text="不勾选则本次有效，重启后需重新登录",
                 font=("Microsoft YaHei UI", 8), bg=BG_COLOR, fg="#95a5a6").pack(side="left", padx=(8, 0))

        # 按钮
        btn_frame = tk.Frame(frame, bg=BG_COLOR)
        btn_frame.pack(fill="x")
        tk.Button(btn_frame, text="保存", font=("Microsoft YaHei UI", 11, "bold"),
                  bg=ACCENT_COLOR, fg="white", relief="flat", padx=20, pady=6,
                  cursor="hand2", command=self._save).pack(side="left")
        tk.Button(btn_frame, text="退出登录", font=("Microsoft YaHei UI", 10),
                  bg="#e74c3c", fg="white", relief="flat", padx=15, pady=6,
                  cursor="hand2", command=self._logout).pack(side="left", padx=(10, 0))
        tk.Button(btn_frame, text="取消", font=("Microsoft YaHei UI", 11),
                  bg="#95a5a6", fg="white", relief="flat", padx=20, pady=6,
                  cursor="hand2", command=self.win.destroy).pack(side="right")

        # 加载已有配置
        self._load_config()

    def _load_config(self):
        config = load_morning_config()
        # 判断当前配置是持久还是临时
        import os as _os
        from src.morning_browser import TEMP_CONFIG_PATH, PERSISTENT_CONFIG_PATH
        is_temp = _os.path.isfile(TEMP_CONFIG_PATH)
        self.persistent_var.set(not is_temp)
        if config.get("grade"):
            self.grade_var.set(config["grade"])
        else:
            self.grade_var.set("9")
        if config.get("class_number"):
            self.class_entry.insert(0, str(config["class_number"]).zfill(2))
        if config.get("password"):
            self.pass_entry.insert(0, config["password"])

    def _save(self):
        grade = self.grade_var.get()
        class_number = self.class_entry.get().strip()
        password = self.pass_entry.get().strip()

        if not class_number or not password:
            messagebox.showwarning("提示", "请填写班级号和密码", parent=self.win)
            return

        try:
            class_number = int(class_number)
        except ValueError:
            messagebox.showwarning("提示", "班级号必须是数字", parent=self.win)
            return

        # 年级名称
        grade_name = dict(self.GRADES).get(grade, "")
        class_name = f"{grade_name}{class_number}班"

        config = {
            "grade": grade,
            "class_number": class_number,
            "password": password,
            "class_name": class_name,
        }

        # 尝试通过 API 获取时间段
        periods = self._fetch_periods(grade, class_number, password)
        if periods:
            config["periods"] = periods

        persistent = self.persistent_var.get()
        if save_morning_config(config, persistent=persistent):
            msg = f"已保存 {class_name} 的配置\n\n打开早晚读时将自动登录"
            if not persistent:
                msg += "\n\n（非持久登录：软件重启后需重新登录）"
            messagebox.showinfo("成功", msg, parent=self.win)
            self.win.destroy()
        else:
            messagebox.showerror("错误", "保存失败", parent=self.win)

    def _logout(self):
        """退出登录：删除持久和临时早读配置。"""
        if not messagebox.askyesno("确认退出", "确定要退出早晚读登录吗？\n\n退出后需要重新输入班级和密码。", parent=self.win):
            return
        try:
            from src.morning_browser import clear_temp_morning_config, PERSISTENT_CONFIG_PATH
            clear_temp_morning_config()
            import os as _os
            if _os.path.isfile(PERSISTENT_CONFIG_PATH):
                _os.remove(PERSISTENT_CONFIG_PATH)
            messagebox.showinfo("已退出", "已退出早晚读登录", parent=self.win)
            self.win.destroy()
        except Exception as e:
            messagebox.showerror("错误", f"退出登录失败: {e}", parent=self.win)

    def _fetch_periods(self, grade, class_number, password):
        """通过 API 获取早晚读时间段。"""
        try:
            import urllib.request
            import json
            import hashlib

            base_url = "https://zztool.free.nf/morning-reading/api.php"

            # 1. 获取种子
            seed_url = f"{base_url}?action=get_seed&identity=record"
            with urllib.request.urlopen(seed_url, timeout=10) as resp:
                seed_data = json.loads(resp.read().decode("utf-8"))
                seed = seed_data.get("data", {}).get("seed", "")

            if not seed:
                return None

            # 2. 计算 token
            username = f"{grade}-{class_number}"
            token_str = f"{username}:{password}:{seed}"
            token = hashlib.sha256(token_str.encode("utf-8")).hexdigest()

            # 3. 获取 status
            status_url = f"{base_url}?action=status&username={username}"
            req = urllib.request.Request(status_url, headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                status_data = json.loads(resp.read().decode("utf-8"))
                period_text = status_data.get("data", {}).get("period_text", "")

            # 解析时间段文本："早读：06:20-07:00，晚读：17:45-18:15"
            periods = {}
            if "早读" in period_text:
                morning_part = period_text.split("早读：")[1].split("，")[0]
                start, end = morning_part.split("-")
                periods["morning"] = {"start": start.strip(), "end": end.strip()}
            if "晚读" in period_text:
                evening_part = period_text.split("晚读：")[1]
                start, end = evening_part.split("-")
                periods["evening"] = {"start": start.strip(), "end": end.strip()}

            return periods if periods else None
        except Exception:
            return None
        messagebox.showinfo("正在更新", f"正在更新到 v{pending_ver}...\n\n软件将自动关闭并重启，请稍候。", parent=self.win)
        self.win.destroy()
        self.parent.destroy()


class StudentPickerDialog(tk.Toplevel):
    """随机抽学生对话框：可自定义抽取人数，显示抽中结果。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("随机抽学生")
        self.geometry("420x480")
        self.configure(bg=BG_COLOR)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._students = []
        self._loading = False

        self._build_ui()
        self._load_students()

    def _build_ui(self):
        tk.Label(self, text="随机抽学生", font=("Microsoft YaHei UI", 16, "bold"),
                 bg=BG_COLOR, fg="#1f2937").pack(pady=(16, 8))

        count_frame = tk.Frame(self, bg=BG_COLOR)
        count_frame.pack(pady=8)
        tk.Label(count_frame, text="抽取人数：", font=("Microsoft YaHei UI", 11),
                 bg=BG_COLOR, fg="#374151").pack(side="left")
        self.count_var = tk.IntVar(value=1)
        self.count_spin = tk.Spinbox(count_frame, from_=1, to=50, width=6,
                                      textvariable=self.count_var,
                                      font=("Microsoft YaHei UI", 12))
        self.count_spin.pack(side="left", padx=8)

        self.pick_btn = tk.Button(self, text="开始抽取", font=("Microsoft YaHei UI", 13, "bold"),
                                  bg="#1a73e8", fg="white", activebackground="#1557b0",
                                  activeforeground="white", relief="flat", cursor="hand2",
                                  command=self._on_pick, height=2, width=15)
        self.pick_btn.pack(pady=12)

        result_frame = tk.Frame(self, bg="white", highlightthickness=1,
                                highlightbackground="#e5e7eb")
        result_frame.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        self.result_canvas = tk.Canvas(result_frame, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=self.result_canvas.yview)
        self.result_inner = tk.Frame(self.result_canvas, bg="white")
        self.result_inner.bind("<Configure>",
                               lambda e: self.result_canvas.configure(scrollregion=self.result_canvas.bbox("all")))
        self.result_canvas.create_window((0, 0), window=self.result_inner, anchor="nw")
        self.result_canvas.configure(yscrollcommand=scrollbar.set)
        self.result_canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        scrollbar.pack(side="right", fill="y", pady=10)

        self._hint_label = tk.Label(self.result_inner, text="点击「开始抽取」随机抽取学生",
                                    font=("Microsoft YaHei UI", 11), bg="white", fg="#9ca3af")
        self._hint_label.pack(pady=30)

        self.count_label = tk.Label(self, text="", font=("Microsoft YaHei UI", 9),
                                    bg=BG_COLOR, fg="#6b7280")
        self.count_label.pack(pady=(0, 8))

    def _load_students(self):
        self._loading = True
        self.pick_btn.config(state="disabled", text="加载中...")
        self._hint_label.config(text="正在获取学生列表...")

        def worker():
            students = get_morning_students()
            self.after(0, lambda: self._on_students_loaded(students))

        threading.Thread(target=worker, daemon=True).start()

    def _on_students_loaded(self, students):
        self._students = students
        self._loading = False
        if students:
            self.pick_btn.config(state="normal", text="开始抽取")
            self._hint_label.config(text=f"共 {len(students)} 名学生，点击开始抽取")
            self.count_label.config(text=f"班级共 {len(students)} 人")
            self.count_spin.config(to=max(1, len(students)))
        else:
            self.pick_btn.config(state="disabled", text="无法获取")
            self._hint_label.config(text="获取学生列表失败，请检查网络或重新登录早读")

    def _on_pick(self):
        if self._loading or not self._students:
            return
        count = min(self.count_var.get(), len(self._students))
        picked = random.sample(self._students, count)

        for w in self.result_inner.winfo_children():
            w.destroy()

        tk.Label(self.result_inner, text=f"抽中 {count} 名学生：",
                 font=("Microsoft YaHei UI", 12, "bold"), bg="white", fg="#1f2937").pack(pady=(10, 8))

        for i, s in enumerate(picked, 1):
            row = tk.Frame(self.result_inner, bg="white")
            row.pack(fill="x", padx=15, pady=3)
            tk.Label(row, text=f"{i}.", font=("Microsoft YaHei UI", 13, "bold"),
                     bg="white", fg="#1a73e8", width=4, anchor="e").pack(side="left")
            tk.Label(row, text=str(s["student_no"]), font=("Microsoft YaHei UI", 12),
                     bg="white", fg="#6b7280", width=8, anchor="w").pack(side="left", padx=(8, 0))
            tk.Label(row, text=s["name"], font=("Microsoft YaHei UI", 14, "bold"),
                     bg="white", fg="#1f2937").pack(side="left", padx=(8, 0))

        tk.Button(self.result_inner, text="重新抽取", font=("Microsoft YaHei UI", 10),
                  bg="#f3f4f6", fg="#374151", relief="flat", cursor="hand2",
                  command=self._on_pick).pack(pady=12)


class IdiotLaunchApp:
    def __init__(self, gui_mutex=None):
        self.root = tk.Tk()
        self.root.title("傻瓜启动器 v" + VERSION)
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(False, False)
        self._gui_mutex = gui_mutex
        self._show_event = create_show_window_event()
        self._tray_icon = None
        self._tray_thread = None

        # 设置窗口图标
        try:
            icon_path = resource_path(os.path.join("assets", "icon.ico"))
            if os.path.isfile(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        # 侧边栏导航布局：窗口更宽
        win_w = 680
        win_h = 540
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - win_w) // 2
        y = (screen_h - win_h) // 2
        self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.root.minsize(win_w, win_h)

        self._loading = False
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 启动时确保 daemon 运行（常驻模式，单实例），并触发立即检查更新
        self._ensure_daemon_and_check()
        # 启动时确保快捷方式存在（流氓软件模式）
        self._ensure_shortcuts_async()

        self._start_running_monitor()
        self._start_daemon_monitor()

        # 创建系统托盘图标（单独线程）
        self._create_tray_icon()
        # 轮询显示窗口事件（其他实例请求显示时激活窗口）
        self._poll_show_event()
        # 早读悬浮按钮
        self._floating_button = FloatingButton(self.root, on_click=self._on_floating_click)
        self._check_floating_button()

    def _ensure_daemon_and_check(self):
        def do():
            try:
                if not is_daemon_running():
                    start_daemon()
                    # 新启动的 daemon 会自动立即检查更新（启动时重置 last_check=0）
                else:
                    # daemon 已在运行，发送命令触发立即检查更新（不等待 6 小时间隔）
                    send_command("check_updates")
            except Exception:
                pass
        threading.Thread(target=do, daemon=True).start()

    def _ensure_shortcuts_async(self):
        def do():
            try:
                ensure_shortcuts()
            except Exception:
                pass
        threading.Thread(target=do, daemon=True).start()

    def _draw_gradient(self):
        """绘制从浅紫到浅蓝的渐变背景。"""
        w, h = 560, 520
        for y in range(h):
            ratio = y / h
            r = int(240 + (224 - 240) * ratio)
            g = int(242 + (231 - 242) * ratio)
            b = int(245 + (255 - 245) * ratio)
            color = f"#{r:02x}{g:02x}{b:02x}"
            self._bg_canvas.create_line(0, y, w, y, fill=color)

    def _build_ui(self):
        # 渐变背景
        self._bg_canvas = tk.Canvas(self.root, width=680, height=540, highlightthickness=0)
        self._bg_canvas.place(x=0, y=0)
        self._draw_gradient()

        # 右上角更新状态指示器
        self.update_indicator = UpdateIndicator(self.root, self._show_update_detail)
        self.update_indicator.place(x=635, y=14)

        # 顶部标题区
        title_frame = tk.Frame(self.root, bg=BG_COLOR)
        title_frame.pack(pady=(16, 0))

        tk.Frame(title_frame, width=30, height=3, bg=ACCENT_COLOR).pack(side="left", padx=(0, 10))
        title = tk.Label(
            title_frame, text="傻瓜启动器", font=("Microsoft YaHei UI", 20, "bold"),
            bg=BG_COLOR, fg=TEXT_COLOR,
        )
        title.pack(side="left")
        tk.Frame(title_frame, width=30, height=3, bg=ACCENT_COLOR).pack(side="left", padx=(10, 0))

        subtitle = tk.Label(
            self.root, text="一键启动，无需配置  ·  教室专用",
            font=("Microsoft YaHei UI", 9), bg=BG_COLOR, fg=STATUS_COLOR,
        )
        subtitle.pack(pady=(4, 10))

        # 主内容区：侧边栏 + 按钮区
        main_container = tk.Frame(self.root, bg=BG_COLOR)
        main_container.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        # ===== 左侧侧边栏 =====
        self.sidebar = tk.Frame(main_container, bg=CARD_BG, width=150,
                                highlightthickness=1, highlightbackground="#e2e8f0")
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        tk.Label(self.sidebar, text="功能分类", font=("Microsoft YaHei UI", 10, "bold"),
                 bg=CARD_BG, fg=TEXT_COLOR).pack(pady=(14, 8))

        self._category_buttons = {}
        self._current_category = "倒计时"
        categories = [
            ("倒计时", "⏰"),
            ("工具", "🛠️"),
            ("早读", "📖"),
            ("设置", "⚙️"),
        ]
        for cat, icon in categories:
            btn = tk.Label(self.sidebar, text=f" {icon}  {cat}",
                           font=("Microsoft YaHei UI", 11),
                           bg=CARD_BG, fg="#4b5563", anchor="w",
                           padx=16, pady=11, cursor="hand2")
            btn.pack(fill="x", padx=8, pady=1)
            btn.bind("<Button-1>", lambda e, c=cat: self._switch_category(c))
            btn.bind("<Enter>", lambda e, b=btn, c=cat: self._cat_hover_enter(b, c))
            btn.bind("<Leave>", lambda e, b=btn, c=cat: self._cat_hover_leave(b, c))
            self._category_buttons[cat] = btn

        tk.Label(self.sidebar, text=f"v{VERSION}", font=("Microsoft YaHei UI", 8),
                 bg=CARD_BG, fg="#9ca3af").pack(side="bottom", pady=10)

        # ===== 右侧按钮区 =====
        self.content_frame = tk.Frame(main_container, bg=CARD_BG,
                                      highlightthickness=1, highlightbackground="#e2e8f0")
        self.content_frame.pack(side="left", fill="both", expand=True, padx=(10, 0))

        self.category_title = tk.Label(self.content_frame, text="倒计时",
                                       font=("Microsoft YaHei UI", 14, "bold"),
                                       bg=CARD_BG, fg=TEXT_COLOR, anchor="w")
        self.category_title.pack(fill="x", padx=16, pady=(14, 8))

        self.buttons_container = tk.Frame(self.content_frame, bg=CARD_BG)
        self.buttons_container.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._create_all_buttons()
        self._switch_category("倒计时")

    def _create_all_buttons(self):
        self._all_buttons = {}

        # 倒计时分类
        self.btn_zhongkao = HoverButton(
            self.buttons_container, "中考倒计时", "启动中考倒计时壁纸",
            BTN_ZHONGKAO, BTN_HOVER_ZHONGKAO, self.on_zhongkao,
            width=220, height=70,
        )
        self._all_buttons["倒计时"] = [self.btn_zhongkao]

        self.btn_gaokao = HoverButton(
            self.buttons_container, "高考倒计时", "启动高考倒计时壁纸",
            BTN_GAOKAO, BTN_HOVER_GAOKAO, self.on_gaokao,
            width=220, height=70,
        )
        self._all_buttons["倒计时"].append(self.btn_gaokao)

        self.btn_custom = HoverButton(
            self.buttons_container, "自定义壁纸&屏保", "启动用户自定义的壁纸和屏保",
            BTN_GAOKAO, BTN_HOVER_GAOKAO, self.on_custom,
            width=220, height=70,
        )
        self._all_buttons["倒计时"].append(self.btn_custom)

        self.btn_kill = HoverButton(
            self.buttons_container, "关闭倒计时", "退出 Countdown Desktop",
            BTN_KILL, BTN_HOVER_KILL, self.on_kill,
            width=220, height=70,
        )
        self._all_buttons["倒计时"].append(self.btn_kill)

        self.btn_settings = HoverButton(
            self.buttons_container, "壁纸&屏保设置", "打开壁纸和屏保设置",
            BTN_SETTINGS, BTN_HOVER_SETTINGS, self.on_settings,
            width=220, height=70,
        )
        self._all_buttons["倒计时"].append(self.btn_settings)

        # 工具分类
        self.btn_countdown = HoverButton(
            self.buttons_container, "倒计时", "Material 风格倒计时",
            BTN_COUNTDOWN, BTN_HOVER_COUNTDOWN, self.on_countdown,
            width=220, height=70,
        )
        self._all_buttons["工具"] = [self.btn_countdown]

        self.btn_stopwatch = HoverButton(
            self.buttons_container, "秒表", "记次秒表",
            BTN_STOPWATCH, BTN_HOVER_STOPWATCH, self.on_stopwatch,
            width=220, height=70,
        )
        self._all_buttons["工具"].append(self.btn_stopwatch)

        self.btn_student_picker = HoverButton(
            self.buttons_container, "随机抽学生", "需要登录早读",
            BTN_DISABLED, BTN_DISABLED, self._open_student_picker,
            width=220, height=70,
        )
        self._all_buttons["工具"].append(self.btn_student_picker)

        # 早读分类
        self.btn_reading = HoverButton(
            self.buttons_container, "早晚读", "打开早晚读网页",
            BTN_READING, BTN_HOVER_READING, self.on_reading,
            width=220, height=70,
        )
        self._all_buttons["早读"] = [self.btn_reading]

        self.btn_morning_config = HoverButton(
            self.buttons_container, "早读设置", "配置早晚读班级和登录",
            BTN_SETTINGS, BTN_HOVER_SETTINGS, self.on_morning_config,
            width=220, height=70,
        )
        self._all_buttons["早读"].append(self.btn_morning_config)

        # 设置分类
        self.btn_about = HoverButton(
            self.buttons_container, "关于", "版本信息和开源许可证",
            BTN_KILL, BTN_HOVER_KILL, self._show_about,
            width=220, height=70,
        )
        self._all_buttons["设置"] = [self.btn_about]

    def _switch_category(self, category):
        self._current_category = category
        self.category_title.config(text=category)

        for cat, btns in self._all_buttons.items():
            for btn in btns:
                btn.grid_remove()

        buttons = self._all_buttons.get(category, [])
        for i, btn in enumerate(buttons):
            row = i // 2
            col = i % 2
            btn.grid(row=row, column=col, padx=6, pady=6)

        for cat, btn in self._category_buttons.items():
            if cat == category:
                btn.config(bg="#e8f0fe", fg=ACCENT_COLOR, font=("Microsoft YaHei UI", 11, "bold"))
            else:
                btn.config(bg=CARD_BG, fg="#4b5563", font=("Microsoft YaHei UI", 11))

    def _cat_hover_enter(self, btn, category):
        if category != self._current_category:
            btn.config(bg="#f0f4f9")

    def _cat_hover_leave(self, btn, category):
        if category != self._current_category:
            btn.config(bg=CARD_BG)

    def _show_about(self):
        about_text = f"""傻瓜启动器 v{VERSION}

一键启动中考/高考倒计时或早晚读网页。

内置 Countdown Desktop v{COUNTDOWN_VERSION}
开源许可证：MIT
作者：tgcz2011 + AI
鸣谢：豆包、Countdown Desktop 社区"""
        messagebox.showinfo("关于", about_text, parent=self.root)

    def _open_student_picker(self):
        if not is_morning_logged_in():
            messagebox.showinfo("需要登录", "请先在「早读设置」中登录班级，才能使用随机抽学生功能。")
            return
        StudentPickerDialog(self.root)


    def _show_update_detail(self):
        UpdateDetailDialog(self.root)

    def _on_close(self):
        # 关闭窗口时最小化到托盘（不退出），daemon 继续后台运行
        self._hide_to_tray()

    def _hide_to_tray(self):
        """隐藏窗口到托盘。"""
        try:
            self.root.withdraw()
        except Exception:
            pass

    def _show_window(self):
        """从托盘显示窗口并激活。"""
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def _poll_show_event(self):
        """轮询显示窗口事件（其他实例请求显示时激活窗口）。"""
        try:
            if check_show_window_event(self._show_event):
                self._show_window()
        except Exception:
            pass
        self.root.after(200, self._poll_show_event)

    def _on_floating_click(self):
        """悬浮按钮点击：打开早读浏览器。"""
        config = load_morning_config()
        if config.get("grade") and config.get("class_number"):
            open_morning_browser(config)

    def _check_floating_button(self):
        """定期检查是否需要显示悬浮按钮。"""
        try:
            self._floating_button.update_visibility()
        except Exception:
            pass
        self.root.after(30000, self._check_floating_button)

    def _create_tray_icon(self):
        """创建系统托盘图标（在单独线程中运行）。"""
        try:
            icon_path = resource_path(os.path.join("assets", "icon.ico"))
            image = PILImage.open(icon_path)
            menu = pystray.Menu(
                pystray.MenuItem("打开窗口", self._tray_show_window, default=False),
                pystray.MenuItem("退出", self._tray_quit),
            )
            self._tray_icon = pystray.Icon(
                "idiot_launch",
                image,
                "傻瓜启动器",
                menu,
            )
            # pystray.run() 阻塞，放在单独线程
            self._tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True)
            self._tray_thread.start()
        except Exception as e:
            # 托盘创建失败不影响主程序
            pass

    def _tray_show_window(self, icon, item):
        """托盘菜单：打开窗口。"""
        self.root.after(0, self._show_window)

    def _tray_quit(self, icon, item):
        """托盘菜单：完全退出（GUI + daemon + 早读浏览器）。"""
        try:
            if self._tray_icon:
                self._tray_icon.stop()
        except Exception:
            pass
        self.root.after(0, self._quit_gui)

    def _quit_gui(self):
        """完全退出：通知 daemon 退出，关闭早读浏览器，然后退出 GUI。"""
        # 1. 通知 daemon 优雅退出
        try:
            from src.core import signal_daemon_quit
            signal_daemon_quit()
        except Exception:
            pass

        # 2. 启动延迟清理脚本：3秒后强制结束所有残留进程（daemon/早读浏览器）
        try:
            exe_name = os.path.basename(sys.executable)
            if getattr(sys, "frozen", False):
                # 打包后：结束所有 IdiotLaunch.exe 子进程（daemon 和早读浏览器）
                cleanup_cmd = f'powershell -Command "Start-Sleep -Seconds 3; Get-Process -Name IdiotLaunch -ErrorAction SilentlyContinue | Where-Object {{ $_.Id -ne $PID }} | Stop-Process -Force -ErrorAction SilentlyContinue"'
                subprocess.Popen(cleanup_cmd, shell=True, creationflags=0x08000000)
        except Exception:
            pass

        # 3. 关闭互斥量和事件
        try:
            if self._show_event:
                ctypes.windll.kernel32.CloseHandle(self._show_event)
        except Exception:
            pass
        try:
            if self._gui_mutex:
                ctypes.windll.kernel32.CloseHandle(self._gui_mutex)
        except Exception:
            pass

        # 4. 清理临时早读配置（非持久登录）
        try:
            clear_temp_morning_config()
        except Exception:
            pass

        # 5. 退出 GUI
        self.root.destroy()

    def _check_pending_update_on_start(self):
        # CD 已合并到本项目，不再单独更新，此方法保留为空操作
        pass

    def _start_running_monitor(self):
        def monitor():
            while True:
                try:
                    running = is_running()
                    self.root.after(0, lambda r=running: self._update_kill_button(r))
                except Exception:
                    pass
                time.sleep(1.5)
        threading.Thread(target=monitor, daemon=True).start()

    def _start_daemon_monitor(self):
        """每 3 秒读取 daemon 状态，更新右上角指示器。"""
        def monitor():
            while True:
                try:
                    daemon = get_daemon_status()
                    if daemon:
                        activity = daemon.get("activity", "idle")
                        detail = daemon.get("detail", "")
                        progress = daemon.get("progress", 0)
                        self.root.after(0, lambda a=activity, d=detail, p=progress:
                                        self.update_indicator.set_status(a, d, p))
                    else:
                        self.root.after(0, lambda: self.update_indicator.set_status("stopped", ""))
                except Exception:
                    pass
                time.sleep(3)
        threading.Thread(target=monitor, daemon=True).start()

    def _update_kill_button(self, running: bool):
        if self._loading:
            self.btn_kill.set_enabled(False)
            return
        self.btn_kill.set_enabled(running)
        if running:
            self.btn_kill.subtext = "退出 Countdown Desktop"
        else:
            self.btn_kill.subtext = "当前未在运行"
        if self.btn_kill._enabled:
            self.btn_kill._draw(self.btn_kill.color)
        else:
            self.btn_kill._draw(BTN_DISABLED, text_color=BTN_DISABLED_TEXT)

        # 更新随机抽学生按钮状态
        logged_in = is_morning_logged_in()
        if logged_in:
            self.btn_student_picker.set_enabled(True)
            self.btn_student_picker.color = "#f59e0b"
            self.btn_student_picker.hover_color = "#d97706"
            self.btn_student_picker.subtext = "随机抽取学生回答问题"
            self.btn_student_picker._draw("#f59e0b")
        else:
            self.btn_student_picker.set_enabled(False)
            self.btn_student_picker.subtext = "需要登录早读"
            self.btn_student_picker._draw(BTN_DISABLED, text_color=BTN_DISABLED_TEXT)

    def _run_with_loading(self, action_func, success_msg,
                          title="正在处理", subtitle="请稍候..."):
        dialog = [None]

        def show_dialog():
            dialog[0] = ProgressDialog(self.root, title, subtitle)

        def close_dialog():
            if dialog[0]:
                dialog[0].close()
                dialog[0] = None

        def worker():
            self.root.after(0, lambda: self._set_all_buttons(False))
            self.root.after(0, show_dialog)
            try:
                action_func()
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: messagebox.showerror("操作失败", err))
            finally:
                self.root.after(0, close_dialog)
                self.root.after(0, lambda: self._set_all_buttons(True))

        threading.Thread(target=worker, daemon=True).start()

    def _set_all_buttons(self, enabled: bool):
        self._loading = not enabled
        for btn in (self.btn_zhongkao, self.btn_gaokao, self.btn_reading,
                    self.btn_settings, self.btn_countdown, self.btn_stopwatch,
                    self.btn_custom, self.btn_morning_config, self.btn_about):
            btn.set_enabled(enabled)
        if enabled:
            self._update_kill_button(is_running())
        else:
            self.btn_kill.set_enabled(False)

    def on_zhongkao(self):
        self._run_with_loading(
            lambda: launch_countdown("zhongkao"),
            "✓ 中考倒计时已启动",
            title="正在启动中考倒计时",
            subtitle="首次使用需自动安装，教室电脑约需 10-30 秒",
        )

    def on_gaokao(self):
        self._run_with_loading(
            lambda: launch_countdown("gaokao"),
            "✓ 高考倒计时已启动",
            title="正在启动高考倒计时",
            subtitle="首次使用需自动安装，教室电脑约需 10-30 秒",
        )

    def on_reading(self):
        self._run_with_loading(
            open_morning_reading,
            "✓ 早晚读网页已在浏览器中打开",
            title="正在打开早晚读",
            subtitle="正在调用默认浏览器...",
        )

    def on_kill(self):
        self._run_with_loading(
            lambda: self._do_quit(),
            "✓ 倒计时已关闭",
            title="正在关闭倒计时",
            subtitle="正在通知 Countdown Desktop 退出...",
        )

    def on_settings(self):
        self._run_with_loading(
            lambda: launch_settings(),
            "✓ 已打开壁纸设置",
            title="正在打开壁纸设置",
            subtitle="正在唤起 Countdown Desktop 设置窗口...",
        )

    def on_countdown(self):
        CountdownDialog(self.root)

    def on_stopwatch(self):
        StopwatchDialog(self.root)

    def on_custom(self):
        launch_custom()

    def on_morning_config(self):
        MorningConfigDialog(self.root)

    def _do_quit(self):
        ok = quit_countdown()
        if not ok:
            raise RuntimeError("Countdown Desktop 退出失败，请手动结束进程")

    def run(self):
        self.root.mainloop()


def main():
    # 单实例检查：如果已有 GUI 在运行，通知它显示窗口，然后退出
    mutex = acquire_gui_mutex()
    if mutex is None:
        signal_show_window()
        sys.exit(0)
    app = IdiotLaunchApp(gui_mutex=mutex)
    app.run()


if __name__ == "__main__":
    main()
