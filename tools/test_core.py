#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""后端核心逻辑单元测试。

运行： python tools/test_core.py
（CI 里每次发布都会跑；不依赖网络、不写系统目录）
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _console import setup_console  # noqa: E402

# unittest 会把中文用例名打到 stderr：CI runner 是 cp1252、中文 Windows 是 GBK，
# 不切换编码会以 UnicodeEncodeError 的形式表现成"测试失败"。
setup_console()

from src import morning_config  # noqa: E402
from src.core import (  # noqa: E402
    compare_versions,
    is_beta_version,
    parse_version,
    sha256_of,
    verify_sha256,
    _installer_files,
)


class TestVersionComparison(unittest.TestCase):
    def test_beta_ordering(self):
        self.assertLess(compare_versions("3.0.0.0-beta18", "3.0.0.0-beta19"), 0)
        self.assertGreater(compare_versions("3.0.0.0-beta10", "3.0.0.0-beta9"), 0)
        self.assertEqual(compare_versions("3.0.0.0-beta19", "3.0.0.0-beta19"), 0)

    def test_beta_vs_stable(self):
        self.assertLess(compare_versions("3.0.0.0-beta19", "3.0.0.0"), 0)
        self.assertGreater(compare_versions("3.0.0.0", "3.0.0.0-beta99"), 0)

    def test_tolerant_input(self):
        self.assertEqual(compare_versions("v3.0.0.0", "3.0.0.0"), 0)
        self.assertEqual(compare_versions("3.0", "3.0.0.0"), 0)
        self.assertLess(compare_versions("3.0.0.0", "3.0.0.1"), 0)

    def test_is_beta(self):
        self.assertTrue(is_beta_version("3.0.0.0-beta19"))
        self.assertTrue(is_beta_version("3.0.0.0-rc1"))
        self.assertFalse(is_beta_version("3.0.0.0"))
        self.assertEqual(parse_version("3.0.0.0-beta7")[1], 2)


class TestMorningPassword(unittest.TestCase):
    def test_roundtrip(self):
        for pwd in ("admin11", "admin01", "带中文的密码", ""):
            enc = morning_config.encrypt_password(pwd)
            self.assertEqual(morning_config.decrypt_password(enc), pwd)

    def test_format_and_plaintext_compat(self):
        self.assertTrue(morning_config.encrypt_password("admin11").startswith("enc:"))
        # 旧版本的明文配置仍然可以读
        self.assertEqual(morning_config.decrypt_password("admin11"), "admin11")
        # 解不开时返回空串，而不是把密文当密码用
        self.assertEqual(morning_config.decrypt_password("enc:!!!not-base64!!!"), "")


class TestSha256(unittest.TestCase):
    def test_verify(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"idiot-launch")
            path = f.name
        try:
            self.assertTrue(verify_sha256(path, sha256_of(path)))
            self.assertTrue(verify_sha256(path, "sha256:" + sha256_of(path).upper()))
            self.assertFalse(verify_sha256(path, "0" * 64))
            # 没有哈希信息时跳过校验（兼容旧 release）
            self.assertTrue(verify_sha256(path, ""))
        finally:
            os.unlink(path)


class TestInstallerCleanup(unittest.TestCase):
    def test_matches_aria2_partials(self):
        """安装包相关的分片/控制文件都要能被识别出来（原来只删 .aria2）。"""
        import src.core as core

        old_dir = core.UPDATE_DIR
        with tempfile.TemporaryDirectory() as d:
            core.UPDATE_DIR = d
            try:
                for name in ("Setup_x.exe", "Setup_x.exe.aria2",
                             "Setup_x.exe.0.part", "Setup_x.exe.8716.part"):
                    open(os.path.join(d, name), "w").close()
                found = list(_installer_files(os.path.join(d, "Setup_x.exe")))
                self.assertEqual(len(found), 4)
                core._remove_installer(os.path.join(d, "Setup_x.exe"))
                self.assertEqual(os.listdir(d), [])
            finally:
                core.UPDATE_DIR = old_dir


class TestSettings(unittest.TestCase):
    def test_defaults_and_patch(self):
        import src.core as core

        old_file = core.SETTINGS_FILE
        with tempfile.TemporaryDirectory() as d:
            core.SETTINGS_FILE = os.path.join(d, "settings.json")
            try:
                cfg = core.load_settings()
                self.assertTrue(cfg["auto_update"])
                self.assertEqual(cfg["theme"], "system")
                core.save_settings({"theme": "dark", "不存在的键": 1})
                cfg = core.load_settings()
                self.assertEqual(cfg["theme"], "dark")
                self.assertNotIn("不存在的键", cfg)
            finally:
                core.SETTINGS_FILE = old_file


