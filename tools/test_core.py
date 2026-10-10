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

_TMP_LOG_DIR = None
_ORIG_DAEMON_LOG = None


def setUpModule():
    """单测不许往用户真正的 daemon.log 里写字。

    2026-10-06 的真实教训：排查"beta32 看不到正式版"时，日志里的
    「GitHub API 带 token 失败」「所有渠道都失败」其实是单测留下的
    （测试只改了 STATE_FILE / SETTINGS_FILE，忘了日志文件），白查了一轮。
    """
    global _TMP_LOG_DIR, _ORIG_DAEMON_LOG
    import src.core as core

    _TMP_LOG_DIR = tempfile.TemporaryDirectory()
    _ORIG_DAEMON_LOG = core.DAEMON_LOG
    core.DAEMON_LOG = os.path.join(_TMP_LOG_DIR.name, "daemon.log")


def tearDownModule():
    import src.core as core

    if _ORIG_DAEMON_LOG:
        core.DAEMON_LOG = _ORIG_DAEMON_LOG
    if _TMP_LOG_DIR:
        _TMP_LOG_DIR.cleanup()


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

    def test_touch_keeps_a_slow_but_alive_download_from_looking_dead(self):
        # 教室网络慢：进度 5 分钟没动，但下载线程还活着 → 不能被判成中断
        self.core.set_download_state("9.9.9", 0.0, "downloading")
        st = self.core.load_state()
        st["launcher_download"]["updated_at"] = (
            self.time.time() - self.core.DOWNLOAD_STALE_SECONDS - 5)
        self.core.save_state(st)
        self.assertEqual(self.core.get_download_state()["status"], "interrupted")
        self.core.touch_download_state()
        self.assertEqual(self.core.get_download_state()["status"], "downloading")

    def test_touch_does_nothing_when_not_downloading(self):
        self.core.set_download_state("9.9.9", 0.0, "failed")
        before = self.core.load_state()["launcher_download"]["updated_at"]
        self.core.touch_download_state()
        after = self.core.load_state()["launcher_download"]["updated_at"]
        self.assertEqual(before, after)

    def test_clear_download_state(self):
        self.core.set_download_state("9.9.9", 5.0, "failed")
        self.core.clear_download_state("测试")
        self.assertEqual(self.core.get_download_state(), {})

    def test_progress_is_clamped(self):
        self.core.set_download_state("9.9.9", 999, "downloading")
        self.assertEqual(self.core.get_download_state()["progress"], 100.0)
        self.core.set_download_state("9.9.9", -5, "downloading")
        self.assertEqual(self.core.get_download_state()["progress"], 0.0)


class TestDownloadApiFields(unittest.TestCase):
    """回归：接口给前端的进度必须是 0~1 的小数。

    历史 bug：后端返回 0~100，前端又乘 100 → 界面会显示 10000%。
    """

    def setUp(self):
        import src.core as core
        import time

        self.core = core
        self.time = time
        self._old = core.STATE_FILE
        self._tmp = tempfile.TemporaryDirectory()
        core.STATE_FILE = os.path.join(self._tmp.name, "state.json")
        try:
            from src import backend_server as bs
        except Exception as e:  # 缺 GUI 依赖时跳过
            self.skipTest(f"backend_server 不可导入: {e}")
            return
        self.bs = bs

    def tearDown(self):
        self.core.STATE_FILE = self._old
        self._tmp.cleanup()

    def test_download_fields_are_fraction(self):
        # _download_fields 不碰 self，可以拿任意对象当 self 调
        empty = self.bs.ApiHandler._download_fields(object())
        self.assertFalse(empty["downloading"])
        self.assertEqual(empty["download_progress"], 0.0)
        self.assertIsNone(empty["download_version"])

        self.core.set_download_state("9.9.9", 42.0, "downloading", "D:/x/a.exe")
        f = self.bs.ApiHandler._download_fields(object())
        self.assertTrue(f["downloading"])
        self.assertAlmostEqual(f["download_progress"], 0.42, places=3)
        self.assertEqual(f["download_status"], "downloading")
        self.assertEqual(f["download_version"], "9.9.9")

    def test_stale_download_is_not_reported_as_downloading(self):
        self.core.set_download_state("9.9.9", 5.0, "downloading")
        st = self.core.load_state()
        st["launcher_download"]["updated_at"] = (
            self.time.time() - self.core.DOWNLOAD_STALE_SECONDS - 5)
        self.core.save_state(st)
        f = self.bs.ApiHandler._download_fields(object())
        self.assertFalse(f["downloading"], "卡死的下载不该让界面一直转圈")

    def test_latest_seen_version_only_when_newer(self):
        self.core.save_state({"latest_seen_version": self.core.LAUNCHER_VERSION})
        self.assertIsNone(self.bs.ApiHandler._latest_seen_version(object()),
                          "等于当前版本不算新版本")
        self.core.save_state({"latest_seen_version": "99.0.0.0"})
        self.assertEqual(self.bs.ApiHandler._latest_seen_version(object()),
                         "99.0.0.0")


