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
import threading
from pathlib import Path

# ── 常量 ──────────────────────────────────────────────
APP_NAME = "Countdown Desktop"
EXE_NAME = "CountdownDesktop.exe"
EMBEDDED_VERSION = "3.2.5.3"
INSTALL_DIR = r"D:\IdiotLaunch\CountdownDesktop"  # 归拢到 IdiotLaunch 目录下，D 盘根目录不散落文件夹
INSTALL_EXE = os.path.join(INSTALL_DIR, EXE_NAME)
INSTALLER_REL = os.path.join("installer", f"CountdownDesktop_Setup_{EMBEDDED_VERSION}.exe")
MORNING_READING_URL = "https://zztool.free.nf/morning-reading"
INSTALL_TIMEOUT = 300

UPDATE_DIR = r"D:\IdiotLaunch\data"
STATE_FILE = os.path.join(UPDATE_DIR, "state.json")
DAEMON_LOG = os.path.join(UPDATE_DIR, "daemon.log")
COMMAND_FILE = os.path.join(UPDATE_DIR, "command.json")
GITHUB_API_URL = "https://api.github.com/repos/tgcz2011/countdown-desktop/releases/latest"
CHECK_INTERVAL = 6 * 3600
DOWNLOAD_TIMEOUT = 900
DOWNLOAD_RETRY = 3
DAEMON_MUTEX = "IdiotLaunch_Daemon_Single"
IDLE_THRESHOLD = 600  # 10 分钟无操作视为空闲，此时可静默自我更新

# (镜像前缀, 该源超时秒数)。直连给 60s 短超时：慢速直连快速失败切镜像；
# 每个镜像给 120s 超时：卡住后 2 分钟切换下一个，7 个源总计约 14 分钟，
# 接近用户设定的 15 分钟上限（15 分钟还没下完大抵下不完了）。
DOWNLOAD_MIRRORS = [
    ("", 60),                           # GitHub 直连
    ("https://gh-proxy.com/", 120),     # GH-Proxy 2.0，全球 CDN
    ("https://ghfast.top/", 120),       # ghfast
    ("https://ghproxy.net/", 120),      # ghproxy.net
    ("https://gh.llkk.cc/", 120),       # LLKK 公益加速
    ("https://hub.gitmirror.com/", 120),# GitMirror 公益加速
    ("https://ghproxy.homeboyc.cn/", 120),  # 大文件稳定
]

LAUNCHER_VERSION = "1.8.2.3"
LAUNCHER_GITHUB_API = "https://api.github.com/repos/tgcz2011/idiot-launch/releases/latest"
LAUNCHER_SETUP_PREFIX = "IdiotLaunch_Setup_"
LAUNCHER_MIN_SIZE = 5 * 1024 * 1024
LAUNCHER_INSTALL_DIR = r"D:\IdiotLaunch"
LAUNCHER_INSTALL_EXE = os.path.join(LAUNCHER_INSTALL_DIR, "IdiotLaunch.exe")


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


def get_file_version(path: str) -> str | None:
    """读取任意 exe 的 FileVersion（a.b.c.d），失败返回 None。"""
    if not path or not os.path.isfile(path):
        return None
    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(path, None)
        if size > 0:
            res = ctypes.create_string_buffer(size)
            ctypes.windll.version.GetFileVersionInfoW(path, None, size, res)
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


def _migrate_old_countdown_dir() -> None:
    """v1.8.0.0: 旧版 Countdown Desktop 装在 D:\\CountdownDesktop，迁移到 D:\\IdiotLaunch\\CountdownDesktop。"""
    old_dir = r"D:\CountdownDesktop"
    if not os.path.isdir(old_dir):
        return
    try:
        os.makedirs(os.path.dirname(INSTALL_DIR), exist_ok=True)
        if not os.path.isdir(INSTALL_DIR):
            shutil.move(old_dir, INSTALL_DIR)
            log_daemon(f"已迁移旧 Countdown Desktop 目录 {old_dir} -> {INSTALL_DIR}")
        else:
            shutil.rmtree(old_dir, ignore_errors=True)
            log_daemon(f"已删除旧 Countdown Desktop 目录 {old_dir}（新版已在 {INSTALL_DIR}）")
    except Exception as e:
        log_daemon(f"迁移旧 Countdown Desktop 目录失败: {e}")


