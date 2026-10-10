#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
早晚读内嵌浏览器窗口。

用 PySide6 + QWebEngineView。已登录时用官方免登录 token 直链打开，
未登录则直接打开网页首页（不拦截用户）。

从 run.py --morning-browser 启动，配置从 D 盘配置文件读取
（不再通过命令行传密码：命令行对本机任何进程可见）。
"""
import json
import logging
import os
import sys
import time

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QMainWindow, QPushButton, QVBoxLayout, QWidget)

from src import morning_config

log = logging.getLogger("morning_browser")

MORNING_READING_URL = morning_config.MORNING_READING_URL
PERSISTENT_CONFIG_PATH = morning_config.PERSISTENT_CONFIG_PATH
TEMP_CONFIG_PATH = morning_config.TEMP_CONFIG_PATH
DATA_DIR = morning_config.DATA_DIR
PID_FILE = os.path.join(DATA_DIR, "morning_browser.pid")

# 兼容旧调用方
load_morning_config = morning_config.load


def save_morning_config(config, persistent: bool = True) -> bool:
    return morning_config.save(config, persistent=persistent)


def clear_temp_morning_config() -> None:
    morning_config.clear_temp()


class MorningBrowserWindow(QMainWindow):
    """早晚读内嵌浏览器窗口。"""

    def __init__(self, config=None):
        super().__init__()
        self.config = config or morning_config.load()
        self._auto_login_done = False
        self._always_on_top = True
        self._fullscreen = False
        self._drag_pos = None

        self.setWindowTitle("早晚读")
        self.setMinimumSize(640, 480)
        self.resize(1000, 700)

        # 先建 UI 再显示：原实现先 show() 后 _build_ui()，会先闪一个空白窗
        self._build_ui()
        self._update_window_flags()
        self.show()
        self._load_page()

    def closeEvent(self, event):
        """关闭时清理 PID 文件（只删自己的，避免误删另一个实例的）。"""
        try:
            if os.path.isfile(PID_FILE):
                with open(PID_FILE, "r", encoding="utf-8") as f:
                    if f.read().strip() == str(os.getpid()):
                        os.remove(PID_FILE)
        except Exception:
            pass
        super().closeEvent(event)

    def eventFilter(self, obj, event):
        """工具栏拖动窗口。"""
        from PySide6.QtGui import QMouseEvent

        if obj == getattr(self, "_toolbar", None) and isinstance(event, QMouseEvent):
            if event.type() == event.Type.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return True
            if event.type() == event.Type.MouseMove and event.buttons() & Qt.LeftButton and self._drag_pos:
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                return True
            if event.type() == event.Type.MouseButtonRelease:
                self._drag_pos = None
                return True
        return super().eventFilter(obj, event)

    def _update_window_flags(self):
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

        # 置顶按钮（明确写成"开/关"，不要用状态词当按钮名）
        self.top_btn = QPushButton("置顶：开")
        self.top_btn.setToolTip("点击切换是否让本窗口始终显示在最前面")
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

        # 全屏按钮（铺满整个屏幕，含任务栏；再点一次/按 Esc 退出）
        self.fs_btn = QPushButton("全屏")
        self.fs_btn.setToolTip("铺满整个屏幕（再点一次退出，Esc 也可以）")
        self.fs_btn.setStyleSheet(
            "background-color: rgba(255,255,255,0.2); color: white; "
            "border: none; padding: 5px 12px; border-radius: 4px; font-size: 12px;"
        )
        self.fs_btn.setCursor(Qt.PointingHandCursor)
        self.fs_btn.clicked.connect(self._toggle_fullscreen)
        tb_layout.addWidget(self.fs_btn)

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

        # 浏览器（stretch=1 填充剩余空间）
        self.browser = QWebEngineView()
        layout.addWidget(self.browser, 1)

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
        self.top_btn.setText("置顶：开" if self._always_on_top else "置顶：关")

    def _toggle_fullscreen(self):
        """全屏：铺满整个屏幕（含任务栏）；顶部工具栏保留，所以还能操作/退出。"""
        self._fullscreen = not self._fullscreen
        if self._fullscreen:
            self.showFullScreen()
            self.fs_btn.setText("退出全屏")
            log.info("morning browser fullscreen on")
        else:
            self.showNormal()
            self.fs_btn.setText("全屏")
            log.info("morning browser fullscreen off")

    def keyPressEvent(self, event):
        from PySide6.QtCore import Qt as _Qt

        if event.key() == _Qt.Key_Escape and self._fullscreen:
            self._toggle_fullscreen()
            return
        super().keyPressEvent(event)

    def _show_load_error(self):
        """网页打不开时给中文说明，而不是让老师看 Chromium 的英文报错页。"""
        html = """
        <html><head><meta charset="utf-8"><style>
        body{font-family:"Microsoft YaHei",sans-serif;background:#1f2328;color:#eee;
             display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
        .box{text-align:center;max-width:520px;line-height:1.9}
        h2{font-size:22px} p{font-size:15px;color:#bbb}
        </style></head><body><div class="box">
        <h2>早晚读网页打不开</h2>
        <p>常见原因：教室网络被限制、服务器临时故障、或系统时间不准确。</p>
        <p>可以点右上角「刷新」重试；如果一直不行，请用手机流量确认一下网站是否正常。</p>
        </div></body></html>
        """
        try:
            self.browser.setHtml(html)
        except Exception:
            pass

    def _on_load_finished(self, ok):
        """页面加载完成后自动登录。"""
        if not ok:
            log.warning("早晚读页面加载失败")
            self._show_load_error()
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
            class_number = f"{int(class_number):02d}"
        except (ValueError, TypeError):
            pass

        # 用 json.dumps 生成 JS 字面量：密码里有引号/反斜杠也不会把脚本写坏
        grade_js = json.dumps(str(grade))
        class_js = json.dumps(str(class_number))
        pass_js = json.dumps(str(password))

        js = f"""
        (function() {{
            function tryLogin() {{
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
                    gradeSelect.value = {grade_js};
                    gradeSelect.dispatchEvent(new Event('change', {{bubbles: true}}));
                    classInput.value = {class_js};
                    classInput.dispatchEvent(new Event('input', {{bubbles: true}}));
                    passInput.value = {pass_js};
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
            log.info("已注入自动登录脚本")
        except Exception as e:
            log.warning(f"自动登录 JS 注入失败: {e}")


def main():
    from src.core import setup_logging

    setup_logging("morning")
    app = QApplication(sys.argv)
    app.setApplicationName("早晚读")

    # 配置一律从 D 盘配置文件读（不接收命令行参数，避免密码出现在命令行里）
    config = morning_config.load()
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

    window = MorningBrowserWindow(config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
