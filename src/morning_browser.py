#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
早读内嵌浏览器窗口。
用 PySide6 + QWebEngineView，支持自动登录（官方 Token 直链）、置顶、调整大小、移动。
通过 run.py --morning-browser 启动，从配置文件读取班级信息。
"""
import sys
import os
import json
import time
import logging
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QLabel, QFrame)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, Qt, QTimer
from PySide6.QtGui import QIcon

log = logging.getLogger("morning_browser")

# 早读网页地址
MORNING_READING_URL = "https://zztool.free.nf/morning-reading"

# 配置文件路径（与 core.py 的 UPDATE_DIR 保持一致：D:\IdiotLaunch\data）
PERSISTENT_CONFIG_PATH = r"D:\IdiotLaunch\data\morning_config.json"
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

    def closeEvent(self, event):
        """窗口关闭时清理 PID 文件。"""
        try:
            pid_file = r"D:\IdiotLaunch\data\morning_browser.pid"
            if os.path.isfile(pid_file):
                os.remove(pid_file)
        except Exception:
            pass
        super().closeEvent(event)

    def eventFilter(self, obj, event):
        """工具栏拖动窗口。"""
        if obj == self._toolbar:
            if event.type() == event.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                return True
            elif event.type() == event.MouseMove and event.buttons() & Qt.LeftButton and self._drag_pos:
                self.move(event.globalPos() - self._drag_pos)
                return True
            elif event.type() == event.MouseButtonRelease:
                self._drag_pos = None
                return True
        return super().eventFilter(obj, event)

    def _update_window_flags(self):
        """更新窗口标志（置顶+无边框）。"""
        flags = Qt.Window | Qt.FramelessWindowHint
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

        # 班级信息（从 grade + class_number 构造，不依赖 class_name 字段）
        grade = str(self.config.get("grade", "")).strip()
        class_number = str(self.config.get("class_number", "")).strip()
        grade_map = {"7": "初一", "8": "初二", "9": "初三", "10": "高一", "11": "高二", "12": "高三"}
        grade_name = grade_map.get(grade, "")
        if grade_name and class_number:
            try:
                class_num = int(class_number)
                cn_nums = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
                           "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"]
                class_cn = cn_nums[class_num] if 0 <= class_num < len(cn_nums) else str(class_num)
                class_name = f"{grade_name}{class_cn}班"
            except (ValueError, IndexError):
                class_name = f"{grade_name}{class_number}班"
        else:
            class_name = "未配置班级"
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

        # 最小化按钮
        min_btn = QPushButton("—")
        min_btn.setStyleSheet(
            "background-color: transparent; color: white; border: none; "
            "padding: 5px 10px; border-radius: 4px; font-size: 14px;"
        )
        min_btn.setCursor(Qt.PointingHandCursor)
        min_btn.clicked.connect(self.showMinimized)
        tb_layout.addWidget(min_btn)

        # 关闭按钮
        close_btn = QPushButton("✕")
        close_btn.setStyleSheet(
            "background-color: transparent; color: white; border: none; "
            "padding: 5px 10px; border-radius: 4px; font-size: 14px;"
        )
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        tb_layout.addWidget(close_btn)

        # 工具栏拖动
        self._drag_pos = None
        toolbar.installEventFilter(self)
        self._toolbar = toolbar

        layout.addWidget(toolbar)

        # 浏览器
        self.browser = QWebEngineView()
        layout.addWidget(self.browser)

        # 页面加载完成后自动登录
        self.browser.loadFinished.connect(self._on_load_finished)

    def _load_page(self):
        """加载早读页面。已登录则用官方 Token 直链免登录打开，否则打开首页。"""
        url = self._get_auto_login_url()
        if url:
            log.info("使用免登录 Token 直链打开早读")
        else:
            url = MORNING_READING_URL
            log.info("未配置登录信息，打开早读首页")
        self.browser.setUrl(QUrl(url))

    def _get_auto_login_url(self):
        """构造官方免登录 Token 直链。失败返回 None。

        官方文档：?username=9-6&token=<sha256>&t=<Unix时间戳>
        token = sha256(username:password:seed)，链接 2 小时有效。
        """
        try:
            grade = str(self.config.get("grade", "")).strip()
            class_number = str(self.config.get("class_number", "")).strip()
            password = self.config.get("password", "")
            if not (grade and class_number and password):
                return None

            # 班级号补零
            try:
                class_number = f"{int(class_number):02d}"
            except (ValueError, TypeError):
                pass

            username = f"{grade}-{class_number}"

            # 用 morning_api_client 获取 token（自动过 InfinityFree JS challenge + 缓存）
            from src.morning_api_client import ApiClient
            client = ApiClient()
            token = client._cached_token("record", username, password)
            if not token:
                log.warning("获取早读 token 失败，回退到首页")
                return None

            timestamp = int(time.time())
            return f"{MORNING_READING_URL}?username={username}&token={token}&t={timestamp}"
        except Exception as e:
            log.warning(f"构造免登录 URL 失败: {e}，回退到首页")
            return None

    def _reload(self):
        """重新加载页面。重新构造免登录 URL（防止 token 过期）。"""
        self._auto_login_done = False
        self._load_page()

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
        class_number = str(self.config.get("class_number", "")).strip()
        password = self.config.get("password")

        if not all([grade, class_number, password]):
            return

        # 班级号补零（如 "1" -> "01"）
        try:
            class_num = int(class_number)
            class_number = f"{class_num:02d}"
        except (ValueError, TypeError):
            pass

        # 注入 JavaScript 自动填写表单并提交
        # 用多种选择器兼容网页改版
        js = f"""
        (function() {{
            function tryLogin() {{
                // 尝试多种选择器，兼容网页改版
                var gradeSelect = document.querySelector('select[name="grade"]') ||
                                  document.querySelector('select') ||
                                  document.querySelector('.grade-select');
                var inputs = document.querySelectorAll('input');
                var classInput = null, passInput = null;
                for (var i = 0; i < inputs.length; i++) {{
                    var t = inputs[i].type;
                    var ph = (inputs[i].placeholder || '').toLowerCase();
                    var n = (inputs[i].name || '').toLowerCase();
                    if (t === 'password' || n.indexOf('pass') >= 0) {{
                        passInput = inputs[i];
                    }} else if (n.indexOf('class') >= 0 || ph.indexOf('班级') >= 0 || ph.indexOf('class') >= 0) {{
                        classInput = inputs[i];
                    }}
                }}
                if (!classInput && inputs.length >= 2) classInput = inputs[0];
                var loginBtn = document.querySelector('button[name="login"]') ||
                               document.querySelector('button[type="submit"]') ||
                               document.querySelector('.login-btn') ||
                               document.querySelector('button');

                if (gradeSelect && classInput && passInput && loginBtn) {{
                    // 设置年级并触发 change 事件
                    gradeSelect.value = '{grade}';
                    gradeSelect.dispatchEvent(new Event('change', {{bubbles: true}}));
                    // 设置班级号和密码并触发 input 事件
                    classInput.value = '{class_number}';
                    classInput.dispatchEvent(new Event('input', {{bubbles: true}}));
                    passInput.value = '{password}';
                    passInput.dispatchEvent(new Event('input', {{bubbles: true}}));
                    loginBtn.click();
                    return true;
                }}
                return false;
            }}

            if (!tryLogin()) {{
                var attempts = 0;
                var interval = setInterval(function() {{
                    attempts++;
                    if (tryLogin() || attempts > 30) {{
                        clearInterval(interval);
                    }}
                }}, 300);
            }}
        }})();
        """
        try:
            self.browser.page().runJavaScript(js)
            self._auto_login_done = True
        except Exception as e:
            log.warning(f"自动登录 JS 注入失败: {e}")


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