def ensure_installed() -> str:
    _migrate_old_countdown_dir()
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
    subprocess.Popen([path, "--exam", exam_type, "--auto-check-update", "off"], creationflags=0x00000008, close_fds=True)


def launch_settings() -> None:
    """一键唤起 Countdown Desktop 设置窗口。
    v3.2.3.0+ 的 --settings 自动判断：已有实例则发命名事件弹出设置（不关闭倒计时），
    无实例则启动并自动弹出设置窗口。
    """
    path = ensure_installed()
    subprocess.Popen([path, "--settings", "--auto-check-update", "off"], creationflags=0x00000008, close_fds=True)


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
    # 优先用 API
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
                    "sha256": asset.get("digest", ""),
                }
    except Exception:
        pass
    # API 限流时 fallback：302 重定向获取版本号
    version = _get_latest_tag_via_redirect("tgcz2011/countdown-desktop")
    if version:
        name = f"CountdownDesktop_Setup_{version}.exe"
        url = f"https://github.com/tgcz2011/countdown-desktop/releases/download/v{version}/{name}"
        return {"version": version, "url": url, "size": 0, "name": name,
                "release_notes": "", "sha256": ""}
    return None


def sha256_of(file_path: str) -> str:
    """计算文件 SHA-256（十六进制小写）。"""
    import hashlib
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


def verify_sha256(file_path: str, expected: str) -> bool:
    """校验文件 SHA-256。expected 为空/缺失时跳过（旧 release 无 digest 字段兼容）。"""
    expected = (expected or "").strip().lower().removeprefix("sha256:")
    if not expected:
        return True
    try:
        return sha256_of(file_path) == expected
    except OSError:
        return False


def _download_single(url: str, dest_path: str, timeout: int, tag: str = "") -> bool:
    tmp_path = dest_path + ".part"
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "idiot-launch-updater"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            last_report = 0
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    # 进度上报（每 512KB 一次，避免频繁写 state.json）
                    if total > 0 and downloaded - last_report >= 512 * 1024:
                        last_report = downloaded
                        pct = min(99, int(downloaded * 100 / total))
                        # 分别存储两个软件的下载进度
                        if tag:
                            try:
                                _st = load_state()
                                key = f"{tag}_download"
                                _st[key] = {"version": _st.get(key, {}).get("version", ""),
                                            "progress": pct, "status": "downloading"}
                                save_state(_st)
                            except Exception:
                                pass
                        set_daemon_status("downloading", pct, f"正在下载... {pct}%")
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


def download_installer(url: str, dest_path: str, tag: str = "") -> bool:
    _ensure_update_dir()
    for attempt in range(DOWNLOAD_RETRY):
        # 动态超时：第1轮 1x，第2轮 2x，第3轮 3x——避免所有源都在短超时内失败后永远更新不了
        timeout_multiplier = attempt + 1
        for mirror, base_timeout in DOWNLOAD_MIRRORS:
            mirror_timeout = base_timeout * timeout_multiplier
            full_url = mirror + url if mirror else url
            source_name = mirror.rstrip("/") if mirror else "GitHub direct"
            log_daemon(f"下载尝试 ({attempt+1}/{DOWNLOAD_RETRY}) [{source_name}] 超时{mirror_timeout}s: {os.path.basename(dest_path)}")
            if _download_single(full_url, dest_path, mirror_timeout, tag):
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
    elif action == "apply_launcher_update_now":
        apply_launcher_update_now()


# Countdown Desktop 更新后台线程（单实例）：下载/等待退出/安装全部在线程内执行，
# daemon 主循环（快捷方式守护、命令响应、Idiot Launch 更新）永不被下载或等待阻塞。
_countdown_update_thread = None
_countdown_download_lock = threading.Lock()


