# -*- coding: utf-8 -*-
"""检查更新：GitHub Releases API 查询 + 多镜像源后台下载 + SHA-256 校验 + 静默安装重启。

移植自 Idiot Launch 的成熟更新机制：
- 7 个下载镜像源自动 fallback（GitHub 直连 → gh-proxy → ghfast → ghproxy.net → ...）
- 动态超时：第 1 轮 1x，第 2 轮 2x，第 3 轮 3x（避免短超时内全失败后永远更新不了）
- SHA-256 校验：Release body 里附带的哈希对不上就拒绝更新
- 全部走 QNetworkAccessManager 异步，不卡设置窗口 UI
"""
import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
import time

from PySide6.QtCore import QObject, QUrl, Signal, QTimer
from PySide6.QtNetwork import (QNetworkAccessManager, QNetworkReply,
                               QNetworkRequest)

log = logging.getLogger("update")

REPO_OWNER = "tgcz2011"
REPO_NAME = "countdown-desktop"
REPO_PAGE = "https://github.com/%s/%s" % (REPO_OWNER, REPO_NAME)
REPO_API = "https://api.github.com/repos/%s/%s/releases/latest" % (REPO_OWNER, REPO_NAME)
ASSET_RE = re.compile(r"\.exe$", re.I)
UA = "CountdownDesktop-Updater"
MIN_INSTALLER_BYTES = 1 << 20  # 安装包约 37MB，小于 1MB 视为被拦截/损坏

# 下载镜像源（前缀, 基础超时秒数）——与 Idiot Launch 保持一致
DOWNLOAD_MIRRORS = [
    ("", 60),                           # GitHub 直连
    ("https://gh-proxy.com/", 120),     # GH-Proxy 2.0
    ("https://ghfast.top/", 120),       # ghfast
    ("https://ghproxy.net/", 120),      # ghproxy.net
    ("https://gh.llkk.cc/", 120),       # LLKK
    ("https://hub.gitmirror.com/", 120),# GitMirror
    ("https://ghproxy.homeboyc.cn/", 120),  # 大文件稳定
]
DOWNLOAD_RETRY = 3  # 最多重试 3 轮


def _to_num(v: str) -> int:
    """3.1.1.1 -> 3111（与项目 a.b.c.d 去点严格递增规则一致）。"""
    parts = [p for p in v.strip().lstrip("vV").split(".") if p.isdigit()]
    return int("".join(parts)) if parts else 0


def is_newer(remote: str, local: str) -> bool:
    return _to_num(remote) > _to_num(local)


def _parse_sha256_from_body(body: str, filename: str) -> str:
    """从 Release body 里解析指定文件的 SHA-256 哈希。
    支持格式：`filename.exe: <hash>` 或 `<hash>  filename.exe`
    """
    if not body:
        return ""
    basename = os.path.basename(filename)
    # 格式1: filename: hash
    m = re.search(re.escape(basename) + r"\s*[:：]\s*([a-fA-F0-9]{64})", body)
    if m:
        return m.group(1).lower()
    # 格式2: hash  filename
    m = re.search(r"\b([a-fA-F0-9]{64})\b\s+\*?" + re.escape(basename), body)
    if m:
        return m.group(1).lower()
    # 格式3: 单独一行 hash（取第一个 64 位十六进制）
    m = re.search(r"\b([a-fA-F0-9]{64})\b", body)
    if m:
        return m.group(1).lower()
    return ""


def verify_sha256(filepath: str, expected: str) -> bool:
    """校验文件 SHA-256。expected 为空时跳过校验（返回 True）。"""
    if not expected:
        return True
    if not os.path.isfile(filepath):
        return False
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    actual = h.hexdigest().lower()
    ok = actual == expected.lower()
    if not ok:
        log.warning("SHA-256 mismatch: expected=%s actual=%s", expected, actual)
    return ok


