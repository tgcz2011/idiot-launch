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


if __name__ == "__main__":
    unittest.main(verbosity=2)