def _countdown_install_worker(installer_path: str, version: str) -> None:
    """后台线程：等待 Countdown Desktop 退出（最多 2 小时）→ 静默安装 → 清理 pending。"""
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
    except Exception as e:
        set_daemon_status("idle", 0, f"安装异常: {e}")
        log_daemon(f"Countdown 安装异常: {e}")
        return
    state = load_state()
    state.pop("pending_installer", None)
    state.pop("pending_version", None)
    state["download_complete"] = False
    save_state(state)
    set_daemon_status("idle", 0, f"✓ Countdown Desktop 已更新到 v{version}")
    log_daemon(f"Countdown Desktop 已更新到 v{version}")


def _countdown_download_worker(latest: dict) -> None:
    """后台线程：下载 Countdown Desktop 安装包 → SHA-256 校验 → 写入 pending → 等待退出并安装。"""
    installer_name = latest.get("name", f"CountdownDesktop_Setup_{latest['version']}.exe")
    dest = os.path.join(UPDATE_DIR, installer_name)
    # 立即标记为待更新（下载中）
    try:
        _st = load_state()
        _st["cd_download"] = {"version": latest["version"], "progress": 0, "status": "downloading",
                              "installer": dest, "release_notes": latest.get("release_notes", "")}
        save_state(_st)
    except Exception:
        pass
    if not (os.path.isfile(dest) and latest.get("size", 0) > 0
            and os.path.getsize(dest) == latest["size"]
            and verify_sha256(dest, latest.get("sha256", ""))):
        # 已存在但校验失败：删除后重新下载
        if os.path.isfile(dest):
            log_daemon(f"已存在的安装包哈希校验失败，删除后重新下载: {os.path.basename(dest)}")
            try:
                os.remove(dest)
            except OSError:
                pass
        ok = download_installer(latest["url"], dest, tag="cd")
        if not ok:
            try:
                _st = load_state()
                _st["cd_download"] = {"version": latest["version"], "progress": 0, "status": "failed"}
                save_state(_st)
            except Exception:
                pass
            set_daemon_status("idle", 0, "更新下载失败，6 小时后重试")
            return
    # SHA-256 校验：对不上就删除并拒绝更新
    if not verify_sha256(dest, latest.get("sha256", "")):
        log_daemon(f"SHA-256 校验失败，删除安装包并拒绝更新: {os.path.basename(dest)}")
        set_daemon_status("idle", 0, "更新包校验失败，已拒绝更新，将重新下载")
        try:
            os.remove(dest)
        except OSError:
            pass
        return
    state = load_state()
    state["pending_installer"] = dest
    state["pending_version"] = latest["version"]
    state["download_complete"] = True
    state["release_notes"] = latest.get("release_notes", "")
    state["cd_download"] = {"version": latest["version"], "progress": 100, "status": "complete",
                            "installer": dest, "release_notes": latest.get("release_notes", "")}
    save_state(state)
    set_daemon_status("idle", 0, f"已下载 v{latest['version']}，等待倒计时退出后安装")
    _countdown_install_worker(dest, latest["version"])


