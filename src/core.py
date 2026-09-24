"""
core.py — 核心逻辑：检测安装、静默安装、带参启动、优雅退出、自动更新、快捷方式管理。
v1.3.0.0: 多源下载 fallback、daemon 常驻、文件 IPC 状态通信、快捷方式自动重建、daemon 日志。
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
import ctypes
from pathlib import Path

# ── 常量 ──────────────────────────────────────────────
APP_NAME = "Countdown Desktop"
EXE_NAME = "CountdownDesktop.exe"
EMBEDDED_VERSION = "3.2.1.1"
INSTALL_DIR = r"D:\CountdownDesktop"
INSTALL_EXE = os.path.join(INSTALL_DIR, EXE_NAME)
INSTALLER_REL = os.path.join("installer", f"CountdownDesktop_Setup_{EMBEDDED_VERSION}.exe")
MORNING_READING_URL = "https://zztool.free.nf/morning-reading"
INSTALL_TIMEOUT = 300

UPDATE_DIR = r"D:\CountdownDesktop_Updates"
STATE_FILE = os.path.join(UPDATE_DIR, "state.json")
DAEMON_LOG = os.path.join(UPDATE_DIR, "daemon.log")
COMMAND_FILE = os.path.join(UPDATE_DIR, "command.json")
GITHUB_API_URL = "https://api.github.com/repos/tgcz2011/countdown-desktop/releases/latest"
CHECK_INTERVAL = 6 * 3600
DOWNLOAD_TIMEOUT = 900
DOWNLOAD_RETRY = 3
DAEMON_MUTEX = "IdiotLaunch_Daemon_Single"
IDLE_THRESHOLD = 600  # 10 分钟无操作视为空闲，此时可静默自我更新

DOWNLOAD_MIRRORS = [
    "",
    "https://gh-proxy.com/",
    "https://ghfast.top/",
    "https://ghproxy.net/",
]

LAUNCHER_VERSION = "1.3.1.0"
LAUNCHER_GITHUB_API = "https://api.github.com/repos/tgcz2011/idiot-launch/releases/latest"
LAUNCHER_ASSET_NAME = "IdiotLaunch.exe"
LAUNCHER_MIN_SIZE = 5 * 1024 * 1024
LAUNCHER_INSTALL_DIR = r"D:\IdiotLaunch"


def resource_path(relative: str) -> str:
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def parse_version(v: str) -> tuple:
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
    a, b = parse_version(v1), parse_version(v2)
    if a < b:
        return -1
    if a > b:
        return 1
    return 0



class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def get_idle_seconds() -> float:
    """返回系统空闲秒数（距上次键盘/鼠标输入的时间）。"""
    try:
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0.0
        tick = ctypes.windll.kernel32.GetTickCount()
        return max(0.0, (tick - lii.dwTime) / 1000.0)
    except Exception:
        return 0.0

def log_daemon(msg: str) -> None:
    try:
        _ensure_update_dir()
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
        if os.path.isfile(DAEMON_LOG) and os.path.getsize(DAEMON_LOG) > 100 * 1024:
            with open(DAEMON_LOG, "w", encoding="utf-8") as f:
                f.write(line)
        else:
            with open(DAEMON_LOG, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass


def find_installed_path() -> str | None:
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
    exe = find_installed_path()
    if exe and os.path.isfile(exe):
        try:
            size = ctypes.windll.version.GetFileVersionInfoSizeW(exe, None)
            if size > 0:
                res = ctypes.create_string_buffer(size)
                ctypes.windll.version.GetFileVersionInfoW(exe, None, size, res)
                val = ctypes.c_void_p()
                length = ctypes.c_uint()
                if ctypes.windll.version.VerQueryValueW(res, "\\", ctypes.byref(val), ctypes.byref(length)):
                    class VS_FIXEDFILEINFO(ctypes.Structure):
                        _fields_ = [("dwSignature", ctypes.c_uint32), ("dwStrucVersion", ctypes.c_uint32),
                                    ("dwFileVersionMS", ctypes.c_uint32), ("dwFileVersionLS", ctypes.c_uint32),
                                    ("dwProductVersionMS", ctypes.c_uint32), ("dwProductVersionLS", ctypes.c_uint32)]
                    info = ctypes.cast(val, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
                    v1 = (info.dwFileVersionMS >> 16) & 0xFFFF
                    v2 = info.dwFileVersionMS & 0xFFFF
                    v3 = (info.dwFileVersionLS >> 16) & 0xFFFF
                    v4 = info.dwFileVersionLS & 0xFFFF
                    return f"{v1}.{v2}.{v3}.{v4}"
        except Exception:
            pass
    return None


def remove_install_dir() -> None:
    if os.path.isdir(INSTALL_DIR):
        try:
            shutil.rmtree(INSTALL_DIR, ignore_errors=True)
        except Exception:
            pass


def install_from_path(installer_path: str) -> bool:
    if not os.path.isfile(installer_path):
        return False
    if not os.path.isdir("D:\\"):
        raise RuntimeError("D 盘不存在，无法安装")
    remove_install_dir()
    try:
        result = subprocess.run(
            [installer_path, "/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES", f"/DIR={INSTALL_DIR}"],
            timeout=INSTALL_TIMEOUT,
            creationflags=0x08000000,
        )
        if result.returncode != 0:
            return False
    except subprocess.TimeoutExpired:
        return False
    time.sleep(2)
    path = find_installed_path()
    return path is not None and os.path.isfile(path)


def silent_install() -> bool:
    installer = resource_path(INSTALLER_REL)
    if not os.path.isfile(installer):
        raise RuntimeError(f"内嵌安装包不存在: {installer}")
    return install_from_path(installer)


def ensure_installed() -> str:
    path = find_installed_path()
    if path:
        local_ver = get_installed_version()
        if local_ver and compare_versions(local_ver, EMBEDDED_VERSION) < 0:
            log_daemon(f"本地版本 {local_ver} 低于内嵌版本 {EMBEDDED_VERSION}，开始重装")
            ok = silent_install()
            if not ok:
                raise RuntimeError("Countdown Desktop 重装失败")
            path = find_installed_path()
            if path is None:
                raise RuntimeError("重装后未找到 Countdown Desktop")
        return path
    ok = silent_install()
    if not ok:
        raise RuntimeError("Countdown Desktop 静默安装失败")
    path = find_installed_path()
    if path is None:
        raise RuntimeError("安装后未找到 Countdown Desktop")
    return path


def launch_countdown(exam_type: str) -> None:
    path = ensure_installed()
    subprocess.Popen([path, "--exam", exam_type], creationflags=0x00000008, close_fds=True)


def is_running() -> bool:
    try:
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        kernel32.OpenMutexW.restype = ctypes.c_void_p
        handle = kernel32.OpenMutexW(SYNCHRONIZE, False, "CountdownDesktop_Single")
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
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
    kernel32 = ctypes.windll.kernel32
    MUTEX_NAME = "CountdownDesktop_Single"
    QUIT_EVENT_NAME = "CountdownDesktop_Quit"
    EVENT_MODIFY_STATE = 0x0002
    SYNCHRONIZE = 0x00100000
    kernel32.OpenMutexW.restype = ctypes.c_void_p
    mutex = kernel32.OpenMutexW(SYNCHRONIZE, False, MUTEX_NAME)
    already_running = bool(mutex)
    if mutex:
        kernel32.CloseHandle(mutex)
    if not already_running:
        return True
    kernel32.OpenEventW.restype = ctypes.c_void_p
    event = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, QUIT_EVENT_NAME)
    if not event:
        return False
    kernel32.SetEvent(event)
    kernel32.CloseHandle(event)
    deadline = time.time() + 8.0
    while time.time() < deadline:
        time.sleep(0.25)
        kernel32.OpenMutexW.restype = ctypes.c_void_p
        m = kernel32.OpenMutexW(SYNCHRONIZE, False, MUTEX_NAME)
        released = not bool(m)
        if m:
            kernel32.CloseHandle(m)
        if released:
            return True
    return False


def open_morning_reading() -> None:
    webbrowser.open(MORNING_READING_URL)


def _ensure_update_dir() -> None:
    os.makedirs(UPDATE_DIR, exist_ok=True)


def load_state() -> dict:
    try:
        _ensure_update_dir()
        if os.path.isfile(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_state(state: dict) -> None:
    try:
        _ensure_update_dir()
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def set_daemon_status(activity: str, progress: float = 0, detail: str = "") -> None:
    state = load_state()
    state["daemon"] = {
        "activity": activity, "progress": progress, "detail": detail,
        "timestamp": time.time(), "pid": os.getpid(),
    }
    save_state(state)


def get_daemon_status() -> dict | None:
    state = load_state()
    daemon = state.get("daemon")
    if not daemon:
        return None
    if time.time() - daemon.get("timestamp", 0) > 300:
        return None
    return daemon


def is_daemon_running() -> bool:
    try:
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        kernel32.OpenMutexW.restype = ctypes.c_void_p
        handle = kernel32.OpenMutexW(SYNCHRONIZE, False, DAEMON_MUTEX)
        if handle:
            kernel32.CloseHandle(handle)
            return True
    except Exception:
        pass
    return False


def send_command(cmd: str, **params) -> None:
    try:
        _ensure_update_dir()
        data = {"cmd": cmd, "timestamp": time.time()}
        data.update(params)
        with open(COMMAND_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def poll_command() -> dict | None:
    try:
        if os.path.isfile(COMMAND_FILE):
            with open(COMMAND_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            os.remove(COMMAND_FILE)
            return data
    except Exception:
        pass
    return None


def get_latest_version_info() -> dict | None:
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
                    "version": version, "url": asset["browser_download_url"],
                    "size": asset.get("size", 0), "name": name,
                    "release_notes": data.get("body", ""),
                }
        return None
    except Exception:
        return None


def _download_single(url: str, dest_path: str, timeout: int) -> bool:
    tmp_path = dest_path + ".part"
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "idiot-launch-updater"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
        if total > 0 and downloaded < total:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            return False
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


def download_installer(url: str, dest_path: str) -> bool:
    _ensure_update_dir()
    for attempt in range(DOWNLOAD_RETRY):
        for mirror in DOWNLOAD_MIRRORS:
            full_url = mirror + url if mirror else url
            source_name = mirror.rstrip("/") if mirror else "GitHub direct"
            log_daemon(f"下载尝试 ({attempt+1}/{DOWNLOAD_RETRY}) [{source_name}]: {os.path.basename(dest_path)}")
            set_daemon_status("downloading", 0, f"正在从 {source_name} 下载...")
            if _download_single(full_url, dest_path, DOWNLOAD_TIMEOUT):
                log_daemon(f"下载成功 [{source_name}]: {os.path.basename(dest_path)}")
                return True
            log_daemon(f"下载失败 [{source_name}]，尝试下一个源")
        log_daemon(f"所有源均失败，重试 {attempt+1}/{DOWNLOAD_RETRY} 完成")
        if attempt < DOWNLOAD_RETRY - 1:
            time.sleep(30)
    set_daemon_status("idle", 0, "下载失败，稍后重试")
    return False


def _acquire_daemon_mutex():
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, DAEMON_MUTEX)
        if kernel32.GetLastError() == 183:
            if handle:
                kernel32.CloseHandle(handle)
            return None
        return handle
    except Exception:
        return None


def _wait_and_install(installer_path: str, version: str, state: dict) -> None:
    deadline = time.time() + 2 * 3600
    while time.time() < deadline:
        if not is_running():
            break
        set_daemon_status("waiting", 0, f"等待 Countdown Desktop 退出以安装 v{version}")
        time.sleep(10)
    if is_running():
        set_daemon_status("idle", 0, "Countdown Desktop 仍在运行，更新保留到下次")
        return
    set_daemon_status("installing", 50, f"正在安装 Countdown Desktop v{version}...")
    try:
        ok = install_from_path(installer_path)
        if not ok:
            set_daemon_status("idle", 0, "安装失败，稍后重试")
            return
        state.pop("pending_installer", None)
        state.pop("pending_version", None)
        state["download_complete"] = False
        state["last_check"] = time.time()
        save_state(state)
        try:
            os.remove(installer_path)
        except OSError:
            pass
        set_daemon_status("idle", 0, f"已更新到 Countdown Desktop v{version}")
        log_daemon(f"Countdown Desktop 已更新到 v{version}")
    except Exception as e:
        set_daemon_status("idle", 0, f"安装异常: {e}")
        log_daemon(f"安装异常: {e}")


def get_daemon_status_detail(state: dict) -> str:
    if state.get("pending_installer") and state.get("download_complete"):
        ver = state.get("pending_version", "?")
        return f"已下载 Countdown Desktop v{ver}，等待退出后安装"
    if state.get("pending_launcher_path"):
        ver = state.get("pending_launcher_version", "?")
        return f"已下载 Idiot Launch v{ver}，空闲时自动更新"
    return "后台运行中"


def _handle_daemon_command(cmd: dict) -> None:
    action = cmd.get("cmd", "")
    log_daemon(f"收到命令: {action}")
    if action == "check_updates":
        state = load_state()
        state["last_check"] = 0
        state["launcher_last_check"] = 0
        save_state(state)
        set_daemon_status("checking", 0, "正在手动检查更新...")


def daemon_run() -> int:
    mutex = _acquire_daemon_mutex()
    if mutex is None:
        log_daemon("daemon 已在运行，退出")
        return 0
    log_daemon(f"daemon 启动 (pid={os.getpid()}, v{LAUNCHER_VERSION})")
    set_daemon_status("starting", 0, "守护进程启动")
    try:
        while True:
            state = load_state()
            cmd = poll_command()
            if cmd:
                _handle_daemon_command(cmd)
            # 空闲时静默自我更新（10 分钟无操作）
            if apply_launcher_update_idle():
                return 0
            _check_and_download_launcher_update()
            state = load_state()
            pending = state.get("pending_installer")
            pending_ver = state.get("pending_version")
            if pending and pending_ver and os.path.isfile(pending):
                local_ver = get_installed_version()
                if local_ver and compare_versions(local_ver, pending_ver) >= 0:
                    state.pop("pending_installer", None)
                    state.pop("pending_version", None)
                    state["download_complete"] = False
                    save_state(state)
                else:
                    _wait_and_install(pending, pending_ver, state)
                    state = load_state()
            last_check = state.get("last_check", 0)
            if time.time() - last_check >= CHECK_INTERVAL:
                set_daemon_status("checking", 0, "正在检查 Countdown Desktop 更新...")
                latest = get_latest_version_info()
                state["last_check"] = time.time()
                save_state(state)
                if latest:
                    local_ver = get_installed_version()
                    if not local_ver or compare_versions(local_ver, latest["version"]) < 0:
                        log_daemon(f"发现新版本 {latest['version']}（本地 {local_ver}），开始下载")
                        installer_name = latest.get("name", f"CountdownDesktop_Setup_{latest['version']}.exe")
                        dest = os.path.join(UPDATE_DIR, installer_name)
                        if not (os.path.isfile(dest) and latest.get("size", 0) > 0
                                and os.path.getsize(dest) == latest["size"]):
                            ok = download_installer(latest["url"], dest)
                            if not ok:
                                set_daemon_status("idle", 0, "更新下载失败，6 小时后重试")
                            else:
                                state = load_state()
                                state["pending_installer"] = dest
                                state["pending_version"] = latest["version"]
                                state["download_complete"] = True
                                state["release_notes"] = latest.get("release_notes", "")
                                save_state(state)
                                set_daemon_status("idle", 0, f"已下载 v{latest['version']}，等待倒计时退出后安装")
                    else:
                        set_daemon_status("idle", 0, "已是最新版本")
                else:
                    set_daemon_status("idle", 0, "更新检查失败，稍后重试")
            set_daemon_status("idle", 0, get_daemon_status_detail(state))
            for _ in range(6):
                time.sleep(5)
                cmd = poll_command()
                if cmd:
                    _handle_daemon_command(cmd)
                    state = load_state()
                    set_daemon_status("idle", 0, get_daemon_status_detail(state))
    except KeyboardInterrupt:
        pass
    finally:
        set_daemon_status("stopped", 0, "守护进程已停止")
        log_daemon("daemon 退出")
        if mutex:
            try:
                ctypes.windll.kernel32.CloseHandle(mutex)
            except Exception:
                pass
    return 0


def start_daemon() -> bool:
    if is_daemon_running():
        return False
    if getattr(sys, "frozen", False):
        exe = sys.executable
        creationflags = 0x00000008 | 0x08000000
        subprocess.Popen([exe, "--daemon"], creationflags=creationflags, close_fds=True)
    else:
        run_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run.py")
        args = [sys.executable, run_py, "--daemon"]
        creationflags = 0x00000008 | 0x08000000
        subprocess.Popen(args, creationflags=creationflags, close_fds=True)
    time.sleep(1)
    return is_daemon_running()


def _create_shortcut(target: str, shortcut_path: str, icon_path: str = "", description: str = "") -> bool:
    try:
        ps_script = f'''$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut("{shortcut_path}")
$s.TargetPath = "{target}"
$s.WorkingDirectory = "{os.path.dirname(target)}"
'''
        if icon_path:
            ps_script += f'$s.IconLocation = "{icon_path},0"\n'
        if description:
            ps_script += f'$s.Description = "{description}"\n'
        ps_script += "$s.Save()\n"
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, timeout=15,
        )
        return result.returncode == 0 and os.path.isfile(shortcut_path)
    except Exception:
        return False


def ensure_shortcuts() -> None:
    if not getattr(sys, "frozen", False):
        return
    target = sys.executable
    if not os.path.isfile(target):
        return
    icon = target
    desc = "傻瓜启动器 - 教室倒计时一键启动"
    locations = []
    if os.path.isdir("D:\\"):
        locations.append(r"D:\傻瓜启动器.lnk")
    desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    if os.path.isdir(desktop):
        locations.append(os.path.join(desktop, "傻瓜启动器.lnk"))
    public_desktop = r"C:\Users\Public\Desktop"
    if os.path.isdir(public_desktop):
        locations.append(os.path.join(public_desktop, "傻瓜启动器.lnk"))
    for lnk in locations:
        try:
            if not os.path.isfile(lnk):
                _create_shortcut(target, lnk, icon, desc)
        except Exception:
            pass


def has_pending_update() -> bool:
    state = load_state()
    return bool(state.get("pending_installer") and state.get("download_complete")
                and os.path.isfile(state["pending_installer"]))


def install_pending_if_idle() -> bool:
    if not has_pending_update():
        return False
    if is_running():
        return False
    state = load_state()
    pending = state.get("pending_installer")
    if not pending or not os.path.isfile(pending):
        return False
    ok = install_from_path(pending)
    if ok:
        state.pop("pending_installer", None)
        state.pop("pending_version", None)
        state["download_complete"] = False
        state["last_check"] = time.time()
        save_state(state)
        try:
            os.remove(pending)
        except OSError:
            pass
    return ok


def get_latest_launcher_info() -> dict | None:
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            LAUNCHER_GITHUB_API,
            headers={"User-Agent": "idiot-launch-updater", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = data.get("tag_name", "")
        version = tag.lstrip("vV")
        for asset in data.get("assets", []):
            if asset.get("name") == LAUNCHER_ASSET_NAME:
                return {
                    "version": version, "url": asset["browser_download_url"],
                    "size": asset.get("size", 0), "release_notes": data.get("body", ""),
                }
        return None
    except Exception:
        return None


def _cleanup_stale_launcher_pending(state: dict) -> dict:
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
    if not getattr(sys, "frozen", False):
        return
    if not has_pending_launcher_update():
        return
    state = load_state()
    new_exe = state.get("pending_launcher_path")
    old_exe = sys.executable
    if not new_exe or not os.path.isfile(new_exe):
        return
    import tempfile
    vbs_content = f'''Option Explicit
Dim fso, shell, oldExe, newExe, i, success
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
oldExe = "{old_exe}"
newExe = "{new_exe}"
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
If Not success Then
    On Error Resume Next
    If Not fso.FileExists(oldExe) Then
        fso.CopyFile newExe, oldExe, False
    End If
    On Error GoTo 0
End If
If success Then
    On Error Resume Next
    fso.DeleteFile newExe, True
    On Error GoTo 0
End If
On Error Resume Next
shell.Run Chr(34) & oldExe & Chr(34), 1, False
On Error GoTo 0
On Error Resume Next
fso.DeleteFile WScript.ScriptFullName, True
On Error GoTo 0
'''
    vbs_path = os.path.join(tempfile.gettempdir(), "idiot_launch_selfupdate.vbs")
    try:
        with open(vbs_path, "wb") as f:
            f.write(b"\xff\xfe")
            f.write(vbs_content.encode("utf-16-le"))
    except OSError:
        return
    try:
        subprocess.Popen(
            ["wscript.exe", "//B", "//Nologo", vbs_path],
            creationflags=0x08000000, close_fds=True,
        )
    except Exception:
        return
    sys.exit(0)



def apply_launcher_update_idle() -> bool:
    """空闲时静默自我更新：关闭所有进程→替换exe→只重启daemon不启动GUI。
    返回 True 表示已触发（daemon 应立即退出），False 表示条件不满足。
    """
    if not getattr(sys, "frozen", False):
        return False
    state = load_state()
    state = _cleanup_stale_launcher_pending(state)
    new_exe = state.get("pending_launcher_path")
    pending_ver = state.get("pending_launcher_version")
    if not new_exe or not pending_ver or not os.path.isfile(new_exe):
        return False
    if os.path.getsize(new_exe) < LAUNCHER_MIN_SIZE:
        return False
    if compare_versions(pending_ver, LAUNCHER_VERSION) <= 0:
        return False
    idle = get_idle_seconds()
    if idle < IDLE_THRESHOLD:
        return False
    old_exe = sys.executable
    log_daemon(f"空闲 {int(idle)}s >= {IDLE_THRESHOLD}s，触发静默自我更新 {LAUNCHER_VERSION} -> {pending_ver}")
    set_daemon_status("updating", 0, f"空闲中静默更新到 v{pending_ver}...")
    import tempfile
    vbs_content = f'''Option Explicit
Dim fso, shell, oldExe, newExe, i, success, wmi, procs
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
oldExe = "{old_exe}"
newExe = "{new_exe}"
' 1. 优雅关闭所有 IdiotLaunch 进程（taskkill 不带 /F = 发 WM_CLOSE）
On Error Resume Next
shell.Run "taskkill /IM IdiotLaunch.exe", 0, True
On Error GoTo 0
' 2. 等待所有进程退出（最多 30 秒）
success = False
For i = 1 To 60
    WScript.Sleep 500
    Set wmi = GetObject("winmgmts:\\\\.\\root\\cimv2")
    Set procs = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name='IdiotLaunch.exe'")
    If procs.Count = 0 Then
        success = True
        Exit For
    End If
Next
' 3. 替换 exe（先备份旧版，失败则恢复）
If success Then
    On Error Resume Next
    If fso.FileExists(oldExe & ".bak") Then fso.DeleteFile oldExe & ".bak", True
    fso.MoveFile oldExe, oldExe & ".bak"
    If Err.Number = 0 Then
        fso.CopyFile newExe, oldExe, False
        If Err.Number = 0 Then
            fso.DeleteFile oldExe & ".bak", True
        Else
            fso.MoveFile oldExe & ".bak", oldExe
        End If
    End If
    On Error GoTo 0
End If
' 4. 清理下载文件
On Error Resume Next
fso.DeleteFile newExe, True
On Error GoTo 0
' 5. 只启动 daemon，不启动 GUI（用户空闲中，不弹窗打扰）
On Error Resume Next
shell.Run Chr(34) & oldExe & Chr(34) & " --daemon", 0, False
On Error GoTo 0
' 6. 自删除
On Error Resume Next
fso.DeleteFile WScript.ScriptFullName, True
On Error GoTo 0
'''
    vbs_path = os.path.join(tempfile.gettempdir(), "idiot_launch_idle_update.vbs")
    try:
        with open(vbs_path, "wb") as f:
            f.write(b"\xff\xfe")
            f.write(vbs_content.encode("utf-16-le"))
    except OSError:
        set_daemon_status("idle", 0, "静默更新脚本生成失败，稍后重试")
        return False
    try:
        subprocess.Popen(
            ["wscript.exe", "//B", "//Nologo", vbs_path],
            creationflags=0x08000000, close_fds=True,
        )
    except Exception:
        set_daemon_status("idle", 0, "静默更新启动失败，稍后重试")
        return False
    log_daemon("静默更新 VBS 已启动，daemon 即将退出")
    return True

def _check_and_download_launcher_update() -> None:
    if not getattr(sys, "frozen", False):
        return
    state = load_state()
    state = _cleanup_stale_launcher_pending(state)
    now = time.time()
    pending_path = state.get("pending_launcher_path")
    pending_ver = state.get("pending_launcher_version")
    if pending_path and pending_ver and os.path.isfile(pending_path):
        if compare_versions(pending_ver, LAUNCHER_VERSION) > 0:
            return
    last_check = state.get("launcher_last_check", 0)
    if now - last_check < CHECK_INTERVAL:
        return
    set_daemon_status("checking", 0, "正在检查 Idiot Launch 更新...")
    latest = get_latest_launcher_info()
    state["launcher_last_check"] = now
    save_state(state)
    if not latest:
        return
    if compare_versions(latest["version"], LAUNCHER_VERSION) <= 0:
        return
    log_daemon(f"发现 Idiot Launch 新版本 {latest['version']}，开始下载")
    dest_name = f"IdiotLaunch_v{latest['version']}.exe"
    dest = os.path.join(UPDATE_DIR, dest_name)
    if (os.path.isfile(dest) and latest.get("size", 0) > 0
            and os.path.getsize(dest) == latest["size"]
            and os.path.getsize(dest) >= LAUNCHER_MIN_SIZE):
        state["pending_launcher_path"] = dest
        state["pending_launcher_version"] = latest["version"]
        state["launcher_release_notes"] = latest.get("release_notes", "")
        save_state(state)
        return
    ok = download_installer(latest["url"], dest)
    if not ok:
        return
    if not os.path.isfile(dest) or os.path.getsize(dest) < LAUNCHER_MIN_SIZE:
        try:
            os.remove(dest)
        except OSError:
            pass
        return
    state = load_state()
    state["pending_launcher_path"] = dest
    state["pending_launcher_version"] = latest["version"]
    state["launcher_release_notes"] = latest.get("release_notes", "")
    save_state(state)
    set_daemon_status("idle", 0, f"已下载 Idiot Launch v{latest['version']}，空闲时自动更新")
    log_daemon(f"Idiot Launch v{latest['version']} 下载完成，空闲时自动更新")