class TestUpdateCheckChannel(unittest.TestCase):
    """回归：更新检查曾经"永远查不到"，界面还谎报"已是最新"。

    两个真实原因（beta29 装机实测：装着的版本坚信自己是最新版）：
      1. `_http_json` 给所有请求都加了 `Accept: application/vnd.github+json`
         （GitHub 专用媒体类型）。Supabase 的 PostgREST 直接判 406：
         PGRST107 "None of these media types are available"。
         而异常被整个吞掉 —— 所以一直是静默失败。
      2. 打包时把 Actions 的临时 GITHUB_TOKEN 塞进了 exe，构建结束就失效，
         GitHub 兜底渠道全部 401。
    这里把"请求头"和"查不查得成的结论"都钉住。
    """

    def setUp(self):
        import src.core as core

        self.core = core
        self._orig_version = core.LAUNCHER_VERSION
        self._orig_http = core._http_json
        self._orig_token = core.GITHUB_TOKEN

    def tearDown(self):
        self.core.LAUNCHER_VERSION = self._orig_version
        self.core._http_json = self._orig_http
        self.core.GITHUB_TOKEN = self._orig_token

    def test_http_json_accept_header_is_not_github_media_type(self):
        """Accept 头必须是通用 JSON：发 GitHub 专用类型会被 Supabase 判 406。"""
        import urllib.request

        seen = {}

        class _Resp:
            def read(self):
                return b"[]"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None, context=None):
            seen["headers"] = {k.lower(): v for k, v in req.header_items()}
            return _Resp()

        orig = urllib.request.urlopen
        urllib.request.urlopen = fake_urlopen
        try:
            self.core._http_json("https://example.supabase.co/rest/v1/x")
        finally:
            urllib.request.urlopen = orig

        accept = seen["headers"].get("accept", "")
        self.assertNotIn("vnd.github", accept.lower(),
                         "GitHub 专用 Accept 会让 Supabase 返回 406")
        self.assertIn("json", accept.lower())

    def test_supabase_row_that_is_newer_wins(self):
        """Supabase 说是新版本就必须认（这是不限流的主渠道）。"""
        self.core.LAUNCHER_VERSION = "3.0.0.0-beta29"

        def fake_http(url, timeout=10, headers=None, label=""):
            if "latest_version" in url:
                return [{
                    "version": "3.0.0.0-beta31",
                    "download_url": "https://example/beta31.exe",
                    "sha256": "ABC",
                    "release_notes": "notes",
                }]
            return None

        self.core._http_json = fake_http
        info = self.core.get_latest_launcher_info()
        self.assertIsNotNone(info, "Supabase 有更新的版本却查不到")
        self.assertEqual(info["version"], "3.0.0.0-beta31")
        self.assertEqual(self.core.last_check_result()["ok"], True)

    def test_no_reachable_channel_is_reported_as_failure(self):
        """所有渠道都拿不到时，必须说"没查成"，不能说"已是最新"。"""
        self.core.LAUNCHER_VERSION = "3.0.0.0-beta29"
        self.core._http_json = lambda *a, **k: None

        info = self.core.get_latest_launcher_info()
        self.assertIsNone(info)
        result = self.core.last_check_result()
        self.assertIs(result["ok"], False,
                      "查不到还报 ok=True，界面就会谎报'已是最新'")
        self.assertTrue(result["detail"])

    def test_supabase_answering_latest_is_not_a_failure(self):
        """Supabase 明确回答"没有更新的版本"时，ok 必须是 True。"""
        self.core.LAUNCHER_VERSION = "3.0.0.0-beta31"
        self.core._http_json = lambda *a, **k: [{"version": "3.0.0.0-beta31"}]

        self.assertIsNone(self.core.get_latest_launcher_info())
        result = self.core.last_check_result()
        self.assertIs(result["ok"], True)
        self.assertEqual(result["detail"], "已是最新")

    def test_github_retries_without_dead_token(self):
        """带 token 失败（401）要能自动降级成未认证重试。"""
        calls = []

        def fake_http(url, timeout=10, headers=None, label=""):
            calls.append(dict(headers or {}))
            return None if len(calls) == 1 else [{"name": "v9.9.9.9"}]

        self.core._http_json = fake_http
        self.core.GITHUB_TOKEN = "ghp_dead_token"
        data = self.core._github_json("https://api.github.com/x")
        self.assertEqual(len(calls), 2, "带 token 失败后应该再试一次")
        self.assertIn("Authorization", calls[0])
        self.assertNotIn("Authorization", calls[1],
                         "重试必须去掉那个已经失效的 token")
        self.assertIsNotNone(data)


