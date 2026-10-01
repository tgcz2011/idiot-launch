#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
早读内嵌浏览器窗口。
用 PySide6 + QWebEngineView，支持自动登录、置顶、调整大小、移动。
通过 run.py --morning-browser 启动，从配置文件读取班级信息。
"""
import sys
import os
import json
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QLabel, QFrame)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, Qt, QTimer
from PySide6.QtGui import QIcon

# 早读网页地址
MORNING_READING_URL = "https://zztool.free.nf/morning-reading"

# 配置文件路径
PERSISTENT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                      "data", "morning_config.json")
TEMP_CONFIG_PATH = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                                "idiot_launch_morning_config.json")


def load_morning_config():
    """加载早读班级配置。优先读取临时配置（非持久登录），没有则读取持久配置。"""
    for path in (TEMP_CONFIG_PATH, PERSISTENT_CONFIG_PATH):
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            continue
    return {}


def save_morning_config(config, persistent=True):
    """保存早读班级配置。persistent=False 时写入临时文件，IL 重启后自动消失。"""
    path = PERSISTENT_CONFIG_PATH if persistent else TEMP_CONFIG_PATH
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        if persistent and os.path.isfile(TEMP_CONFIG_PATH):
            try:
                os.remove(TEMP_CONFIG_PATH)
            except Exception:
                pass
        return True
    except Exception:
        return False


def clear_temp_morning_config():
    """删除临时早读配置（IL 退出时调用）。"""
    try:
        if os.path.isfile(TEMP_CONFIG_PATH):
            os.remove(TEMP_CONFIG_PATH)
    except Exception:
        pass


class MorningBrowserWindow(QMainWindow):
    """早读内嵌浏览器窗口。"""

    def __init__(self, config=None):
        super().__init__()
        self.config = config or load_morning_config()
        self._auto_login_done = False
        self._always_on_top = True

        self.setWindowTitle("早晚读")
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)

        # 窗口置顶
        self._update_window_flags()

        self._build_ui()
        self._load_page()

    def _update_window_flags(self):
        """更新窗口标志（置顶）。"""
        flags = Qt.Window
        if self._always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def _build_ui(self):
        """构建界面：顶部工具栏 + 浏览器。"""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部工具栏
        toolbar = QFrame()
        toolbar.setStyleSheet("background-color: #2F6B4F; color: white;")
        toolbar.setFixedHeight(40)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(10, 0, 10, 0)

        title = QLabel("早晚读")
        title.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
        tb_layout.addWidget(title)

        tb_layout.addStretch()

        # 班级信息
        class_name = self.config.get("class_name", "未配置班级")
        class_label = QLabel(class_name)
        class_label.setStyleSheet("color: rgba(255,255,255,0.8); font-size: 12px;")
        tb_layout.addWidget(class_label)
        tb_layout.addSpacing(15)

        # 置顶按钮
        self.top_btn = QPushButton("置顶中")
        self.top_btn.setStyleSheet(
            "background-color: rgba(255,255,255,0.2); color: white; "
            "border: none; padding: 5px 12px; border-radius: 4px; font-size: 12px;"
        )
        self.top_btn.setCursor(Qt.PointingHandCursor)
        self.top_btn.clicked.connect(self._toggle_top)
        tb_layout.addWidget(self.top_btn)

        # 刷新按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet(
            "background-color: rgba(255,255,255,0.2); color: white; "
            "border: none; padding: 5px 12px; border-radius: 4px; font-size: 12px;"
        )
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self._reload)
        tb_layout.addWidget(refresh_btn)

        layout.addWidget(toolbar)

        # 浏览器
        self.browser = QWebEngineView()
        layout.addWidget(self.browser)

        # 页面加载完成后自动登录
        self.browser.loadFinished.connect(self._on_load_finished)

    def _load_page(self):
        """加载早读页面。"""
        self.browser.setUrl(QUrl(MORNING_READING_URL))

    def _reload(self):
        """重新加载页面。"""
        self._auto_login_done = False
        self.browser.reload()

    def _toggle_top(self):
        """切换置顶状态。"""
        self._always_on_top = not self._always_on_top
        self._update_window_flags()
        self.top_btn.setText("置顶中" if self._always_on_top else "未置顶")

    def _on_load_finished(self, ok):
        """页面加载完成后自动登录。"""
        if not ok:
            return
        if self._auto_login_done:
            return

        grade = self.config.get("grade")
        class_number = self.config.get("class_number")
        password = self.config.get("password")

        if not all([grade, class_number, password]):
            return

        # 注入 JavaScript 自动填写表单并提交
        js = f"""
        (function() {{
            // 等待表单元素出现
            function tryLogin() {{
                var gradeSelect = document.querySelector('select[name="grade"]');
                var classInput = document.querySelector('input[name="class_number"]');
                var passInput = document.querySelector('input[name="password"]');
                var loginBtn = document.querySelector('button[name="login"]');

                if (gradeSelect && classInput && passInput && loginBtn) {{
                    gradeSelect.value = '{grade}';
                    // 触发 change 事件
                    gradeSelect.dispatchEvent(new Event('change'));
                    classInput.value = '{class_number:02d}';
                    passInput.value = '{password}';
                    loginBtn.click();
                    return true;
                }}
                return false;
            }}

            if (!tryLogin()) {{
                // 页面可能还没渲染完，重试
                var attempts = 0;
                var interval = setInterval(function() {{
                    attempts++;
                    if (tryLogin() || attempts > 20) {{
                        clearInterval(interval);
                    }}
                }}, 200);
            }}
        }})();
        """
        self.browser.page().runJavaScript(js)
        self._auto_login_done = True


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("早晚读")

    # 从命令行参数读取配置（如果有）
    config = {}
    if len(sys.argv) > 1:
        try:
            config = json.loads(sys.argv[1])
        except Exception:
            pass

    window = MorningBrowserWindow(config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