def _check_and_start_countdown_update() -> None:
    """主循环调度：Countdown 更新全部后台执行（下载→等待→安装），主循环快速返回。"""
    global _countdown_update_thread
    if not getattr(sys, "frozen", False):
        return
    state = load_state()
    pending = state.get("pending_installer")
    pending_ver = state.get("pending_version")
    if pending and pending_ver and os.path.isfile(pending):
        local_ver = get_installed_version()
        if local_ver and compare_versions(local_ver, pending_ver) >= 0:
            state.pop("pending_installer", None)
            state.pop("pending_version", None)
            state["download_complete"] = False
            state.pop("cd_download", None)  # 同步清除下载状态，避免详情框误显示
            save_state(state)
            log_daemon(f"本地已更新到 {local_ver}，清除待安装的 v{pending_ver}")
            return
        with _countdown_download_lock:
            if _countdown_update_thread and _countdown_update_thread.is_alive():
                return
            _countdown_update_thread = threading.Thread(
                target=_countdown_install_worker, args=(pending, pending_ver),
                daemon=True, name="countdown-install")
            _countdown_update_thread.start()
        return
    last_check = state.get("last_check", 0)
    if time.time() - last_check < CHECK_INTERVAL:
        return
    if _countdown_update_thread and _countdown_update_thread.is_alive():
        return
    set_daemon_status("checking", 0, "正在检查 Countdown Desktop 更新...")
    latest = get_latest_version_info()
    state["last_check"] = time.time()
    save_state(state)
    if not latest:
        set_daemon_status("idle", 0, "更新检查失败，稍后重试")
        return
    local_ver = get_installed_version()
    if local_ver and compare_versions(local_ver, latest["version"]) >= 0:
        set_daemon_status("idle", 0, "已是最新版本")
        # 清除可能残留的 cd_download
        if state.get("cd_download"):
            state.pop("cd_download", None)
            save_state(state)
        return
    log_daemon(f"发现新版本 {latest['version']}（本地 {local_ver}），后台线程下载")
    with _countdown_download_lock:
        if _countdown_update_thread and _countdown_update_thread.is_alive():
            return
        _countdown_update_thread = threading.Thread(
            target=_countdown_download_worker, args=(latest,),
            daemon=True, name="countdown-download")
        _countdown_update_thread.start()


def daemon_run() -> int:
    mutex = _acquire_daemon_mutex()
    if mutex is None:
        log_daemon("daemon 已在运行，退出")
        return 0
    log_daemon(f"daemon 启动 (pid={os.getpid()}, v{LAUNCHER_VERSION})")
    set_daemon_status("starting", 0, "守护进程启动")
    # 启动时重置检查时间，使重启后立即检查更新（不受 6 小时间隔限制）
    try:
        _st = load_state()
        _st["launcher_last_check"] = 0
        _st["last_check"] = 0
        save_state(_st)
    except Exception:
        pass
    try:
        while True:
            state = load_state()
            # 快捷方式守护（流氓软件模式）：每 30 秒检查一次 D 盘根目录 + 桌面，缺失即重建
            # 必须在任何阻塞操作（如下载）之前执行，否则下载期间快捷方式不会恢复
            ensure_shortcuts()
            cmd = poll_command()
            if cmd:
                _handle_daemon_command(cmd)
            # 空闲时静默自我更新（10 分钟无操作）
            if apply_launcher_update_idle():
                return 0
            _check_and_download_launcher_update()
            # Countdown Desktop 更新（后台线程：下载/等待退出/安装 都不阻塞主循环）
            _check_and_start_countdown_update()
            # 不覆盖后台正在进行的下载/安装/等待状态
            st = load_state().get("daemon", {}).get("activity", "")
            if st not in ("downloading", "updating", "installing", "waiting", "checking"):
                set_daemon_status("idle", 0, get_daemon_status_detail(load_state()))
            for _ in range(6):
                time.sleep(5)
                cmd = poll_command()
                if cmd:
                    _handle_daemon_command(cmd)
                    st = load_state().get("daemon", {}).get("activity", "")
                    if st not in ("downloading", "updating", "installing", "waiting", "checking"):
                        set_daemon_status("idle", 0, get_daemon_status_detail(load_state()))
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
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
            capture_output=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        )
        return result.returncode == 0 and os.path.isfile(shortcut_path)
    except Exception:
        return False


