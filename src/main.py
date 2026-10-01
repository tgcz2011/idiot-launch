"""
main.py — Idiot Launch 主入口与 GUI
v1.3.0.0: 图标、右上角更新状态指示器、daemon 常驻启动、快捷方式自动重建。
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import random
import time
import sys
import os
import ctypes

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

        # 标题装饰线
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

        # 侧边栏标题
        tk.Label(self.sidebar, text="功能分类", font=("Microsoft YaHei UI", 10, "bold"),
                 bg=CARD_BG, fg=TEXT_COLOR).pack(pady=(14, 8))

        # 分类按钮
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

        # 侧边栏底部版本
        tk.Label(self.sidebar, text=f"v{VERSION}", font=("Microsoft YaHei UI", 8),
                 bg=CARD_BG, fg="#9ca3af").pack(side="bottom", pady=10)

        # ===== 右侧按钮区 =====
        self.content_frame = tk.Frame(main_container, bg=CARD_BG,
                                      highlightthickness=1, highlightbackground="#e2e8f0")
        self.content_frame.pack(side="left", fill="both", expand=True, padx=(10, 0))

        # 分类标题
        self.category_title = tk.Label(self.content_frame, text="倒计时",
                                       font=("Microsoft YaHei UI", 14, "bold"),
                                       bg=CARD_BG, fg=TEXT_COLOR, anchor="w")
        self.category_title.pack(fill="x", padx=16, pady=(14, 8))

        # 按钮容器
        self.buttons_container = tk.Frame(self.content_frame, bg=CARD_BG)
        self.buttons_container.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # 创建所有按钮（先创建，再根据分类显示/隐藏）
        self._create_all_buttons()
        self._switch_category("倒计时")

    def _create_all_buttons(self):
        """创建所有按钮，存储到字典中，根据分类显示。"""
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
        """切换分类，显示对应按钮。"""
        self._current_category = category
        self.category_title.config(text=category)

        # 隐藏所有按钮
        for cat, btns in self._all_buttons.items():
            for btn in btns:
                btn.grid_remove()

        # 显示当前分类的按钮（2列网格）
        buttons = self._all_buttons.get(category, [])
        for i, btn in enumerate(buttons):
            row = i // 2
            col = i % 2
            btn.grid(row=row, column=col, padx=6, pady=6)

        # 更新侧边栏按钮样式
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
        """显示关于对话框。"""
        about_text = f"""傻瓜启动器 v{VERSION}

一键启动中考/高考倒计时或早晚读网页。

内置 Countdown Desktop v{COUNTDOWN_VERSION}
开源许可证：MIT
作者：tgcz2011 + AI
鸣谢：豆包、Countdown Desktop 社区"""
        messagebox.showinfo("关于", about_text, parent=self.root)

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

    def _open_student_picker(self):
        """打开随机抽学生对话框。"""
        if not is_morning_logged_in():
            messagebox.showinfo("需要登录", "请先在「早读设置」中登录班级，才能使用随机抽学生功能。")
            return
        StudentPickerDialog(self.root)

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
