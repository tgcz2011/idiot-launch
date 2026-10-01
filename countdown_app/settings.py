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

from PySide6.QtCore import QUrl, QSize, Qt
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
        self.cmb_exam.currentIndexChanged.connect(self._on_exam_changed)
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
        self.btn_test.clicked.connect(lambda: self.app.start_screensaver())
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
        from .update import REPO_PAGE

        grp = QGroupBox("关于")
        form = QFormLayout(grp)
        for label, value in (("程序", "Countdown Desktop"),
                             ("版本", "v%s" % version.VERSION),
                             ("功能", "动态壁纸 + 屏幕保护（网页/视频/图片/动图）"),
                             ("渲染", "pywebview + WebView2（Chromium）")):
            text = QLabel(value)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(label, text)
        link_repo = QLabel('<a href="%s">GitHub 仓库（tgcz2011/countdown-desktop）</a>'
                           % REPO_PAGE)
        link_repo.setOpenExternalLinks(True)
        form.addRow("源码", link_repo)
        link_issue = QLabel('<a href="%s/issues">反馈问题 / 提交建议</a>' % REPO_PAGE)
        link_issue.setOpenExternalLinks(True)
        form.addRow("反馈", link_issue)
        layout.addWidget(grp)

        # ---- 检查更新 ----
        grp_upd = QGroupBox("更新")
        v_upd = QVBoxLayout(grp_upd)
        self.lbl_update = QLabel("点击「检查更新」查询 GitHub 最新版本")
        self.lbl_update.setWordWrap(True)
        v_upd.addWidget(self.lbl_update)
        row_upd = QHBoxLayout()
        self.btn_check_update = QPushButton("检查更新")
        self.btn_check_update.clicked.connect(self._on_check_update)
        row_upd.addWidget(self.btn_check_update)
        self.btn_update_now = QPushButton("一键更新")
        self.btn_update_now.setEnabled(False)
        self.btn_update_now.clicked.connect(self._on_update_now)
        row_upd.addWidget(self.btn_update_now)
        self.btn_open_release = QPushButton("打开发布页")
        self.btn_open_release.clicked.connect(self._on_open_release)
        row_upd.addWidget(self.btn_open_release)
        row_upd.addStretch()
        v_upd.addLayout(row_upd)
        self.chk_auto_update = QCheckBox("启动时自动检查更新（仅提示，不自动下载）")
        self.chk_auto_update.setChecked(
            bool(self.app.cfg.get("auto_check_update", True)))
        self.chk_auto_update.toggled.connect(self._on_auto_update_toggled)
        v_upd.addWidget(self.chk_auto_update)
        layout.addWidget(grp_upd)

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

        # 更新检查器（随对话框销毁）
        from .update import UpdateChecker
        self.updater = UpdateChecker(self)
        self.updater.checkFinished.connect(self._on_check_finished)
        self.updater.downloadProgress.connect(self._on_download_progress)
        self.updater.downloadFinished.connect(self._on_download_finished)
        self._update_installer_path = ""
        if self.chk_auto_update.isChecked():
            self.updater.check()
            self.lbl_update.setText("正在检查更新…")

        layout.addStretch()
        return page

    # ---------------- 更新 ----------------
    def about_page_labels(self):
        """关于页内全部 QLabel（测试与文案检查用）。"""
        page = self._pages.get("about", (None, None))[0]
        return page.findChildren(QLabel)

    def _on_check_update(self) -> None:
        self.btn_check_update.setEnabled(False)
        self.lbl_update.setText("正在检查更新…")
        self.updater.check()

    def _on_check_finished(self, has_update: bool, latest: str, notes: str) -> None:
        self.btn_check_update.setEnabled(True)
        if has_update:
            self.btn_update_now.setEnabled(True)
            text = "发现新版本 v%s，可一键更新（下载后自动静默安装并重启）" % latest
            if notes:
                text += "\n更新说明：" + notes
            self.lbl_update.setText(text)
        elif latest:
            self.lbl_update.setText("已是最新版本（v%s）" % latest)
        else:
            self.lbl_update.setText("检查更新失败，请稍后重试或直接打开发布页")

    def _on_update_now(self) -> None:
        self.btn_update_now.setEnabled(False)
        self.lbl_update.setText("正在下载更新…")
        self.updater.download()

    def _on_download_progress(self, received: int, total: int) -> None:
        pct = int(received * 100 / total) if total else 0
        self.lbl_update.setText("正在下载更新… %d%%（%.1f / %.1f MB）"
                                % (pct, received / 1048576.0, total / 1048576.0))

    def _on_download_finished(self, ok: bool, payload: str) -> None:
        if not ok:
            self.lbl_update.setText("下载失败：%s。可打开发布页手动下载。" % payload)
            self.btn_update_now.setEnabled(True)
            return
        self._update_installer_path = payload
        try:
            from .update import make_update_bat, run_update_bat
            bat = make_update_bat(payload)
            run_update_bat(bat)
            self.lbl_update.setText("更新包已就绪，正在退出程序并安装新版本…")
            # 给标签一点刷新时间，然后退出主程序（批处理负责杀进程+静默安装+重启）
            from PySide6.QtCore import QTimer
            QTimer.singleShot(800, self.app.quit)
        except Exception as e:
            log.exception("prepare update failed")
            self.lbl_update.setText("准备更新失败：%s" % e)
            self.btn_update_now.setEnabled(True)

    def _on_open_release(self) -> None:
        from PySide6.QtGui import QDesktopServices
        from .update import REPO_PAGE
        QDesktopServices.openUrl(QUrl(REPO_PAGE + "/releases"))

    def _on_auto_update_toggled(self, checked: bool) -> None:
        from . import config
        self.app.cfg["auto_check_update"] = bool(checked)
        config.save(self.app.cfg)

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
        self.app.restart_wallplayer_if_needed(changed)
        super().accept()

    def reject(self) -> None:  # 取消/关闭
        super().reject()
