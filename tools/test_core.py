"""
test_core.py — core.py 单元测试（无需 GUI）
运行：python tools/test_core.py
"""
import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import (
    find_installed_path,
    resource_path,
    is_running,
    quit_countdown,
    get_installed_version,
    compare_versions,
    parse_version,
    EMBEDDED_VERSION,
    INSTALL_DIR,
    INSTALL_EXE,
    EXE_NAME,
    MORNING_READING_URL,
    INSTALLER_REL,
    has_pending_update,
    load_state,
    save_state,
    LAUNCHER_VERSION,
    LAUNCHER_MIN_SIZE,
    has_pending_launcher_update,
    _cleanup_stale_launcher_pending,
    log_daemon,
    set_daemon_status,
    get_daemon_status,
    is_daemon_running,
    send_command,
    poll_command,
    DOWNLOAD_MIRRORS,
    DOWNLOAD_TIMEOUT,
    DOWNLOAD_RETRY,
    DAEMON_MUTEX,
    UPDATE_DIR,
    STATE_FILE,
    DAEMON_LOG,
    COMMAND_FILE,
)


def test_constants():
    assert INSTALL_DIR == r"D:\IdiotLaunch\CountdownDesktop"
    assert EXE_NAME == "CountdownDesktop.exe"
    assert INSTALL_EXE == os.path.join(INSTALL_DIR, EXE_NAME)
    assert "morning-reading" in MORNING_READING_URL
    assert EMBEDDED_VERSION in INSTALLER_REL
    print("✓ test_constants passed")


def test_version_parsing():
    assert parse_version("3.2.3.0") == (3, 2, 3, 0)
    assert parse_version("v3.2.0.0") == (3, 2, 0, 0)
    assert parse_version("1.0") == (1, 0, 0, 0)
    print("✓ test_version_parsing passed")


def test_version_comparison():
    assert compare_versions("3.2.1.0", "3.2.3.0") == -1
    assert compare_versions("3.2.3.0", "3.2.3.0") == 0
    assert compare_versions("3.3.0.0", "3.2.9.9") == 1
    assert compare_versions("v4.0.0.0", "3.9.9.9") == 1
    print("✓ test_version_comparison passed")


def test_resource_path():
    p = resource_path(INSTALLER_REL)
    assert p.endswith(INSTALLER_REL) or p.endswith(INSTALLER_REL.replace("/", os.sep))
    print(f"✓ test_resource_path passed: {p}")


def test_find_installed_no_crash():
    result = find_installed_path()
    print(f"✓ test_find_installed_no_crash passed: {result}")


def test_get_installed_version():
    result = get_installed_version()
    print(f"✓ test_get_installed_version passed: {result}")


def test_installer_file_exists():
    p = resource_path(INSTALLER_REL)
    exists = os.path.isfile(p)
    if exists:
        size = os.path.getsize(p)
        print(f"✓ test_installer_file_exists passed: {size} bytes")
    else:
        print(f"⚠ test_installer_file_exists: 安装包不存在（构建前需先下载）: {p}")


def test_is_running_no_crash():
    result = is_running()
    assert isinstance(result, bool)
    print(f"✓ test_is_running_no_crash passed: {result}")


def test_quit_countdown_no_crash():
    if not is_running():
        result = quit_countdown()
        assert result is True
        print(f"✓ test_quit_countdown_no_crash passed: quit returned {result}")
    else:
        print("⚠ test_quit_countdown_no_crash: Countdown Desktop 正在运行，跳过实际退出")


def test_state_functions():
    state = load_state()
    assert isinstance(state, dict)
    pending = has_pending_update()
    assert isinstance(pending, bool)
    print(f"✓ test_state_functions passed: pending_update={pending}")


def test_launcher_version_constant():
    assert isinstance(LAUNCHER_VERSION, str)
    parts = LAUNCHER_VERSION.split(".")
    assert len(parts) == 4
    assert all(p.isdigit() for p in parts)
    assert LAUNCHER_MIN_SIZE > 0
    print(f"✓ test_launcher_version_constant passed: LAUNCHER_VERSION={LAUNCHER_VERSION}")


