"""
core.py — 核心逻辑：检测安装、静默安装、带参启动 Countdown Desktop、打开网页。
所有路径与常量集中在此，便于维护。
"""
import os
import sys
import subprocess
import winreg
import time
import webbrowser
from pathlib import Path

# ── 常量 ──────────────────────────────────────────────
APP_NAME = "Countdown Desktop"
EXE_NAME = "CountdownDesktop.exe"
# 学校电脑 C 盘有冰点还原，统一装到 D 盘
INSTALL_DIR = r"D:\CountdownDesktop"
INSTALL_EXE = os.path.join(INSTALL_DIR, EXE_NAME)
# 内嵌安装包在打包后的相对路径
INSTALLER_REL = os.path.join("installer", "CountdownDesktop_Setup_3.2.0.0.exe")
# 早晚读网页
MORNING_READING_URL = "https://zztool.free.nf/morning-reading"
# 静默安装超时（秒），Inno 安装含 WebView2 可能较慢
INSTALL_TIMEOUT = 300


def resource_path(relative: str) -> str:
    """打包后资源路径解析。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        # 开发模式：项目根目录
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def find_installed_path() -> str | None:
    """
    检测 Countdown Desktop 是否已安装。
    优先级：1) D:\\CountdownDesktop（我们指定的路径）
            2) 注册表卸载信息中的 InstallLocation
            3) 常见用户目录
    返回可执行文件完整路径，未找到返回 None。
    """
    # 1) 我们指定的 D 盘路径
    if os.path.isfile(INSTALL_EXE):
        return INSTALL_EXE

    # 2) 查注册表（HKCU + HKLM，32/64 位视图）
    reg_paths = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for root, subkey in reg_paths:
        try:
            with winreg.OpenKey(root, subkey) as key:
                idx = 0
                while True:
                    try:
                        app_name = winreg.EnumKey(key, idx)
                        idx += 1
                        if "countdown" not in app_name.lower():
                            continue
                        with winreg.OpenKey(key, app_name) as app_key:
                            try:
                                loc, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                if loc and os.path.isfile(os.path.join(loc, EXE_NAME)):
                                    return os.path.join(loc, EXE_NAME)
                            except OSError:
                                pass
                            try:
                                icon, _ = winreg.QueryValueEx(app_key, "DisplayIcon")
                                if icon and "," in icon:
                                    icon = icon.split(",")[0]
                                if icon and os.path.isfile(icon):
                                    return icon
                            except OSError:
                                pass
                    except OSError:
                        break
        except OSError:
            continue

    # 3) 常见用户安装目录（Inno lowest 权限默认 {autopf}）
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "CountdownDesktop", EXE_NAME),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "CountdownDesktop", EXE_NAME),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "CountdownDesktop", EXE_NAME),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c

    return None


def silent_install() -> bool:
    """
    使用内嵌安装包静默安装 Countdown Desktop 到 D 盘。
    Inno Setup 标准参数：
      /VERYSILENT  — 完全无界面
      /NORESTART   — 不重启
      /DIR=...     — 指定安装目录
      /SUPPRESSMSGBOXES — 抑制所有消息框
    返回 True 安装成功（或已存在），False 失败。
    """
    installer = resource_path(INSTALLER_REL)
    if not os.path.isfile(installer):
        raise FileNotFoundError(f"内嵌安装包不存在: {installer}")

    # 确保 D 盘存在
    if not os.path.isdir("D:\\"):
        raise RuntimeError("D 盘不存在，无法安装到 D 盘。请检查磁盘。")

    args = [
        installer,
        "/VERYSILENT",
        "/NORESTART",
        "/SUPPRESSMSGBOXES",
        f"/DIR={INSTALL_DIR}",
    ]

    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=INSTALL_TIMEOUT,
    )
    # Inno Setup 退出码：0=成功，其他=失败
    if proc.returncode != 0:
        raise RuntimeError(
            f"安装失败（退出码 {proc.returncode}）\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        )

    # 安装后验证
    for _ in range(10):
        if os.path.isfile(INSTALL_EXE):
            return True
        time.sleep(1)
    return os.path.isfile(INSTALL_EXE)


def ensure_installed() -> str:
    """
    确保 Countdown Desktop 已安装，返回可执行文件路径。
    未安装则自动静默安装。
    """
    path = find_installed_path()
    if path:
        return path
    silent_install()
    path = find_installed_path()
    if not path:
        raise RuntimeError("安装完成后仍未找到 CountdownDesktop.exe")
    return path


def launch_countdown(exam_type: str) -> None:
    """
    带参数启动 Countdown Desktop。
    exam_type: 'gaokao'（高考）或 'zhongkao'（中考）
    Countdown Desktop 内置单实例接管，重复启动会自动切换倒计时类型。
    """
    exe = ensure_installed()
    # 使用 DETACHED_PROCESS 让子进程独立于启动器，启动器可关闭而不影响倒计时
    creationflags = 0x00000008  # DETACHED_PROCESS
    subprocess.Popen(
        [exe, "--exam", exam_type],
        creationflags=creationflags,
        close_fds=True,
    )


def open_morning_reading() -> None:
    """在默认浏览器中打开早晚读网页。"""
    webbrowser.open(MORNING_READING_URL)


def is_running() -> bool:
    """检测 Countdown Desktop 是否正在运行（通过命名互斥量，比 tasklist 更可靠）。"""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # 尝试创建互斥量，若已存在说明有实例在运行
        handle = kernel32.CreateMutexW(None, False, "CountdownDesktop_Single")
        already_exists = kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
        if handle:
            kernel32.CloseHandle(handle)
        return already_exists
    except Exception:
        # 回退到 tasklist 检测
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq CountdownDesktop.exe", "/NH"],
                capture_output=True, text=True, timeout=10,
            )
            return "CountdownDesktop.exe" in result.stdout
        except Exception:
            return False


def quit_countdown() -> bool:
    """
    优雅关闭 Countdown Desktop：通过命名事件通知运行中的实例自行退出。
    Countdown Desktop 运行时会创建命名事件 CountdownDesktop_Quit 并每 250ms 轮询；
    收到信号后调用 quit()：停壁纸/屏保、恢复桌面、退托盘，全程优雅不强制。
    流程：检测是否在运行 → 打开并触发退出事件 → 轮询等待互斥量释放（最多8秒）。
    返回 True 成功退出，False 超时未退出。
    """
    import ctypes
    kernel32 = ctypes.windll.kernel32

    MUTEX_NAME = "CountdownDesktop_Single"
    QUIT_EVENT_NAME = "CountdownDesktop_Quit"
    EVENT_MODIFY_STATE = 0x0002
    ERROR_ALREADY_EXISTS = 183

    # 1) 检测是否在运行
    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    already_running = kernel32.GetLastError() == ERROR_ALREADY_EXISTS
    if mutex:
        kernel32.CloseHandle(mutex)
    if not already_running:
        return True  # 本就没在运行，算成功

    # 2) 打开退出事件并触发（运行实例的 250ms 轮询定时器会捕获并 quit）
    event_handle = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, QUIT_EVENT_NAME)
    if not event_handle:
        # 旧版本可能没有创建退出事件，无法优雅退出
        raise RuntimeError("无法连接 Countdown Desktop 退出通道（可能版本过旧）")
    kernel32.SetEvent(event_handle)
    kernel32.CloseHandle(event_handle)

    # 3) 轮询等待互斥量释放（实例退出后会释放互斥量）
    import time
    deadline = time.time() + 8.0
    while time.time() < deadline:
        time.sleep(0.25)
        m = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        released = kernel32.GetLastError() != ERROR_ALREADY_EXISTS
        if m:
            kernel32.CloseHandle(m)
        if released:
            return True

    return False  # 超时，实例未退出
