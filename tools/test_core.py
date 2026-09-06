"""
test_core.py — core.py 单元测试（无需 GUI）
验证：安装检测路径解析、常量、注册表扫描不崩溃。
运行：python tools/test_core.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import (
    find_installed_path,
    resource_path,
    is_running,
    kill_countdown,
    INSTALL_DIR,
    INSTALL_EXE,
    EXE_NAME,
    MORNING_READING_URL,
    INSTALLER_REL,
)


def test_constants():
    assert INSTALL_DIR == r"D:\CountdownDesktop"
    assert EXE_NAME == "CountdownDesktop.exe"
    assert INSTALL_EXE == os.path.join(INSTALL_DIR, EXE_NAME)
    assert "morning-reading" in MORNING_READING_URL
    assert "CountdownDesktop_Setup" in INSTALLER_REL
    print("✓ test_constants passed")


def test_resource_path():
    p = resource_path(INSTALLER_REL)
    assert p.endswith(INSTALLER_REL) or p.endswith(INSTALLER_REL.replace("/", os.sep))
    print(f"✓ test_resource_path passed: {p}")


def test_find_installed_no_crash():
    # 不断言结果（测试机可能装了也可能没装），只验证不抛异常
    result = find_installed_path()
    print(f"✓ test_find_installed_no_crash passed: {result}")


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


def test_kill_countdown_no_crash():
    # 不实际运行时调用应返回 0，不抛异常
    if not is_running():
        result = kill_countdown()
        print(f"✓ test_kill_countdown_no_crash passed: killed={result}")
    else:
        print("⚠ test_kill_countdown_no_crash: Countdown Desktop 正在运行，跳过实际终止")


if __name__ == "__main__":
    test_constants()
    test_resource_path()
    test_find_installed_no_crash()
    test_installer_file_exists()
    test_is_running_no_crash()
    test_kill_countdown_no_crash()
    print("\n全部测试通过！")
