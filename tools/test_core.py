#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""核心逻辑单元测试"""
import sys, os, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

class TestVersionComparison(unittest.TestCase):
    def test_beta_versions(self):
        from core import compare_versions
        self.assertLess(compare_versions("3.0.0.0-beta18", "3.0.0.0-beta19"), 0)
        self.assertGreater(compare_versions("3.0.0.0-beta10", "3.0.0.0-beta9"), 0)
        self.assertEqual(compare_versions("3.0.0.0-beta19", "3.0.0.0-beta19"), 0)
    def test_beta_vs_stable(self):
        from core import compare_versions
        self.assertLess(compare_versions("3.0.0.0-beta19", "3.0.0.0"), 0)
    def test_is_beta(self):
        from core import is_beta_version
        self.assertTrue(is_beta_version("3.0.0.0-beta19"))
        self.assertFalse(is_beta_version("3.0.0.0"))

class TestPasswordEncryption(unittest.TestCase):
    def test_encrypt_decrypt(self):
        from core import _encrypt_morning_password, _decrypt_morning_password
        for pwd in ["admin11", "admin01", ""]:
            enc = _encrypt_morning_password(pwd)
            dec = _decrypt_morning_password(enc)
            self.assertEqual(dec, pwd)
    def test_format(self):
        from core import _encrypt_morning_password
        self.assertTrue(_encrypt_morning_password("admin11").startswith("enc:"))
    def test_plaintext_compat(self):
        from core import _decrypt_morning_password
        self.assertEqual(_decrypt_morning_password("admin11"), "admin11")

class TestSHA256(unittest.TestCase):
    def test_verify(self):
        from core import sha256_of, verify_sha256
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"test")
            path = f.name
        try:
            self.assertTrue(verify_sha256(path, sha256_of(path)))
            self.assertFalse(verify_sha256(path, "0"*64))
        finally:
            os.unlink(path)

class TestInstallerCleanup(unittest.TestCase):
    def test_remove_with_aria2(self):
        from core import _remove_installer
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "test.exe")
            aria2 = exe + ".aria2"
            open(exe, "w").close()
            open(aria2, "w").close()
            _remove_installer(exe)
            self.assertFalse(os.path.isfile(exe))
            self.assertFalse(os.path.isfile(aria2))

if __name__ == "__main__":
    unittest.main(verbosity=2)
