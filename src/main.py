"""
main.py — Idiot Launch 主入口与 GUI
四个大按钮：中考倒计时 / 高考倒计时 / 早晚读 / 关闭倒计时
傻瓜式操作，无需任何配置。
关闭倒计时按钮：Countdown Desktop 未运行时自动变灰不可点击。
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
    APP_NAME,
)

VERSION = "1.0.0.2"

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
        self._refresh_install_status()
        self._start_running_monitor()

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
            self.root, text=f"v{VERSION}  |  内嵌 Countdown Desktop v3.2.0.0",
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

    def _run_with_loading(self, action_func, success_msg):
        """
        在后台线程执行操作，期间禁用所有按钮并显示加载状态，完成后恢复。
        """
        def worker():
            self.root.after(0, lambda: self._set_all_buttons(False))
            self.root.after(0, lambda: self.status_var.set("⏳ 正在处理，请稍候..."))
            try:
                action_func()
                self.root.after(0, lambda: self.status_var.set(success_msg))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: messagebox.showerror("操作失败", err))
                self.root.after(0, lambda: self.status_var.set("✗ 操作失败"))
            finally:
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
        )

    def on_gaokao(self):
        self._run_with_loading(
            lambda: launch_countdown("gaokao"),
            "✓ 高考倒计时已启动",
        )

    def on_reading(self):
        self._run_with_loading(
            open_morning_reading,
            "✓ 早晚读网页已在浏览器中打开",
        )

    def on_kill(self):
        self._run_with_loading(
            lambda: self._do_quit(),
            "✓ 倒计时已关闭",
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