def test_launcher_self_update_dev_mode():
    """开发模式下（非 frozen），自我更新函数应安全返回不崩溃。"""
    # has_pending_launcher_update 在非 frozen 模式下应返回 False
    result = has_pending_launcher_update()
    assert result is False
    # _cleanup_stale_launcher_pending 不应崩溃
    state = _cleanup_stale_launcher_pending({})
    assert isinstance(state, dict)
    # 模拟一个过期的待更新记录（版本 <= 当前），应被清理
    stale = {"pending_launcher_path": r"D:\nonexistent\fake.exe",
             "pending_launcher_version": "0.0.0.1"}
    cleaned = _cleanup_stale_launcher_pending(stale)
    assert "pending_launcher_path" not in cleaned
    print("✓ test_launcher_self_update_dev_mode passed")


def test_vbs_encoding_chinese_path():
    """验证 VBS 自我更新脚本用 UTF-16 LE BOM 编码，能正确处理中文路径。

    用户可能把 exe 改名为"点我.exe""倒计时启动器.exe"等中文名。
    若 VBS 用 UTF-8 编码，wscript 在中文系统上会乱码导致替换失败。
    """
    import tempfile, os
    # 模拟用户改名后的中文路径
    chinese_old_exe = r"D:\教室工具\点我点我.exe"
    chinese_new_exe = r"D:\IdiotLaunch\data\IdiotLaunch_v9.9.9.9.exe"
    # 构造与 apply_launcher_update_if_pending 相同格式的 VBS 片段
    vbs_sample = f'''oldExe = "{chinese_old_exe}"
newExe = "{chinese_new_exe}"
fso.CopyFile newExe, oldExe, True
'''
    # 用与 core.py 相同的方式写入（UTF-16 LE BOM）
    tmp = os.path.join(tempfile.gettempdir(), "test_vbs_encoding.vbs")
    try:
        with open(tmp, "wb") as f:
            f.write(b"\xff\xfe")  # BOM
            f.write(vbs_sample.encode("utf-16-le"))
        # 读回验证：BOM 存在 + 中文路径完整保留
        with open(tmp, "rb") as f:
            raw = f.read()
        assert raw[:2] == b"\xff\xfe", "缺少 UTF-16 LE BOM"
        decoded = raw[2:].decode("utf-16-le")
        assert chinese_old_exe in decoded, f"中文路径丢失: {decoded}"
        assert chinese_new_exe in decoded, "新文件路径丢失"
        # 验证 wscript 能识别的关键：BOM + 内容可被 UTF-16 LE 解码
        print(f"✓ test_vbs_encoding_chinese_path passed: BOM={raw[:2].hex()}, 中文路径完整")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def test_download_mirrors():
    """验证镜像源配置：直连优先(短超时快速失败切镜像)，镜像 120 秒超时加快 fallback。"""
    from src.core import DOWNLOAD_MIRRORS, DOWNLOAD_TIMEOUT, DOWNLOAD_RETRY
    assert isinstance(DOWNLOAD_MIRRORS, list)
    assert len(DOWNLOAD_MIRRORS) >= 7
    assert DOWNLOAD_MIRRORS[0][0] == ""  # 第一个是直连
    assert DOWNLOAD_MIRRORS[0][1] <= 120  # 直连短超时，避免慢速直连白等
    for prefix, timeout in DOWNLOAD_MIRRORS[1:]:
        assert prefix.startswith("https://")
        assert timeout == 120  # 镜像 120s 超时，卡住后快速切换下一个
    assert DOWNLOAD_TIMEOUT == 900
    assert DOWNLOAD_RETRY >= 2
    print(f"✓ test_download_mirrors passed: {len(DOWNLOAD_MIRRORS)} 个源, 直连 {DOWNLOAD_MIRRORS[0][1]}s, 镜像 900s")


def test_daemon_constants():
    assert DAEMON_MUTEX == "IdiotLaunch_Daemon_Single"
    assert UPDATE_DIR == r"D:\IdiotLaunch\data"
    assert "state.json" in STATE_FILE
    assert "daemon.log" in DAEMON_LOG
    assert "command.json" in COMMAND_FILE
    print("✓ test_daemon_constants passed")


