"""
core.py — 核心逻辑：检测安装、静默安装、带参启动、优雅退出、自动更新。
所有路径与常量集中在此，便于维护。
"""
import os
import sys
import subprocess
import winreg
import time
import json
import shutil
import webbrowser
import urllib.request
import ssl
from pathlib import Path

# ── 常量 ──────────────────────────────────────────────
APP_NAME = "Countdown Desktop"
EXE_NAME = "CountdownDesktop.exe"
# 内嵌的 Countdown Desktop 版本（随 idiot-launch 发布一起更新）
EMBEDDED_VERSION = "3.2.1.1"
# 学校电脑 C 盘有冰点还原，统一装到 D 盘
INSTALL_DIR = r"D:\CountdownDesktop"
INSTALL_EXE = os.path.join(INSTALL_DIR, EXE_NAME)
# 内嵌安装包在打包后的相对路径
INSTALLER_REL = os.path.join("installer", f"CountdownDesktop_Setup_{EMBEDDED_VERSION}.exe")
# 早晚读网页
MORNING_READING_URL = "https://zztool.free.nf/morning-reading"
# 静默安装超时（秒），Inno 安装含 WebView2 可能较慢
INSTALL_TIMEOUT = 300
# 自动更新相关
UPDATE_DIR = r"D:\CountdownDesktop_Updates"
STATE_FILE = os.path.join(UPDATE_DIR, "state.json")
GITHUB_API_URL = "https://api.github.com/repos/tgcz2011/countdown-desktop/releases/latest"
# 两次检查更新的最小间隔（秒），避免频繁请求 GitHub
CHECK_INTERVAL = 6 * 3600  # 6 小时
# 下载超时（秒），GitHub 不稳定时给足时间
DOWNLOAD_TIMEOUT = 600

# ── Idiot Launch 自我更新 ─────────────────────────────
LAUNCHER_VERSION = "1.2.0.0"
LAUNCHER_GITHUB_API = "https://api.github.com/repos/tgcz2011/idiot-launch/releases/latest"
LAUNCHER_ASSET_NAME = "IdiotLaunch.exe"
# 合法 IdiotLaunch.exe 的最小体积（内嵌约 37MB 安装包 + Python 运行时）
LAUNCHER_MIN_SIZE = 5 * 1024 * 1024  # 5MB