class UpdateChecker(QObject):
    """关于页更新组件。信号驱动，设置窗口关闭即随对象树销毁，无泄漏。"""

    checkFinished = Signal(bool, str, str)  # (有更新, 最新版本, 更新说明/错误)
    downloadProgress = Signal(int, int)     # (received, total)
    downloadFinished = Signal(bool, str)    # (成功, 安装包路径/错误)
    installPrepared = Signal(str)           # (bat 路径)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.nam = QNetworkAccessManager(self)
        self.nam.finished.connect(self._on_finished)
        self._phase = "idle"  # idle / check / meta / asset
        self._latest = ""
        self._release_body = ""
        self._reply = None
        self._fh = None
        self._file_path = ""
        self._original_url = ""
        self._mirror_index = 0
        self._attempt = 0
        self._expected_sha256 = ""

    # ---------------- 公共动作 ----------------
    def check(self) -> None:
        self._phase = "check"
        self.nam.get(self._req(REPO_API))

    def download(self) -> None:
        """先拉 release 元数据拿资产 URL（下载按钮按下时才联网）。"""
        if not self._latest:
            self.downloadFinished.emit(False, "请先检查更新")
            return
        self._phase = "meta"
        self._mirror_index = 0
        self._attempt = 0
        self.nam.get(self._req(REPO_API))

    def cancel(self) -> None:
        if self._reply is not None:
            self._reply.abort()

    # ---------------- 内部 ----------------
    @staticmethod
    def _req(url: str, timeout_ms: int = 120000) -> QNetworkRequest:
        req = QNetworkRequest(QUrl(url))
        req.setHeader(QNetworkRequest.UserAgentHeader, UA)
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        req.setAttribute(QNetworkRequest.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        req.setTransferTimeout(timeout_ms)
        return req

    def _fail(self, msg: str) -> None:
        if self._phase in ("check", "meta"):
            self.checkFinished.emit(False, "", msg)
        else:
            self.downloadFinished.emit(False, msg)
        self._cleanup()

    def _cleanup(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
        self._phase = "idle"

    def _on_finished(self, reply: QNetworkReply) -> None:
        phase = self._phase
        if reply.error() != QNetworkReply.NetworkError.NoError:
            # 下载资产时失败：尝试下一个镜像源
            if phase == "asset":
                self._try_next_mirror("网络错误：%s" % reply.errorString())
                reply.deleteLater()
                return
            self._fail("网络错误：%s" % reply.errorString())
            reply.deleteLater()
            return
        try:
            if phase == "check":
                self._handle_check(reply)
            elif phase == "meta":
                self._handle_meta(reply)
            elif phase == "asset":
                self._handle_asset_done(reply)
        except Exception as e:
            log.exception("update flow error")
            self._fail("更新失败：%s" % e)
        finally:
            if phase != "asset":  # asset 落盘由 _handle_asset_done 收尾
                self._phase = "idle"
            reply.deleteLater()

    def _handle_check(self, reply: QNetworkReply) -> None:
        data = json.loads(bytes(reply.readAll()).decode("utf-8", "replace"))
        if data.get("draft") or data.get("prerelease"):
            self.checkFinished.emit(False, "", "")
            return
        tag = str(data.get("tag_name", "")).lstrip("vV")
        self._latest = tag
        self._release_body = str(data.get("body") or "")
        from . import version
        if not is_newer(tag, version.VERSION):
            self.checkFinished.emit(False, tag, "")
            return
        notes = self._release_body.strip()
        if len(notes) > 500:
            notes = notes[:500] + "..."
        self.checkFinished.emit(True, tag, notes)

    def _handle_meta(self, reply: QNetworkReply) -> None:
        data = json.loads(bytes(reply.readAll()).decode("utf-8", "replace"))
        asset = next((a for a in data.get("assets", [])
                      if ASSET_RE.search(str(a.get("name", "")))), None)
        if not asset:
            self._fail("Release 中未找到安装包资产")
            return
        url = str(asset.get("browser_download_url", ""))
        name = str(asset.get("name", "CountdownDesktop_Setup.exe"))
        self._original_url = url
        self._file_path = os.path.join(tempfile.gettempdir(), name)
        # 从 release body 解析 SHA-256
        self._expected_sha256 = _parse_sha256_from_body(
            str(data.get("body") or ""), name)
        self._start_download()

    def _start_download(self) -> None:
        """用当前镜像源开始下载。"""
        mirror_prefix, base_timeout = DOWNLOAD_MIRRORS[self._mirror_index]
        timeout_multiplier = self._attempt + 1
        timeout_ms = base_timeout * timeout_multiplier * 1000
        full_url = mirror_prefix + self._original_url if mirror_prefix else self._original_url
        source_name = mirror_prefix.rstrip("/") if mirror_prefix else "GitHub direct"
        log.info("下载尝试 (%d/%d) [%s] 超时%ds: %s",
                 self._attempt + 1, DOWNLOAD_RETRY, source_name,
                 timeout_ms // 1000, os.path.basename(self._file_path))
        self._phase = "asset"
        # 清理部分下载的文件
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
        if os.path.exists(self._file_path):
            try:
                os.remove(self._file_path)
            except OSError:
                pass
        rep = self.nam.get(self._req(full_url, timeout_ms))
        self._reply = rep
        rep.downloadProgress.connect(self._on_progress)
        rep.readyRead.connect(self._on_data)

    def _try_next_mirror(self, reason: str) -> None:
        """下载失败：尝试下一个镜像源，或下一轮重试。"""
        log.info("下载失败 [%s]: %s",
                 DOWNLOAD_MIRRORS[self._mirror_index][0] or "direct", reason)
        self._mirror_index += 1
        if self._mirror_index >= len(DOWNLOAD_MIRRORS):
            # 所有镜像源都失败，下一轮重试（递增超时）
            self._mirror_index = 0
            self._attempt += 1
            if self._attempt >= DOWNLOAD_RETRY:
                self._fail("所有镜像源均下载失败，请检查网络或手动下载")
                return
            log.info("所有源失败，第 %d 轮重试（超时 x%d）",
                     self._attempt + 1, self._attempt + 1)
            # 等 5 秒再重试
            QTimer.singleShot(5000, self._start_download)
            return
        self._start_download()

    def _on_data(self) -> None:
        rep = self.sender()
        if self._fh is None:
            self._fh = open(self._file_path, "wb")
        self._fh.write(bytes(rep.readAll()))

    def _on_progress(self, received: int, total: int) -> None:
        if total > 0:
            self.downloadProgress.emit(int(received), int(total))

    def _handle_asset_done(self, reply: QNetworkReply) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        size = os.path.getsize(self._file_path) if os.path.exists(self._file_path) else 0
        if size < MIN_INSTALLER_BYTES:
            self._try_next_mirror("下载文件过小（%d 字节）" % size)
            return
        # SHA-256 校验
        if self._expected_sha256:
            if not verify_sha256(self._file_path, self._expected_sha256):
                self._try_next_mirror("SHA-256 校验失败")
                return
            log.info("SHA-256 校验通过")
        self._phase = "idle"
        self.downloadFinished.emit(True, self._file_path)


def make_update_bat(installer_path: str,
                    exe_name: str = "CountdownDesktop.exe") -> str:
    """生成更新批处理：杀进程 → 静默安装（自动重启应用）→ 兜底拉起。"""
    bat = os.path.join(tempfile.gettempdir(), "CountdownDesktop_update.bat")
    content = """@echo off
rem Countdown Desktop auto-update
taskkill /F /IM {exe} /T >nul 2>&1
timeout /t 2 /nobreak >nul
"{installer}" /SILENT /SUPPRESSMSGBOXES /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS
timeout /t 3 /nobreak >nul
del "%~f0"
""".format(exe=exe_name, installer=installer_path)
    with open(bat, "w", encoding="ascii", errors="strict") as f:
        f.write(content)
    return bat


def run_update_bat(bat_path: str) -> None:
    """脱离主程序执行更新批处理（调用方随后退出主程序）。"""
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    subprocess.Popen(["cmd", "/c", bat_path], creationflags=flags, close_fds=True)
    log.info("update bat launched: %s", bat_path)