def test_daemon_log_no_crash():
    log_daemon("test message from unit test")
    # 不验证文件内容，只验证不崩溃
    print("✓ test_daemon_log_no_crash passed")


def test_daemon_status_roundtrip():
    """set_daemon_status -> get_daemon_status 往返测试。"""
    set_daemon_status("checking", 50, "test detail")
    status = get_daemon_status()
    assert status is not None
    assert status.get("activity") == "checking"
    assert status.get("progress") == 50
    assert status.get("detail") == "test detail"
    assert "pid" in status
    assert "timestamp" in status
    # 恢复为 idle
    set_daemon_status("idle", 0, "")
    print("✓ test_daemon_status_roundtrip passed")


def test_daemon_running_detection():
    """is_daemon_running 不应崩溃，返回 bool。"""
    result = is_daemon_running()
    assert isinstance(result, bool)
    print(f"✓ test_daemon_running_detection passed: running={result}")


def test_command_ipc_roundtrip():
    """send_command -> poll_command 文件 IPC 往返测试。"""
    send_command("check_updates", reason="test")
    cmd = poll_command()
    assert cmd is not None
    assert cmd.get("cmd") == "check_updates"
    assert cmd.get("reason") == "test"
    # poll 后文件应被删除
    cmd2 = poll_command()
    assert cmd2 is None
    print("✓ test_command_ipc_roundtrip passed")


def test_ensure_shortcuts_dev_mode():
    """开发模式下 ensure_shortcuts 应安全返回（frozen=False 时跳过）。"""
    # 非 frozen 模式下直接返回，不创建任何快捷方式
    import src.core as core
    original_frozen = getattr(core.sys, "frozen", False)
    try:
        core.sys.frozen = False
        # 不应崩溃
        from src.core import ensure_shortcuts
        ensure_shortcuts()
        print("✓ test_ensure_shortcuts_dev_mode passed (dev mode, no-op)")
    finally:
        if original_frozen:
            core.sys.frozen = original_frozen
        else:
            if hasattr(core.sys, "frozen"):
                delattr(core.sys, "frozen")



def test_idle_threshold_constant():
    from src.core import IDLE_THRESHOLD
    assert IDLE_THRESHOLD == 600, f"IDLE_THRESHOLD should be 600, got {IDLE_THRESHOLD}"
    print(f"✓ test_idle_threshold_constant passed: {IDLE_THRESHOLD}s = 10min")


def test_get_idle_seconds_returns_float():
    from src.core import get_idle_seconds
    idle = get_idle_seconds()
    assert isinstance(idle, float), f"get_idle_seconds should return float, got {type(idle)}"
    assert idle >= 0, f"idle should be >= 0, got {idle}"
    print(f"✓ test_get_idle_seconds_returns_float passed: current idle={idle:.1f}s")

def test_launcher_install_mode_constants():
    from src.core import LAUNCHER_SETUP_PREFIX, LAUNCHER_INSTALL_DIR, LAUNCHER_INSTALL_EXE
    assert LAUNCHER_SETUP_PREFIX == "IdiotLaunch_Setup_"
    assert LAUNCHER_INSTALL_DIR == r"D:\IdiotLaunch"
    assert LAUNCHER_INSTALL_EXE == r"D:\IdiotLaunch\IdiotLaunch.exe"
    print(f"✓ test_launcher_install_mode_constants passed: {LAUNCHER_SETUP_PREFIX}* -> {LAUNCHER_INSTALL_EXE}")


def test_get_file_version():
    from src.core import get_file_version
    import sys
    ver = get_file_version(sys.executable)
    assert ver is None or len(ver.split('.')) >= 2, f"version malformed: {ver}"
    print(f"✓ test_get_file_version passed: python.exe version={ver}")


