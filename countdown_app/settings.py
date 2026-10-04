# -*- coding: utf-8 -*-
"""设置界面：左侧导航 + 多页内容区（QListWidget + QStackedWidget）。

为什么分页：设置项会持续增加（未来新功能），单页对话框塞不下且难导航。
页面采用注册制（PAGES 列表 + 页面工厂），新增设置页只需：
  1. 写一个 make_xxx_page(self) 工厂，返回含 load()/save() 接口的 QWidget；
  2. 在 PAGES 里注册 (key, 标题, 工厂)。
导航切换、统一 load/save 由基类逻辑自动处理。

v3.2.0.0 起新增「倒计时」页：高考/中考/自定义 三态切换（高考=原默认链接，
中考=countdown-junior）；自定义时壁纸/屏保地址分别在各自页面设置。
"""
import logging
import os

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QSpinBox, QStackedWidget,
                               QVBoxLayout, QWidget)

log = logging.getLogger("settings")

URL_HELP = "http(s) 网页地址，或本地 视频/图片/动图 文件；留空则使用「倒计时」页默认地址"

# 导航页注册表：(key, 标题, 工厂函数名)。需要新页时在此追加即可。
PAGES = [
    ("countdown", "倒计时", "_make_countdown_page"),
    ("wallpaper", "动态壁纸", "_make_wallpaper_page"),
    ("screensaver", "屏幕保护", "_make_screensaver_page"),
    ("general", "通用", "_make_general_page"),
    ("about", "关于", "_make_about_page"),
]


def _normalize_url(text: str, default_url: str = None) -> str:
    from . import config
    text = text.strip()
    if not text:
        return default_url or config.DEFAULT_URL
    if text.startswith(("http://", "https://")):
        return text
    if os.path.isfile(text):
        return text
    if len(text) > 3 and "." in text.split("/")[0]:
        return "https://" + text
    return text


