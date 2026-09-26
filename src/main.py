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

from src.core import (
    launch_countdown,
    launch_settings,
    open_morning_reading,
    quit_countdown,
    find_installed_path,
    is_running,
    start_daemon,
    is_daemon_running,
    install_pending_if_idle,
    has_pending_update,
    ensure_shortcuts,
    get_daemon_status,
    load_state,
    send_command,
    resource_path,
    EMBEDDED_VERSION,
    APP_NAME,
    LAUNCHER_VERSION,
    LAUNCHER_INSTALL_EXE,
    LAUNCHER_INSTALL_DIR,
)

VERSION = LAUNCHER_VERSION

BG_COLOR = "#f5f7fa"
BTN_ZHONGKAO = "#e74c3c"
BTN_GAOKAO = "#2980b9"
BTN_READING = "#27ae60"
BTN_KILL = "#5d6d7e"
BTN_DISABLED = "#bdc3c7"
BTN_DISABLED_TEXT = "#ecf0f1"
BTN_HOVER_ZHONGKAO = "#c0392b"
BTN_HOVER_GAOKAO = "#1f6fa0"
BTN_HOVER_READING = "#1e8449"
BTN_HOVER_KILL = "#4a5568"
BTN_SETTINGS = "#8e44ad"
BTN_HOVER_SETTINGS = "#6c3483"
TEXT_COLOR = "#2c3e50"
STATUS_COLOR = "#7f8c8d"

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
        super().__init__(parent, width=width, height=height, bg=BG_COLOR,
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
        r = 16
        w, h = self.width, self.height
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
        if (state.get("pending_installer") and state.get("download_complete")) or \
           state.get("pending_launcher_path"):
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
        top_bar = tk.Frame(self.win, bg="#2980b9", height=6)
        top_bar.pack(fill="x", side="top")
        content = tk.Frame(self.win, bg="#ffffff", padx=30, pady=20)
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

        w, h = 420, 380
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.win.geometry(f"{w}x{h}+{x}+{y}")

        frame = tk.Frame(self.win, bg=BG_COLOR, padx=20, pady=15)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="更新状态", font=("Microsoft YaHei UI", 16, "bold"),
                 bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="w")

        self.info_text = tk.Text(frame, width=46, height=14, font=("Microsoft YaHei UI", 9),
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
                "stopped": "已停止",
            }
            act = activity_map.get(daemon.get("activity", "idle"), daemon.get("activity", "未知"))
            lines.append(f"  状态: {act}")
            if daemon.get("detail"):
                lines.append(f"  详情: {daemon['detail']}")
            lines.append(f"  PID: {daemon.get('pid', '?')}")
        else:
            lines.append("  状态: 未运行（关闭窗口后自动启动）")

        lines.append("")
        lines.append("【Countdown Desktop】")
        local_ver = "未知"
        try:
            from src.core import get_installed_version
            v = get_installed_version()
            if v:
                local_ver = v
        except Exception:
            pass
        lines.append(f"  当前版本: {local_ver}")
        lines.append(f"  内嵌版本: {EMBEDDED_VERSION}")
        if state.get("pending_installer") and state.get("download_complete"):
            lines.append(f"  待安装版本: v{state.get('pending_version', '?')}")
            lines.append(f"  安装包: {os.path.basename(state['pending_installer'])}")
            if state.get("release_notes"):
                notes = state["release_notes"][:200]
                lines.append(f"  更新日志: {notes}")
        else:
            lines.append("  待安装更新: 无")

        lines.append("")
        lines.append("【Idiot Launch】")
        lines.append(f"  当前版本: v{VERSION}")
        if state.get("pending_launcher_path") and os.path.isfile(state["pending_launcher_path"]):
            lines.append(f"  待更新版本: v{state.get('pending_launcher_version', '?')}")
            lines.append("  (电脑空闲 10 分钟后静默更新)")
            if state.get("launcher_release_notes"):
                notes = state["launcher_release_notes"][:200]
                lines.append(f"  更新日志: {notes}")
        elif daemon and daemon.get("activity") == "downloading":
            lines.append(f"  正在下载更新: {daemon.get('detail', '下载中...')}")
            if daemon.get("progress"):
                lines.append(f"  进度: {daemon['progress']}%")
        else:
            lines.append("  待更新: 无")

        lines.append("")
        lines.append("【下载源】")
        lines.append("  GitHub 直连 → gh-proxy.com → ghfast.top → ghproxy.net")
        lines.append("  超时: 15 分钟 / 源，自动 fallback，最多重试 3 轮")

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
        messagebox.showinfo("正在更新", f"正在更新到 v{pending_ver}...\n\n软件将自动关闭并重启，请稍候。", parent=self.win)
        self.win.destroy()
        self.parent.destroy()


class IdiotLaunchApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("傻瓜启动器 v" + VERSION)
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(False, False)

        # 设置窗口图标
        try:
            icon_path = resource_path(os.path.join("assets", "icon.ico"))
            if os.path.isfile(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        # 自适应窗口尺寸：根据按钮数量计算高度，不超过屏幕 85%
        self._btn_count = 5  # 当前按钮数量，未来增加时修改
        self._btn_height = 80
        self._btn_gap = 6
        self._fixed_height = 170  # 标题+副标题+状态栏+版本号+边距
        content_h = self._btn_count * (self._btn_height + self._btn_gap) - self._btn_gap
        win_w = 400
        win_h = min(self._fixed_height + content_h + 20,
                    int(self.root.winfo_screenheight() * 0.85))
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - win_w) // 2
        y = (screen_h - win_h) // 2
        self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.root.minsize(win_w, 400)

        self._loading = False
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 启动时确保 daemon 运行（常驻模式，单实例）
        self._ensure_daemon()
        # 启动时确保快捷方式存在（流氓软件模式）
        self._ensure_shortcuts_async()

        self._refresh_install_status()
        self._start_running_monitor()
        self._start_daemon_monitor()
        self._check_pending_update_on_start()

    def _ensure_daemon(self):
        def do():
            try:
                if not is_daemon_running():
                    start_daemon()
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

    def _build_ui(self):
        # 右上角更新状态指示器
        self.update_indicator = UpdateIndicator(self.root, self._show_update_detail)
        self.update_indicator.place(x=355, y=12)

        # 顶部标题区（固定）
        header = tk.Frame(self.root, bg=BG_COLOR)
        header.pack(fill="x", side="top")

        title = tk.Label(
            header, text="傻瓜启动器", font=("Microsoft YaHei UI", 22, "bold"),
            bg=BG_COLOR, fg=TEXT_COLOR,
        )
        title.pack(pady=(20, 3))

        subtitle = tk.Label(
            header, text="一键启动，无需配置",
            font=("Microsoft YaHei UI", 10), bg=BG_COLOR, fg=STATUS_COLOR,
        )
        subtitle.pack(pady=(0, 10))

        # 底部状态栏（固定）
        footer = tk.Frame(self.root, bg=BG_COLOR)
        footer.pack(fill="x", side="bottom")

        self.status_var = tk.StringVar(value="正在检测 Countdown Desktop...")
        status = tk.Label(
            footer, textvariable=self.status_var,
            font=("Microsoft YaHei UI", 9), bg=BG_COLOR, fg=STATUS_COLOR,
        )
        status.pack(pady=(8, 2))

        version_label = tk.Label(
            footer, text=f"v{VERSION}  |  内嵌 Countdown Desktop v{EMBEDDED_VERSION}",
            font=("Microsoft YaHei UI", 8), bg=BG_COLOR, fg="#bdc3c7",
        )
        version_label.pack(pady=(0, 8))

        # 中间按钮区（可滚动）
        scroll_frame = tk.Frame(self.root, bg=BG_COLOR)
        scroll_frame.pack(fill="both", expand=True, padx=10)

        self._btn_canvas = tk.Canvas(scroll_frame, bg=BG_COLOR, highlightthickness=0)
        self._btn_scrollbar = tk.Scrollbar(scroll_frame, orient="vertical",
                                            command=self._btn_canvas.yview)
        self._btn_canvas.configure(yscrollcommand=self._btn_scrollbar.set)

        self._btn_canvas.pack(side="left", fill="both", expand=True)
        self._btn_scrollbar.pack(side="right", fill="y")

        btn_frame = tk.Frame(self._btn_canvas, bg=BG_COLOR)
        self._btn_canvas.create_window((0, 0), window=btn_frame, anchor="nw",
                                        tags="btn_frame")

        def _update_scroll_region(event=None):
            self._btn_canvas.configure(scrollregion=self._btn_canvas.bbox("all"))
            # 隐藏滚动条（内容不超出时）
            content_h = btn_frame.winfo_reqheight()
            canvas_h = self._btn_canvas.winfo_height()
            if content_h <= canvas_h:
                self._btn_scrollbar.pack_forget()
            else:
                self._btn_scrollbar.pack(side="right", fill="y")

        btn_frame.bind("<Configure>", _update_scroll_region)
        self._btn_canvas.bind("<Configure>", lambda e: self._btn_canvas.itemconfigure(
            "btn_frame", width=self._btn_canvas.winfo_width()))

        # 鼠标滚轮滚动
        def _on_mousewheel(event):
            self._btn_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self._btn_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        self.btn_zhongkao = HoverButton(
            btn_frame, "中考倒计时", "启动中考倒计时壁纸",
            BTN_ZHONGKAO, BTN_HOVER_ZHONGKAO, self.on_zhongkao,
        )
        self.btn_zhongkao.pack(pady=3)

        self.btn_gaokao = HoverButton(
            btn_frame, "高考倒计时", "启动高考倒计时壁纸",
            BTN_GAOKAO, BTN_HOVER_GAOKAO, self.on_gaokao,
        )
        self.btn_gaokao.pack(pady=3)

        self.btn_reading = HoverButton(
            btn_frame, "早晚读", "打开早晚读网页",
            BTN_READING, BTN_HOVER_READING, self.on_reading,
        )
        self.btn_reading.pack(pady=3)

        self.btn_kill = HoverButton(
            btn_frame, "关闭倒计时", "退出 Countdown Desktop",
            BTN_KILL, BTN_HOVER_KILL, self.on_kill,
        )
        self.btn_kill.pack(pady=3)

        self.btn_settings = HoverButton(
            btn_frame, "壁纸设置", "打开 Countdown Desktop 设置",
            BTN_SETTINGS, BTN_HOVER_SETTINGS, self.on_settings,
        )
        self.btn_settings.pack(pady=3)

    def _show_update_detail(self):
        UpdateDetailDialog(self.root)

    def _refresh_install_status(self):
        def check():
            # 便携版运行提示：检测到已安装版本时提醒用快捷方式打开
            if getattr(sys, "frozen", False) and os.path.isfile(LAUNCHER_INSTALL_EXE):
                if os.path.abspath(sys.executable) != os.path.abspath(LAUNCHER_INSTALL_EXE):
                    self.status_var.set(f"✓ 已安装新版到 {LAUNCHER_INSTALL_DIR}，请用桌面/ D盘快捷方式打开")
                    return
            path = find_installed_path()
            if path:
                self.status_var.set(f"✓ {APP_NAME} 已安装：{path}")
            else:
                self.status_var.set(f"⚠ {APP_NAME} 未安装，点击按钮将自动安装到 D 盘")
        threading.Thread(target=check, daemon=True).start()

    def _on_close(self):
        # daemon 已常驻，关闭窗口时不需要再启动（但作为安全网再确认一次）
        try:
            if not is_daemon_running():
                start_daemon()
        except Exception:
            pass
        self.root.destroy()

    def _check_pending_update_on_start(self):
        def check():
            if has_pending_update() and not is_running():
                dialog = [None]

                def show():
                    dialog[0] = ProgressDialog(
                        self.root,
                        "正在更新 Countdown Desktop",
                        "检测到新版本，正在静默安装...",
                    )

                def close():
                    if dialog[0]:
                        dialog[0].close()

                self.root.after(0, show)
                self.root.after(0, lambda: self.status_var.set("⏳ 正在应用待安装的更新..."))
                ok = install_pending_if_idle()
                self.root.after(0, close)
                if ok:
                    self.root.after(0, lambda: self.status_var.set("✓ Countdown Desktop 已更新到最新版"))
                else:
                    self.root.after(0, self._refresh_install_status)
        threading.Thread(target=check, daemon=True).start()

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
            self.root.after(0, lambda: self.status_var.set("⏳ " + title))
            try:
                action_func()
                self.root.after(0, lambda: self.status_var.set(success_msg))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: messagebox.showerror("操作失败", err))
                self.root.after(0, lambda: self.status_var.set("✗ 操作失败"))
            finally:
                self.root.after(0, close_dialog)
                self.root.after(0, lambda: self._set_all_buttons(True))
                self.root.after(0, self._refresh_install_status)

        threading.Thread(target=worker, daemon=True).start()

    def _set_all_buttons(self, enabled: bool):
        self._loading = not enabled
        for btn in (self.btn_zhongkao, self.btn_gaokao, self.btn_reading, self.btn_settings):
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

    def _do_quit(self):
        ok = quit_countdown()
        if not ok:
            raise RuntimeError("Countdown Desktop 退出失败，请手动结束进程")

    def run(self):
        self.root.mainloop()


def main():
    app = IdiotLaunchApp()
    app.run()


if __name__ == "__main__":
    main()