class TestUpdateCheckApiFields(unittest.TestCase):
    """接口要把"查成没查成"透给前端，否则界面只能靠猜。"""

    def setUp(self):
        import src.core as core

        self.core = core
        self._old = core.STATE_FILE
        self._tmp = tempfile.TemporaryDirectory()
        core.STATE_FILE = os.path.join(self._tmp.name, "state.json")
        try:
            from src import backend_server as bs
        except Exception as e:  # 缺 GUI 依赖时跳过
            self.skipTest(f"backend_server 不可导入: {e}")
            return
        self.bs = bs

    def tearDown(self):
        self.core.STATE_FILE = self._old
        self._tmp.cleanup()

    def test_check_state_is_persisted_and_exposed(self):
        self.core.save_state({
            "launcher_check_ok": False,
            "launcher_check_detail": "连不上更新服务器",
            "latest_seen_version": "",
        })
        state = self.core.load_state()
        self.assertIs(state.get("launcher_check_ok"), False)
        self.assertEqual(state.get("launcher_check_detail"), "连不上更新服务器")
        # 前端读的就是这两个字段
        self.assertIsNone(self.bs.ApiHandler._latest_seen_version(object()))


class TestUpdateChannelSelection(unittest.TestCase):
    """回归：beta 装机版必须能被拉到正式版。

    历史设计：beta 版只查 `channel=eq.beta&is_latest=eq.true`。
    正式版发布时那条 beta 记录还在（is_latest 还是 true），
    查询返回的就是它自己 → 判成"已是最新" → beta 用户永远升不到正式版。
    现在的规矩：beta 版查所有渠道的 is_latest 再挑最高的；正式版只认 stable。
    """

    def setUp(self):
        import src.core as core

        self.core = core
        self._orig_version = core.LAUNCHER_VERSION
        self._orig_http = core._http_json
        self._orig_settings = core.load_settings
        self.urls = []
        # 隔离真实设置文件：用户测试时可能点开过「β 版试用」，那会让
        # "正式版只认 stable" 的用例失真（正式版开着 β 试用本来就该被拉到 β）。
        # 这里固定成"没选过"，渠道只看构建版本。
        self.core.load_settings = lambda: dict(core.DEFAULT_SETTINGS)

    def tearDown(self):
        self.core.LAUNCHER_VERSION = self._orig_version
        self.core._http_json = self._orig_http
        self.core.load_settings = self._orig_settings

    def _stub(self, rows):
        def fake_http(url, timeout=10, headers=None, label=""):
            self.urls.append(url)
            if "latest_version" in url:
                return rows
            return None

        self.core._http_json = fake_http

    def test_beta_install_sees_stable_release(self):
        self.core.LAUNCHER_VERSION = "3.0.0.0-beta32"
        self._stub([
            {"version": "3.0.0.0-beta32", "download_url": "beta32",
             "sha256": "B", "release_notes": ""},
            {"version": "3.0.0.0", "download_url": "stable",
             "sha256": "S", "release_notes": "正式版"},
        ])
        info = self.core.get_latest_launcher_info()
        self.assertIsNotNone(info, "beta 装机版看不到正式版就一直卡在 beta")
        self.assertEqual(info["version"], "3.0.0.0")
        self.assertEqual(info["sha256"], "S",
                         "必须挑版本号最高的那条（正式版压过 beta）")
        # 查询本身不能再按渠道过滤，否则只会拿回自己的 beta 记录
        self.assertIn("is_latest=eq.true", self.urls[0])
        self.assertNotIn("channel=eq.beta", self.urls[0])

    def test_beta_install_picks_newer_beta_over_older_stable(self):
        self.core.LAUNCHER_VERSION = "3.0.0.0-beta32"
        self._stub([
            {"version": "3.0.0.0", "download_url": "stable", "sha256": "S"},
            {"version": "3.0.1.0-beta1", "download_url": "beta1", "sha256": "B"},
        ])
        info = self.core.get_latest_launcher_info()
        self.assertIsNotNone(info)
        self.assertEqual(info["version"], "3.0.1.0-beta1")

    def test_stable_install_is_not_pulled_to_beta(self):
        self.core.LAUNCHER_VERSION = "3.0.0.0"
        self._stub([
            {"version": "3.0.0.0", "download_url": "stable", "sha256": "S"},
            {"version": "3.0.1.0-beta1", "download_url": "beta1", "sha256": "B"},
        ])
        info = self.core.get_latest_launcher_info()
        self.assertIsNone(info, "正式版用户不该被拉去装 beta")
        self.assertIs(self.core.last_check_result()["ok"], True)
        self.assertIn("channel=eq.stable", self.urls[0])

    def test_stable_install_sees_next_stable(self):
        self.core.LAUNCHER_VERSION = "3.0.0.0"
        self._stub([{"version": "3.0.1.0", "download_url": "u", "sha256": "S"}])
        info = self.core.get_latest_launcher_info()
        self.assertIsNotNone(info)
        self.assertEqual(info["version"], "3.0.1.0")