# ── 资源路径 ──────────────────────────────────────────
def resource_path(relative: str) -> str:
    """打包后资源路径解析。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


# ── 版本号工具 ────────────────────────────────────────
def parse_version(v: str) -> tuple:
    """将 'a.b.c.d' 转为整数元组用于比较。容错处理前缀 'v' 和多余段。"""
    v = v.strip().lstrip("vV")
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def compare_versions(v1: str, v2: str) -> int:
    """比较版本号：返回 -1(v1<v2), 0(相等), 1(v1>v2)。"""
    a, b = parse_version(v1), parse_version(v2)
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


# ── 安装检测 ──────────────────────────────────────────
def find_installed_path() -> str | None:
    """
    检测 Countdown Desktop 是否已安装。
    优先级：1) D:\\CountdownDesktop（我们指定的路径）
            2) 注册表卸载信息中的 InstallLocation
            3) 常见用户目录
    """
    if os.path.isfile(INSTALL_EXE):
        return INSTALL_EXE

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

    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "CountdownDesktop", EXE_NAME),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "CountdownDesktop", EXE_NAME),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "CountdownDesktop", EXE_NAME),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def get_installed_version() -> str | None:
    """
    读取已安装 Countdown Desktop 的版本号。
    优先从注册表卸载信息的 DisplayVersion 读取，回退到 exe 文件版本。
    """
    # 1) 注册表
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
                                ver, _ = winreg.QueryValueEx(app_key, "DisplayVersion")
                                if ver:
                                    return ver
                            except OSError:
                                pass
                    except OSError:
                        break
        except OSError:
            continue

    # 2) 从 exe 文件版本信息读取
    exe = find_installed_path()
    if exe and os.path.isfile(exe):
        try:
            import ctypes
            from ctypes import wintypes
            size = ctypes.windll.version.GetFileVersionInfoSizeW(exe, None)
            if size:
                buf = ctypes.create_string_buffer(size)
                if ctypes.windll.version.GetFileVersionInfoW(exe, 0, size, buf):
                    trans = ctypes.c_uint()
                    tlen = ctypes.c_uint()
                    ctypes.windll.version.VerQueryValueW(
                        buf, r"\VarFileInfo\Translation",
                        ctypes.byref(trans), ctypes.byref(tlen))
                    lang = trans.value & 0xFFFF
                    cp = (trans.value >> 16) & 0xFFFF
                    sub = f"\\StringFileInfo\\{lang:04x}{cp:04x}\\FileVersion"
                    res = ctypes.c_wchar_p()
                    rlen = ctypes.c_uint()
                    if ctypes.windll.version.VerQueryValueW(buf, sub, ctypes.byref(res), ctypes.byref(rlen)):
                        return res.value
        except Exception:
            pass
    return None


# ── 安装 / 卸载 ───────────────────────────────────────
def remove_install_dir() -> bool:
    """删除整个安装目录 D:\\CountdownDesktop（更新前清理旧版）。"""
    if not os.path.isdir(INSTALL_DIR):
        return True
    try:
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)
        # 验证删除
        if os.path.isdir(INSTALL_DIR):
            # 二次尝试（可能有文件句柄延迟释放）
            time.sleep(1)
            shutil.rmtree(INSTALL_DIR, ignore_errors=True)
        return not os.path.isdir(INSTALL_DIR)
    except Exception:
        return False


def install_from_path(installer_path: str) -> bool:
    """
    使用指定安装包静默安装到 D 盘。
    安装前自动删除旧安装目录（确保干净升级）。
    """
    if not os.path.isfile(installer_path):
        raise FileNotFoundError(f"安装包不存在: {installer_path}")
    if not os.path.isdir("D:\\"):
        raise RuntimeError("D 盘不存在，无法安装。")

    # 安装前删除旧目录（用户要求：发现旧版时删除原文件夹）
    remove_install_dir()

    args = [
        installer_path,
        "/VERYSILENT",
        "/NORESTART",
        "/SUPPRESSMSGBOXES",
        f"/DIR={INSTALL_DIR}",
    ]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=INSTALL_TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(
            f"安装失败（退出码 {proc.returncode}）\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    for _ in range(15):
        if os.path.isfile(INSTALL_EXE):
            return True
        time.sleep(1)
    return os.path.isfile(INSTALL_EXE)


def silent_install() -> bool:
    """使用内嵌安装包静默安装。"""
    installer = resource_path(INSTALLER_REL)
    if not os.path.isfile(installer):
        raise FileNotFoundError(f"内嵌安装包不存在: {installer}")
    return install_from_path(installer)


def ensure_installed() -> str:
    """确保 Countdown Desktop 已安装且版本不低于内嵌版本，返回可执行文件路径。"""
    path = find_installed_path()
    if path:
        local_ver = get_installed_version()
        # 本地版本低于内嵌版本 → 删除旧版，用内嵌包重装
        if local_ver and compare_versions(local_ver, EMBEDDED_VERSION) < 0:
            silent_install()
            path = find_installed_path()
        return path
    silent_install()
    path = find_installed_path()
    if not path:
        raise RuntimeError("安装完成后仍未找到 CountdownDesktop.exe")
    return path


# ── 启动 / 退出 ───────────────────────────────────────
def launch_countdown(exam_type: str) -> None:
    """带参数启动 Countdown Desktop。"""
    exe = ensure_installed()
    creationflags = 0x00000008  # DETACHED_PROCESS
    subprocess.Popen([exe, "--exam", exam_type], creationflags=creationflags, close_fds=True)


def open_morning_reading() -> None:
    """在默认浏览器中打开早晚读网页。"""
    webbrowser.open(MORNING_READING_URL)


def is_running() -> bool:
    """检测 Countdown Desktop 是否正在运行（命名互斥量）。"""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, "CountdownDesktop_Single")
        already_exists = kernel32.GetLastError() == 183
        if handle:
            kernel32.CloseHandle(handle)
        return already_exists
    except Exception:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq CountdownDesktop.exe", "/NH"],
                capture_output=True, text=True, timeout=10,
            )
            return "CountdownDesktop.exe" in result.stdout
        except Exception:
            return False


def quit_countdown() -> bool:
    """通过命名事件优雅关闭 Countdown Desktop。"""
    import ctypes
    kernel32 = ctypes.windll.kernel32
    MUTEX_NAME = "CountdownDesktop_Single"
    QUIT_EVENT_NAME = "CountdownDesktop_Quit"
    EVENT_MODIFY_STATE = 0x0002
    ERROR_ALREADY_EXISTS = 183

    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    already_running = kernel32.GetLastError() == ERROR_ALREADY_EXISTS
    if mutex:
        kernel32.CloseHandle(mutex)
    if not already_running:
        return True

    event_handle = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, QUIT_EVENT_NAME)
    if not event_handle:
        raise RuntimeError("无法连接 Countdown Desktop 退出通道（可能版本过旧）")
    kernel32.SetEvent(event_handle)
    kernel32.CloseHandle(event_handle)

    deadline = time.time() + 8.0
    while time.time() < deadline:
        time.sleep(0.25)
        m = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        released = kernel32.GetLastError() != ERROR_ALREADY_EXISTS
        if m:
            kernel32.CloseHandle(m)
        if released:
            return True
    return False


# ── 自动更新：状态管理 ────────────────────────────────
def _ensure_update_dir() -> None:
    if not os.path.isdir(UPDATE_DIR):
        os.makedirs(UPDATE_DIR, exist_ok=True)


def load_state() -> dict:
    """读取更新状态文件。"""
    _ensure_update_dir()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    """写入更新状态文件。"""
    _ensure_update_dir()
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


# ── 自动更新：GitHub 查询 ─────────────────────────────
def get_latest_version_info() -> dict | None:
    """
    查询 GitHub 最新 Release 信息。
    返回 {"version": "3.2.1.1", "url": "https://...", "size": 12345} 或 None。
    """
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={"User-Agent": "idiot-launch-updater", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = data.get("tag_name", "")
        version = tag.lstrip("vV")
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.startswith("CountdownDesktop_Setup_") and name.endswith(".exe"):
                return {
                    "version": version,
                    "url": asset["browser_download_url"],
                    "size": asset.get("size", 0),
                    "name": name,
                }
        return None
    except Exception:
        return None


def download_installer(url: str, dest_path: str) -> bool:
    """
    下载安装包到指定路径。下载到 .part 临时文件，完成后重命名。
    GitHub 不稳定时给足超时，失败返回 False（daemon 下次重试）。
    """
    _ensure_update_dir()
    tmp_path = dest_path + ".part"
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "idiot-launch-updater"})
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT, context=ctx) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
        # 验证下载完整性（如果有 Content-Length）
        if total > 0 and downloaded < total:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            return False
        # 下载完成，重命名
        if os.path.isfile(dest_path):
            os.remove(dest_path)
        os.rename(tmp_path, dest_path)
        return os.path.isfile(dest_path)
    except Exception:
        try:
            if os.path.isfile(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False


# ── 自动更新：守护进程逻辑 ────────────────────────────
def daemon_run() -> int:
    """
    后台守护进程主逻辑（无窗口，由 GUI 关闭时启动）。
    流程：
      1. 如有已下载的待安装更新 → 等 Countdown Desktop 退出 → 安装 → 退出
      2. 如距上次检查超过 6 小时 → 查询 GitHub 最新版
      3. 如有新版 → 下载 → 标记待安装 → 等退出 → 安装 → 退出
      4. 已是最新 → 直接退出
    返回 0=正常结束，1=出错。
    """
    state = load_state()
    now = time.time()

    # 0) 检查 Idiot Launch 自身更新（仅下载，替换在下次启动时完成）
    _check_and_download_launcher_update()

    # 1) 检查是否有待安装的更新
    pending = state.get("pending_installer")
    pending_ver = state.get("pending_version")
    if pending and pending_ver and os.path.isfile(pending):
        local_ver = get_installed_version()
        # 本地版本已经 >= 待安装版本，说明已更新过，清理状态
        if local_ver and compare_versions(local_ver, pending_ver) >= 0:
            state.pop("pending_installer", None)
            state.pop("pending_version", None)
            state["download_complete"] = False
            save_state(state)
        else:
            # 等待 Countdown Desktop 退出后安装
            _wait_and_install(pending, pending_ver, state)
            return 0

    # 2) 检查是否需要查询更新
    last_check = state.get("last_check", 0)
    if now - last_check < CHECK_INTERVAL:
        # 距上次检查不足 6 小时，直接退出
        return 0

    # 3) 查询最新版本
    latest = get_latest_version_info()
    state["last_check"] = now
    save_state(state)
    if not latest:
        return 0  # 查询失败，下次再试

    local_ver = get_installed_version()
    # 本地已安装且版本 >= 最新版，无需更新
    if local_ver and compare_versions(local_ver, latest["version"]) >= 0:
        return 0

    # 4) 下载新版安装包
    installer_name = latest.get("name", f"CountdownDesktop_Setup_{latest['version']}.exe")
    dest = os.path.join(UPDATE_DIR, installer_name)
    # 如果已下载过同名文件且大小匹配，跳过下载
    if not (os.path.isfile(dest) and latest.get("size", 0) > 0
            and os.path.getsize(dest) == latest["size"]):
        ok = download_installer(latest["url"], dest)
        if not ok:
            return 0  # 下载失败，下次重试
    # 5) 标记待安装，等待退出后安装
    state["pending_installer"] = dest
    state["pending_version"] = latest["version"]
    state["download_complete"] = True
    save_state(state)
    _wait_and_install(dest, latest["version"], state)
    return 0


def _wait_and_install(installer_path: str, version: str, state: dict) -> None:
    """
    等待 Countdown Desktop 退出（最多等 2 小时），然后静默安装。
    如果一直不退出（比如用户一直开着），状态保留，下次 daemon 启动时继续。
    """
    deadline = time.time() + 2 * 3600  # 最多等 2 小时
    while time.time() < deadline:
        if not is_running():
            break
        time.sleep(10)

    if is_running():
        # 还在运行，不装了，状态保留下次处理
        return

    # 已退出，执行安装
    try:
        install_from_path(installer_path)
        # 安装成功，清理待安装标记
        state.pop("pending_installer", None)
        state.pop("pending_version", None)
        state["download_complete"] = False
        state["last_check"] = time.time()
        save_state(state)
        # 清理已安装的安装包文件（节省空间）
        try:
            os.remove(installer_path)
        except OSError:
            pass
    except Exception:
        pass  # 安装失败，状态保留，下次重试


def start_daemon() -> None:
    """启动后台守护进程（当前 exe 加 --daemon 参数，无窗口）。"""
    if getattr(sys, "frozen", False):
        exe = sys.executable
    else:
        exe = sys.executable
        args = [sys.executable, os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "run.py"), "--daemon"]
        creationflags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
        subprocess.Popen(args, creationflags=creationflags, close_fds=True)
        return
    creationflags = 0x00000008 | 0x08000000
    subprocess.Popen([exe, "--daemon"], creationflags=creationflags, close_fds=True)


def has_pending_update() -> bool:
    """是否有已下载待安装的更新（GUI 启动时可提示）。"""
    state = load_state()
    return bool(state.get("pending_installer") and state.get("download_complete")
                and os.path.isfile(state["pending_installer"]))


def install_pending_if_idle() -> bool:
    """GUI 启动时调用：如果有待安装更新且 Countdown Desktop 未运行，立即安装。"""
    if not has_pending_update():
        return False
    if is_running():
        return False
    state = load_state()
    installer = state.get("pending_installer")
    version = state.get("pending_version")
    if not installer or not version:
        return False
    try:
        install_from_path(installer)
        state.pop("pending_installer", None)
        state.pop("pending_version", None)
        state["download_complete"] = False
        state["last_check"] = time.time()
        save_state(state)
        try:
            os.remove(installer)
        except OSError:
            pass
        return True
    except Exception:
        return False


# ── Idiot Launch 自我更新 ──────────────────────────────
def get_latest_launcher_info() -> dict | None:
    """
    查询 GitHub 最新 Idiot Launch Release。
    返回 {"version": "1.2.0.0", "url": "https://...", "size": 12345} 或 None。
    """
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            LAUNCHER_GITHUB_API,
            headers={"User-Agent": "idiot-launch-selfupdater", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = data.get("tag_name", "")
        version = tag.lstrip("vV")
        for asset in data.get("assets", []):
            if asset.get("name") == LAUNCHER_ASSET_NAME:
                return {
                    "version": version,
                    "url": asset["browser_download_url"],
                    "size": asset.get("size", 0),
                }
        return None
    except Exception:
        return None


def _cleanup_stale_launcher_pending(state: dict) -> dict:
    """清理已过期的待更新记录（版本 <= 当前版本，说明已更新过）。"""
    path = state.get("pending_launcher_path")
    version = state.get("pending_launcher_version")
    if path and version:
        if compare_versions(version, LAUNCHER_VERSION) <= 0:
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
            state.pop("pending_launcher_path", None)
            state.pop("pending_launcher_version", None)
            save_state(state)
    return state


def has_pending_launcher_update() -> bool:
    """是否有已下载待替换的 Idiot Launch 更新。"""
    if not getattr(sys, "frozen", False):
        return False
    state = load_state()
    state = _cleanup_stale_launcher_pending(state)
    path = state.get("pending_launcher_path")
    version = state.get("pending_launcher_version")
    if not path or not version or not os.path.isfile(path):
        return False
    if os.path.getsize(path) < LAUNCHER_MIN_SIZE:
        return False
    return compare_versions(version, LAUNCHER_VERSION) > 0


def apply_launcher_update_if_pending() -> None:
    """
    启动时调用（仅 frozen 模式）：如果有待更新，生成 VBScript 替换器，
    启动它后立即退出当前进程。VBS 会等待进程退出、覆盖旧 exe、启动新版、自删除。
    此函数在有待更新时不会返回（直接 sys.exit）。
    """
    if not getattr(sys, "frozen", False):
        return
    if not has_pending_launcher_update():
        return

    state = load_state()
    new_exe = state.get("pending_launcher_path")
    old_exe = sys.executable

    if not new_exe or not os.path.isfile(new_exe):
        return

    # 生成 VBScript 到临时目录。VBS 优势：wscript //B 完全无窗口，Windows 自带。
    import tempfile
    vbs_content = f'''Option Explicit
Dim fso, shell, oldExe, newExe, i, success
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

oldExe = "{old_exe}"
newExe = "{new_exe}"

' 等待旧进程释放文件锁（每 500ms 重试，最多 15 秒）
success = False
For i = 1 To 30
    WScript.Sleep 500
    On Error Resume Next
    fso.CopyFile newExe, oldExe, True
    If Err.Number = 0 Then
        success = True
        On Error GoTo 0
        Exit For
    End If
    On Error GoTo 0
Next

If success Then
    On Error Resume Next
    fso.DeleteFile newExe, True
    On Error GoTo 0
    shell.Run Chr(34) & oldExe & Chr(34), 1, False
End If

' VBS 自删除
On Error Resume Next
fso.DeleteFile WScript.ScriptFullName, True
On Error GoTo 0
'''
    vbs_path = os.path.join(tempfile.gettempdir(), "idiot_launch_selfupdate.vbs")
    try:
        with open(vbs_path, "w", encoding="utf-8") as f:
            f.write(vbs_content)
    except OSError:
        return

    # 以隐藏窗口启动 VBS，然后立即退出
    try:
        subprocess.Popen(
            ["wscript.exe", "//B", "//Nologo", vbs_path],
            creationflags=0x08000000,  # CREATE_NO_WINDOW
            close_fds=True,
        )
    except Exception:
        return

    # 注意：不清除 pending 状态。如果 VBS 替换失败，下次启动再试。
    # 如果替换成功，新版运行时 LAUNCHER_VERSION 已更新，
    # _cleanup_stale_launcher_pending 会自动清理旧记录。
    sys.exit(0)


def _check_and_download_launcher_update() -> None:
    """
    daemon 中调用：检查 Idiot Launch 最新版，有新版则下载到 UPDATE_DIR 并标记待更新。
    不执行替换（替换在下次启动时由 apply_launcher_update_if_pending 完成）。
    仅 frozen 模式生效。
    """
    if not getattr(sys, "frozen", False):
        return

    state = load_state()
    state = _cleanup_stale_launcher_pending(state)
    now = time.time()

    # 已有有效的待更新？跳过检查。
    pending_path = state.get("pending_launcher_path")
    pending_ver = state.get("pending_launcher_version")
    if pending_path and pending_ver and os.path.isfile(pending_path):
        if compare_versions(pending_ver, LAUNCHER_VERSION) > 0:
            return

    # 距上次检查不足 6 小时？跳过。
    last_check = state.get("launcher_last_check", 0)
    if now - last_check < CHECK_INTERVAL:
        return

    latest = get_latest_launcher_info()
    state["launcher_last_check"] = now
    save_state(state)

    if not latest:
        return  # 查询失败，下次再试

    if compare_versions(latest["version"], LAUNCHER_VERSION) <= 0:
        return  # 已是最新或更新

    # 下载新版 exe
    dest_name = f"IdiotLaunch_v{latest['version']}.exe"
    dest = os.path.join(UPDATE_DIR, dest_name)

    # 已下载过且大小匹配？直接标记。
    if (os.path.isfile(dest) and latest.get("size", 0) > 0
            and os.path.getsize(dest) == latest["size"]
            and os.path.getsize(dest) >= LAUNCHER_MIN_SIZE):
        state["pending_launcher_path"] = dest
        state["pending_launcher_version"] = latest["version"]
        save_state(state)
        return

    ok = download_installer(latest["url"], dest)
    if not ok:
        return  # 下载失败，下次重试

    # 校验下载文件大小
    if not os.path.isfile(dest) or os.path.getsize(dest) < LAUNCHER_MIN_SIZE:
        try:
            os.remove(dest)
        except OSError:
            pass
        return

    state["pending_launcher_path"] = dest
    state["pending_launcher_version"] = latest["version"]
    save_state(state)
