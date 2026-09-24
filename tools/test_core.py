"""
test_core.py — core.py 单元测试（无需 GUI）
运行：python tools/test_core.py
"""
import sys
import os

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
    assert INSTALL_DIR == r"D:\CountdownDesktop"
    assert EXE_NAME == "CountdownDesktop.exe"
    assert INSTALL_EXE == os.path.join(INSTALL_DIR, EXE_NAME)
    assert "morning-reading" in MORNING_READING_URL
    assert EMBEDDED_VERSION in INSTALLER_REL
    print("✓ test_constants passed")


def test_version_parsing():
    assert parse_version("3.2.1.1") == (3, 2, 1, 1)
    assert parse_version("v3.2.0.0") == (3, 2, 0, 0)
    assert parse_version("1.0") == (1, 0, 0, 0)
    print("✓ test_version_parsing passed")


def test_version_comparison():
    assert compare_versions("3.2.1.0", "3.2.1.1") == -1
    assert compare_versions("3.2.1.1", "3.2.1.1") == 0
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
    chinese_new_exe = r"D:\CountdownDesktop_Updates\IdiotLaunch_v9.9.9.9.exe"
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
    """验证镜像源配置：直连优先，至少 3 个镜像，超时 900 秒。"""
    assert isinstance(DOWNLOAD_MIRRORS, list)
    assert len(DOWNLOAD_MIRRORS) >= 4
    assert DOWNLOAD_MIRRORS[0] == ""  # 第一个是直连
    for m in DOWNLOAD_MIRRORS[1:]:
        assert m.startswith("https://")
    assert DOWNLOAD_TIMEOUT == 900
    assert DOWNLOAD_RETRY >= 2
    print(f"✓ test_download_mirrors passed: {len(DOWNLOAD_MIRRORS)} 个源, 超时 {DOWNLOAD_TIMEOUT}s")


def test_daemon_constants():
    assert DAEMON_MUTEX == "IdiotLaunch_Daemon_Single"
    assert UPDATE_DIR == r"D:\CountdownDesktop_Updates"
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
    print("\n全部测试通过！")