class TestBetaTrialChannel(unittest.TestCase):
    """β 版试用开关如何决定"该查哪个渠道"。

    产品规则：
      * 开启（True）：即使当前是正式版，也按 β 渠道查 → 能被拉到 β；
      * 关闭（False）：即使当前正跑着 β 版，也只查正式版 → "停查 β"，
        并自然等到一个 ≥ 当前主版本的正式版出现才升级过去；
      * 没选过（None）：按构建版本决定（beta 版自带 β 行为）。
    """

    def setUp(self):
        import src.core as core

        self.core = core
        self._orig_version = core.LAUNCHER_VERSION
        self._orig_http = core._http_json
        self._orig_settings = core.load_settings
        self.urls = []
        self._ROWS = [
            {"version": "3.0.0.0", "download_url": "stable", "sha256": "S"},
            {"version": "3.0.1.0-beta1", "download_url": "beta1", "sha256": "B"},
        ]

    def tearDown(self):
        self.core.LAUNCHER_VERSION = self._orig_version
        self.core._http_json = self._orig_http
        self.core.load_settings = self._orig_settings

    def _stub(self, beta_trial):
        def fake_http(url, timeout=10, headers=None, label=""):
            self.urls.append(url)
            if "latest_version" in url:
                return self._ROWS
            return None

        self.core._http_json = fake_http
        cfg = dict(self.core.DEFAULT_SETTINGS)
        cfg["beta_trial"] = beta_trial
        self.core.load_settings = lambda: dict(cfg)

    def test_trial_on_stable_build_sees_beta(self):
        self.core.LAUNCHER_VERSION = "3.0.0.0"  # 正式版
        self._stub(beta_trial=True)             # 但用户开了 β 试用
        info = self.core.get_latest_launcher_info()
        self.assertIsNotNone(info, "开了 β 试用就该能看到 β 版")
        self.assertEqual(info["version"], "3.0.1.0-beta1")
        self.assertNotIn("channel=eq.stable", self.urls[0])

    def test_trial_off_on_beta_build_not_pulled_to_newer_beta(self):
        self.core.LAUNCHER_VERSION = "3.0.0.0-beta40"  # 正跑着 beta
        self._stub(beta_trial=False)                   # 用户关了试用
        info = self.core.get_latest_launcher_info()
        # 关掉后不该再被拉去 3.0.1.0-beta1；同号正式版 3.0.0.0 >= 当前主版本 → 升级过去
        self.assertIsNotNone(info, "关掉试用后应等到同号正式版并升级过去")
        self.assertEqual(info["version"], "3.0.0.0")
        self.assertIn("channel=eq.stable", self.urls[0])

    def test_trial_unset_follows_build_version(self):
        self.core.LAUNCHER_VERSION = "3.0.0.0-beta40"
        self._stub(beta_trial=None)  # 没选过
        info = self.core.get_latest_launcher_info()
        self.assertIsNotNone(info)
        self.assertEqual(info["version"], "3.0.1.0-beta1",
                         "没设置过的 beta 版应保留原来的 β 行为")


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