class SettingsDialog(QDialog):
    def __init__(self, app):
        super().__init__()
        self.app = app
        from . import version
        self.setWindowTitle("Countdown Desktop 设置 v%s" % version.VERSION)
        self.resize(680, 460)
        self.setMinimumSize(560, 400)
        self.setWindowFlags((self.windowFlags()
                             | Qt.WindowType.WindowSystemMenuHint
                             | Qt.WindowType.WindowCloseButtonHint)
                            & ~Qt.WindowType.WindowContextHelpButtonHint)

        outer = QVBoxLayout(self)
        content = QHBoxLayout()

        # ---- 左侧导航 ----
        self.nav = QListWidget()
        self.nav.setObjectName("settingsNav")
        self.nav.setIconSize(QSize(20, 20))
        self.nav.setFixedWidth(148)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.currentRowChanged.connect(self._switch_page)
        content.addWidget(self.nav)

        # ---- 右侧内容区 ----
        self.stack = QStackedWidget()
        self.stack.setContentsMargins(0, 0, 0, 0)
        content.addWidget(self.stack, 1)
        outer.addLayout(content, 1)

        self._pages = {}  # key -> (widget, 标题)
        for key, title, factory in PAGES:
            page = getattr(self, factory)()
            page.setObjectName("page-" + key)
            self.stack.addWidget(page)
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.nav.addItem(item)
            self._pages[key] = (page, title)

        # ---- 底部按钮（全局保存/取消，作用于所有页） ----
        row_btns = QHBoxLayout()
        row_btns.setContentsMargins(16, 8, 16, 12)
        self.btn_save = QPushButton("保存")
        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        row_btns.addStretch()
        row_btns.addWidget(self.btn_save)
        row_btns.addWidget(self.btn_cancel)
        outer.addLayout(row_btns)

        self._style_nav()
        self.nav.setCurrentRow(0)
        self.load_all()

    # ---------------- 导航 ----------------
    def _style_nav(self) -> None:
        self.nav.setStyleSheet("""
            QListWidget#settingsNav {
                background: transparent; border: none;
                outline: 0; padding: 8px 0;
            }
            QListWidget#settingsNav::item {
                padding: 10px 14px; margin: 2px 6px;
                border-radius: 6px; color: #333;
            }
            QListWidget#settingsNav::item:hover { background: #ececf2; }
            QListWidget#settingsNav::item:selected {
                background: #d8d8e8; color: #111;
            }
        """)

    def _switch_page(self, row: int) -> None:
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    def goto_page(self, key: str) -> None:
        """按 key 跳转到指定设置页（供托盘等外部入口定位）。"""
        for row in range(self.nav.count()):
            if self.nav.item(row).data(Qt.ItemDataRole.UserRole) == key:
                self.nav.setCurrentRow(row)
                return

    # ---------------- 页面工厂 ----------------
    def _make_fit_combo(self) -> QComboBox:
        from . import config
        combo = QComboBox()
        for key in config.FIT_MODES:
            combo.addItem(config.FIT_LABELS[key], key)
        return combo

    def _make_countdown_page(self) -> QWidget:
        from . import config
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        grp = QGroupBox("倒计时类型")
        form = QFormLayout(grp)
        self.cmb_exam = QComboBox()
        for key in config.EXAM_TYPES:
            self.cmb_exam.addItem(config.EXAM_LABELS[key], key)
        self.cmb_exam.currentIndexChanged.connect(
            # 只关心"用户切换了类型"，忽略回调带回的 index：
            # 高考是第 0 项，直接用 index 当 bool 会导致选高考时不自动勾选（历史 bug）
            lambda *_: self._on_exam_changed(True))
        form.addRow("类型", self.cmb_exam)
        self.lbl_exam_hint = QLabel(
            "高考 / 中考：壁纸与屏保统一使用对应倒计时页面（高考为原默认链接）。\n"
            "自定义：壁纸与屏保可在各自页面分别设置地址。")
        self.lbl_exam_hint.setWordWrap(True)
        form.addRow(self.lbl_exam_hint)
        layout.addWidget(grp)

        layout.addStretch()
        return page

    def _on_exam_changed(self, auto_enable: bool = True) -> None:
        """按倒计时类型同步壁纸/屏保源输入框：预设时只读显示预设地址，自定义时可编辑。

        auto_enable=True（用户手动切换时）：切到高考/中考预设自动勾选启用壁纸/屏保，
        因为预设模式的核心用途就是显示倒计时；auto_enable=False（load_all 同步时）
        不改动勾选态，保持用户已保存的配置。
        """
        from . import config
        et = self.cmb_exam.currentData() or "gaokao"
        custom = (et == "custom")
        for txt in (self.txt_wall_url, self.txt_ss_url):
            txt.setEnabled(custom)
            txt.setReadOnly(not custom)
            if custom:
                txt.setPlaceholderText("网页地址，或浏览选择 视频/图片/动图 文件（留空=高考默认）")
            else:
                txt.setPlaceholderText("跟随「倒计时」页：%s" % config.EXAM_URLS[et])
                txt.setText(config.EXAM_URLS[et])
        if auto_enable and not custom:
            self.chk_wall.setChecked(True)
            self.chk_ss.setChecked(True)

    def _make_wallpaper_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        grp = QGroupBox("动态壁纸")
        form = QFormLayout(grp)
        self.chk_wall = QCheckBox("启用动态壁纸")
        form.addRow(self.chk_wall)
        row_wall = QHBoxLayout()
        self.txt_wall_url = QLineEdit()
        self.txt_wall_url.setPlaceholderText(URL_HELP)
        row_wall.addWidget(self.txt_wall_url)
        self.btn_wall_file = QPushButton("浏览…")
        self.btn_wall_file.clicked.connect(lambda: self._pick(self.txt_wall_url))
        row_wall.addWidget(self.btn_wall_file)
        form.addRow("壁纸源", row_wall)
        self.cmb_wall_fit = self._make_fit_combo()
        self.cmb_wall_fit.setToolTip("仅对图片/视频源生效；网页源铺满窗口")
        form.addRow("画幅", self.cmb_wall_fit)
        self.chk_wall_mute = QCheckBox("静音（网页与视频）")
        self.chk_wall_mute.setToolTip("取消勾选则网页/视频开启声音")
        form.addRow("声音", self.chk_wall_mute)
        layout.addWidget(grp)

        layout.addStretch()
        return page

    def _make_screensaver_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        grp = QGroupBox("屏幕保护")
        form = QFormLayout(grp)
        self.chk_ss = QCheckBox("启用屏保（自绘全屏窗口，不使用系统屏保）")
        form.addRow(self.chk_ss)
        row_ss_url = QHBoxLayout()
        self.txt_ss_url = QLineEdit()
        self.txt_ss_url.setPlaceholderText(URL_HELP)
        row_ss_url.addWidget(self.txt_ss_url)
        self.btn_ss_file = QPushButton("浏览…")
        self.btn_ss_file.clicked.connect(lambda: self._pick(self.txt_ss_url))
        row_ss_url.addWidget(self.btn_ss_file)
        form.addRow("屏保源", row_ss_url)
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(30, 86400)
        self.spin_timeout.setSuffix(" 秒")
        form.addRow("空闲触发时长", self.spin_timeout)
        self.cmb_ss_fit = self._make_fit_combo()
        self.cmb_ss_fit.setToolTip("仅对图片/视频源生效；网页源铺满窗口")
        form.addRow("画幅", self.cmb_ss_fit)
        self.chk_ss_mute = QCheckBox("静音（网页与视频）")
        form.addRow("声音", self.chk_ss_mute)
        row_ss = QHBoxLayout()
        self.btn_test = QPushButton("立即测试屏保")
        self.btn_test.setToolTip("保存前也可以先看看屏保效果")
        self.btn_test.clicked.connect(self._on_test_screensaver)
        row_ss.addWidget(self.btn_test)
        form.addRow(row_ss)
        layout.addWidget(grp)

        layout.addStretch()
        return page

    def _make_general_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        grp = QGroupBox("通用")
        form = QFormLayout(grp)
        self.chk_startup = QCheckBox("开机自启（写入注册表 HKCU，卸载自动清理）")
        form.addRow(self.chk_startup)
        layout.addWidget(grp)

        grp_play = QGroupBox("播放")
        form_p = QFormLayout(grp_play)
        self.chk_video_loop = QCheckBox("视频循环播放（壁纸与屏保）")
        form_p.addRow(self.chk_video_loop)
        layout.addWidget(grp_play)

        layout.addStretch()
        return page

    def _make_about_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        from . import version

        grp = QGroupBox("关于")
        form = QFormLayout(grp)
        for label, value in (("程序", "Countdown Desktop（傻瓜启动器特供版）"),
                             ("版本", "v%s" % version.VERSION),
                             ("功能", "动态壁纸 + 屏幕保护（网页/视频/图片/动图）"),
                             ("渲染", "pywebview + WebView2（Chromium）"),
                             ("更新", "已由傻瓜启动器统一管理，此处不提供更新")):
            text = QLabel(value)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(label, text)
        layout.addWidget(grp)

        # ---- 开源许可与鸣谢 ----
        grp_lic = QGroupBox("开源许可与鸣谢")
        v_lic = QVBoxLayout(grp_lic)
        lbl_lic = QLabel(
            "本软件基于 GPL-3.0 授权开源，使用即表示同意许可条款，"
            "全文见仓库 LICENSE 文件。"
            "壁纸嵌入实现学习并借鉴了 Lively Wallpaper（GPL-3.0），"
            '在此向作者 <a href="https://github.com/rocksdanister">rocksdanister</a>'
            " 及社区贡献者致谢。")
        lbl_lic.setWordWrap(True)
        lbl_lic.setOpenExternalLinks(True)
        v_lic.addWidget(lbl_lic)
        link_lively = QLabel(
            '<a href="https://github.com/rocksdanister/lively">'
            "github.com/rocksdanister/lively</a>")
        link_lively.setOpenExternalLinks(True)
        v_lic.addWidget(link_lively)
        layout.addWidget(grp_lic)

        layout.addStretch()
        return page

    # ---------------- 屏保测试 ----------------
    def _on_test_screensaver(self) -> None:
        """立即测试屏保。

        原实现直接调 start_screensaver()，但未勾选"启用屏保"时那个函数会静默
        return，用户点了没反应，以为按钮坏了。这里先说清楚原因。
        """
        from PySide6.QtWidgets import QMessageBox

        if not self.chk_ss.isChecked():
            QMessageBox.information(
                self, "屏幕保护未启用",
                "当前没有勾选「启用屏保」。\n\n"
                "可以先勾选它再点测试；测试会全屏显示屏保内容，"
                "动一下鼠标或按键盘就会退出。")
            return
        self.app.start_screensaver()

    # ---------------- 文件选择 ----------------
    def _pick(self, line_edit) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择媒体文件", "",
            "视频/图片/动图 (*.mp4 *.webm *.mkv *.mov *.m4v *.gif *.png *.jpg "
            "*.jpeg *.bmp *.webp);;视频 (*.mp4 *.webm *.mkv *.mov *.m4v);;"
            "图片/动图 (*.gif *.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*.*)")
        if path:
            line_edit.setText(path)

    # ---------------- 统一读取/保存 ----------------
    def load_all(self) -> None:
        """从配置刷新所有页面控件（含通用页）。"""
        from . import config
        cfg = self.app.cfg
        et = cfg.get("exam_type", "gaokao")
        self.cmb_exam.setCurrentIndex(max(0, self.cmb_exam.findData(et)))
        if et in config.EXAM_URLS:
            # 预设模式：只读显示预设地址
            self.txt_wall_url.setText(config.EXAM_URLS[et])
            self.txt_ss_url.setText(config.EXAM_URLS[et])
        else:
            wall_url = cfg["wallpaper"]["url"]
            self.txt_wall_url.setText("" if wall_url == config.DEFAULT_URL else wall_url)
            ss_url = cfg["screensaver"]["url"]
            self.txt_ss_url.setText("" if ss_url == config.DEFAULT_URL else ss_url)
        self._on_exam_changed(auto_enable=False)
        self.chk_wall.setChecked(bool(cfg["wallpaper"]["enabled"]))
        self.chk_ss.setChecked(bool(cfg["screensaver"]["enabled"]))
        try:
            self.spin_timeout.setValue(int(cfg["screensaver"]["timeout"]))
        except (TypeError, ValueError):
            self.spin_timeout.setValue(600)
        wall_fit = cfg["wallpaper"].get("fit", "cover")
        self.cmb_wall_fit.setCurrentIndex(max(0, self.cmb_wall_fit.findData(wall_fit)))
        ss_fit = cfg["screensaver"].get("fit", "cover")
        self.cmb_ss_fit.setCurrentIndex(max(0, self.cmb_ss_fit.findData(ss_fit)))
        self.chk_wall_mute.setChecked(bool(cfg["wallpaper"].get("mute", True)))
        self.chk_ss_mute.setChecked(bool(cfg["screensaver"].get("mute", True)))
        self.chk_video_loop.setChecked(bool(cfg.get("playback", {}).get("video_loop", True)))
        self.chk_startup.setChecked(bool(cfg.get("run_at_startup")))

    def save_all(self) -> bool:
        """写回全部设置。返回壁纸配置是否变化（需要重启播放器）。"""
        from . import config
        cfg = self.app.cfg
        old_enabled = bool(cfg["wallpaper"]["enabled"])
        old_url = cfg["wallpaper"]["url"]
        old_fit = cfg["wallpaper"].get("fit", "cover")
        old_mute = bool(cfg["wallpaper"].get("mute", True))

        et = self.cmb_exam.currentData() or "gaokao"
        cfg["exam_type"] = et
        if et in config.EXAM_URLS:
            cfg["wallpaper"]["url"] = config.EXAM_URLS[et]
            cfg["screensaver"]["url"] = config.EXAM_URLS[et]
        else:
            cfg["wallpaper"]["url"] = _normalize_url(self.txt_wall_url.text())
            cfg["screensaver"]["url"] = _normalize_url(self.txt_ss_url.text())
        cfg["wallpaper"]["enabled"] = self.chk_wall.isChecked()
        cfg["wallpaper"]["fit"] = self.cmb_wall_fit.currentData() or "cover"
        cfg["wallpaper"]["mute"] = self.chk_wall_mute.isChecked()
        cfg["screensaver"]["enabled"] = self.chk_ss.isChecked()
        cfg["screensaver"]["timeout"] = self.spin_timeout.value()
        cfg["screensaver"]["fit"] = self.cmb_ss_fit.currentData() or "cover"
        cfg["screensaver"]["mute"] = self.chk_ss_mute.isChecked()
        cfg.setdefault("playback", {})["video_loop"] = self.chk_video_loop.isChecked()
        # 先同步自启（内部可能改 cfg["run_at_startup"]），再统一落盘一次
        self.app.set_autostart(self.chk_startup.isChecked())
        config.save(cfg)
        log.info("config saved")

        return (cfg["wallpaper"]["enabled"] != old_enabled
                or cfg["wallpaper"]["url"] != old_url
                or cfg["wallpaper"]["fit"] != old_fit
                or cfg["wallpaper"]["mute"] != old_mute)

    # 兼容旧调用名
    load = load_all
    save = save_all

    # ---------------- 按钮 ----------------
    def accept(self) -> None:  # 保存
        changed = self.save_all()
        # 先关窗再重启播放器：stop_wallpaper 里要等子进程退出（最长 3 秒 + 屏保 3 秒），
        # 放在关窗之前会让"保存"看起来卡死（历史体验问题）。
        super().accept()
        if changed:
            QTimer.singleShot(0, lambda: self.app.restart_wallplayer_if_needed(True))

    def reject(self) -> None:  # 取消/关闭
        super().reject()