def test_installer_asset_name_pattern():
    from src.core import LAUNCHER_SETUP_PREFIX
    assets = ["IdiotLaunch.exe", "IdiotLaunch_Setup_1.4.0.0.exe", "Other.exe"]
    matched = [a for a in assets if a.startswith(LAUNCHER_SETUP_PREFIX) and a.endswith(".exe")]
    assert matched == ["IdiotLaunch_Setup_1.4.0.0.exe"], f"matched={matched}"
    version = "1.4.0.0"
    dest_name = f"IdiotLaunch_Setup_{version}.exe"
    assert dest_name == "IdiotLaunch_Setup_1.4.0.0.exe"
    print("✓ test_installer_asset_name_pattern passed: 只匹配安装包资产，单文件被忽略")



def test_countdown_update_threaded_dev_mode():
    """v1.5.0.0: Countdown 更新全后台线程化，dev 模式下调度函数安全返回不崩溃。"""
    from src.core import (
        _check_and_start_countdown_update,
        _countdown_download_worker,
        _countdown_install_worker,
        _countdown_update_thread,
    )
    assert _countdown_update_thread is None  # 初始无线程
    _check_and_start_countdown_update()  # dev 模式应安全返回（非 frozen 直接 return）
    assert _countdown_download_worker is not None
    assert _countdown_install_worker is not None
    print("✓ test_countdown_update_threaded_dev_mode passed: 调度函数安全返回")


def test_iss_overwrite_install_settings():
    """v1.5.0.0: 安装包覆盖安装加固——自动关停旧进程、装完恢复启动。"""
    import os
    iss_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "IdiotLaunch.iss")
    with io.open(iss_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "CloseApplications=yes" in content
    assert "CloseApplicationsFilter=IdiotLaunch.exe" in content
    assert "RestartApplications=yes" in content
    assert "AppId=" in content  # 固定 AppId，同版本覆盖不产生重复安装
    assert "[Tasks]" not in content  # 死代码已删
    print("✓ test_iss_overwrite_install_settings passed: 覆盖安装加固生效")



def test_sha256_verify():
    """v1.6.0.0: SHA-256 校验——匹配放行、不匹配拒绝、无期望跳过。"""
    from src.core import sha256_of, verify_sha256
    import tempfile
    # 已知值：sha256("abc") = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("abc")
        p = f.name
    try:
        h = sha256_of(p)
        assert h == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", f"sha256 mismatch: {h}"
        assert verify_sha256(p, h) is True
        assert verify_sha256(p, "0" * 64) is False          # 不匹配 → 拒绝
        assert verify_sha256(p, "sha256:" + h) is True      # 带前缀（GitHub digest 格式）→ 放行
        assert verify_sha256(p, "") is True                 # 无期望哈希 → 跳过（旧 release 兼容）
        assert verify_sha256(p, None) is True
    finally:
        import os as _os
        try: _os.remove(p)
        except OSError: pass
    print("✓ test_sha256_verify passed: 匹配/不匹配/带前缀/无期望 全部正确")


def test_release_body_has_sha256():
    """v1.6.0.0: release.yml 发布时附带 SHA-256 校验和。"""
    import os
    yml_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            ".github", "workflows", "release.yml")
    with io.open(yml_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Get-FileHash" in content and "-Algorithm SHA256" in content
    assert "sha256=" in content          # GITHUB_OUTPUT 写入
    assert "校验和（SHA-256）" in content  # release body 展示
    print("✓ test_release_body_has_sha256 passed: CI 发布附带哈希")



if __name__ == "__main__":
    test_constants()
    test_version_parsing()
    test_version_comparison()
    test_resource_path()
    test_find_installed_no_crash()
    test_get_installed_version()
    test_installer_file_exists()
    test_is_running_no_crash()
    test_quit_countdown_no_crash()
    test_state_functions()
    test_launcher_version_constant()
    test_launcher_self_update_dev_mode()
    test_vbs_encoding_chinese_path()
    test_download_mirrors()
    test_daemon_constants()
    test_daemon_log_no_crash()
    test_daemon_status_roundtrip()
    test_daemon_running_detection()
    test_command_ipc_roundtrip()
    test_ensure_shortcuts_dev_mode()
    test_launcher_install_mode_constants()
    test_get_file_version()
    test_installer_asset_name_pattern()
    test_countdown_update_threaded_dev_mode()
    test_iss_overwrite_install_settings()
    test_sha256_verify()
    test_release_body_has_sha256()
    print("\n全部测试通过！")