class TestManualUpdateCheck(unittest.TestCase):
    """回归：点"检查更新"不能把 last_check 清零。

    清零会让界面立刻从"x 分钟前检查过"变成"还没有检查过更新"（用户实测反馈）。
    """

    def test_force_check_flag_without_clearing_timestamp(self):
        import src.core as core

        old_state = core.STATE_FILE
        with tempfile.TemporaryDirectory() as d:
            core.STATE_FILE = os.path.join(d, "state.json")
            try:
                core.save_state({"launcher_last_check": 1234.5})
                core._handle_daemon_command({"cmd": "check_updates"})
                st = core.load_state()
                self.assertEqual(st.get("launcher_last_check"), 1234.5)
                self.assertTrue(st.get("force_check"))
            finally:
                core.STATE_FILE = old_state


class TestDownloadState(unittest.TestCase):
    """回归：界面上的"正在后台下载 N%"完全依赖这几个函数。

    用户实测（beta27/beta28）：进度永远是 0%，而且状态一直卡在 downloading，
    看起来像一直在下载。根因就是进度没写进 launcher_download、且中断后没人清。
    """

    def setUp(self):
        import src.core as core
        import time

        self.core = core
        self.time = time
        self._old = core.STATE_FILE
        self._tmp = tempfile.TemporaryDirectory()
        core.STATE_FILE = os.path.join(self._tmp.name, "state.json")

    def tearDown(self):
        self.core.STATE_FILE = self._old
        self._tmp.cleanup()

    def test_progress_is_written_and_readable(self):
        self.core.set_download_state("9.9.9", 42.5, "downloading",
                                     "D:/x/Setup.exe", "notes")
        dl = self.core.get_download_state()
        self.assertEqual(dl["status"], "downloading")
        self.assertEqual(dl["progress"], 42.5)
        self.assertEqual(dl["version"], "9.9.9")
        self.assertTrue(dl.get("updated_at"))

    def test_stale_downloading_is_reported_as_interrupted(self):
        self.core.set_download_state("9.9.9", 10.0, "downloading")
        st = self.core.load_state()
        st["launcher_download"]["updated_at"] = (
            self.time.time() - self.core.DOWNLOAD_STALE_SECONDS - 5)
        self.core.save_state(st)
        self.assertEqual(self.core.get_download_state()["status"], "interrupted")

    def test_startup_clears_leftover_download(self):
        # 用户遇到的情况：state 里留着"正在下载 beta27"，但当前已经是 beta28
        self.core.set_download_state("3.0.0.0-beta1", 0.0, "downloading")
        self.core._clear_stale_download_on_start()
        self.assertEqual(self.core.get_download_state(), {},
                         "启动时必须清掉上次没下完的状态，否则界面永远显示下载中")

    def test_clear_download_state(self):
        self.core.set_download_state("9.9.9", 5.0, "failed")
        self.core.clear_download_state("测试")
        self.assertEqual(self.core.get_download_state(), {})

    def test_progress_is_clamped(self):
        self.core.set_download_state("9.9.9", 999, "downloading")
        self.assertEqual(self.core.get_download_state()["progress"], 100.0)
        self.core.set_download_state("9.9.9", -5, "downloading")
        self.assertEqual(self.core.get_download_state()["progress"], 0.0)


class TestProcessKillSafety(unittest.TestCase):
    """回归：结束进程前必须确认映像名，绝不能误杀（PID 会被复用）。"""

    def test_refuses_self_and_foreign_process(self):
        try:
            from src import backend_server as bs
        except Exception as e:  # 缺 GUI 依赖时跳过（CI 里装了 PySide6）
            self.skipTest(f"backend_server 不可导入: {e}")
            return

        self.assertFalse(bs._kill_process(os.getpid()))
        self.assertFalse(bs._kill_process(0))

        import subprocess
        import time as _time

        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
        try:
            _time.sleep(0.5)
            self.assertFalse(bs._kill_process(proc.pid),
                             "不应该结束非本程序的进程")
            self.assertIsNone(proc.poll(), "目标进程被误杀了")
        finally:
            proc.kill()


if __name__ == "__main__":
    unittest.main(verbosity=2)
