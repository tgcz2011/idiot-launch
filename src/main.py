"""
main.py — Idiot Launch 主入口与 GUI
四个大按钮：中考倒计时 / 高考倒计时 / 早晚读 / 关闭倒计时
傻瓜式操作，无需任何配置。
关闭倒计时按钮：Countdown Desktop 未运行时自动变灰不可点击。
关闭窗口后启动后台守护进程，自动检查并下载 Countdown Desktop 更新。
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import sys
import os

from src.core import (
    launch_countdown,
    open_morning_reading,
    quit_countdown,
    find_installed_path,
    is_running,
    start_daemon,
    install_pending_if_idle,
    has_pending_update,
    EMBEDDED_VERSION,
    APP_NAME,
)

VERSION = "1.1.1.0"

# ── 配色 ──
BG_COLOR = "#f5f7fa"
BTN_ZHONGKAO = "#e74c3c"       # 红色 — 中考
BTN_GAOKAO = "#2980b9"         # 蓝色 — 高考
BTN_READING = "#27ae60"        # 绿色 — 早晚读
BTN_KILL = "#5d6d7e"           # 深灰 — 关闭倒计时
BTN_DISABLED = "#bdc3c7"       # 浅灰 — 禁用态
BTN_DISABLED_TEXT = "#ecf0f1"  # 禁用态文字
BTN_HOVER_ZHONGKAO = "#c0392b"
BTN_HOVER_GAOKAO = "#1f6fa0"
BTN_HOVER_READING = "#1e8449"
BTN_HOVER_KILL = "#4a5568"
TEXT_COLOR = "#2c3e50"
STATUS_COLOR = "#7f8c8d"


class HoverButton(tk.Canvas):
    """带悬停效果和禁用态的大按钮（Canvas 绘制圆角矩形）。"""

    def __init__(self, parent, text, subtext, color, hover_color, command,
                 width=320, height=110):
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
        # 圆角矩形（四个矩形+四个椭圆拼出）
        self.create_rectangle(r, 0, w - r, h, fill=color, outline="")
        self.create_rectangle(0, r, w, h - r, fill=color, outline="")
        self.create_oval(0, 0, 2 * r, 2 * r, fill=color, outline="")
        self.create_oval(w - 2 * r, 0, w, 2 * r, fill=color, outline="")
        self.create_oval(0, h - 2 * r, 2 * r, h, fill=color, outline="")
        self.create_oval(w - 2 * r, h - 2 * r, w, h, fill=color, outline="")
        # 主文字
        self.create_text(w // 2, h // 2 - 10, text=self.text, fill=text_color,
                         font=("Microsoft YaHei UI", 22, "bold"))
        # 副文字
        self.create_text(w // 2, h // 2 + 24, text=self.subtext,
                         fill=BTN_DISABLED_TEXT if not self._enabled else "white",
                         font=("Microsoft YaHei UI", 11))

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
        """设置按钮启用/禁用状态，禁用时变灰且不响应点击。"""
        self._enabled = enabled
        if enabled:
            self._draw(self.color)
            self.configure(cursor="")
        else:
            self._draw(BTN_DISABLED, text_color=BTN_DISABLED_TEXT)
            self.configure(cursor="arrow")


class ProgressDialog:
    """
    安装/启动进度弹窗：置顶、无关闭按钮、居中显示，带不确定进度条。
    防止老师在教室电脑上因安装耗时较长而误以为软件卡死。
    """

    def __init__(self, parent, title: str, subtitle: str = "",
                 hint: str = "教室电脑性能有限，请耐心等待，请勿关闭"):
        self.parent = parent

        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)  # 无标题栏，防止误关
        self.win.attributes("-topmost", True)
        self.win.configure(bg="#ffffff")

        # 窗口尺寸与居中
        w, h = 380, 170
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.win.geometry(f"{w}x{h}+{x}+{y}")

        # 顶部色条
        top_bar = tk.Frame(self.win, bg="#2980b9", height=6)
        top_bar.pack(fill="x", side="top")

        # 内容区
        content = tk.Frame(self.win, bg="#ffffff", padx=30, pady=20)
        content.pack(fill="both", expand=True)

        # 标题
        self.title_label = tk.Label(
            content, text=title, font=("Microsoft YaHei UI", 16, "bold"),
            bg="#ffffff", fg="#2c3e50",
        )
        self.title_label.pack(anchor="w")

        # 副标题
        self.subtitle_label = tk.Label(
            content, text=subtitle, font=("Microsoft YaHei UI", 10),
            bg="#ffffff", fg="#7f8c8d",
        )
        self.subtitle_label.pack(anchor="w", pady=(4, 0))

        # 进度条（不确定模式，来回滚动）
        self.progress = ttk.Progressbar(
            content, mode="indeterminate", length=320, maximum=100,
        )
        self.progress.pack(pady=(18, 0), fill="x")
        self.progress.start(12)  # 动画速度（ms/帧）

        # 底部提示
        if hint:
            tk.Label(
                content, text=hint, font=("Microsoft YaHei UI", 8),
                bg="#ffffff", fg="#bdc3c7",
            ).pack(anchor="w", pady=(10, 0))

        self.win.lift()
        self.win.focus_force()

    def update_text(self, title: str, subtitle: str = ""):
        """动态更新弹窗标题和副标题。"""
        self.title_label.config(text=title)
        if subtitle:
            self.subtitle_label.config(text=subtitle)

    def close(self):
        """关闭弹窗。"""
        try:
            self.progress.stop()
            self.win.destroy()
        except Exception:
            pass


class IdiotLaunchApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("傻瓜启动器 v" + VERSION)
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(False, False)

        # 窗口居中
        win_w, win_h = 420, 640
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - win_w) // 2
        y = (screen_h - win_h) // 2
        self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")

        self._loading = False  # 是否处于加载中（所有按钮禁用）
        self._build_ui()
        # 关闭窗口时启动后台守护进程（检查更新），然后退出 GUI
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_install_status()
        self._start_running_monitor()
        self._check_pending_update_on_start()

    def _build_ui(self):
        # 标题
        title = tk.Label(
            self.root, text="傻瓜启动器", font=("Microsoft YaHei UI", 26, "bold"),
            bg=BG_COLOR, fg=TEXT_COLOR,
        )
        title.pack(pady=(30, 5))

        subtitle = tk.Label(
            self.root, text="一键启动，无需配置",
            font=("Microsoft YaHei UI", 11), bg=BG_COLOR, fg=STATUS_COLOR,
        )
        subtitle.pack(pady=(0, 20))

        # 按钮区
        btn_frame = tk.Frame(self.root, bg=BG_COLOR)
        btn_frame.pack(pady=10)

        self.btn_zhongkao = HoverButton(
            btn_frame, "中考倒计时", "启动中考倒计时壁纸",
            BTN_ZHONGKAO, BTN_HOVER_ZHONGKAO, self.on_zhongkao,
        )
        self.btn_zhongkao.pack(pady=8)

        self.btn_gaokao = HoverButton(
            btn_frame, "高考倒计时", "启动高考倒计时壁纸",
            BTN_GAOKAO, BTN_HOVER_GAOKAO, self.on_gaokao,
        )
        self.btn_gaokao.pack(pady=8)

        self.btn_reading = HoverButton(
            btn_frame, "早晚读", "打开早晚读网页",
            BTN_READING, BTN_HOVER_READING, self.on_reading,
        )
        self.btn_reading.pack(pady=8)

        self.btn_kill = HoverButton(
            btn_frame, "关闭倒计时", "退出 Countdown Desktop",
            BTN_KILL, BTN_HOVER_KILL, self.on_kill,
        )
        self.btn_kill.pack(pady=8)

        # 状态栏
        self.status_var = tk.StringVar(value="正在检测 Countdown Desktop...")
        status = tk.Label(
            self.root, textvariable=self.status_var,
            font=("Microsoft YaHei UI", 9), bg=BG_COLOR, fg=STATUS_COLOR,
        )
        status.pack(side="bottom", pady=15)

        version_label = tk.Label(
            self.root, text=f"v{VERSION}  |  内嵌 Countdown Desktop v{EMBEDDED_VERSION}",
            font=("Microsoft YaHei UI", 8), bg=BG_COLOR, fg="#bdc3c7",
        )
        version_label.place(relx=0.5, rely=0.97, anchor="s")

    def _refresh_install_status(self):
        """后台检测安装状态，更新状态栏。"""
        def check():
            path = find_installed_path()
            if path:
                self.status_var.set(f"✓ {APP_NAME} 已安装：{path}")
            else:
                self.status_var.set(f"⚠ {APP_NAME} 未安装，点击按钮将自动安装到 D 盘")
        threading.Thread(target=check, daemon=True).start()

    def _on_close(self):
        """窗口关闭时：启动后台守护进程检查更新，然后退出 GUI。"""
        try:
            start_daemon()
        except Exception:
            pass
        self.root.destroy()

    def _check_pending_update_on_start(self):
        """启动时检查：如果有已下载的待安装更新且 Countdown Desktop 未运行，立即静默安装。"""
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
        """启动运行状态轮询：每 1.5 秒检测 Countdown Desktop 是否在运行，
        同步更新「关闭倒计时」按钮的启用/禁用状态。"""
        def monitor():
            while True:
                try:
                    running = is_running()
                    self.root.after(0, lambda r=running: self._update_kill_button(r))
                except Exception:
                    pass
                time.sleep(1.5)

        import time
        threading.Thread(target=monitor, daemon=True).start()

    def _update_kill_button(self, running: bool):
        """根据运行状态更新关闭按钮。加载中时保持禁用。"""
        if self._loading:
            self.btn_kill.set_enabled(False)
            return
        self.btn_kill.set_enabled(running)
        if running:
            self.btn_kill.subtext = "退出 Countdown Desktop"
        else:
            self.btn_kill.subtext = "当前未在运行"
        # 重绘以更新副文字
        if self.btn_kill._enabled:
            self.btn_kill._draw(self.btn_kill.color)
        else:
            self.btn_kill._draw(BTN_DISABLED, text_color=BTN_DISABLED_TEXT)

    def _run_with_loading(self, action_func, success_msg,
                          title="正在处理", subtitle="请稍候..."):
        """
        在后台线程执行操作，期间禁用所有按钮并显示进度弹窗，完成后恢复。
        进度弹窗置顶且无关闭按钮，防止老师误以为软件卡死。
        """
        dialog = [None]  # 用列表包裹以便在闭包中修改

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
        """设置所有按钮的加载态启用/禁用。关闭按钮额外受运行状态约束。"""
        self._loading = not enabled
        for btn in (self.btn_zhongkao, self.btn_gaokao, self.btn_reading):
            btn.set_enabled(enabled)
        # 关闭按钮：加载中禁用；非加载中由运行状态决定
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

    def _do_quit(self):
        """调用 Countdown Desktop --quit 优雅退出；失败则抛异常。"""
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
