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
    LAUNCHER_VERSION,
    LAUNCHER_MIN_SIZE,
    has_pending_launcher_update,
    _cleanup_stale_launcher_pending,
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
    print("\n全部测试通过！")