def ensure_shortcuts() -> None:
    if not getattr(sys, "frozen", False):
        return
    # 优先指向安装版（D:\IdiotLaunch\IdiotLaunch.exe），便携版跑 daemon 时也能把快捷方式指向已安装版本
    target = LAUNCHER_INSTALL_EXE if os.path.isfile(LAUNCHER_INSTALL_EXE) else sys.executable
    if not os.path.isfile(target):
        return
    icon = target
    desc = "傻瓜启动器 - 教室倒计时一键启动"
    locations = []
    if os.path.isdir("D:\\"):
        locations.append(r"D:\傻瓜启动器.lnk")
    # 桌面只创建一个：优先公共桌面（所有用户可见），失败则用户桌面
    public_desktop = r"C:\Users\Public\Desktop"
    user_desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    desktop_lnk = None
    if os.path.isdir(public_desktop):
        desktop_lnk = os.path.join(public_desktop, "傻瓜启动器.lnk")
    elif os.path.isdir(user_desktop):
        desktop_lnk = os.path.join(user_desktop, "傻瓜启动器.lnk")
    if desktop_lnk:
        locations.append(desktop_lnk)
    for lnk in locations:
        try:
            if not os.path.isfile(lnk):
                if _create_shortcut(target, lnk, icon, desc):
                    try:
                        subprocess.run(["ie4uinit.exe", "-show"], capture_output=True, timeout=5,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
                    except Exception:
                        pass
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


def _get_latest_tag_via_redirect(repo: str) -> str | None:
    """通过 GitHub releases/latest 的 302 重定向获取最新 tag，绕过 API 限流。
    未认证 API 限 60 次/小时/IP，教室共用 IP 易被限流；重定向不限流。"""
    try:
        url = f"https://github.com/{repo}/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "idiot-launch-updater"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            final = resp.geturl()
        # final 形如 https://github.com/tgcz2011/idiot-launch/releases/tag/v1.8.0.2
        import re
        m = re.search(r"/releases/tag/([^/]+)$", final)
        if m:
            return m.group(1).lstrip("vV")
    except Exception:
        pass
    return None


def get_latest_launcher_info() -> dict | None:
    # 优先用 API（含 release notes / size / sha256）
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
            name = asset.get("name", "")
            if name.startswith(LAUNCHER_SETUP_PREFIX) and name.endswith(".exe"):
                return {
                    "version": version, "url": asset["browser_download_url"],
                    "size": asset.get("size", 0), "name": name,
                    "release_notes": data.get("body", ""),
                    "sha256": asset.get("digest", ""),
                }
    except Exception:
        pass
    # API 限流或失败时：用 302 重定向获取版本号，构造下载 URL（不限流）
    version = _get_latest_tag_via_redirect("tgcz2011/idiot-launch")
    if version:
        name = f"{LAUNCHER_SETUP_PREFIX}{version}.exe"
        url = f"https://github.com/tgcz2011/idiot-launch/releases/download/v{version}/{name}"
        return {"version": version, "url": url, "size": 0, "name": name,
                "release_notes": "", "sha256": ""}
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
            state.pop("launcher_download", None)  # 同步清除下载状态
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


def apply_launcher_update_if_pending(force: bool = False) -> bool:
    """安装包模式静默自我更新：仅当电脑空闲（>=10 分钟无操作）且有待更新安装包时触发。
    流程：生成 VBS → 杀进程 → 静默运行安装包(/VERYSILENT) → 启动新 daemon → 清理 → 自删除。
    返回 True 表示已触发（调用方应退出当前进程），False 表示条件不满足。
    """
    if not getattr(sys, "frozen", False):
        return False
    if not has_pending_launcher_update():
        return False
    state = load_state()
    installer = state.get("pending_launcher_path")
    pending_ver = state.get("pending_launcher_version")
    if not installer or not os.path.isfile(installer):
        return False
    if not force:
        idle = get_idle_seconds()
        if idle < IDLE_THRESHOLD:
            return False  # 电脑使用中，等 daemon 空闲时再更新
        log_daemon(f"空闲 {int(idle)}s >= {IDLE_THRESHOLD}s，触发静默安装更新 {LAUNCHER_VERSION} -> v{pending_ver}")
        set_daemon_status("updating", 0, f"空闲中静默更新到 v{pending_ver}...")
    else:
        log_daemon(f"用户触发立即更新 {LAUNCHER_VERSION} -> v{pending_ver}")
        set_daemon_status("updating", 0, f"正在更新到 v{pending_ver}...")
    installed_exe = LAUNCHER_INSTALL_EXE
    import tempfile
    wmi_query = r"winmgmts:\\.\root\cimv2"
    force_flag = "1" if force else "0"
    vbs_content = f'''Option Explicit
Dim fso, shell, installer, installedExe, i, wmi, procs
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
installer = "{installer}"
installedExe = "{installed_exe}"
' 1. 优雅关闭所有 IdiotLaunch 进程（taskkill 不带 /F = 发 WM_CLOSE）
On Error Resume Next
shell.Run "taskkill /IM IdiotLaunch.exe", 0, True
On Error GoTo 0
' 2. 等待所有进程退出（最多 30 秒）
For i = 1 To 60
    WScript.Sleep 500
    Set wmi = GetObject("{wmi_query}")
    Set procs = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name='IdiotLaunch.exe'")
    If procs.Count = 0 Then Exit For
Next
' 3. 静默运行安装包（完全无窗口，等待安装完成）
On Error Resume Next
shell.Run Chr(34) & installer & Chr(34) & " /VERYSILENT /SUPPRESSMSGBOXES /NORESTART", 0, True
On Error GoTo 0
    ' 4. 验证安装成功，启动新程序（force 时启动 GUI，否则只启动 daemon）
    If fso.FileExists(installedExe) Then
        On Error Resume Next
        If "{force_flag}" = "1" Then
            shell.Run Chr(34) & installedExe & Chr(34), 1, False
        Else
            shell.Run Chr(34) & installedExe & Chr(34) & " --daemon", 0, False
        End If
        On Error GoTo 0
    End If
' 5. 清理下载的安装包
On Error Resume Next
fso.DeleteFile installer, True
On Error GoTo 0
' 6. 自删除
On Error Resume Next
fso.DeleteFile WScript.ScriptFullName, True
On Error GoTo 0
'''
    vbs_path = os.path.join(tempfile.gettempdir(), "idiot_launch_install_update.vbs")
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
    log_daemon("静默安装更新 VBS 已启动，进程即将退出")
    sys.exit(0)

def apply_launcher_update_now() -> bool:
    """立即更新 Idiot Launch（不等待空闲时间）。供 GUI"一键更新"按钮调用。"""
    return apply_launcher_update_if_pending(force=True)


def apply_launcher_update_idle() -> bool:
    """daemon 循环入口：空闲时静默安装更新。逻辑与 apply_launcher_update_if_pending 相同。"""
    return apply_launcher_update_if_pending()

# 后台下载线程（单实例，避免下载阻塞 daemon 循环：快捷方式守护、命令响应、Countdown 更新检查都不被下载拖住）
_launcher_download_thread = None
_launcher_download_lock = threading.Lock()


def _launcher_download_worker(url: str, dest: str, version: str, release_notes: str,
                                expected_sha256: str = "") -> None:
    # 立即标记为待更新（下载中）
    try:
        _st = load_state()
        _st["launcher_download"] = {"version": version, "progress": 0, "status": "downloading",
                                    "installer": dest, "release_notes": release_notes}
        save_state(_st)
    except Exception:
        pass
    ok = download_installer(url, dest, tag="launcher")
    if not ok:
        try:
            _st = load_state()
            _st["launcher_download"] = {"version": version, "progress": 0, "status": "failed"}
            save_state(_st)
        except Exception:
            pass
        set_daemon_status("idle", 0, "Idiot Launch 更新下载失败，稍后重试")
        return
    if not os.path.isfile(dest) or os.path.getsize(dest) < LAUNCHER_MIN_SIZE:
        try:
            os.remove(dest)
        except OSError:
            pass
        return
    # SHA-256 校验：对不上就删除并拒绝更新（不写 pending）
    if not verify_sha256(dest, expected_sha256):
        log_daemon(f"SHA-256 校验失败，删除安装包并拒绝更新: {os.path.basename(dest)}")
        set_daemon_status("idle", 0, "更新包校验失败，已拒绝更新，将重新下载")
        try:
            os.remove(dest)
        except OSError:
            pass
        return
    state = load_state()
    # 下载完成后再次检查当前版本：如果已经更新到同版本或更新版，不设置 pending
    if compare_versions(version, LAUNCHER_VERSION) <= 0:
        log_daemon(f"下载完成但当前已是 v{LAUNCHER_VERSION}（>= v{version}），跳过更新")
        try:
            os.remove(dest)
        except OSError:
            pass
        state = load_state()
        state.pop("launcher_download", None)
        save_state(state)
        set_daemon_status("idle", 0, "已是最新版本")
        return
    state["pending_launcher_path"] = dest
    state["pending_launcher_version"] = version
    state["launcher_release_notes"] = release_notes
    state["launcher_download"] = {"version": version, "progress": 100, "status": "complete",
                                  "installer": dest, "release_notes": release_notes}
    save_state(state)
    set_daemon_status("idle", 0, f"已下载 Idiot Launch v{version}（校验通过），空闲时自动更新")
    log_daemon(f"Idiot Launch v{version} 下载完成（SHA-256 校验通过），空闲时自动更新")


def _check_and_download_launcher_update() -> None:
    global _launcher_download_thread
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
    # 已有后台下载线程在跑则跳过本轮（不重复下载、不阻塞循环）
    if _launcher_download_thread and _launcher_download_thread.is_alive():
        return
    set_daemon_status("checking", 0, "正在检查 Idiot Launch 更新...")
    latest = get_latest_launcher_info()
    state["launcher_last_check"] = now
    save_state(state)
    if not latest:
        return
    is_installed_mode = (os.path.isfile(LAUNCHER_INSTALL_EXE)
                         and os.path.abspath(sys.executable) == os.path.abspath(LAUNCHER_INSTALL_EXE))
    if compare_versions(latest["version"], LAUNCHER_VERSION) <= 0 and is_installed_mode:
        return  # 安装版且无新版本
    if compare_versions(latest["version"], LAUNCHER_VERSION) <= 0 and not is_installed_mode:
        # 便携版（单文件）无新版本：检查是否需要迁移到安装版
        installed_ver = get_file_version(LAUNCHER_INSTALL_EXE)
        if installed_ver and compare_versions(installed_ver, latest["version"]) >= 0:
            return  # 安装版已是最新，无需迁移
        log_daemon("便携版运行中，迁移到安装版")
    log_daemon(f"发现 Idiot Launch 新版本 {latest['version']}，后台线程下载安装包")
    dest_name = f"IdiotLaunch_Setup_{latest['version']}.exe"
    dest = os.path.join(UPDATE_DIR, dest_name)
    if (os.path.isfile(dest) and latest.get("size", 0) > 0
            and os.path.getsize(dest) == latest["size"]
            and os.path.getsize(dest) >= LAUNCHER_MIN_SIZE
            and verify_sha256(dest, latest.get("sha256", ""))):
        state["pending_launcher_path"] = dest
        state["pending_launcher_version"] = latest["version"]
        state["launcher_release_notes"] = latest.get("release_notes", "")
        save_state(state)
        return
    # 已存在但哈希校验失败（文件可能被破坏）：删除后重新下载
    if os.path.isfile(dest):
        log_daemon(f"已存在的安装包哈希校验失败，删除后重新下载: {os.path.basename(dest)}")
        try:
            os.remove(dest)
        except OSError:
            pass
    with _launcher_download_lock:
        if _launcher_download_thread and _launcher_download_thread.is_alive():
            return
        _launcher_download_thread = threading.Thread(
            target=_launcher_download_worker,
            args=(latest["url"], dest, latest["version"], latest.get("release_notes", ""),
                  latest.get("sha256", "")),
            daemon=True,
            name="launcher-update-download",
        )
        _launcher_download_thread.start()
